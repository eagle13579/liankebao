"""
Neo4j 知识图谱迁移 + Cypher 查询测试
=====================================
测试覆盖:
1. 连接初始化 / 降级检测 (3)
2. Schema 约束 / 索引 (2)
3. 节点迁移 (2)
4. 关系迁移 (1)
5. 查询: find_competitors (1)
6. 查询: find_path (1)
7. 查询: get_enterprise_ego (1)
8. 查询: recommend_partners (1)
9. 清空图谱 / 完整流程 (1)
---
总计 13 个测试用例，全部可在无 Neo4j 实例时运行（降级模式）。
"""

import os
import sys
import unittest
from typing import Any

# ---------------------------------------------------------------------------
# 将 backend 加入模块搜索路径
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

try:
    import networkx as nx
except ImportError:
    nx = None  # type: ignore[assignment]

from ml.knowledge_graph.neo4j_client import (
    Neo4jClient,
    Neo4jSchema,
    HAS_NEO4J,
    _get_node_label,
    _get_relation_type,
    _filter_properties,
    _sanitize_value,
)
from ml.knowledge_graph.schema import (
    EntityType,
    RelationType,
    EnterpriseEntity,
    PersonEntity,
    IndustryEntity,
    ProductEntity,
)


# ---------------------------------------------------------------------------
# Helper: 构建一个测试用的 NetworkX 图
# ---------------------------------------------------------------------------


def build_test_graph() -> Any:
    """构建一个小型 NetworkX 测试图

    包含 2 家企业、1 个人、1 个行业、竞争和股东关系
    """
    if nx is None:
        raise RuntimeError("需要 networkx 库: pip install networkx")
    G = nx.DiGraph()

    # 节点: 企业
    G.add_node(
        "e001",
        **EnterpriseEntity(
            id="e001",
            name="阿里巴巴",
            industry="互联网服务",
            scale="大型",
            credit_score=92,
        ),
    )
    G.add_node(
        "e002",
        **EnterpriseEntity(
            id="e002",
            name="京东",
            industry="互联网服务",
            scale="大型",
            credit_score=88,
        ),
    )
    G.add_node(
        "e003",
        **EnterpriseEntity(
            id="e003",
            name="腾讯",
            industry="互联网服务",
            scale="大型",
            credit_score=90,
        ),
    )
    G.add_node(
        "e004",
        **EnterpriseEntity(
            id="e004",
            name="拼多多",
            industry="电商",
            scale="大型",
            credit_score=78,
        ),
    )

    # 节点: 个人
    G.add_node(
        "person_马云",
        **PersonEntity(id="person_马云", name="马云", role="founder", gender="男"),
    )
    G.add_node(
        "person_刘强东",
        **PersonEntity(
            id="person_刘强东", name="刘强东", role="founder", gender="男"
        ),
    )
    G.add_node(
        "person_张一鸣",
        **PersonEntity(id="person_张一鸣", name="张一鸣", role="investor", gender="男"),
    )

    # 节点: 行业
    G.add_node(
        "ind_internet",
        **IndustryEntity(id="ind_internet", name="互联网服务", level=2, category="信息技术"),
    )
    G.add_node(
        "ind_ecommerce",
        **IndustryEntity(id="ind_ecommerce", name="电商", level=3, category="信息技术"),
    )

    # 关系: INDUSTRY_OF
    G.add_edge(
        "e001", "ind_internet",
        _type=RelationType.INDUSTRY_OF.value,
        label=RelationType.INDUSTRY_OF.value,
    )
    G.add_edge(
        "e002", "ind_internet",
        _type=RelationType.INDUSTRY_OF.value,
        label=RelationType.INDUSTRY_OF.value,
    )
    G.add_edge(
        "e003", "ind_internet",
        _type=RelationType.INDUSTRY_OF.value,
        label=RelationType.INDUSTRY_OF.value,
    )
    G.add_edge(
        "e004", "ind_ecommerce",
        _type=RelationType.INDUSTRY_OF.value,
        label=RelationType.INDUSTRY_OF.value,
    )

    # 关系: COMPETES_WITH (同行业竞争)
    G.add_edge(
        "e001", "e002",
        _type=RelationType.COMPETES_WITH.value,
        label=RelationType.COMPETES_WITH.value,
        strength=80.0,
    )
    G.add_edge(
        "e001", "e003",
        _type=RelationType.COMPETES_WITH.value,
        label=RelationType.COMPETES_WITH.value,
        strength=90.0,
    )
    G.add_edge(
        "e002", "e003",
        _type=RelationType.COMPETES_WITH.value,
        label=RelationType.COMPETES_WITH.value,
        strength=75.0,
    )

    # 关系: HAS_SHAREHOLDER
    G.add_edge(
        "e001", "person_马云",
        _type=RelationType.HAS_SHAREHOLDER.value,
        label=RelationType.HAS_SHAREHOLDER.value,
        ratio=4.5,
        type="founder",
    )
    G.add_edge(
        "e002", "person_刘强东",
        _type=RelationType.HAS_SHAREHOLDER.value,
        label=RelationType.HAS_SHAREHOLDER.value,
        ratio=12.7,
        type="founder",
    )
    # 张一鸣同时是 e001 和 e004 的股东（共享股东 → 推荐触发）
    G.add_edge(
        "e001", "person_张一鸣",
        _type=RelationType.HAS_SHAREHOLDER.value,
        label=RelationType.HAS_SHAREHOLDER.value,
        ratio=2.0,
        type="investor",
    )
    G.add_edge(
        "e004", "person_张一鸣",
        _type=RelationType.HAS_SHAREHOLDER.value,
        label=RelationType.HAS_SHAREHOLDER.value,
        ratio=3.5,
        type="investor",
    )

    # 关系: INVESTED (投资关系 — 用于合作伙伴推荐测试)
    G.add_edge(
        "e003", "e004",
        _type=RelationType.INVESTED.value,
        label=RelationType.INVESTED.value,
        amount=10000,
        date="2020-06-01",
    )

    return G


