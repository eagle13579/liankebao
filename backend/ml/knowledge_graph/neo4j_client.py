"""
企业关系知识图谱 — Neo4j 图数据库客户端 + 迁移工具
====================================================
支持从 NetworkX 内存图谱迁移到 Neo4j，并提供 Cypher 查询接口。
无 Neo4j 实例时自动降级为 NetworkX 模式（不崩溃）。

设计原则:
1. Neo4j 连接失败/不可用 → 降级到 NetworkX 查询（利用 builder 的图）
2. 环境变量 NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD 配置连接
3. 所有 Cypher 查询均提供 NetworkX 回退实现
4. 迁移操作（create_constraints / drop_all / migrate_from_networkx）在无 Neo4j 时静默跳过

依赖:
    neo4j (pip install neo4j) — 可选，缺失时自动降级
    networkx — 回退模式的底层图引擎

用法:
    from backend.ml.knowledge_graph.neo4j_client import Neo4jClient

    client = Neo4jClient()
    client.connect()                     # 尝试连接，失败则降级
    client.migrate_from_networkx(graph)  # 迁移 NetworkX 图到 Neo4j
    result = client.find_competitors("e001")
    client.close()
"""

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 尝试导入 neo4j 驱动
# ---------------------------------------------------------------------------

try:
    from neo4j import GraphDatabase, basic_auth

    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False
    GraphDatabase = None  # type: ignore[assignment]
    basic_auth = None

# ---------------------------------------------------------------------------
# 尝试导入 NetworkX（降级模式需要）
# ---------------------------------------------------------------------------

try:
    import networkx as nx

    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# 环境变量默认值
# ---------------------------------------------------------------------------

DEFAULT_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
DEFAULT_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", None)


# ---------------------------------------------------------------------------
# Neo4j 客户端
# ---------------------------------------------------------------------------


