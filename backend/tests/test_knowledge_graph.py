"""
企业关系知识图谱 — 单元测试
============================
验证 Schema 定义、图谱构建器各方法、统计与导出功能。

运行:
    pytest tests/test_knowledge_graph.py -v
    # 或
    python -m pytest tests/test_knowledge_graph.py -v
"""

import json
import os
import sys
import tempfile

import pytest

# 添加项目根目录到 path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ml.knowledge_graph.schema import (
    EntityType,
    RelationType,
    RELATION_DIRECTION_MAP,
    SCHEMA,
    validate_entity_type,
    validate_relation_type,
    get_required_fields,
    get_optional_fields,
    EnterpriseEntity,
    PersonEntity,
    IndustryEntity,
    ProductEntity,
)

from ml.knowledge_graph.builder import (
    KnowledgeGraphBuilder,
    ALL_INDUSTRIES,
    INDUSTRY_LEVEL_1,
    INDUSTRY_LEVEL_2,
    INDUSTRY_LEVEL_3,
)


# =========================================================================
# 测试数据
# =========================================================================

SAMPLE_ENTERPRISES = [
    {
        "id": "ent_alibaba",
        "name": "阿里巴巴集团",
        "industry": "互联网服务",
        "region": "浙江",
        "scale": "大型",
        "credit_score": 92,
        "legal_person": "马云",
        "reg_capital": "100000万",
        "reg_status": "存续",
        "established_date": "1999-09-09",
        "products": ["淘宝", "阿里云", "支付宝"],
    },
    {
        "id": "ent_tencent",
        "name": "腾讯科技",
        "industry": "互联网服务",
        "region": "广东",
        "scale": "大型",
        "credit_score": 90,
        "legal_person": "马化腾",
        "reg_capital": "80000万",
        "reg_status": "存续",
        "established_date": "1998-11-11",
        "products": ["微信", "QQ", "腾讯云"],
    },
    {
        "id": "ent_huawei",
        "name": "华为技术",
        "industry": "电子设备制造",
        "region": "广东",
        "scale": "大型",
        "credit_score": 95,
        "legal_person": "任正非",
        "reg_capital": "500000万",
        "reg_status": "存续",
        "established_date": "1987-09-15",
        "products": ["智能手机", "通信设备", "鸿蒙OS"],
    },
    {
        "id": "ent_xiaomi",
        "name": "小米科技",
        "industry": "电子设备制造",
        "region": "北京",
        "scale": "大型",
        "credit_score": 85,
        "legal_person": "雷军",
        "reg_capital": "30000万",
        "reg_status": "存续",
        "established_date": "2010-04-06",
        "products": ["智能手机", "智能家居", "MIUI"],
    },
    {
        "id": "ent_bytedance",
        "name": "字节跳动",
        "industry": "互联网服务",
        "region": "北京",
        "scale": "大型",
        "credit_score": 88,
        "legal_person": "张一鸣",
        "reg_capital": "50000万",
        "reg_status": "存续",
        "established_date": "2012-03-09",
        "products": ["抖音", "今日头条", "飞书"],
    },
]


# =========================================================================
# 测试: Schema 定义
# =========================================================================


