"""
企业知识图谱查询引擎 — Neo4j+NetworkX 双模式
============================================
优先连接 Neo4j（bolt://localhost:7687），失败时自动降级为 NetworkX 纯 Python 内存图。

提供三个核心查询接口:
  - query_enterprise_relations(enterprise_id) → 企业的上下游关系
  - query_industry_map(industry) → 某行业的企业分布
  - recommend_partners(enterprise_id, k=5) → 基于图谱的合作伙伴推荐

用法:
    from features.knowledge_graph import GraphQueryEngine

    engine = GraphQueryEngine()                     # 自动尝试 Neo4j，失败降级
    rels = engine.query_enterprise_relations("e001")
    ind_map = engine.query_industry_map("人工智能")
    recs = engine.recommend_partners("e001", k=5)
    print(engine.mode)                              # "neo4j" or "networkx"

依赖:
    neo4j (可选) — 未安装时自动降级
    networkx — 降级模式必需的图引擎
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 导入 schema 常量
# ---------------------------------------------------------------------------
try:
    from ml.knowledge_graph.schema import (
        EntityType,
        RelationType,
        SCHEMA,
        EnterpriseEntity,
        PersonEntity,
        IndustryEntity,
        ProductEntity,
    )
    HAS_SCHEMA = True
except ImportError:
    HAS_SCHEMA = False
    EntityType = None
    RelationType = None

# ---------------------------------------------------------------------------
# 导入 Neo4jClient（可选）
# ---------------------------------------------------------------------------
try:
    from ml.knowledge_graph.neo4j_client import Neo4jClient, HAS_NEO4J
except ImportError:
    Neo4jClient = None  # type: ignore[assignment]
    HAS_NEO4J = False

# ---------------------------------------------------------------------------
# 导入 KnowledgeGraphBuilder（NetworkX 降级模式用）
# ---------------------------------------------------------------------------
try:
    from ml.knowledge_graph.builder import KnowledgeGraphBuilder, create_builder
    HAS_BUILDER = True
except ImportError:
    KnowledgeGraphBuilder = None  # type: ignore[assignment]
    create_builder = None
    HAS_BUILDER = False

# ---------------------------------------------------------------------------
# 确保 networkx 可用（降级模式的底层引擎）
# ---------------------------------------------------------------------------
try:
    import networkx as nx

    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None  # type: ignore[assignment]


# ===========================================================================
# 示例数据（当既无 Neo4j 又无持久化图谱时的最小降级数据集）
# ===========================================================================

SAMPLE_ENTERPRISES = [
    {
        "id": "e001",
        "name": "深度智能科技",
        "industry": "人工智能",
        "region": "北京",
        "scale": "中型",
        "credit_score": 88,
        "legal_person": "张三",
    },
    {
        "id": "e002",
        "name": "云算力数据集团",
        "industry": "人工智能",
        "region": "上海",
        "scale": "大型",
        "credit_score": 92,
        "legal_person": "李四",
    },
    {
        "id": "e003",
        "name": "星辰软件工作室",
        "industry": "软件开发",
        "region": "深圳",
        "scale": "小型",
        "credit_score": 75,
        "legal_person": "王五",
    },
    {
        "id": "e004",
        "name": "海量芯片制造",
        "industry": "电子设备制造",
        "region": "上海",
        "scale": "大型",
        "credit_score": 95,
        "legal_person": "周六",
    },
    {
        "id": "e005",
        "name": "绿能电池科技",
        "industry": "电池/储能",
        "region": "宁德",
        "scale": "中型",
        "credit_score": 85,
        "legal_person": "赵七",
    },
    {
        "id": "e006",
        "name": "智联物流平台",
        "industry": "物流",
        "region": "杭州",
        "scale": "大型",
        "credit_score": 78,
        "legal_person": "陈八",
    },
    {
        "id": "e007",
        "name": "天启机器人公司",
        "industry": "人工智能",
        "region": "深圳",
        "scale": "中型",
        "credit_score": 82,
        "legal_person": "刘九",
    },
]

SAMPLE_INVEST_RELATIONS = [
    {"from_id": "e002", "to_id": "e005", "amount": 5000, "date": "2025-03-01", "ratio": 15.0},
    {"from_id": "e002", "to_id": "e007", "amount": 3000, "date": "2025-06-15", "ratio": 10.0},
    {"from_id": "e004", "to_id": "e005", "amount": 2000, "date": "2024-12-01", "ratio": 8.0},
]

SAMPLE_SUPPLY_RELATIONS = [
    {"from_id": "e004", "to_id": "e005", "category": "芯片供应"},
    {"from_id": "e004", "to_id": "e007", "category": "芯片供应"},
    {"from_id": "e005", "to_id": "e006", "category": "电池供应"},
]


def _build_sample_graph() -> Any:
    """构建示例 NetworkX 有向图作为降级数据源

    Returns:
        networkx.DiGraph 实例，含企业、行业、产品、自然人节点及关系
    """
    if not HAS_NETWORKX:
        raise RuntimeError("NetworkX 未安装，无法构建示例图")

    if not HAS_SCHEMA:
        # 无 schema 模块时使用纯 dict 降级
        graph = nx.DiGraph()
        for ent in SAMPLE_ENTERPRISES:
            graph.add_node(
                ent["id"],
                **{
                    "_type": "Enterprise",
                    "_id": ent["id"],
                    "id": ent["id"],
                    "name": ent["name"],
                    "industry": ent.get("industry", ""),
                    "region": ent.get("region", ""),
                    "scale": ent.get("scale", ""),
                    "credit_score": ent.get("credit_score", 0),
                    "legal_person": ent.get("legal_person", ""),
                },
            )
        return graph

    builder = KnowledgeGraphBuilder(db_path=":memory:")
    builder.build_from_enterprise_data(SAMPLE_ENTERPRISES)
    builder.build_industry_tree()
    builder.extract_shareholder_relations()
    builder.infer_competitor_relations()
    builder.extract_invest_relations(SAMPLE_INVEST_RELATIONS)

    # 添加供应链关系
    for sup in SAMPLE_SUPPLY_RELATIONS:
        from_id = sup.get("from_id", "")
        to_id = sup.get("to_id", "")
        if from_id and to_id and builder.graph.has_node(from_id) and builder.graph.has_node(to_id):
            builder.graph.add_edge(
                from_id,
                to_id,
                label="SUPPLIES",
                _type="SUPPLIES",
                category=sup.get("category", ""),
            )

    return builder.graph


# ===========================================================================
# 查询引擎
# ===========================================================================


class GraphQueryEngine:
    """企业知识图谱查询引擎

    双模式设计:
      - Neo4j 模式: 连接真实 Neo4j 图数据库，使用 Cypher 查询
      - NetworkX 模式: 降级为纯 Python 内存图（由 KnowledgeGraphBuilder 构建）

    Attributes:
        mode: 当前运行模式 ("neo4j" | "networkx")
        _neo4j_client: Neo4jClient 实例（Neo4j 模式时有效）
        _graph: NetworkX DiGraph 实例（降级模式时有效）
    """

    def __init__(
        self,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_user: str = "neo4j",
        neo4j_password: Optional[str] = None,
        graph_path: Optional[str] = None,
    ):
        """初始化查询引擎

        Args:
            neo4j_uri: Neo4j Bolt 连接 URI
            neo4j_user: Neo4j 用户名
            neo4j_password: Neo4j 密码
            graph_path: 预构建的 NetworkX 图 JSON 文件路径（降级模式时加载）
                        不提供时使用内置示例数据
        """
        self._neo4j_client: Optional[Any] = None
        self._graph: Optional[Any] = None
        self._mode: str = "init"

        # ---- 尝试连接 Neo4j ----
        neo4j_ok = False
        if Neo4jClient is not None and HAS_NEO4J:
            try:
                client = Neo4jClient(
                    uri=neo4j_uri,
                    user=neo4j_user,
                    password=neo4j_password,
                )
                if client.connect():
                    self._neo4j_client = client
                    self._mode = "neo4j"
                    neo4j_ok = True
                    logger.info("GraphQueryEngine → Neo4j 模式 (%s)", neo4j_uri)
            except Exception as e:
                logger.warning("Neo4j 连接尝试失败: %s", e)

        if neo4j_ok:
            return

        # ---- 降级到 NetworkX ----
        logger.info("GraphQueryEngine → NetworkX 降级模式")

        if not HAS_NETWORKX:
            raise RuntimeError(
                "NetworkX 未安装，无法在降级模式下运行。请安装: pip install networkx"
            )

        # 尝试从文件加载，否则使用示例数据
        if graph_path:
            if HAS_BUILDER:
                try:
                    builder = KnowledgeGraphBuilder(db_path=graph_path)
                    builder.load(graph_path)
                    self._graph = builder.graph
                    logger.info("从文件加载图谱: %s", graph_path)
                except Exception as e:
                    logger.warning("加载图谱文件失败 (%s)，使用示例数据", e)
                    self._graph = _build_sample_graph()
            else:
                logger.warning("KnowledgeGraphBuilder 不可用，使用示例数据")
                self._graph = _build_sample_graph()
        else:
            self._graph = _build_sample_graph()

        self._mode = "networkx"
        logger.info(
            "GraphQueryEngine 降级模式初始化完成: %d 节点, %d 边",
            self._graph.number_of_nodes(),
            self._graph.number_of_edges(),
        )

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        """当前运行模式: 'neo4j' | 'networkx'"""
        return self._mode

    @property
    def is_connected(self) -> bool:
        """检查是否连接到 Neo4j"""
        if self._mode != "neo4j" or self._neo4j_client is None:
            return False
        return self._neo4j_client.is_connected()

    # ------------------------------------------------------------------
    # 核心查询 1: 企业上下游关系
    # ------------------------------------------------------------------

    def query_enterprise_relations(
        self, enterprise_id: str
    ) -> dict[str, Any]:
        """查询企业的上下游关系

        返回该企业所有关联实体，按关系类型分组:
          - INDUSTRY_OF: 所属行业
          - HAS_SHAREHOLDER: 股东/高管
          - INVESTED: 对外投资
          - COMPETES_WITH: 竞争对手
          - SUPPLIES: 供应商/客户
          - HAS_PRODUCT: 产品/服务

        Args:
            enterprise_id: 企业 ID

        Returns:
            dict {
                "enterprise": {id, name, ...},  # 企业基本信息
                "relations": {
                    "INDUSTRY_OF": [...],
                    "HAS_SHAREHOLDER": [...],
                    ...
                },
                "stats": { "total_relations": N, "relation_types": [...] }
            }
        """
        if self._mode == "neo4j" and self._neo4j_client is not None:
            return self._query_enterprise_relations_neo4j(enterprise_id)
        return self._query_enterprise_relations_networkx(enterprise_id)

    def _query_enterprise_relations_neo4j(
        self, enterprise_id: str
    ) -> dict[str, Any]:
        """Neo4j 实现: 查询企业上下游关系"""
        client = self._neo4j_client
        if client is None:
            return {"enterprise": {}, "relations": {}, "stats": {"total_relations": 0, "relation_types": []}}

        # 查询企业基本信息
        ent_query = "MATCH (e:Enterprise {id: $eid}) RETURN properties(e) AS props"
        ent_results = client._run(ent_query, {"eid": enterprise_id}) if hasattr(client, '_run') else []
        
        # Try the _neo4j_run internal function or use session directly
        try:
            from ml.knowledge_graph.neo4j_client import _neo4j_run as _run_cypher
        except ImportError:
            _run_cypher = None

        if _run_cypher:
            ent_records = _run_cypher(client, ent_query, {"eid": enterprise_id})
        else:
            ent_records = []

        enterprise_info = {}
        if ent_records:
            enterprise_info = ent_records[0].get("props", {})

        # 查询所有关联关系
        rel_query = """
            MATCH (e:Enterprise {id: $eid})
            OPTIONAL MATCH (e)-[r]->(target)
            RETURN type(r) AS rel_type,
                   properties(r) AS rel_props,
                   properties(target) AS target_props,
                   id(target) AS target_id,
                   labels(target) AS target_labels
            UNION
            MATCH (e:Enterprise {id: $eid})
            OPTIONAL MATCH (source)-[r]->(e)
            RETURN type(r) AS rel_type,
                   properties(r) AS rel_props,
                   properties(source) AS target_props,
                   id(source) AS target_id,
                   labels(source) AS target_labels
        """
        if _run_cypher:
            rel_records = _run_cypher(client, rel_query, {"eid": enterprise_id})
        else:
            rel_records = []

        relations: dict[str, list[dict[str, Any]]] = {}
        for rec in rel_records:
            if not rec.get("rel_type"):
                continue
            rtype = rec["rel_type"]
            if rtype not in relations:
                relations[rtype] = []
            target_info = dict(rec.get("target_props", {}))
            target_info["_id"] = rec.get("target_id", "")
            relations[rtype].append({
                "entity": target_info,
                "relation": rec.get("rel_props", {}),
            })

        total = sum(len(v) for v in relations.values())
        return {
            "enterprise": enterprise_info,
            "relations": relations,
            "stats": {
                "total_relations": total,
                "relation_types": list(relations.keys()),
            },
        }

    def _query_enterprise_relations_networkx(
        self, enterprise_id: str
    ) -> dict[str, Any]:
        """NetworkX 实现: 查询企业上下游关系"""
        graph = self._graph
        if graph is None or not graph.has_node(enterprise_id):
            return {"enterprise": {}, "relations": {}, "stats": {"total_relations": 0, "relation_types": []}}

        # 企业基本信息
        ent_data = dict(graph.nodes[enterprise_id])
        enterprise_info = {
            "id": enterprise_id,
            "name": ent_data.get("name", enterprise_id),
            "industry": ent_data.get("industry", ""),
            "region": ent_data.get("region", ""),
            "scale": ent_data.get("scale", ""),
            "credit_score": ent_data.get("credit_score", 0),
        }

        # 出边（该企业指向其他实体）
        relations: dict[str, list[dict[str, Any]]] = {}
        for _, target, edge_data in graph.edges(enterprise_id, data=True):
            rel_type = edge_data.get("_type", edge_data.get("label", "RELATED"))
            if rel_type not in relations:
                relations[rel_type] = []
            target_info = dict(graph.nodes[target])
            target_info["id"] = target
            relations[rel_type].append({
                "entity": target_info,
                "relation": {k: v for k, v in edge_data.items() if k not in ("_type", "label")},
                "direction": "outgoing",
            })

        # 入边（其他实体指向该企业）
        if graph.is_directed():
            for source, _, edge_data in graph.in_edges(enterprise_id, data=True):
                rel_type = edge_data.get("_type", edge_data.get("label", "RELATED"))
                if rel_type not in relations:
                    relations[rel_type] = []
                source_info = dict(graph.nodes[source])
                source_info["id"] = source
                relations[rel_type].append({
                    "entity": source_info,
                    "relation": {k: v for k, v in edge_data.items() if k not in ("_type", "label")},
                    "direction": "incoming",
                })

        total = sum(len(v) for v in relations.values())
        return {
            "enterprise": enterprise_info,
            "relations": relations,
            "stats": {
                "total_relations": total,
                "relation_types": list(relations.keys()),
            },
        }

    # ------------------------------------------------------------------
    # 核心查询 2: 行业地图
    # ------------------------------------------------------------------

    def query_industry_map(self, industry: str) -> dict[str, Any]:
        """查询某行业的企业分布

        返回该行业下所有企业及其基本信息、行业层级路径。

        Args:
            industry: 行业名称（如 "人工智能", "软件开发"）

        Returns:
            dict {
                "industry": {id, name, level, ...},
                "enterprises": [
                    {id, name, region, scale, credit_score, ...},
                    ...
                ],
                "stats": { "count": N, "avg_credit_score": X.X }
            }
        """
        if self._mode == "neo4j" and self._neo4j_client is not None:
            return self._query_industry_map_neo4j(industry)
        return self._query_industry_map_networkx(industry)

    def _query_industry_map_neo4j(self, industry: str) -> dict[str, Any]:
        """Neo4j 实现: 查询行业企业分布"""
        try:
            from ml.knowledge_graph.neo4j_client import _neo4j_run as _run_cypher
        except ImportError:
            _run_cypher = None

        client = self._neo4j_client
        if client is None or not _run_cypher:
            return {"industry": {}, "enterprises": [], "stats": {"count": 0, "avg_credit_score": 0.0}}

        # 查询行业节点
        ind_query = """
            MATCH (ind:Industry {name: $name})
            RETURN properties(ind) AS props
        """
        ind_records = _run_cypher(client, ind_query, {"name": industry})

        industry_info = {}
        if ind_records:
            industry_info = ind_records[0].get("props", {})
            # 如果没有直接命中的行业节点，尝试模糊匹配
        elif HAS_SCHEMA:
            # 模糊匹配：按名称包含关系查找行业
            ind_query2 = """
                MATCH (ind:Industry)
                WHERE ind.name CONTAINS $name
                RETURN properties(ind) AS props
                LIMIT 1
            """
            ind_records2 = _run_cypher(client, ind_query2, {"name": industry})
            if ind_records2:
                industry_info = ind_records2[0].get("props", {})

        # 查询该行业下的企业
        ent_query = """
            MATCH (e:Enterprise)-[:INDUSTRY_OF]->(ind:Industry)
            WHERE ind.name = $name
            RETURN properties(e) AS props
            ORDER BY e.credit_score DESC
        """
        ent_records = _run_cypher(client, ent_query, {"name": industry})

        enterprises = []
        for rec in ent_records:
            props = dict(rec.get("props", {}))
            enterprises.append({
                "id": props.get("id", ""),
                "name": props.get("name", ""),
                "region": props.get("region", ""),
                "scale": props.get("scale", ""),
                "credit_score": props.get("credit_score", 0),
                "reg_status": props.get("reg_status", ""),
            })

        # 如果 Neo4j 无结果，降级到 NetworkX
        if not enterprises and self._graph is not None:
            return self._query_industry_map_networkx(industry)

        scores = [e["credit_score"] for e in enterprises if e["credit_score"]]
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0

        return {
            "industry": industry_info,
            "enterprises": enterprises,
            "stats": {
                "count": len(enterprises),
                "avg_credit_score": avg_score,
            },
        }

    def _query_industry_map_networkx(self, industry: str) -> dict[str, Any]:
        """NetworkX 实现: 查询行业企业分布"""
        graph = self._graph
        if graph is None:
            return {"industry": {}, "enterprises": [], "stats": {"count": 0, "avg_credit_score": 0.0}}

        # 查找行业节点
        industry_info = {}
        industry_id = None
        for nid, ndata in graph.nodes(data=True):
            if ndata.get("name") == industry or ndata.get("name", "").endswith(industry):
                industry_info = dict(ndata)
                industry_info["id"] = nid
                industry_id = nid
                break

        # 如果未精确匹配，尝试包含匹配
        if industry_id is None:
            for nid, ndata in graph.nodes(data=True):
                name = ndata.get("name", "")
                if industry in name or name in industry:
                    industry_info = dict(ndata)
                    industry_info["id"] = nid
                    industry_id = nid
                    break

        # 查找该行业下的企业
        enterprises = []
        if industry_id:
            for u, v, d in graph.edges(data=True):
                if v == industry_id and d.get("_type") == "INDUSTRY_OF":
                    ent_data = dict(graph.nodes[u])
                    enterprises.append({
                        "id": u,
                        "name": ent_data.get("name", u),
                        "region": ent_data.get("region", ""),
                        "scale": ent_data.get("scale", ""),
                        "credit_score": ent_data.get("credit_score", 0),
                        "reg_status": ent_data.get("reg_status", ""),
                    })

        # 按信用评分排序
        enterprises.sort(key=lambda x: x["credit_score"] or 0, reverse=True)

        scores = [e["credit_score"] for e in enterprises if e["credit_score"]]
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0

        # 如果通过 INDUSTRY_OF 边没找到，尝试通过 enterprise.industry 属性
        if not enterprises:
            for nid, ndata in graph.nodes(data=True):
                if ndata.get("_type") == "Enterprise" and ndata.get("industry", "") == industry:
                    enterprises.append({
                        "id": nid,
                        "name": ndata.get("name", nid),
                        "region": ndata.get("region", ""),
                        "scale": ndata.get("scale", ""),
                        "credit_score": ndata.get("credit_score", 0),
                        "reg_status": ndata.get("reg_status", ""),
                    })
            enterprises.sort(key=lambda x: x["credit_score"] or 0, reverse=True)
            scores = [e["credit_score"] for e in enterprises if e["credit_score"]]
            avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0

        return {
            "industry": industry_info,
            "enterprises": enterprises,
            "stats": {
                "count": len(enterprises),
                "avg_credit_score": avg_score,
            },
        }

    # ------------------------------------------------------------------
    # 核心查询 3: 合作伙伴推荐
    # ------------------------------------------------------------------

    def recommend_partners(
        self, enterprise_id: str, k: int = 5
    ) -> list[dict[str, Any]]:
        """基于知识图谱推荐潜在合作伙伴

        推荐策略（多因素加权）:
          1. 同行业非竞争企业（评分 +0.6）
          2. 共享股东的企业（评分 +0.3 × 共同股东数）
          3. 投资组合协同（评分 +0.4）
          4. 供应链上下游（评分 +0.5）

        Args:
            enterprise_id: 目标企业 ID
            k: 最大推荐数量（默认 5）

        Returns:
            推荐列表，每项包含 {id, name, industry, score, reason}，
            按评分降序排列
        """
        if self._mode == "neo4j" and self._neo4j_client is not None:
            return self._recommend_partners_neo4j(enterprise_id, k)
        return self._recommend_partners_networkx(enterprise_id, k)

    def _recommend_partners_neo4j(
        self, enterprise_id: str, k: int = 5
    ) -> list[dict[str, Any]]:
        """Neo4j 实现: 合作伙伴推荐"""
        try:
            from ml.knowledge_graph.neo4j_client import _neo4j_run as _run_cypher
        except ImportError:
            _run_cypher = None

        client = self._neo4j_client
        if client is None or not _run_cypher:
            return self._recommend_partners_networkx(enterprise_id, k)

        # 检查目标企业是否存在
        check_query = "MATCH (e:Enterprise {id: $eid}) RETURN count(e) AS cnt"
        check = _run_cypher(client, check_query, {"eid": enterprise_id})
        if not check or check[0].get("cnt", 0) == 0:
            return self._recommend_partners_networkx(enterprise_id, k)

        cypher_query = """
            // 目标企业
            MATCH (e:Enterprise {id: $eid})
            OPTIONAL MATCH (e)-[:INDUSTRY_OF]->(ind:Industry)
            OPTIONAL MATCH (e)-[:HAS_SHAREHOLDER]->(sh:Person)
            OPTIONAL MATCH (e)<-[:INVESTED]-(inv:Enterprise)

            // 策略1: 同行业非竞争企业
            OPTIONAL MATCH (ind)<-[:INDUSTRY_OF]-(peer:Enterprise)
            WHERE peer.id <> $eid
            AND NOT EXISTS { MATCH (e)-[:COMPETES_WITH]-(peer) }

            // 策略2: 共享股东
            OPTIONAL MATCH (sh)<-[:HAS_SHAREHOLDER]-(shared_peer:Enterprise)
            WHERE shared_peer.id <> $eid
            AND NOT EXISTS { MATCH (e)-[:COMPETES_WITH]-(shared_peer) }

            // 策略3: 投资组合协同
            OPTIONAL MATCH (inv)-[:INVESTED]->(co_invested:Enterprise)
            WHERE co_invested.id <> $eid
            AND NOT EXISTS { MATCH (e)-[:COMPETES_WITH]-(co_invested) }

            // 聚合推荐
            WITH 
                COALESCE(peer.id, shared_peer.id, co_invested.id) AS rec_id,
                COALESCE(peer.name, shared_peer.name, co_invested.name) AS rec_name,
                COALESCE(peer.industry, shared_peer.industry, co_invested.industry) AS rec_industry,
                CASE 
                    WHEN peer.id IS NOT NULL THEN 0.6
                    WHEN shared_peer.id IS NOT NULL THEN 0.3
                    WHEN co_invested.id IS NOT NULL THEN 0.4
                    ELSE 0
                END AS base_score,
                CASE 
                    WHEN peer.id IS NOT NULL THEN '同行业企业'
                    WHEN shared_peer.id IS NOT NULL THEN '共享股东'
                    WHEN co_invested.id IS NOT NULL THEN '投资组合协同'
                    ELSE ''
                END AS rec_reason
            WHERE rec_id IS NOT NULL AND rec_id <> $eid

            RETURN DISTINCT
                rec_id AS id,
                rec_name AS name,
                rec_industry AS industry,
                ROUND(base_score, 2) AS score,
                rec_reason AS reason
            ORDER BY score DESC
            LIMIT $limit
        """

        results = _run_cypher(client, cypher_query, {"eid": enterprise_id, "limit": k})

        if results:
            return [
                {
                    "id": r.get("id", ""),
                    "name": r.get("name", ""),
                    "industry": r.get("industry", ""),
                    "score": r.get("score", 0),
                    "reason": r.get("reason", ""),
                }
                for r in results
                if r.get("id")
            ]

        return self._recommend_partners_networkx(enterprise_id, k)

    def _recommend_partners_networkx(
        self, enterprise_id: str, k: int = 5
    ) -> list[dict[str, Any]]:
        """NetworkX 实现: 合作伙伴推荐"""
        graph = self._graph
        if graph is None or not graph.has_node(enterprise_id):
            return []

        ent_data = dict(graph.nodes[enterprise_id])

        # ---- 收集目标企业的信息 ----
        target_industries = set()
        for _, v, d in graph.edges(enterprise_id, data=True):
            if d.get("_type") == "INDUSTRY_OF":
                target_industries.add(v)

        target_shareholders = set()
        for _, v, d in graph.edges(enterprise_id, data=True):
            if d.get("_type") == "HAS_SHAREHOLDER":
                target_shareholders.add(v)

        # 投资方（哪些企业投资了目标企业）
        target_investors = set()
        for u, v, d in graph.edges(data=True):
            if d.get("_type") == "INVESTED" and v == enterprise_id:
                target_investors.add(u)

        # 目标企业的竞争对手（排除用）
        target_competitors = set()
        for u, v, d in graph.edges(data=True):
            if d.get("_type") != "COMPETES_WITH":
                continue
            if u == enterprise_id:
                target_competitors.add(v)
            elif v == enterprise_id:
                target_competitors.add(u)

        # ---- 遍历所有企业评分 ----
        scores: dict[str, dict[str, Any]] = {}

        for node_id, node_data in graph.nodes(data=True):
            if node_id == enterprise_id:
                continue
            if node_data.get("_type") != "Enterprise":
                continue

            total_score = 0.0
            reasons: list[str] = []

            # 策略1: 同行业非竞争 (0.6)
            peer_industries = set()
            for _, v, d in graph.edges(node_id, data=True):
                if d.get("_type") == "INDUSTRY_OF":
                    peer_industries.add(v)

            shared_industries = target_industries & peer_industries
            if shared_industries and node_id not in target_competitors:
                total_score += 0.6
                reasons.append("同行业企业")

            # 策略2: 共享股东 (0.3 × 共同股东数)
            peer_shareholders = set()
            for _, v, d in graph.edges(node_id, data=True):
                if d.get("_type") == "HAS_SHAREHOLDER":
                    peer_shareholders.add(v)

            shared_holders = target_shareholders & peer_shareholders
            if shared_holders:
                total_score += 0.3 * len(shared_holders)
                reasons.append(f"共享股东({len(shared_holders)})")

            # 策略3: 投资组合协同 (0.4)
            # 同一投资方投资的另一家企业
            for investor_id in target_investors:
                for u2, v2, d2 in graph.edges(data=True):
                    if (d2.get("_type") == "INVESTED"
                            and u2 == investor_id
                            and v2 == node_id
                            and node_id not in target_competitors):
                        total_score += 0.4
                        reasons.append("投资组合协同")
                        break

            # 策略4: 供应链上下游 (0.5)
            # 目标企业供应给 peer，或 peer 供应给目标企业
            if node_id not in target_competitors:
                for _, v, d in graph.edges(enterprise_id, data=True):
                    if d.get("_type") == "SUPPLIES" and v == node_id:
                        total_score += 0.5
                        reasons.append("供应链下游")
                        break
                for u, _, d in graph.edges(enterprise_id, data=True):
                    if d.get("_type") == "SUPPLIES" and u == node_id:
                        # Actually this is wrong direction, let's check properly
                        pass

            # 检查 peer 供应给目标企业
            for u, v, d in graph.edges(data=True):
                if (d.get("_type") == "SUPPLIES"
                        and u == node_id and v == enterprise_id
                        and node_id not in target_competitors):
                    total_score += 0.5
                    reasons.append("供应链上游")
                    break
                if (d.get("_type") == "SUPPLIES"
                        and u == enterprise_id and v == node_id
                        and node_id not in target_competitors):
                    # Already counted above, skip duplicate
                    if "供应链下游" not in reasons:
                        total_score += 0.5
                        reasons.append("供应链下游")
                        break

            if total_score > 0:
                scores[node_id] = {
                    "id": node_id,
                    "name": node_data.get("name", node_id),
                    "industry": node_data.get("industry", ""),
                    "score": round(total_score, 2),
                    "reason": reasons[0] if reasons else "",
                }

        sorted_results = sorted(
            scores.values(), key=lambda x: x["score"], reverse=True
        )
        return sorted_results[:k]

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def close(self) -> None:
        """关闭引擎，释放资源（Neo4j 连接等）"""
        if self._neo4j_client is not None:
            try:
                self._neo4j_client.close()
            except Exception as e:
                logger.warning("关闭 Neo4j 连接时出错: %s", e)
            self._neo4j_client = None
        self._graph = None
        self._mode = "closed"
        logger.info("GraphQueryEngine 已关闭")


# ===========================================================================
# 便利函数
# ===========================================================================


def create_engine(
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_user: str = "neo4j",
    neo4j_password: Optional[str] = None,
    graph_path: Optional[str] = None,
) -> GraphQueryEngine:
    """创建 GraphQueryEngine 实例的便利函数

    Args:
        neo4j_uri: Neo4j URI
        neo4j_user: Neo4j 用户名
        neo4j_password: Neo4j 密码
        graph_path: NetworkX 图 JSON 文件路径（降级模式）

    Returns:
        GraphQueryEngine 实例
    """
    return GraphQueryEngine(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        graph_path=graph_path,
    )