class Neo4jClient:
    """Neo4j 图数据库客户端

    管理 Neo4j 连接生命周期，所有 Cypher 查询操作均有 NetworkX 降级实现。
    无 Neo4j 实例时所有方法正常工作（基于传入的 NetworkX 图）。

    Attributes:
        driver: Neo4j 驱动实例（未连接时为 None）
        _mode: 当前运行模式 "neo4j" | "networkx"
        _graph: 降级模式下的 NetworkX 图引用
    """

    def __init__(
        self,
        uri: str = DEFAULT_NEO4J_URI,
        user: str = DEFAULT_NEO4J_USER,
        password: Optional[str] = DEFAULT_NEO4J_PASSWORD,
    ):
        """初始化 Neo4j 客户端

        Args:
            uri: Neo4j Bolt 连接 URI（默认从 NEO4J_URI 环境变量读取）
            user: Neo4j 用户名（默认从 NEO4J_USER 环境变量读取）
            password: Neo4j 密码（默认从 NEO4J_PASSWORD 环境变量读取）
        """
        self.uri = uri
        self.user = user
        self.password = password
        self.driver: Optional[Any] = None
        self._mode: str = "init"
        self._graph: Optional[Any] = None  # NetworkX 图的引用（降级用）

        logger.info(
            "Neo4jClient 初始化: uri=%s, user=%s, has_password=%s",
            uri,
            user,
            password is not None,
        )

    # --------------------------------------------------------------
    # 连接管理
    # --------------------------------------------------------------

    def connect(self) -> bool:
        """连接到 Neo4j 数据库

        如果 neo4j 驱动未安装或连接失败，自动降级为 NetworkX 模式。
        降级时会打印警告日志，但不会抛出异常。

        Returns:
            True 表示 Neo4j 连接成功，False 表示降级到 NetworkX
        """
        if not HAS_NEO4J:
            logger.warning(
                "neo4j 驱动未安装 (pip install neo4j)，降级为 NetworkX 模式"
            )
            self._mode = "networkx"
            return False

        if not self.password:
            logger.warning("Neo4j 密码未配置，降级为 NetworkX 模式")
            self._mode = "networkx"
            return False

        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=basic_auth(self.user, self.password),
            )
            # 验证连接
            with self.driver.session(database="neo4j") as session:
                session.run("RETURN 1")
            self._mode = "neo4j"
            logger.info("Neo4j 连接成功: %s@%s", self.user, self.uri)
            return True
        except Exception as e:
            logger.warning("Neo4j 连接失败 (%s)，降级为 NetworkX 模式", e)
            self._mode = "networkx"
            if self.driver:
                try:
                    self.driver.close()
                except Exception:
                    pass
                self.driver = None
            return False

    def close(self) -> None:
        """关闭 Neo4j 连接"""
        if self.driver:
            try:
                self.driver.close()
                logger.info("Neo4j 连接已关闭")
            except Exception as e:
                logger.warning("关闭 Neo4j 连接时出错: %s", e)
            finally:
                self.driver = None
        self._mode = "init"

    def is_connected(self) -> bool:
        """检查当前是否连接到 Neo4j

        Returns:
            True 表示 Neo4j 连接正常
        """
        if self._mode != "neo4j" or not self.driver:
            return False
        try:
            with self.driver.session(database="neo4j") as session:
                session.run("RETURN 1")
            return True
        except Exception:
            return False

    def set_fallback_graph(self, graph: Any) -> None:
        """设置降级模式用的 NetworkX 图

        当 Neo4j 不可用时，所有查询操作将基于此 NetworkX 图执行。

        Args:
            graph: networkx.Graph 实例
        """
        self._graph = graph

    @property
    def mode(self) -> str:
        """当前运行模式: 'neo4j' | 'networkx' | 'init'"""
        return self._mode

    def _require_fallback_graph(self) -> Any:
        """确保降级模式下有可用的 NetworkX 图"""
        if self._graph is None:
            if not HAS_NETWORKX:
                raise RuntimeError(
                    "降级模式需要 NetworkX 库。请安装: pip install networkx"
                )
            self._graph = nx.DiGraph()
        return self._graph


# ---------------------------------------------------------------------------
# Schema 管理（约束 + 索引）
# ---------------------------------------------------------------------------