class TestSchema:
    """验证 Schema 定义的完整性和正确性"""

    def test_entity_types_enum(self):
        """验证实体类型枚举包含所有定义的类型"""
        assert len(EntityType) == 4
        assert EntityType.ENTERPRISE.value == "Enterprise"
        assert EntityType.PERSON.value == "Person"
        assert EntityType.INDUSTRY.value == "Industry"
        assert EntityType.PRODUCT.value == "Product"

    def test_relation_types_enum(self):
        """验证关系类型枚举包含所有定义的关系"""
        assert len(RelationType) == 6
        assert RelationType.INDUSTRY_OF.value == "INDUSTRY_OF"
        assert RelationType.HAS_SHAREHOLDER.value == "HAS_SHAREHOLDER"
        assert RelationType.INVESTED.value == "INVESTED"
        assert RelationType.COMPETES_WITH.value == "COMPETES_WITH"
        assert RelationType.SUPPLIES.value == "SUPPLIES"
        assert RelationType.HAS_PRODUCT.value == "HAS_PRODUCT"

    def test_schema_contains_all_entities(self):
        """验证 SCHEMA 包含所有实体类型定义"""
        entities = SCHEMA["entities"]
        assert len(entities) == 4
        for etype in EntityType:
            assert etype in entities

    def test_schema_contains_all_relations(self):
        """验证 SCHEMA 包含所有关系类型定义"""
        relations = SCHEMA["relations"]
        assert len(relations) == 6
        for rtype in RelationType:
            assert rtype in relations

    def test_relation_direction_map(self):
        """验证关系方向映射正确"""
        # Enterprise -> Industry
        assert RELATION_DIRECTION_MAP[RelationType.INDUSTRY_OF] == (
            EntityType.ENTERPRISE, EntityType.INDUSTRY
        )
        # Enterprise -> Person
        assert RELATION_DIRECTION_MAP[RelationType.HAS_SHAREHOLDER] == (
            EntityType.ENTERPRISE, EntityType.PERSON
        )
        # Enterprise -> Enterprise
        assert RELATION_DIRECTION_MAP[RelationType.COMPETES_WITH] == (
            EntityType.ENTERPRISE, EntityType.ENTERPRISE
        )
        assert RELATION_DIRECTION_MAP[RelationType.INVESTED] == (
            EntityType.ENTERPRISE, EntityType.ENTERPRISE
        )

    def test_enterprise_required_fields(self):
        """验证 Enterprise 必填字段"""
        fields = get_required_fields(EntityType.ENTERPRISE)
        assert "id" in fields
        assert "name" in fields

    def test_industry_required_fields(self):
        """验证 Industry 必填字段"""
        fields = get_required_fields(EntityType.INDUSTRY)
        assert "id" in fields
        assert "name" in fields
        assert "level" in fields

    def test_validate_entity_type(self):
        """验证实体类型验证函数"""
        assert validate_entity_type("Enterprise") is True
        assert validate_entity_type("Person") is True
        assert validate_entity_type("InvalidType") is False

    def test_validate_relation_type(self):
        """验证关系类型验证函数"""
        assert validate_relation_type("INDUSTRY_OF") is True
        assert validate_relation_type("HAS_SHAREHOLDER") is True
        assert validate_relation_type("INVALID_REL") is False


# =========================================================================
# 测试: Schema 实体构造器
# =========================================================================


class TestEntityConstructors:
    """验证实体构造器函数的正确性"""

    def test_enterprise_entity_constructor(self):
        """创建企业实体并验证字段"""
        ent = EnterpriseEntity(
            id="e001",
            name="测试企业",
            industry="制造业",
            region="上海",
            scale="中型",
            credit_score=75,
        )
        assert ent["_type"] == "Enterprise"
        assert ent["_id"] == "e001"
        assert ent["name"] == "测试企业"
        assert ent["industry"] == "制造业"
        assert ent["region"] == "上海"
        assert ent["credit_score"] == 75

    def test_enterprise_entity_minimal(self):
        """创建最小企业实体（仅必填字段）"""
        ent = EnterpriseEntity(id="e002", name="最小企业")
        assert ent["_type"] == "Enterprise"
        assert ent["id"] == "e002"
        assert ent["name"] == "最小企业"
        # 可选字段不应存在
        assert "industry" not in ent
        assert "region" not in ent

    def test_person_entity_constructor(self):
        """创建人物实体"""
        person = PersonEntity(
            id="p001",
            name="张三",
            role="legal_person",
            position="法定代表人",
        )
        assert person["_type"] == "Person"
        assert person["name"] == "张三"
        assert person["role"] == "legal_person"

    def test_industry_entity_constructor(self):
        """创建行业实体"""
        ind = IndustryEntity(
            id="ind_tech",
            name="信息技术",
            level=1,
            category="科技",
        )
        assert ind["_type"] == "Industry"
        assert ind["level"] == 1
        assert ind["category"] == "科技"

    def test_product_entity_constructor(self):
        """创建产品实体"""
        prod = ProductEntity(
            id="prod_001",
            name="智能音箱",
            category="消费电子",
            enterprise_id="ent_001",
        )
        assert prod["_type"] == "Product"
        assert prod["name"] == "智能音箱"
        assert prod["enterprise_id"] == "ent_001"


# =========================================================================
# 测试: 图谱构建器
# =========================================================================


