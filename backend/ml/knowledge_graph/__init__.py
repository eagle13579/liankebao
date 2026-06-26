"""
链客宝 — 企业关系知识图谱模块
==============================
基于企业数据（天眼查 + 企查查）构建结构化知识图谱，
支持企业关联分析、竞争关系推断、产业链追踪等场景。

能力矩阵：
┌──────────────────────┬─────────────────────────────────────────────┐
│ 模块                  │ 能力                                        │
├──────────────────────┼─────────────────────────────────────────────┤
│ schema               │ 图谱Schema：实体类型定义 + 关系类型定义     │
│ builder              │ 图谱构建器：从企业数据构建 NetworkX 图      │
│ neo4j_client         │ Neo4j 迁移 + Cypher 查询（自动降级）       │
└──────────────────────┴─────────────────────────────────────────────┘

快速开始:
    from backend.ml.knowledge_graph import KnowledgeGraphBuilder

    builder = KnowledgeGraphBuilder()
    builder.build_from_enterprise_data(enterprise_list)
    builder.build_industry_tree()
    builder.extract_shareholder_relations()
    builder.infer_competitor_relations()
    print(builder.stats())
    builder.export_to_json("graph.json")

Neo4j 迁移（有 Neo4j 实例时）:
    from backend.ml.knowledge_graph import Neo4jClient

    client = Neo4jClient()
    client.connect()
    client.migrate_from_networkx(builder.graph)
    result = client.find_competitors("e001")
    client.close()
"""

from .schema import (
    EntityType,
    RelationType,
    EntityDef,
    RelationDef,
    EnterpriseEntity,
    PersonEntity,
    IndustryEntity,
    ProductEntity,
    SHAREHOLDER_REL,
    INVESTED_REL,
    COMPETES_REL,
    SUPPLIES_REL,
    INDUSTRY_REL,
    PRODUCT_REL,
    SCHEMA,
)

from .builder import KnowledgeGraphBuilder, create_builder

from .neo4j_client import Neo4jClient, Neo4jSchema, HAS_NEO4J

__all__ = [
    # schema
    "EntityType",
    "RelationType",
    "EntityDef",
    "RelationDef",
    "EnterpriseEntity",
    "PersonEntity",
    "IndustryEntity",
    "ProductEntity",
    "SHAREHOLDER_REL",
    "INVESTED_REL",
    "COMPETES_REL",
    "SUPPLIES_REL",
    "INDUSTRY_REL",
    "PRODUCT_REL",
    "SCHEMA",
    # builder
    "KnowledgeGraphBuilder",
    "create_builder",
    # neo4j
    "Neo4jClient",
    "Neo4jSchema",
    "HAS_NEO4J",
]

__version__ = "1.0.0"
__author__ = "鴒䳩 (市场部, 关系图谱/数据建模)"