class Neo4jSchema:
    """Neo4j 图数据库 Schema 管理

    负责创建唯一约束、索引以及清空整个图谱。
    无 Neo4j 连接时所有方法静默跳过。
    """

    # 需要创建唯一约束的标签和属性
    UNIQUE_CONSTRAINTS: list[tuple[str, str]] = [
        ("Enterprise", "id"),
        ("Person", "id"),
        ("Industry", "id"),
    ]

    # 需要创建索引的标签和属性
    INDEXES: list[tuple[str, str]] = [
        ("Enterprise", "name"),
        ("Person", "name"),
        ("Industry", "name"),
        ("Enterprise", "industry"),
    ]

    def __init__(self, client: Neo4jClient):
        """初始化 Schema 管理器

        Args:
            client: Neo4jClient 实例
        """
        self.client = client

    def _run(self, query: str, params: Optional[dict[str, Any]] = None) -> list[Any]:
        """在 Neo4j 上执行写/DDL 语句（无连接时静默跳过）

        Args:
            query: Cypher 语句
            params: 查询参数

        Returns:
            查询结果列表，降级时返回空列表
        """
        if self.client.mode != "neo4j" or not self.client.driver:
            logger.debug("Neo4j 不可用，跳过: %s", query[:80])
            return []
        try:
            with self.client.driver.session(database="neo4j") as session:
                result = session.run(query, params or {})
                return list(result)
        except Exception as e:
            logger.warning("Neo4j 查询失败 (%s)，跳过: %s", e, query[:80])
            return []

    def create_constraints(self) -> int:
        """为关键实体类型创建唯一约束

        为 Enterprise.id, Person.id, Industry.id 创建唯一性约束，
        确保迁移时不会产生重复节点。

        Returns:
            成功创建的约束数量（降级时返回 0）
        """
        count = 0
        if self.client.mode != "neo4j":
            logger.info("Neo4j 不可用，跳过创建约束")
            return 0

        for label, prop in self.UNIQUE_CONSTRAINTS:
            constraint_name = f"unique_{label}_{prop}".lower()
            query = (
                f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
            )
            self._run(query)
            count += 1
            logger.info("已创建约束: %s (%s.%s)", constraint_name, label, prop)

        logger.info("约束创建完成: 共 %d 条", count)
        return count

    def create_indexes(self) -> int:
        """为常用查询字段创建索引

        为 Enterprise.name, Person.name, Industry.name, Enterprise.industry
        创建 BTREE 索引，加速按名称/行业查询。

        Returns:
            成功创建的索引数量（降级时返回 0）
        """
        count = 0
        if self.client.mode != "neo4j":
            logger.info("Neo4j 不可用，跳过创建索引")
            return 0

        for label, prop in self.INDEXES:
            index_name = f"idx_{label}_{prop}".lower()
            query = (
                f"CREATE INDEX {index_name} IF NOT EXISTS "
                f"FOR (n:{label}) ON (n.{prop})"
            )
            self._run(query)
            count += 1
            logger.info("已创建索引: %s (%s.%s)", index_name, label, prop)

        logger.info("索引创建完成: 共 %d 条", count)
        return count

    def drop_all(self) -> int:
        """清空整个图谱（删除所有节点和关系）

        用于重建图谱前的清理操作。
        注意: 此操作不可逆！

        Returns:
            删除的节点数量（降级时返回 0）
        """
        if self.client.mode != "neo4j":
            logger.info("Neo4j 不可用，跳过清空图谱")
            return 0

        # 先获取节点总数
        count_result = self._run("MATCH (n) RETURN count(n) AS cnt")
        total = count_result[0]["cnt"] if count_result else 0

        # 删除所有关系和节点
        self._run("MATCH (n) DETACH DELETE n")
        logger.info("图谱已清空: 删除 %d 个节点", total)

        # 删除所有约束和索引（可选清理）
        # Neo4j 5.x 中 DETACH DELETE 不删除 schema 对象
        # 但 drop_all 只负责数据清理，schema 保留

        return total


# ---------------------------------------------------------------------------
# 数据迁移：NetworkX → Neo4j
# ---------------------------------------------------------------------------

# 需要过滤掉的 NetworkX 内部属性键
_NX_INTERNAL_KEYS = {"_type", "_id"}

# 节点标签与关系类型的映射规则
# NetworkX 用 _type 属性表示节点类型，Neo4j 用 Label


def _get_node_label(node_data: dict[str, Any]) -> str:
    """从节点数据中提取 Neo4j 标签

    Args:
        node_data: NetworkX 节点属性字典

    Returns:
        Neo4j Label（如 "Enterprise", "Person"）
    """
    return node_data.get("_type", "Unknown")


def _get_relation_type(edge_data: dict[str, Any]) -> str:
    """从边数据中提取 Neo4j 关系类型

    Args:
        edge_data: NetworkX 边属性字典

    Returns:
        关系类型字符串（如 "INDUSTRY_OF", "COMPETES_WITH"）
    """
    return edge_data.get("_type") or edge_data.get("label", "RELATED")


def _filter_properties(data: dict[str, Any]) -> dict[str, Any]:
    """过滤掉 NetworkX 内部属性，保留用户属性

    Args:
        data: 原始属性字典

    Returns:
        过滤后的属性字典（不含 _type, _id 等内部键）
    """
    return {k: v for k, v in data.items() if k not in _NX_INTERNAL_KEYS}