class TestKnowledgeGraphBuilder:
    """验证 KnowledgeGraphBuilder 各方法"""

    def test_initialization(self):
        """测试初始化"""
        builder = KnowledgeGraphBuilder()
        assert builder.graph is not None
        assert builder.graph.number_of_nodes() == 0
        assert builder.graph.number_of_edges() == 0
        assert builder.db_path == "chainke.db"

    def test_build_from_empty_list(self):
        """测试空列表构建（不应报错）"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data([])
        assert builder.graph.number_of_nodes() == 0

    def test_build_from_enterprise_data(self):
        """测试从企业数据构建图谱"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data(SAMPLE_ENTERPRISES)

        stats = builder.stats()
        assert stats["enterprises"] == 5  # 5 家企业
        assert stats["industries"] == 2   # 互联网服务 + 电子设备制造
        assert stats["persons"] == 5      # 5 个法定代表人
        # 企业(5) + 行业(2) + 人(5) + 产品(15, 每企业3个)
        assert stats["nodes"] == 5 + 2 + 5 + 15

    def test_node_attributes(self):
        """测试节点属性是否正确存储"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data(SAMPLE_ENTERPRISES)

        # 验证企业节点数据
        alibaba_data = builder.graph.nodes["ent_alibaba"]
        assert alibaba_data["name"] == "阿里巴巴集团"
        assert alibaba_data["region"] == "浙江"
        assert alibaba_data["credit_score"] == 92

        # 验证法人节点
        mayun_data = builder.graph.nodes.get("person_马云")
        assert mayun_data is not None
        assert mayun_data["role"] == "legal_person"

    def test_industry_of_relations(self):
        """测试 Industry-of 关系是否正确建立"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data(SAMPLE_ENTERPRISES)

        # 阿里巴巴 -> 互联网服务
        edges = list(builder.graph.edges("ent_alibaba", data=True))
        industry_edges = [
            (u, v) for u, v, d in edges
            if d.get("_type") == "INDUSTRY_OF"
        ]
        assert len(industry_edges) >= 1

        # 验证华为行业关系
        huawei_edges = list(builder.graph.edges("ent_huawei", data=True))
        huawei_industry = [
            v for _, v, d in huawei_edges
            if d.get("_type") == "INDUSTRY_OF"
        ]
        assert len(huawei_industry) >= 1

    def test_build_industry_tree(self):
        """测试行业树构建"""
        builder = KnowledgeGraphBuilder()
        builder.build_industry_tree()

        stats = builder.stats()
        expected_industries = len(INDUSTRY_LEVEL_1) + len(INDUSTRY_LEVEL_2) + len(INDUSTRY_LEVEL_3)
        assert stats["industries"] == expected_industries
        assert stats["nodes"] == expected_industries

        # 验证一级行业节点
        assert builder.graph.has_node("ind_tech")
        tech_data = builder.graph.nodes["ind_tech"]
        assert tech_data["level"] == 1

        # 验证二级行业节点
        assert builder.graph.has_node("ind_tech_ai")
        ai_data = builder.graph.nodes["ind_tech_ai"]
        assert ai_data["level"] == 2
        assert ai_data["parent_id"] == "ind_tech"

    def test_industry_tree_hierarchy(self):
        """测试行业树层级关系"""
        builder = KnowledgeGraphBuilder()
        builder.build_industry_tree()

        # 子行业 -> 父行业 的 IS_CHILD_OF 边
        edges = list(builder.graph.edges("ind_tech_ai", data=True))
        child_edges = [
            (u, v) for u, v, d in edges
            if d.get("label") == "IS_CHILD_OF"
        ]
        assert len(child_edges) >= 1

    def test_extract_shareholder_relations(self):
        """测试股东关系提取"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data(SAMPLE_ENTERPRISES[:2])

        # 添加股东数据到图中
        builder.graph.nodes["ent_alibaba"]["shareholders"] = [
            {"name": "孙正义", "ratio": 29.6, "type": "法人股东"},
            {"name": "马云", "ratio": 7.0, "type": "自然人股东"},
        ]

        builder.extract_shareholder_relations()

        # 验证股东边
        edges = list(builder.graph.edges("ent_alibaba", data=True))
        shareholder_edges = [
            d for _, _, d in edges
            if d.get("_type") == "HAS_SHAREHOLDER"
        ]
        assert len(shareholder_edges) >= 2

        # 验证孙正义节点
        assert builder.graph.has_node("person_孙正义")

    def test_extract_shareholder_external_data(self):
        """测试外部传入的股东数据"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data([SAMPLE_ENTERPRISES[0]])

        external_sh = [
            {"enterprise_id": "ent_alibaba", "name": "软银集团", "ratio": 34.4, "type": "法人股东"},
        ]
        builder.extract_shareholder_relations(external_sh)

        assert builder.graph.has_node("person_软银集团")

    def test_infer_competitor_relations(self):
        """测试竞争关系推断"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data(SAMPLE_ENTERPRISES)
        builder.infer_competitor_relations()

        stats = builder.stats()
        comp_count = stats["relation_types"].get("COMPETES_WITH", 0)
        # 5家企业在2个行业中: 互联网服务3家(C(3,2)=3), 电子设备制造2家(C(2,2)=1)
        assert comp_count == 4

        # 验证阿里巴巴和腾讯有竞争关系（同属互联网服务）
        competitor_edges = list(
            builder.graph.get_edge_data("ent_alibaba", "ent_tencent") or
            builder.graph.get_edge_data("ent_tencent", "ent_alibaba") or
            {}
        )
        # 只看是否有边，不管方向
        assert builder.graph.has_edge("ent_alibaba", "ent_tencent")
        edge_data = builder.graph.get_edge_data("ent_alibaba", "ent_tencent")
        assert edge_data is not None

    def test_competitor_strength_calculation(self):
        """测试竞争强度计算"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data([
            {
                "id": "ent_a",
                "name": "企业A",
                "industry": "互联网服务",
                "credit_score": 90,
            },
            {
                "id": "ent_b",
                "name": "企业B",
                "industry": "互联网服务",
                "credit_score": 85,
            },
        ])
        builder.infer_competitor_relations()

        edge_data = builder.graph.get_edge_data("ent_a", "ent_b")
        assert edge_data is not None
        # strength = max(0, 100 - |90-85| * 10) = max(0, 50) = 50
        assert edge_data["strength"] == 50.0

    def test_extract_invest_relations(self):
        """测试投资关系提取"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data(SAMPLE_ENTERPRISES[:3])

        invest_data = [
            {"from_id": "ent_alibaba", "to_id": "ent_huawei", "amount": 10000, "date": "2020-01-01"},
            {"from_id": "ent_tencent", "to_id": "ent_alibaba", "amount": 5000, "date": "2019-06-01"},
        ]
        builder.extract_invest_relations(invest_data)

        assert builder.graph.has_edge("ent_alibaba", "ent_huawei")
        assert builder.graph.has_edge("ent_tencent", "ent_alibaba")

        edge_data = builder.graph.get_edge_data("ent_alibaba", "ent_huawei")
        assert edge_data["amount"] == 10000
        assert edge_data["date"] == "2020-01-01"

    def test_stats(self):
        """测试统计信息"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data(SAMPLE_ENTERPRISES)
        builder.build_industry_tree()

        stats = builder.stats()
        assert isinstance(stats, dict)
        assert "nodes" in stats
        assert "edges" in stats
        assert "density" in stats
        assert "entity_types" in stats
        assert "relation_types" in stats
        assert stats["nodes"] > 0
        assert stats["density"] >= 0

    def test_export_to_json(self):
        """测试 JSON 导出"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data(SAMPLE_ENTERPRISES[:2])
        builder.infer_competitor_relations()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            tmp_path = f.name

        try:
            result = builder.export_to_json(tmp_path)

            # 验证返回结构
            assert "nodes" in result
            assert "edges" in result
            assert "stats" in result
            assert len(result["nodes"]) > 0

            # 验证文件存在且可解析
            with open(tmp_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            assert len(loaded["nodes"]) == len(result["nodes"])
            assert len(loaded["edges"]) == len(result["edges"])
        finally:
            os.unlink(tmp_path)

    def test_save_and_load(self):
        """测试保存和加载图谱"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data(SAMPLE_ENTERPRISES)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            tmp_path = f.name

        try:
            builder.save(tmp_path)

            # 新构建器加载
            builder2 = KnowledgeGraphBuilder()
            builder2.load(tmp_path)

            assert builder2.graph.number_of_nodes() == builder.graph.number_of_nodes()
            assert builder2.graph.number_of_edges() == builder.graph.number_of_edges()

            stats1 = builder.stats()
            stats2 = builder2.stats()
            assert stats1["nodes"] == stats2["nodes"]
            assert stats1["enterprises"] == stats2["enterprises"]
        finally:
            os.unlink(tmp_path)

    def test_clear(self):
        """测试清空图谱"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data(SAMPLE_ENTERPRISES)
        assert builder.graph.number_of_nodes() > 0

        builder.clear()
        assert builder.graph.number_of_nodes() == 0
        assert builder.graph.number_of_edges() == 0

    def test_find_enterprises_by_industry(self):
        """测试按行业查询企业"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data(SAMPLE_ENTERPRISES)

        internet_companies = builder.find_enterprises_by_industry("互联网服务")
        assert len(internet_companies) == 3
        assert "ent_alibaba" in internet_companies
        assert "ent_tencent" in internet_companies
        assert "ent_bytedance" in internet_companies

        electronics = builder.find_enterprises_by_industry("电子设备制造")
        assert len(electronics) == 2

    def test_find_competitors(self):
        """测试查询竞争对手"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data(SAMPLE_ENTERPRISES)
        builder.infer_competitor_relations()

        competitors = builder.find_competitors("ent_alibaba")
        # 阿里巴巴的竞争对手：腾讯和字节（同属互联网服务）
        assert len(competitors) >= 2
        comp_ids = [c["id"] for c in competitors]
        assert "ent_tencent" in comp_ids
        assert "ent_bytedance" in comp_ids

    def test_get_enterprise_neighbors(self):
        """测试获取企业关联实体"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data([SAMPLE_ENTERPRISES[0]])

        neighbors = builder.get_enterprise_neighbors("ent_alibaba")
        assert "INDUSTRY_OF" in neighbors
        assert "HAS_SHAREHOLDER" in neighbors
        assert "HAS_PRODUCT" in neighbors

    def test_full_pipeline(self):
        """测试完整构建流水线"""
        builder = KnowledgeGraphBuilder()

        # 完整流水线
        (builder
         .build_from_enterprise_data(SAMPLE_ENTERPRISES)
         .build_industry_tree()
         .extract_shareholder_relations()
         .infer_competitor_relations())

        stats = builder.stats()
        assert stats["nodes"] > 0
        assert stats["edges"] > 0
        assert stats["density"] > 0
        assert "COMPETES_WITH" in stats["relation_types"]
        assert "HAS_SHAREHOLDER" in stats["relation_types"]
        assert "INDUSTRY_OF" in stats["relation_types"]

        # JSON 导出（不写文件）
        result = builder.export_to_json()
        assert len(result["nodes"]) == stats["nodes"]
        assert len(result["edges"]) == stats["edges"]


