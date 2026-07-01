"""
AI数字名片 企业关系图谱
======================
基于 User / Brochure / MatchRecord / UserTag / TrustNetwork / VisitorLog
构建用户之间的关系网络，用于图谱查询、可视化和推荐增强。

功能:
  1. 用户节点 & 关系边构建
  2. 多类型关系: 标签匹配、信任连接、行业同行、画册浏览、匹配记录
  3. 图谱查询: 最短路径、共同邻居、社区发现
  4. 缓存支持 (Redis)
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache
from app.models.brochure import Brochure
from app.models.tag import MatchRecord, UserTag
from app.models.trust import TrustNetwork
from app.models.user import User
from app.models.visitor import VisitorLog

logger = logging.getLogger(__name__)


# ======================================================================
# 数据模型
# ======================================================================


@dataclass
class GraphNode:
    """知识图谱节点"""

    id: str  # "user:{id}" / "brochure:{id}" / "tag:{tag}"
    label: str
    type: str  # "user" | "brochure" | "tag"
    properties: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "properties": self.properties,
        }


@dataclass
class GraphEdge:
    """知识图谱边"""

    source: str  # 源节点 ID
    target: str  # 目标节点 ID
    relation: str  # 关系类型
    weight: float = 1.0
    properties: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "weight": self.weight,
            "properties": self.properties,
        }


@dataclass
class KnowledgeGraph:
    """完整知识图谱"""

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    def add_node(self, node: GraphNode):
        if node.id not in {n.id for n in self.nodes}:
            self.nodes.append(node)

    def add_edge(self, edge: GraphEdge):
        self.edges.append(edge)


# ======================================================================
# 关系图谱构建器
# ======================================================================


class KnowledgeGraphBuilder:
    """企业关系图谱构建器"""

    RELATION_TAG_MATCH = "tag_match"  # 标签供需匹配
    RELATION_TRUST = "trust"  # 信任连接
    RELATION_INDUSTRY = "industry_peer"  # 同行（同公司/行业）
    RELATION_MATCH_RECORD = "match_record"  # 匹配记录
    RELATION_BROCHURE_VIEW = "brochure_view"  # 浏览画册
    RELATION_COMMON_TAG = "common_tag"  # 共同标签
    RELATION_OWN_BROCHURE = "own_brochure"  # 拥有画册

    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_user_graph(
        self,
        user_id: int,
        max_depth: int = 2,
        max_nodes: int = 200,
    ) -> KnowledgeGraph:
        """以指定用户为中心构建关系子图

        Args:
            user_id: 中心用户 ID
            max_depth: 最大关系深度 (1=直连, 2=间接)
            max_nodes: 最大节点数

        Returns:
            KnowledgeGraph 对象
        """
        kg = KnowledgeGraph()
        visited = set()

        # 添加中心用户节点
        user_node = await self._make_user_node(user_id)
        if user_node:
            kg.add_node(user_node)
            visited.add(user_id)

        # 深度优先构建
        await self._build_edges_for_user(kg, user_id, visited, depth=0, max_depth=max_depth, max_nodes=max_nodes)

        return kg

    async def _build_edges_for_user(
        self,
        kg: KnowledgeGraph,
        user_id: int,
        visited: set,
        depth: int,
        max_depth: int,
        max_nodes: int,
    ):
        """递归构建用户关系边"""
        if depth >= max_depth or len(visited) >= max_nodes:
            return

        # 1. 标签匹配关系
        await self._add_tag_match_edges(kg, user_id, visited, depth, max_depth, max_nodes)

        # 2. 信任连接关系
        await self._add_trust_edges(kg, user_id, visited, depth, max_depth, max_nodes)

        # 3. 同行关系
        await self._add_industry_edges(kg, user_id, visited, depth, max_depth, max_nodes)

        # 4. 画册所有权
        await self._add_brochure_edges(kg, user_id, visited, depth, max_depth, max_nodes)

        # 5. 匹配记录关系
        await self._add_match_record_edges(kg, user_id, visited, depth, max_depth, max_nodes)

        # 6. 浏览关系
        await self._add_visitor_edges(kg, user_id, visited, depth, max_depth, max_nodes)

    async def _make_user_node(self, user_id: int) -> GraphNode | None:
        """构建用户节点"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            return None

        # 获取用户标签
        result = await self.db.execute(select(UserTag).where(UserTag.user_id == user_id))
        tags = result.scalars().all()
        tag_list = [{"tag": t.tag, "type": t.tag_type, "weight": t.weight} for t in tags]

        return GraphNode(
            id=f"user:{user_id}",
            label=user.name,
            type="user",
            properties={
                "user_id": user.id,
                "name": user.name,
                "company": user.company,
                "title": user.title,
                "intro": user.intro[:200] if user.intro else "",
                "tags": tag_list,
                "membership_tier": user.membership_tier,
            },
        )

    async def _add_tag_match_edges(self, kg, user_id, visited, depth, max_depth, max_nodes):
        """添加标签供需匹配关系边"""
        # 获取当前用户的标签
        result = await self.db.execute(select(UserTag).where(UserTag.user_id == user_id))
        my_tags = result.scalars().all()
        my_provide = {t.tag: t.weight for t in my_tags if t.tag_type == "provide"}
        my_need = {t.tag: t.weight for t in my_tags if t.tag_type == "need"}

        if not my_provide and not my_need:
            return

        # 查找所有有其他用户的标签进行匹配
        all_tags = set(my_provide.keys()) | set(my_need.keys())
        for tag in all_tags:
            result = await self.db.execute(
                select(UserTag)
                .where(
                    UserTag.tag == tag,
                    UserTag.user_id != user_id,
                )
                .limit(20)
            )
            matching_tags = result.scalars().all()
            for mt in matching_tags:
                if mt.user_id in visited:
                    continue
                if len(visited) >= max_nodes:
                    return
                visited.add(mt.user_id)

                node = await self._make_user_node(mt.user_id)
                if node:
                    kg.add_node(node)

                # 计算匹配权重
                is_provide_match = tag in my_provide and mt.tag_type == "need"
                is_need_match = tag in my_need and mt.tag_type == "provide"
                if is_provide_match or is_need_match:
                    weight = my_provide.get(tag, my_need.get(tag, 0)) * mt.weight
                    kg.add_edge(
                        GraphEdge(
                            source=f"user:{user_id}",
                            target=f"user:{mt.user_id}",
                            relation=self.RELATION_TAG_MATCH,
                            weight=weight,
                            properties={
                                "tag": tag,
                                "direction": "provide→need" if is_provide_match else "need→provide",
                            },
                        )
                    )

    async def _add_trust_edges(self, kg, user_id, visited, depth, max_depth, max_nodes):
        """添加信任连接关系边"""
        result = await self.db.execute(
            select(TrustNetwork)
            .where((TrustNetwork.user_id == user_id) | (TrustNetwork.trusted_user_id == user_id))
            .limit(30)
        )
        trusts = result.scalars().all()
        for t in trusts:
            target_id = t.trusted_user_id if t.user_id == user_id else t.user_id
            if target_id in visited:
                continue
            if len(visited) >= max_nodes:
                return
            visited.add(target_id)

            node = await self._make_user_node(target_id)
            if node:
                kg.add_node(node)
            kg.add_edge(
                GraphEdge(
                    source=f"user:{user_id}",
                    target=f"user:{target_id}",
                    relation=self.RELATION_TRUST,
                    weight=1.0,
                    properties={"created_at": str(t.created_at)},
                )
            )

            # 如果还有深度，递归
            if depth + 1 < max_depth:
                await self._build_edges_for_user(kg, target_id, visited, depth + 1, max_depth, max_nodes)

    async def _add_industry_edges(self, kg, user_id, visited, depth, max_depth, max_nodes):
        """添加行业同行关系边"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user or not user.company:
            return

        result = await self.db.execute(
            select(User)
            .where(
                User.company == user.company,
                User.id != user_id,
            )
            .limit(20)
        )
        peers = result.scalars().all()
        for peer in peers:
            if peer.id in visited:
                continue
            if len(visited) >= max_nodes:
                return
            visited.add(peer.id)

            node = await self._make_user_node(peer.id)
            if node:
                kg.add_node(node)
            kg.add_edge(
                GraphEdge(
                    source=f"user:{user_id}",
                    target=f"user:{peer.id}",
                    relation=self.RELATION_INDUSTRY,
                    weight=0.8,
                    properties={"company": user.company},
                )
            )

    async def _add_brochure_edges(self, kg, user_id, visited, depth, max_depth, max_nodes):
        """添加画册拥有关系边"""
        result = await self.db.execute(select(Brochure).where(Brochure.user_id == user_id).limit(10))
        brochures = result.scalars().all()
        for b in brochures:
            node_id = f"brochure:{b.id}"
            if node_id not in {n.id for n in kg.nodes}:
                kg.add_node(
                    GraphNode(
                        id=node_id,
                        label=b.title,
                        type="brochure",
                        properties={
                            "brochure_id": b.id,
                            "title": b.title,
                            "purpose": b.purpose,
                            "status": b.status,
                        },
                    )
                )
            kg.add_edge(
                GraphEdge(
                    source=f"user:{user_id}",
                    target=node_id,
                    relation=self.RELATION_OWN_BROCHURE,
                    weight=1.0,
                )
            )

    async def _add_match_record_edges(self, kg, user_id, visited, depth, max_depth, max_nodes):
        """添加匹配记录关系边"""
        result = await self.db.execute(
            select(MatchRecord)
            .where(
                (MatchRecord.user_a_id == user_id) | (MatchRecord.user_b_id == user_id),
                MatchRecord.match_score >= 0.3,
            )
            .order_by(MatchRecord.match_score.desc())
            .limit(20)
        )
        records = result.scalars().all()
        for rec in records:
            target_id = rec.user_b_id if rec.user_a_id == user_id else rec.user_a_id
            if target_id in visited:
                continue
            if len(visited) >= max_nodes:
                return
            visited.add(target_id)

            node = await self._make_user_node(target_id)
            if node:
                kg.add_node(node)
            kg.add_edge(
                GraphEdge(
                    source=f"user:{user_id}",
                    target=f"user:{target_id}",
                    relation=self.RELATION_MATCH_RECORD,
                    weight=rec.match_score,
                    properties={
                        "match_score": rec.match_score,
                        "status": rec.status,
                        "common_tags": rec.common_tags,
                    },
                )
            )

    async def _add_visitor_edges(self, kg, user_id, visited, depth, max_depth, max_nodes):
        """添加浏览关系边（谁看了我的画册）"""
        # 获取用户的画册
        result = await self.db.execute(select(Brochure).where(Brochure.user_id == user_id).limit(10))
        brochures = result.scalars().all()
        brochure_ids = [b.id for b in brochures]
        if not brochure_ids:
            return

        # 统计浏览频次
        from sqlalchemy import func as sa_func

        result = await self.db.execute(
            select(
                VisitorLog.visitor_id,
                sa_func.count(VisitorLog.id).label("visit_count"),
            )
            .where(
                VisitorLog.brochure_id.in_(brochure_ids),
                VisitorLog.visitor_id.isnot(None),
                VisitorLog.visitor_id != str(user_id),
            )
            .group_by(VisitorLog.visitor_id)
            .order_by(sa_func.count(VisitorLog.id).desc())
            .limit(10)
        )
        visitors = result.all()
        for visitor_id_str, count in visitors:
            try:
                visitor_id = int(visitor_id_str)
            except (ValueError, TypeError):
                continue
            if visitor_id in visited:
                continue
            if len(visited) >= max_nodes:
                return
            visited.add(visitor_id)

            node = await self._make_user_node(visitor_id)
            if node:
                kg.add_node(node)
            kg.add_edge(
                GraphEdge(
                    source=f"user:{visitor_id}",
                    target=f"user:{user_id}",
                    relation=self.RELATION_BROCHURE_VIEW,
                    weight=min(count / 5.0, 1.0),
                    properties={"visit_count": count},
                )
            )

    # ======================================================================
    # 图谱查询方法
    # ======================================================================

    async def get_shortest_path(
        self,
        user_id_a: int,
        user_id_b: int,
        max_depth: int = 4,
    ) -> list[list[dict]]:
        """查找两个用户之间的最短关系路径（BFS）

        Returns:
            路径列表，每个路径是节点字典列表
        """
        if user_id_a == user_id_b:
            return []

        # BFS
        from collections import deque

        queue = deque()
        queue.append((user_id_a, [f"user:{user_id_a}"]))
        visited = {user_id_a}
        paths = []

        while queue and len(paths) < 3:  # 最多返回 3 条路径
            current_id, path = queue.popleft()
            if len(path) > max_depth:
                continue

            # 获取当前用户的邻居
            neighbors = await self._get_neighbors(current_id)
            for neighbor_id, relation in neighbors:
                neighbor_str = f"user:{neighbor_id}"
                if neighbor_id == user_id_b:
                    full_path = path + [neighbor_str]
                    path_detail = []
                    for i in range(len(full_path) - 1):
                        src = full_path[i]
                        dst = full_path[i + 1]
                        # 查找边上的关系类型
                        rel = "connected"
                        for e in self._edges_between(src, dst):
                            rel = e["relation"]
                            break
                        path_detail.append(
                            {
                                "from": src,
                                "to": dst,
                                "relation": rel,
                            }
                        )
                    # 添加最后一个节点
                    path_detail.append({"node": f"user:{user_id_b}"})
                    paths.append(path_detail)
                elif neighbor_id not in visited and len(path) < max_depth:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, path + [neighbor_str]))

        return paths

    async def _get_neighbors(self, user_id: int) -> list[tuple[int, str]]:
        """获取用户的直接邻居用户"""
        neighbors = []

        # 信任网络
        result = await self.db.execute(
            select(TrustNetwork).where((TrustNetwork.user_id == user_id) | (TrustNetwork.trusted_user_id == user_id))
        )
        for t in result.scalars().all():
            nid = t.trusted_user_id if t.user_id == user_id else t.user_id
            neighbors.append((nid, "trust"))

        # 匹配记录
        result = await self.db.execute(
            select(MatchRecord).where((MatchRecord.user_a_id == user_id) | (MatchRecord.user_b_id == user_id))
        )
        for m in result.scalars().all():
            nid = m.user_b_id if m.user_a_id == user_id else m.user_a_id
            neighbors.append((nid, "match_record"))

        # 同行（同公司）
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if user and user.company:
            result = await self.db.execute(
                select(User.id)
                .where(
                    User.company == user.company,
                    User.id != user_id,
                )
                .limit(20)
            )
            for row in result.scalars().all():
                neighbors.append((row, "industry_peer"))

        return list(set(neighbors))

    def _edges_between(self, src: str, dst: str) -> list[dict]:
        """查找两个节点之间的边（用于路径描述，简化实现）"""
        # 实际项目中应查询数据库或缓存
        return [{"relation": "connected"}]

    async def get_common_neighbors(
        self,
        user_id_a: int,
        user_id_b: int,
    ) -> list[dict]:
        """查找两个用户的共同邻居"""
        neighbors_a = set(nid for nid, _ in await self._get_neighbors(user_id_a))
        neighbors_b = set(nid for nid, _ in await self._get_neighbors(user_id_b))
        common = neighbors_a & neighbors_b

        result = []
        for nid in common:
            node = await self._make_user_node(nid)
            if node:
                result.append(node.to_dict())
        return result

    async def get_recommendation_candidates(
        self,
        user_id: int,
        max_candidates: int = 50,
    ) -> list[dict]:
        """基于图谱推荐潜在匹配用户"""
        # 获取当前用户的直接邻居
        neighbors = set(nid for nid, _ in await self._get_neighbors(user_id))

        # 获取邻居的邻居（二度关系）
        candidates = {}
        for nid in neighbors:
            n2_list = await self._get_neighbors(nid)
            for n2_id, relation in n2_list:
                if n2_id == user_id or n2_id in neighbors:
                    continue
                # 累积推荐分数
                if n2_id not in candidates:
                    candidates[n2_id] = {"score": 0, "paths": []}
                candidates[n2_id]["score"] += 1.0
                candidates[n2_id]["paths"].append(
                    {
                        "via": nid,
                        "relation": relation,
                    }
                )

        # 排序并返回 top N
        sorted_candidates = sorted(
            candidates.items(),
            key=lambda x: x[1]["score"],
            reverse=True,
        )[:max_candidates]

        result = []
        for cid, data in sorted_candidates:
            node = await self._make_user_node(cid)
            if node:
                result.append(
                    {
                        **node.to_dict(),
                        "recommendation_score": data["score"],
                        "paths": data["paths"],
                    }
                )
        return result

    async def get_graph_summary(self, user_id: int) -> dict:
        """获取用户的关系图谱摘要统计"""
        kg = await self.build_user_graph(user_id, max_depth=1)

        stats = {
            "total_nodes": len(kg.nodes),
            "total_edges": len(kg.edges),
            "direct_connections": 0,
            "trust_connections": 0,
            "match_record_connections": 0,
            "industry_peers": 0,
            "tag_match_connections": 0,
            "brochure_views": 0,
        }

        for e in kg.edges:
            if e.source == f"user:{user_id}" or e.target == f"user:{user_id}":
                stats["direct_connections"] += 1
                if e.relation == self.RELATION_TRUST:
                    stats["trust_connections"] += 1
                elif e.relation == self.RELATION_MATCH_RECORD:
                    stats["match_record_connections"] += 1
                elif e.relation == self.RELATION_INDUSTRY:
                    stats["industry_peers"] += 1
                elif e.relation == self.RELATION_TAG_MATCH:
                    stats["tag_match_connections"] += 1
                elif e.relation == self.RELATION_BROCHURE_VIEW:
                    stats["brochure_views"] += 1

        return stats


# ======================================================================
# 缓存包装
# ======================================================================


class CachedKnowledgeGraphBuilder(KnowledgeGraphBuilder):
    """带缓存的知识图谱构建器"""

    @cache(ttl=300, prefix="kg_user_graph")
    async def build_user_graph(self, user_id: int, max_depth: int = 2, max_nodes: int = 200) -> KnowledgeGraph:
        return await super().build_user_graph(user_id, max_depth, max_nodes)

    @cache(ttl=600, prefix="kg_user_summary")
    async def get_graph_summary(self, user_id: int) -> dict:
        return await super().get_graph_summary(user_id)

    @cache(ttl=300, prefix="kg_recommend_candidates")
    async def get_recommendation_candidates(self, user_id: int, max_candidates: int = 50) -> list[dict]:
        return await super().get_recommendation_candidates(user_id, max_candidates)
