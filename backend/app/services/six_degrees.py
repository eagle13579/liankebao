"""
六度人脉 — 核心算法与信任评分服务

核心能力：
1. 双向BFS (Bidirectional BFS) — 在关系图中寻找最短路径
2. 信任传递衰减计算 — 基于六度分隔理论的信任度传播
3. 路径缓存管理 — 高频路径的LRU缓存 + 数据库缓存
4. 朋友圈关系推荐 — 二度/三度人脉推荐

性能目标：
- 1万用户/10万边: BFS < 50ms
- 10万用户/100万边: BFS < 200ms (需缓存)
- 100万用户/1000万边: BFS < 1s (Redis缓存 + 异步预计算)
"""
import json
import logging
import math
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.six_degrees import (
    RelationEvent,
    SixDegreePathCache,
    UserRelation,
)
from app.models import User

logger = logging.getLogger(__name__)

# ============================================================
# 配置常量
# ============================================================

# 六度最大深度（理论上限6，实际B2B场景通常只需3~4度）
MAX_DEGREES = 6

# 信任衰减因子 (0~1)，每跳衰减比例
# 1度: 1.0, 2度: 0.6, 3度: 0.36, 4度: 0.216, 5度: 0.13, 6度: 0.078
TRUST_DECAY_FACTOR = 0.6

# BFS最大搜索节点数（防止计算爆炸）
BFS_MAX_NODES = 500_000

# 路径缓存TTL（秒）
PATH_CACHE_TTL = 3600  # 1小时
PATH_CACHE_WARM_TTL = 86400  # 24小时（热点路径）

# 信任度计算参数
TRUST_WEIGHT_INTERACTION = 0.3  # 交互次数权重
TRUST_WEIGHT_RECENCY = 0.2      # 最近交互权重
TRUST_WEIGHT_MUTUAL = 0.3       # 双向关系权重
TRUST_WEIGHT_ENDORSEMENT = 0.2  # 背书/推荐权重


# ============================================================
# 图数据加载器
# ============================================================

class RelationGraph:
    """
    关系图内存表示（邻接表）

    用于BFS搜索前加载子图，避免频繁数据库查询。
    对百万级图，按需加载用户周围N度范围内的子图。
    """

    def __init__(self, db: Session):
        self.db = db
        # 邻接表: user_id -> [(neighbor_id, trust_score), ...]
        self.adjacency: Dict[int, List[Tuple[int, float]]] = {}
        # 用户信息缓存
        self.user_cache: Dict[int, dict] = {}

    def load_ego_network(self, user_id: int, degrees: int = 2) -> None:
        """
        加载用户 ego network（自我中心网络），
        即用户周围指定度数范围内的所有节点和边。

        这是 BFS 的关键优化 — 只在子图上搜索，而非全量图。
        """
        visited = {user_id}
        current_layer = {user_id}
        edges: List[Tuple[int, int, float]] = []

        for _ in range(degrees):
            if not current_layer:
                break
            # 批量查询当前层所有用户的直接关系
            relations = (
                self.db.query(UserRelation)
                .filter(
                    UserRelation.from_user_id.in_(current_layer),
                    UserRelation.is_active == True,
                    UserRelation.is_deleted == False,
                )
                .all()
            )
            next_layer = set()
            for rel in relations:
                if rel.to_user_id not in visited:
                    visited.add(rel.to_user_id)
                    next_layer.add(rel.to_user_id)
                edges.append((rel.from_user_id, rel.to_user_id, rel.trust_score))
                if rel.bidirectional:
                    edges.append((rel.to_user_id, rel.from_user_id, rel.trust_score))
                    if rel.from_user_id not in visited:
                        visited.add(rel.from_user_id)
                        next_layer.add(rel.from_user_id)

            current_layer = next_layer

        # 构建邻接表
        self.adjacency = {uid: [] for uid in visited}
        for from_id, to_id, trust in edges:
            if from_id in self.adjacency and to_id in self.adjacency:
                self.adjacency[from_id].append((to_id, trust))

        # 批量加载用户信息
        users = self.db.query(User).filter(User.id.in_(visited)).all()
        for u in users:
            self.user_cache[u.id] = {
                "user_id": u.id,
                "name": u.name,
                "company": u.company or "",
                "position": u.position or "",
                "avatar": u.avatar or "",
            }

    def get_neighbors(self, user_id: int) -> List[Tuple[int, float]]:
        """获取用户的一度人脉（直接关系）"""
        return self.adjacency.get(user_id, [])

    def get_user_info(self, user_id: int) -> Optional[dict]:
        """获取用户信息"""
        if user_id not in self.user_cache:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                return None
            self.user_cache[user_id] = {
                "user_id": user.id,
                "name": user.name,
                "company": user.company or "",
                "position": user.position or "",
                "avatar": user.avatar or "",
            }
        return self.user_cache[user_id]

    def node_count(self) -> int:
        return len(self.adjacency)