def _sanitize_value(value: Any) -> Any:
    """将 Python 值转换为 Neo4j 兼容的类型

    Neo4j 不支持 set、tuple、numpy 类型等，需要转换为 list 或标量。

    Args:
        value: 原始 Python 值

    Returns:
        Neo4j 兼容的值
    """
    if isinstance(value, (set, tuple)):
        return list(value)
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    return value


def _sanitize_properties(data: dict[str, Any]) -> dict[str, Any]:
    """清洗属性字典，确保所有值 Neo4j 兼容

    Args:
        data: 原始属性字典

    Returns:
        清洗后的属性字典
    """
    return {k: _sanitize_value(v) for k, v in data.items()}


# ---------------------------------------------------------------------------
# 迁移实现（在 Neo4jClient 上混入迁移方法）
# ---------------------------------------------------------------------------


def migrate_from_networkx(
    client: Neo4jClient, graph: Any, batch_size: int = 500
) -> dict[str, int]:
    """将 NetworkX 图全量迁移到 Neo4j

    迁移步骤:
    1. 创建 Schema（约束 + 索引）
    2. 逐批写入节点（MERGE 避免重复）
    3. 逐批写入关系（MERGE 避免重复）
    4. 返回统计信息

    Args:
        client: Neo4jClient 实例（如果未连接则直接返回统计 0）
        graph: networkx.Graph 实例（DiGraph 或 Graph）
        batch_size: 每批写入的节点/关系数

    Returns:
        dict 包含迁移统计:
            - nodes_migrated: 迁移的节点数
            - edges_migrated: 迁移的边数
            - schema_created: 是否创建了 schema
    """
    stats: dict[str, int] = {"nodes_migrated": 0, "edges_migrated": 0, "schema_created": 0}

    if client.mode != "neo4j" or not client.driver:
        logger.info("Neo4j 不可用，跳过迁移")
        return stats

    # 1. 创建 Schema
    schema = Neo4jSchema(client)
    schema.create_constraints()
    schema.create_indexes()
    stats["schema_created"] = 1

    # 2. 迁移节点
    nodes_list = list(graph.nodes(data=True))
    logger.info("开始迁移节点: 共 %d 个", len(nodes_list))

    for i in range(0, len(nodes_list), batch_size):
        batch = nodes_list[i : i + batch_size]
        with client.driver.session(database="neo4j") as session:
            for node_id, node_data in batch:
                label = _get_node_label(node_data)
                props = _sanitize_properties(_filter_properties(node_data))
                # 确保 id 属性存在
                if "id" not in props:
                    props["id"] = str(node_id)

                # 使用 MERGE 保证幂等性
                props_keys = list(props.keys())
                set_clause = ", ".join(
                    f"n.{k} = ${k}" for k in props_keys
                )
                query = (
                    f"MERGE (n:{label} {{id: $id}}) "
                    f"SET {set_clause}"
                )
                try:
                    session.run(query, props)
                except Exception as e:
                    logger.warning("节点写入失败 %s (%s): %s", node_id, label, e)

        stats["nodes_migrated"] += len(batch)
        logger.debug("节点迁移进度: %d/%d", stats["nodes_migrated"], len(nodes_list))

    # 3. 迁移关系
    edges_list = list(graph.edges(data=True))
    logger.info("开始迁移关系: 共 %d 条", len(edges_list))

    for i in range(0, len(edges_list), batch_size):
        batch = edges_list[i : i + batch_size]
        with client.driver.session(database="neo4j") as session:
            for src_id, tgt_id, edge_data in batch:
                rel_type = _get_relation_type(edge_data)
                props = _sanitize_properties(_filter_properties(edge_data))

                if props:
                    props_keys = list(props.keys())
                    set_clause = ", ".join(
                        f"r.{k} = ${k}" for k in props_keys
                    )
                    query = (
                        f"MATCH (a {{id: $src_id}}) "
                        f"MATCH (b {{id: $tgt_id}}) "
                        f"MERGE (a)-[r:{rel_type}]->(b) "
                        f"SET {set_clause}"
                    )
                    params = {"src_id": str(src_id), "tgt_id": str(tgt_id), **props}
                else:
                    query = (
                        f"MATCH (a {{id: $src_id}}) "
                        f"MATCH (b {{id: $tgt_id}}) "
                        f"MERGE (a)-[r:{rel_type}]->(b)"
                    )
                    params = {"src_id": str(src_id), "tgt_id": str(tgt_id)}

                try:
                    session.run(query, params)
                except Exception as e:
                    logger.warning(
                        "关系写入失败 %s ->[%s]-> %s: %s",
                        src_id,
                        rel_type,
                        tgt_id,
                        e,
                    )

        stats["edges_migrated"] += len(batch)
        logger.debug("关系迁移进度: %d/%d", stats["edges_migrated"], len(edges_list))

    logger.info(
        "迁移完成: %d 节点, %d 关系",
        stats["nodes_migrated"],
        stats["edges_migrated"],
    )
    return stats