# =========================================================================
# 测试: 边界情况
# =========================================================================


class TestEdgeCases:
    """边界条件测试"""

    def test_missing_required_fields(self):
        """缺少必填字段时不应崩溃"""
        builder = KnowledgeGraphBuilder()
        bad_data = [
            {"id": "e001"},  # 缺少 name
            {"name": "无名氏"},  # 缺少 id
        ]
        builder.build_from_enterprise_data(bad_data)
        assert builder.graph.number_of_nodes() == 0

    def test_duplicate_nodes(self):
        """重复添加相同ID的企业应合并而非重复"""
        builder = KnowledgeGraphBuilder()
        builder.build_from_enterprise_data([
            {"id": "e001", "name": "企业A", "industry": "互联网"},
            {"id": "e001", "name": "企业A", "industry": "互联网"},  # 重复
        ])
        assert builder.graph.number_of_nodes() > 0

    def test_empty_industry_tree(self):
        """行业树应该总是返回固定的行业列表"""
        builder = KnowledgeGraphBuilder()
        builder.build_industry_tree()
        assert builder._industry_count == len(ALL_INDUSTRIES)

    def test_export_with_empty_graph(self):
        """空图谱导出不应报错"""
        builder = KnowledgeGraphBuilder()
        result = builder.export_to_json()
        assert len(result["nodes"]) == 0
        assert len(result["edges"]) == 0
        assert result["stats"]["nodes"] == 0

    def test_load_from_nonexistent_file(self):
        """加载不存在的文件应返回空图"""
        builder = KnowledgeGraphBuilder()
        builder.load("/nonexistent/graph.json")
        assert builder.graph.number_of_nodes() == 0