# ============================================================
# 双向BFS算法
# ============================================================

def bidirectional_bfs(
    graph: RelationGraph,
    source: int,
    target: int,
    max_depth: int = MAX_DEGREES,
) -> Optional[dict]:
    """
    双向BFS查找最短路径

    原理：
    - 从 source 和 target 同时向中间搜索
    - 每次选择分支因子更小的一侧扩展
    - 相遇时拼接路径

    时间复杂度：O(b^(d/2))，其中 b 为分支因子，d 为路径长度
    相比单向 BFS O(b^d)，效率提升指数级。

    Args:
        graph: 关系图
        source: 起点用户ID
        target: 终点用户ID
        max_depth: 最大搜索深度

    Returns:
        {
            "path": [user_id, ...],  # 路径节点ID列表（含起止）
            "nodes": [info_dict, ...], # 节点详细信息
            "length": int,           # 路径长度（跳数）
            "trust_score": float,    # 路径总信任度
        }
        or None if no path found
    """
    if source == target:
        return {
            "path": [source],
            "nodes": [graph.get_user_info(source)],
            "length": 0,
            "trust_score": 1.0,
        }

    # 初始化正向/反向 BFS
    # queue: (node, path)
    forward_queue = deque([(source, [source])])
    backward_queue = deque([(target, [target])])

    # visited: node -> path
    forward_visited = {source: [source]}
    backward_visited = {target: [target]}

    # 双向交替搜索
    forward_depth = 0
    backward_depth = 0

    total_nodes_searched = 0

    while forward_queue and backward_queue:
        total_nodes_searched += 1
        if total_nodes_searched > BFS_MAX_NODES:
            logger.warning(f"BFS exceeded max nodes ({BFS_MAX_NODES}), aborting")
            return None

        # 选择分支更小的一侧扩展（优化关键）
        if len(forward_queue) <= len(backward_queue):
            # 扩展正向
            if forward_depth < max_depth // 2 + 1:
                result = _expand_frontier(
                    graph, forward_queue, forward_visited,
                    backward_visited, forward_depth, is_forward=True,
                )
                if result:
                    return result
                forward_depth += 1
        else:
            # 扩展反向
            if backward_depth < max_depth // 2 + 1:
                result = _expand_frontier(
                    graph, backward_queue, backward_visited,
                    forward_visited, backward_depth, is_forward=False,
                )
                if result:
                    return result
                backward_depth += 1

        # 总深度超过限制时提前退出
        if forward_depth + backward_depth > max_depth:
            break

    return None


def _expand_frontier(
    graph: RelationGraph,
    queue: deque,
    visited: dict,
    other_visited: dict,
    current_depth: int,
    is_forward: bool,
) -> Optional[dict]:
    """
    扩展一层BFS前沿
    """
    level_size = len(queue)
    for _ in range(level_size):
        current, path = queue.popleft()
        neighbors = graph.get_neighbors(current)

        for neighbor_id, trust_score in neighbors:
            # 检查是否与另一侧相遇
            if neighbor_id in other_visited:
                # 拼接路径
                other_path = other_visited[neighbor_id]
                if is_forward:
                    full_path = path + [neighbor_id] + other_path[::-1]
                else:
                    full_path = path + [neighbor_id] + other_path[::-1]

                # 去重（避免首尾重复）
                if full_path[0] == full_path[-1]:
                    full_path = full_path[:-1]

                # 计算信任度
                trust = _compute_path_trust(graph, full_path)

                # 获取节点信息
                nodes = []
                for uid in full_path:
                    info = graph.get_user_info(uid)
                    if info:
                        nodes.append(info)

                return {
                    "path": full_path,
                    "nodes": nodes,
                    "length": len(full_path) - 1,
                    "trust_score": trust,
                }

            if neighbor_id not in visited:
                visited[neighbor_id] = path + [neighbor_id]
                queue.append((neighbor_id, path + [neighbor_id]))

    return None


# ============================================================
# 信任度计算
# ============================================================