class TestNeo4jClient(unittest.TestCase):
    """Neo4j 客户端测试套件（全部在降级模式下运行）"""

    def setUp(self):
        """每个测试前创建新的客户端和测试图"""
        self.client = Neo4jClient(
            uri="bolt://localhost:7687",
            user="neo4j",
            password=None,  # 无密码 → 自动降级
        )
        self.test_graph = build_test_graph()
        self.client.set_fallback_graph(self.test_graph)

    def tearDown(self):
        """每个测试后清理"""
        self.client.close()

    # --------------------------------------------------------------
    # 1. 连接初始化 / 降级检测
    # --------------------------------------------------------------

    def test_init_defaults(self):
        """测试：默认参数从环境变量读取"""
        client = Neo4jClient()
        self.assertEqual(client.uri, os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
        self.assertEqual(client.user, os.environ.get("NEO4J_USER", "neo4j"))
        # 密码可能为 None，取决于环境变量
        self.assertIn(client.mode, ("init", "networkx"))

    def test_connect_without_password_degradation(self):
        """测试：无密码时自动降级为 NetworkX"""
        result = self.client.connect()
        self.assertFalse(result)  # 降级
        self.assertEqual(self.client.mode, "networkx")
        self.assertFalse(self.client.is_connected())

    def test_is_connected_returns_false_when_degraded(self):
        """测试：降级模式下 is_connected 返回 False"""
        self.client.connect()
        self.assertFalse(self.client.is_connected())

    # --------------------------------------------------------------
    # 2. Schema 约束 / 索引
    # --------------------------------------------------------------

    def test_create_constraints_skipped_when_degraded(self):
        """测试：降级模式下创建约束返回 0"""
        self.client.connect()
        schema = Neo4jSchema(self.client)
        count = schema.create_constraints()
        self.assertEqual(count, 0)

    def test_create_indexes_skipped_when_degraded(self):
        """测试：降级模式下创建索引返回 0"""
        self.client.connect()
        schema = Neo4jSchema(self.client)
        count = schema.create_indexes()
        self.assertEqual(count, 0)

    # --------------------------------------------------------------
    # 3. 数据迁移
    # --------------------------------------------------------------

    def test_migrate_from_networkx_skipped_when_degraded(self):
        """测试：降级模式下迁移返回空统计"""
        self.client.connect()
        # 需要先连接让 mode 变成 networkx
        stats = self.client.migrate_from_networkx(self.test_graph)
        self.assertEqual(stats["nodes_migrated"], 0)
        self.assertEqual(stats["edges_migrated"], 0)
        self.assertEqual(stats["schema_created"], 0)

    def test_get_node_label(self):
        """测试：从节点数据提取 Neo4j 标签"""
        node_data = dict(self.test_graph.nodes["e001"])
        label = _get_node_label(node_data)
        self.assertEqual(label, "Enterprise")

        node_data2 = dict(self.test_graph.nodes["person_马云"])
        label2 = _get_node_label(node_data2)
        self.assertEqual(label2, "Person")

        node_data3 = dict(self.test_graph.nodes["ind_internet"])
        label3 = _get_node_label(node_data3)
        self.assertEqual(label3, "Industry")

    # --------------------------------------------------------------
    # 4. 关系迁移辅助
    # --------------------------------------------------------------

    def test_get_relation_type(self):
        """测试：从边数据提取 Neo4j 关系类型"""
        edge_data = self.test_graph.get_edge_data("e001", "e002")
        rel_type = _get_relation_type(edge_data)
        self.assertEqual(rel_type, "COMPETES_WITH")

        edge_data2 = self.test_graph.get_edge_data("e001", "person_马云")
        rel_type2 = _get_relation_type(edge_data2)
        self.assertEqual(rel_type2, "HAS_SHAREHOLDER")

    def test_filter_properties(self):
        """测试：过滤内部属性"""
        data = {"_type": "Enterprise", "_id": "e001", "name": "阿里巴巴", "industry": "互联网"}
        filtered = _filter_properties(data)
        self.assertNotIn("_type", filtered)
        self.assertNotIn("_id", filtered)
        self.assertIn("name", filtered)
        self.assertIn("industry", filtered)

    def test_sanitize_value(self):
        """测试：值类型清洗"""
        self.assertCountEqual(_sanitize_value({"a", "b"}), ["a", "b"])
        self.assertEqual(_sanitize_value((1, 2)), [1, 2])
        self.assertEqual(_sanitize_value("hello"), "hello")
        self.assertEqual(_sanitize_value(42), 42)
        self.assertEqual(_sanitize_value({"nested": {1, 2}}), {"nested": [1, 2]})

    # --------------------------------------------------------------
    # 5. Cypher 查询（均使用 NetworkX 降级）
    # --------------------------------------------------------------

    def test_find_competitors(self):
        """测试：查询同行业竞争对手"""
        self.client.connect()
        competitors = self.client.find_competitors("e001", limit=5)

        self.assertGreaterEqual(len(competitors), 2)
        # 阿里巴巴的竞争对手应该是京东 (e002) 和腾讯 (e003)
        comp_ids = {c["id"] for c in competitors}
        self.assertIn("e002", comp_ids)
        self.assertIn("e003", comp_ids)

        # 按强度降序
        for i in range(len(competitors) - 1):
            self.assertGreaterEqual(
                competitors[i]["strength"], competitors[i + 1]["strength"]
            )

        # 每个竞争对手都应该有 name 和 strength
        for c in competitors:
            self.assertIn("name", c)
            self.assertIn("strength", c)

    def test_find_competitors_limit(self):
        """测试：竞争对手查询 limit 参数"""
        self.client.connect()
        competitors = self.client.find_competitors("e001", limit=1)
        self.assertEqual(len(competitors), 1)

    def test_find_competitors_no_competitors(self):
        """测试：无竞争对手的企业返回空列表"""
        self.client.connect()
        # e004 (拼多多) 没有竞争对手
        competitors = self.client.find_competitors("e004", limit=5)
        self.assertEqual(len(competitors), 0)

    def test_find_path(self):
        """测试：最短路径查询"""
        self.client.connect()
        result = self.client.find_path("e001", "person_刘强东", max_depth=4)

        self.assertGreater(len(result), 0)
        path = result[0]
        self.assertIn("nodes", path)
        self.assertIn("relationships", path)

        # 路径应该包含 e001 -> e002 (COMPETES_WITH) -> person_刘强东 (HAS_SHAREHOLDER)
        node_ids = [n["id"] for n in path["nodes"]]
        self.assertIn("e001", node_ids)
        self.assertIn("e002", node_ids)
        self.assertIn("person_刘强东", node_ids)

    def test_find_path_no_path(self):
        """测试：不存在的路径返回空列表"""
        self.client.connect()
        # 不存在的节点
        result = self.client.find_path("e001", "not_a_node", max_depth=4)
        self.assertEqual(len(result), 0)

    def test_find_path_same_node(self):
        """测试：起点等于终点"""
        self.client.connect()
        result = self.client.find_path("e001", "e001", max_depth=4)
        self.assertGreater(len(result), 0)

    def test_get_enterprise_ego(self):
        """测试：企业关联子图查询"""
        self.client.connect()
        result = self.client.get_enterprise_ego("e001", depth=2)

        self.assertIn("nodes", result)
        self.assertIn("edges", result)
        self.assertIn("center", result)
        self.assertEqual(result["center"], "e001")

        # 至少包含自身
        self.assertGreater(len(result["nodes"]), 0)
        node_ids = {n["id"] for n in result["nodes"]}
        self.assertIn("e001", node_ids)

    def test_get_enterprise_ego_no_enterprise(self):
        """测试：不存在的企业返回空子图"""
        self.client.connect()
        result = self.client.get_enterprise_ego("not_a_node", depth=2)
        self.assertEqual(len(result["nodes"]), 0)
        self.assertEqual(len(result["edges"]), 0)
        self.assertEqual(result["center"], "not_a_node")

    def test_recommend_partners(self):
        """测试：合作伙伴推荐"""
        self.client.connect()
        # 阿里巴巴 (e001) 的推荐
        partners = self.client.recommend_partners("e001", limit=5)

        self.assertGreater(len(partners), 0)
        for p in partners:
            self.assertIn("id", p)
            self.assertIn("name", p)
            self.assertIn("score", p)
            self.assertIn("reason", p)
            # 不会推荐自己
            self.assertNotEqual(p["id"], "e001")
            # 不会推荐竞争对手
            self.assertNotIn(p["id"], {"e002", "e003"})

        # 按评分降序
        for i in range(len(partners) - 1):
            self.assertGreaterEqual(partners[i]["score"], partners[i + 1]["score"])

    # --------------------------------------------------------------
    # 6. 完整流程
    # --------------------------------------------------------------

    def test_full_migration_flow_degraded(self):
        """测试：完整迁移流程（降级模式 — 全部安全跳过）"""
        self.client.connect()

        # Schema
        schema = Neo4jSchema(self.client)
        self.assertEqual(schema.create_constraints(), 0)
        self.assertEqual(schema.create_indexes(), 0)
        self.assertEqual(schema.drop_all(), 0)

        # 迁移
        stats = self.client.migrate_from_networkx(self.test_graph)
        self.assertEqual(stats["nodes_migrated"], 0)
        self.assertEqual(stats["edges_migrated"], 0)

        # 查询（降级后应正常返回）
        comps = self.client.find_competitors("e001", limit=3)
        self.assertGreater(len(comps), 0)

        path = self.client.find_path("e001", "person_马云", max_depth=2)
        self.assertGreater(len(path), 0)


# ---------------------------------------------------------------------------
# 运行测试
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 确保 environment variables 不会被干扰
    if "NEO4J_PASSWORD" in os.environ:
        del os.environ["NEO4J_PASSWORD"]

    unittest.main(verbosity=2)