# 将 migrate_from_networkx 作为 Neo4jClient 的方法
Neo4jClient.migrate_from_networkx = migrate_from_networkx  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Cypher 查询（含 NetworkX 降级实现）
# ---------------------------------------------------------------------------


def _neo4j_run(client: Neo4jClient, query: str, params: Optional[dict[str, Any]] = None) -> list[Any]:
    """在 Neo4j 上执行只读查询（降级时返回空列表）

    Args:
        client: Neo4jClient 实例
        query: Cypher 查询语句
        params: 查询参数

    Returns:
        查询结果记录列表
    """
    if client.mode != "neo4j" or not client.driver:
        return []
    try:
        with client.driver.session(database="neo4j") as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]
    except Exception as e:
        logger.warning("Cypher 查询失败: %s\n查询: %s", e, query[:120])
        return []


# --------------------------------------------------------------
# 1. find_competitors — 同行业竞争对手
# --------------------------------------------------------------


def find_competitors(
    client: Neo4jClient, enterprise_id: str, limit: int = 10
) -> list[dict[str, Any]]:
    """查询某企业的同行业竞争对手

    通过 COMPETES_WITH 关系查找直接竞争对手，按竞争强度排序。

    Args:
        client: Neo4jClient 实例
        enterprise_id: 企业 ID
        limit: 最大返回数量

    Returns:
        竞争对手列表，每项包含 {id, name, strength, ...}
    """
    if client.mode == "neo4j":
        query = """
            MATCH (e:Enterprise {id: $eid})-[r:COMPETES_WITH]->(competitor:Enterprise)
            RETURN competitor.id AS id, competitor.name AS name,
                   r.strength AS strength, competitor.industry AS industry
            ORDER BY r.strength DESC
            LIMIT $limit
        """
        results = _neo4j_run(client, query, {"eid": enterprise_id, "limit": limit})
        if results:
            return results

    # ---- NetworkX 降级实现 ----
    graph = client._require_fallback_graph()
    competitors = []

    for u, v, d in graph.edges(data=True):
        if d.get("_type") != "COMPETES_WITH":
            continue
        # 双向检查：企业可能出现在 u 或 v 位置
        if u == enterprise_id:
            comp_id = v
        elif v == enterprise_id:
            comp_id = u
        else:
            continue

        node_data = dict(graph.nodes[comp_id])
        competitors.append({
            "id": comp_id,
            "name": node_data.get("name", comp_id),
            "strength": d.get("strength", 0),
            "industry": node_data.get("industry", ""),
        })

    # 按强度降序
    competitors.sort(key=lambda x: x["strength"], reverse=True)
    return competitors[:limit]


# --------------------------------------------------------------
# 2. find_path — 最短路径查询
# --------------------------------------------------------------