def _compute_path_trust(graph: RelationGraph, path: List[int]) -> float:
    """
    计算路径总信任度

    信任传递衰减公式：
        T(A→D) = T(A→B) * decay^1 + T(B→C) * decay^2 + T(C→D) * decay^3
        其中 decay = TRUST_DECAY_FACTOR

    归一化后：
        T_path = Σ(T_i * decay^(i)) / Σ(decay^(i))
    """
    if len(path) < 2:
        return 1.0

    total_weighted = 0.0
    total_weight = 0.0

    for i in range(len(path) - 1):
        from_id = path[i]
        to_id = path[i + 1]
        decay = TRUST_DECAY_FACTOR ** i  # 每跳衰减

        # 查找直接关系的信任度
        edge_trust = _get_edge_trust(graph, from_id, to_id)
        total_weighted += edge_trust * decay
        total_weight += decay

    return round(total_weighted / total_weight, 4) if total_weight > 0 else 0.0


def _get_edge_trust(graph: RelationGraph, from_id: int, to_id: int) -> float:
    """获取两个用户之间的直接信任度"""
    for neighbor_id, trust in graph.get_neighbors(from_id):
        if neighbor_id == to_id:
            return trust
    return 0.3  # 默认信任度


def compute_trust_score(
    interaction_count: int,
    days_since_last_interaction: int,
    is_bidirectional: bool,
    endorsement_count: int = 0,
) -> float:
    """
    综合计算两个用户之间的信任度

    公式：
        trust = W_i * f(interactions) + W_r * g(recency)
              + W_m * bidirectional + W_e * h(endorsements)

    其中：
        f(interactions) = min(interactions / 10, 1.0)
        g(recency) = max(1 - days_since / 365, 0.2)
        h(endorsements) = min(endorsements / 5, 1.0)
    """
    interaction_score = min(interaction_count / 10.0, 1.0)
    recency_score = max(1.0 - days_since_last_interaction / 365.0, 0.2)
    mutual_score = 1.0 if is_bidirectional else 0.5
    endorsement_score = min(endorsement_count / 5.0, 1.0)

    trust = (
        TRUST_WEIGHT_INTERACTION * interaction_score
        + TRUST_WEIGHT_RECENCY * recency_score
        + TRUST_WEIGHT_MUTUAL * mutual_score
        + TRUST_WEIGHT_ENDORSEMENT * endorsement_score
    )

    return round(min(max(trust, 0.0), 1.0), 4)


# ============================================================
# 信任传递衰减
# ============================================================

def compute_trust_decay(hop: int, base_trust: float = 1.0) -> float:
    """
    计算经过 hop 跳后的信任衰减值

    六度理论核心公式：
        T_n = T_0 * decay^n

    典型值：
        hop=0: 1.0      （自己）
        hop=1: 0.6      （朋友）
        hop=2: 0.36     （朋友的朋友）
        hop=3: 0.216    （三度人脉）
        hop=4: 0.13     （四度）
        hop=5: 0.078    （五度）
        hop=6: 0.047    （六度 — 理论上限）
    """
    return round(base_trust * (TRUST_DECAY_FACTOR ** hop), 4)


# ============================================================
# 路径缓存管理
# ============================================================