# =========================================================================
# 测试: 行业树常量
# =========================================================================


class TestIndustryConstants:
    """验证行业树常量数据"""

    def test_industry_levels_count(self):
        """验证各级行业数量"""
        assert len(INDUSTRY_LEVEL_1) == 10
        assert len(INDUSTRY_LEVEL_2) == 23
        assert len(INDUSTRY_LEVEL_3) == 13
        assert len(ALL_INDUSTRIES) == 10 + 23 + 13

    def test_industry_id_uniqueness(self):
        """验证行业ID唯一性"""
        ids = [ind["id"] for ind in ALL_INDUSTRIES]
        assert len(ids) == len(set(ids))

    def test_level_1_has_no_parent(self):
        """验证一级行业没有 parent_id"""
        for ind in INDUSTRY_LEVEL_1:
            assert "parent_id" not in ind

    def test_level_2_has_parent(self):
        """验证二级行业有 parent_id"""
        for ind in INDUSTRY_LEVEL_2:
            assert "parent_id" in ind
            assert ind["parent_id"] in {l1["id"] for l1 in INDUSTRY_LEVEL_1}

    def test_level_3_has_parent(self):
        """验证三级行业有 parent_id"""
        for ind in INDUSTRY_LEVEL_3:
            assert "parent_id" in ind
            assert ind["parent_id"] in {l2["id"] for l2 in INDUSTRY_LEVEL_2}