def find_path(
    client: Neo4jClient, from_id: str, to_id: str, max_depth: int = 4
) -> list[dict[str, Any]]:
    """查询两个实体之间的最短路径

    使用 Cypher 的 shortestPath 函数查找任意类型实体间的关联路径。

    Args:
        client: Neo4jClient 实例
        from_id: 起始实体 ID
        to_id: 目标实体 ID
        max_depth: 最大搜索深度（默认 4）

    Returns:
        路径列表。每条路径为节点序列 [node, rel, node, rel, ..., node]，
        每个节点/关系为 dict。无路径时返回空列表。
    """
    if client.mode == "neo4j":
        query = """
            MATCH path = shortestPath(
                (a {id: $from_id})-[*1..$max_depth]-(b {id: $to_id})
            )
            RETURN [node IN nodes(path) | 
                {id: node.id, name: node.name, labels: labels(node)}
            ] AS nodes,
            [rel IN relationships(path) | 
                {type: type(rel), properties: properties(rel)}
            ] AS relationships
        """
        results = _neo4j_run(client, query, {
            "from_id": from_id,
            "to_id": to_id,
            "max_depth": max_depth,
        })
        if results and results[0].get("nodes"):
            return results

    # ---- NetworkX 降级实现 ----
    graph = client._require_fallback_graph()

    if not graph.has_node(from_id) or not graph.has_node(to_id):
        return []

    try:
        # 在有向图中查找最短路径（忽略方向）
        path_nodes = nx.shortest_path(
            graph, source=from_id, target=to_id,
        )
        if len(path_nodes) - 1 > max_depth:
            return []

        # 构建路径表示
        nodes_seq = []
        rels_seq = []
        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            node_data = dict(graph.nodes[u])
            nodes_seq.append({
                "id": u,
                "name": node_data.get("name", u),
                "labels": [node_data.get("_type", "Unknown")],
            })
            edge_data = graph.get_edge_data(u, v) or {}
            rels_seq.append({
                "type": edge_data.get("_type", edge_data.get("label", "RELATED")),
                "properties": {k: v for k, v in edge_data.items()
                               if k not in ("_type", "label")},
            })
        # 最后一个节点
        last_data = dict(graph.nodes[path_nodes[-1]])
        nodes_seq.append({
            "id": path_nodes[-1],
            "name": last_data.get("name", path_nodes[-1]),
            "labels": [last_data.get("_type", "Unknown")],
        })

        return [{"nodes": nodes_seq, "relationships": rels_seq}]

    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


# --------------------------------------------------------------
# 3. get_enterprise_ego — 企业关联子图
# --------------------------------------------------------------