class PathCacheManager:
    """
    六度路径缓存管理器

    策略：
    1. 内存LRU缓存（一级）：最近查询的路径，最快响应
    2. 数据库缓存（二级）：高频路径持久化，跨进程共享
    3. 缓存击穿保护：热点路径互斥锁，防止并发BFS
    """

    def __init__(self, db: Session, max_memory_cache: int = 10000):
        self.db = db
        self._memory_cache: Dict[str, dict] = {}
        self._max_memory = max_memory_cache
        self._cache_key_queue: deque = deque()
        self._hot_keys: Set[str] = set()

    def _make_key(self, from_id: int, to_id: int) -> str:
        return f"{min(from_id, to_id)}:{max(from_id, to_id)}"

    def get(self, from_id: int, to_id: int) -> Optional[dict]:
        """尝试从缓存获取路径"""
        key = self._make_key(from_id, to_id)

        # 1. 内存缓存
        if key in self._memory_cache:
            cached = self._memory_cache[key]
            if cached["expires_at"] > time.time():
                return cached["data"]
            del self._memory_cache[key]

        # 2. 数据库缓存
        try:
            record = (
                self.db.query(SixDegreePathCache)
                .filter(
                    SixDegreePathCache.from_user_id == min(from_id, to_id),
                    SixDegreePathCache.to_user_id == max(from_id, to_id),
                    SixDegreePathCache.expires_at > datetime.now(timezone.utc),
                )
                .first()
            )
            if record:
                # 增加命中次数
                record.hit_count += 1
                self.db.commit()

                data = {
                    "path": json.loads(record.path_json),
                    "length": record.path_length,
                    "trust_score": record.total_trust_score,
                }

                # 提升到内存缓存
                self._add_to_memory(key, data, PATH_CACHE_TTL)

                return data
        except Exception as e:
            logger.warning(f"Path cache DB lookup failed: {e}")

        return None

    def set(
        self,
        from_id: int,
        to_id: int,
        data: dict,
        ttl: int = PATH_CACHE_TTL,
    ) -> None:
        """写入缓存"""
        key = self._make_key(from_id, to_id)
        path_ids = data.get("path", [])

        # 内存缓存
        self._add_to_memory(key, data, ttl)

        # 数据库缓存（异步写入，此处同步保留）
        try:
            existing = (
                self.db.query(SixDegreePathCache)
                .filter(
                    SixDegreePathCache.from_user_id == min(from_id, to_id),
                    SixDegreePathCache.to_user_id == max(from_id, to_id),
                )
                .first()
            )
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

            if existing:
                existing.path_json = json.dumps(path_ids, ensure_ascii=False)
                existing.path_length = data.get("length", len(path_ids) - 1)
                existing.total_trust_score = data.get("trust_score", 0.0)
                existing.expires_at = expires_at
                existing.hit_count += 1
            else:
                record = SixDegreePathCache(
                    from_user_id=min(from_id, to_id),
                    to_user_id=max(from_id, to_id),
                    path_json=json.dumps(path_ids, ensure_ascii=False),
                    path_length=data.get("length", len(path_ids) - 1),
                    total_trust_score=data.get("trust_score", 0.0),
                    expires_at=expires_at,
                )
                self.db.add(record)

            self.db.commit()
        except Exception as e:
            logger.warning(f"Path cache DB write failed: {e}")

    def _add_to_memory(self, key: str, data: dict, ttl: int) -> None:
        """添加到内存缓存（LRU淘汰）"""
        if len(self._memory_cache) >= self._max_memory:
            oldest_key = self._cache_key_queue.popleft()
            self._memory_cache.pop(oldest_key, None)

        self._memory_cache[key] = {
            "data": data,
            "expires_at": time.time() + ttl,
        }
        self._cache_key_queue.append(key)

    def invalidate_user(self, user_id: int) -> None:
        """用户关系变更时，清除相关缓存"""
        # 内存缓存：清除包含该用户的所有路径
        keys_to_remove = []
        for key in self._memory_cache:
            parts = key.split(":")
            if user_id in [int(parts[0]), int(parts[1])]:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            del self._memory_cache[key]

        # 数据库缓存：设置过期
        try:
            now = datetime.now(timezone.utc)
            self.db.query(SixDegreePathCache).filter(
                or_(
                    SixDegreePathCache.from_user_id == user_id,
                    SixDegreePathCache.to_user_id == user_id,
                )
            ).update({"expires_at": now})
            self.db.commit()
        except Exception as e:
            logger.warning(f"Path cache invalidation failed: {e}")


# ============================================================
# 核心API封装
# ============================================================

def find_shortest_path(
    db: Session,
    from_user_id: int,
    to_user_id: int,
    max_depth: int = MAX_DEGREES,
    use_cache: bool = True,
) -> Optional[dict]:
    """
    查找两个用户之间的最短六度路径

    流程：
    1. 查缓存（如有）
    2. 加载子图（按需）
    3. 双向BFS
    4. 写缓存
    """
    cache_mgr = PathCacheManager(db)

    # 1. 查缓存
    if use_cache:
        cached = cache_mgr.get(from_user_id, to_user_id)
        if cached:
            logger.info(f"Path cache HIT: {from_user_id} -> {to_user_id}")
            return cached

    # 2. 加载子图
    start_time = time.time()
    graph = RelationGraph(db)

    # 加载源和目标周围的子图（最多3度，可覆盖6度路径）
    graph.load_ego_network(from_user_id, degrees=3)
    graph.load_ego_network(to_user_id, degrees=3)

    load_time = time.time() - start_time
    logger.info(
        f"Graph loaded: {graph.node_count()} nodes in {load_time:.3f}s"
    )

    # 3. 双向BFS
    bfs_start = time.time()
    result = bidirectional_bfs(graph, from_user_id, to_user_id, max_depth)
    bfs_time = time.time() - bfs_start

    if result:
        result["search_time_ms"] = round((time.time() - start_time) * 1000, 2)
        result["nodes_searched"] = graph.node_count()
        logger.info(
            f"BFS found path: {from_user_id} -> {to_user_id}, "
            f"length={result['length']}, trust={result['trust_score']}, "
            f"time={bfs_time:.3f}s"
        )

        # 4. 写缓存
        if use_cache:
            ttl = PATH_CACHE_WARM_TTL if result["length"] <= 3 else PATH_CACHE_TTL
            cache_mgr.set(from_user_id, to_user_id, result, ttl=ttl)

    else:
        logger.info(f"BFS no path: {from_user_id} -> {to_user_id}")

    return result


def find_network(
    db: Session,
    user_id: int,
    degree: int = 2,
    page: int = 1,
    page_size: int = 20,
    min_trust: float = 0.0,
) -> dict:
    """
    查找用户N度人脉网络

    Args:
        user_id: 用户ID
        degree: 度数 (1~6)
        page: 页码
        page_size: 每页数量
        min_trust: 最小信任度阈值

    Returns:
        {
            "items": [...],
            "total": int,
            "page": int,
            "page_size": int,
            "degrees": {degree: count, ...}
        }
    """
    # 加载子图
    graph = RelationGraph(db)
    graph.load_ego_network(user_id, degrees=degree)

    # 按度数分层
    visited = {user_id: 0}
    queue = deque([(user_id, 0, [user_id])])
    degrees_map: Dict[int, List[dict]] = {}

    while queue:
        current, depth, path = queue.popleft()
        if depth > degree:
            break

        if depth > 0:
            trust = _compute_path_trust(graph, path)
            if trust >= min_trust:
                if depth not in degrees_map:
                    degrees_map[depth] = []
                user_info = graph.get_user_info(current)
                if user_info:
                    degrees_map[depth].append({
                        "user": user_info,
                        "degree": depth,
                        "trust_score": trust,
                        "path": path[1:],
                    })

        if depth < degree:
            for neighbor_id, _ in graph.get_neighbors(current):
                if neighbor_id not in visited or visited[neighbor_id] > depth + 1:
                    visited[neighbor_id] = depth + 1
                    queue.append((neighbor_id, depth + 1, path + [neighbor_id]))

    # 展平并分页
    all_items = []
    for d in range(1, degree + 1):
        if d in degrees_map:
            all_items.extend(degrees_map[d])

    total = len(all_items)
    start = (page - 1) * page_size
    end = start + page_size
    items = all_items[start:end]

    # 各度数统计
    degree_counts = {str(d): len(degrees_map.get(d, [])) for d in range(1, degree + 1)}

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "degree_counts": degree_counts,
    }


def create_relation(
    db: Session,
    from_user_id: int,
    to_user_id: int,
    relation_type: str = "invite",
    trust_score: float = 0.5,
    bidirectional: bool = False,
    source: str = "invite",
) -> UserRelation:
    """
    创建用户关系边
    """
    # 检查是否已存在
    existing = (
        db.query(UserRelation)
        .filter(
            UserRelation.from_user_id == from_user_id,
            UserRelation.to_user_id == to_user_id,
            UserRelation.is_deleted == False,
        )
        .first()
    )
    if existing:
        return existing

    relation = UserRelation(
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        relation_type=relation_type,
        trust_score=trust_score,
        bidirectional=bidirectional,
        source=source,
        interaction_count=1,
        last_interaction_at=datetime.now(timezone.utc),
    )
    db.add(relation)
    db.flush()

    # 记录事件
    event = RelationEvent(
        relation_id=relation.id,
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        event_type="created",
        new_trust_score=trust_score,
        reason=f"通过{source}建立关系",
    )
    db.add(event)
    db.commit()
    db.refresh(relation)

    return relation


def update_trust_score(
    db: Session,
    relation_id: int,
    new_score: float,
    reason: str = "",
) -> UserRelation:
    """
    更新关系信任度
    """
    relation = db.query(UserRelation).filter(UserRelation.id == relation_id).first()
    if not relation:
        raise ValueError(f"Relation {relation_id} not found")

    old_score = relation.trust_score
    relation.trust_score = new_score
    relation.interaction_count += 1
    relation.last_interaction_at = datetime.now(timezone.utc)
    relation.version += 1

    # 记录事件
    event = RelationEvent(
        relation_id=relation.id,
        from_user_id=relation.from_user_id,
        to_user_id=relation.to_user_id,
        event_type="trust_updated",
        old_trust_score=old_score,
        new_trust_score=new_score,
        reason=reason or "信任度更新",
    )
    db.add(event)
    db.commit()
    db.refresh(relation)

    return relation