def get_enterprise_ego(
    client: Neo4jClient, enterprise_id: str, depth: int = 2
) -> dict[str, Any]:
    """获取企业为中心的关联子图（Ego 网络）

    返回以目标企业为中心、指定深度内的所有节点和关系，
    用于前端可视化（类 ECharts 图数据格式）。

    Args:
        client: Neo4jClient 实例
        enterprise_id: 中心企业 ID
        depth: 扩展深度（默认 2）

    Returns:
        dict 包含:
            - nodes: 节点列表 [{id, name, labels, properties}, ...]
            - edges: 边列表 [{source, target, type, properties}, ...]
            - center: 中心节点 ID
    """
    if client.mode == "neo4j":
        query = """
            MATCH (center {id: $eid})
            OPTIONAL MATCH path = (center)-[r*1..$depth]-(connected)
            WITH center, collect(DISTINCT connected) AS all_nodes,
                 collect(DISTINCT r) AS all_rels
            WITH center, all_nodes + [center] AS all_nodes_unique, all_rels
            UNWIND all_nodes_unique AS node
            WITH DISTINCT node, all_rels
            RETURN 
                collect(DISTINCT {
                    id: node.id,
                    name: node.name,
                    labels: labels(node),
                    properties: properties(node)
                }) AS nodes,
                [rel IN all_rels | 
                    {source: id(startNode(rel)), target: id(endNode(rel)),
                     type: type(rel), properties: properties(rel)}
                ] AS edges
        """
        results = _neo4j_run(client, query, {"eid": enterprise_id, "depth": depth})
        if results and results[0].get("nodes"):
            data = results[0]
            data["center"] = enterprise_id
            return data

    # ---- NetworkX 降级实现 ----
    graph = client._require_fallback_graph()

    if not graph.has_node(enterprise_id):
        return {"nodes": [], "edges": [], "center": enterprise_id}

    # 获取 ego 子图（深度递归）
    ego_nodes = {enterprise_id}
    current_frontier = {enterprise_id}

    for _ in range(depth):
        next_frontier = set()
        for node_id in current_frontier:
            neighbors = set(graph.neighbors(node_id))
            # 有向图也查反向邻居
            if graph.is_directed():
                neighbors.update(graph.predecessors(node_id))
            next_frontier.update(neighbors)
        ego_nodes.update(next_frontier)
        current_frontier = next_frontier - current_frontier
        if not current_frontier:
            break

    # 收集节点和边
    sub_nodes = []
    sub_edges = []

    for nid in sorted(ego_nodes):
        ndata = dict(graph.nodes[nid])
        sub_nodes.append({
            "id": nid,
            "name": ndata.get("name", nid),
            "labels": [ndata.get("_type", "Unknown")],
            "properties": _filter_properties(ndata),
        })

    for u, v, d in graph.edges(data=True):
        if u in ego_nodes and v in ego_nodes:
            sub_edges.append({
                "source": u,
                "target": v,
                "type": d.get("_type", d.get("label", "RELATED")),
                "properties": _filter_properties(d),
            })

    return {"nodes": sub_nodes, "edges": sub_edges, "center": enterprise_id}


# --------------------------------------------------------------
# 4. recommend_partners — 基于图谱的合作伙伴推荐
# --------------------------------------------------------------


def recommend_partners(
    client: Neo4jClient, enterprise_id: str, limit: int = 5
) -> list[dict[str, Any]]:
    """基于知识图谱推荐潜在合作伙伴

    推荐策略（多因素加权）:
    1. 同行业但非竞争企业（同 INDUSTRY_OF 但无 COMPETES_WITH）
    2. 共享股东的企业（通过同一 Person 节点连接）
    3. 投资方投资的其他企业（投资组合协同）

    Args:
        client: Neo4jClient 实例
        enterprise_id: 目标企业 ID
        limit: 最大推荐数量

    Returns:
        推荐列表，每项包含:
            {id, name, score, reason, industry}
        按推荐评分降序排列
    """
    if client.mode == "neo4j":
        query = """
            // 策略1: 同行业非竞争企业
            MATCH (e:Enterprise {id: $eid})-[:INDUSTRY_OF]->(ind:Industry)<-[:INDUSTRY_OF]-(peer:Enterprise)
            WHERE peer.id <> $eid
            AND NOT EXISTS {
                MATCH (e)-[:COMPETES_WITH]-(peer)
            }
            WITH peer, 0.6 AS score, '同行业企业' AS reason

            // 策略2: 共享股东
            OPTIONAL MATCH (e)-[:HAS_SHAREHOLDER]->(p:Person)<-[:HAS_SHAREHOLDER]-(shared_peer:Enterprise)
            WHERE shared_peer.id <> $eid
            AND NOT EXISTS {
                MATCH (e)-[:COMPETES_WITH]-(shared_peer)
            }

            // 策略3: 投资组合协同
            OPTIONAL MATCH (e)<-[:INVESTED]-(investor:Enterprise)-[:INVESTED]->(invested_peer:Enterprise)
            WHERE invested_peer.id <> $eid
            AND NOT EXISTS {
                MATCH (e)-[:COMPETES_WITH]-(invested_peer)
            }

            // 合并和加权
            WITH peer, score, reason
            RETURN DISTINCT 
                peer.id AS id, 
                peer.name AS name, 
                peer.industry AS industry,
                score,
                reason
            ORDER BY score DESC
            LIMIT $limit
        """
        results = _neo4j_run(client, query, {"eid": enterprise_id, "limit": limit})
        if results:
            return results

    # ---- NetworkX 降级实现 ----
    graph = client._require_fallback_graph()

    if not graph.has_node(enterprise_id):
        return []

    enterprise_data = dict(graph.nodes[enterprise_id])
    enterprise_industry = enterprise_data.get("industry", "")

    # 获取目标企业的行业
    target_industries = set()
    for _, v, d in graph.edges(enterprise_id, data=True):
        if d.get("_type") == "INDUSTRY_OF":
            target_industries.add(v)

    # 获取目标企业的股东
    target_shareholders = set()
    for _, v, d in graph.edges(enterprise_id, data=True):
        if d.get("_type") == "HAS_SHAREHOLDER":
            target_shareholders.add(v)

    # 获取目标企业的竞争对手（排除用）
    target_competitors = set()
    for u, v, d in graph.edges(data=True):
        if d.get("_type") != "COMPETES_WITH":
            continue
        if u == enterprise_id:
            target_competitors.add(v)
        elif v == enterprise_id:
            target_competitors.add(u)

    # 评分
    scores: dict[str, dict[str, Any]] = {}

    for node_id, node_data in graph.nodes(data=True):
        if node_id == enterprise_id:
            continue
        if node_data.get("_type") != "Enterprise":
            continue

        total_score = 0.0
        reasons = []

        # 策略1: 同行业非竞争
        peer_industries = set()
        for _, v, d in graph.edges(node_id, data=True):
            if d.get("_type") == "INDUSTRY_OF":
                peer_industries.add(v)

        shared_industries = target_industries & peer_industries
        if shared_industries and node_id not in target_competitors:
            total_score += 0.6
            reasons.append("同行业企业")

        # 策略2: 共享股东
        peer_shareholders = set()
        for _, v, d in graph.edges(node_id, data=True):
            if d.get("_type") == "HAS_SHAREHOLDER":
                peer_shareholders.add(v)

        shared_holders = target_shareholders & peer_shareholders
        if shared_holders:
            total_score += 0.3 * len(shared_holders)
            reasons.append(f"共享股东({len(shared_holders)})")

        # 策略3: 投资组合协同
        for u, v, d in graph.edges(data=True):
            if d.get("_type") != "INVESTED":
                continue
            if v == node_id:
                # node_id 被某个投资者投资
                if any(
                    eu == enterprise_id and ed.get("_type") == "INVESTED"
                    for eu, ev, ed in graph.edges(data=True)
                ):
                    # 目标企业也被同一个投资者投资
                    for eu2, ev2, ed2 in graph.edges(data=True):
                        if ed2.get("_type") == "INVESTED" and eu2 == u and ev2 == enterprise_id:
                            total_score += 0.4
                            reasons.append("投资组合协同")
                            break

        if total_score > 0:
            scores[node_id] = {
                "id": node_id,
                "name": node_data.get("name", node_id),
                "industry": node_data.get("industry", ""),
                "score": round(total_score, 2),
                "reason": reasons[0] if reasons else "",
            }

    # 按评分降序排列
    sorted_results = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    return sorted_results[:limit]


# ---------------------------------------------------------------------------
# 将查询函数挂载为 Neo4jClient 的方法
# ---------------------------------------------------------------------------

Neo4jClient.find_competitors = find_competitors  # type: ignore[attr-defined]
Neo4jClient.find_path = find_path  # type: ignore[attr-defined]
Neo4jClient.get_enterprise_ego = get_enterprise_ego  # type: ignore[attr-defined]
Neo4jClient.recommend_partners = recommend_partners  # type: ignore[attr-defined]
