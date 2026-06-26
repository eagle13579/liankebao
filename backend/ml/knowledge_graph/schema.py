"""
企业关系知识图谱 — Schema（图谱数据模型）
=========================================
定义实体类型、关系类型、属性约束，形成统一的数据建模语言。

设计原则：
1. 所有实体/关系使用枚举 + 数据类，避免 magic string
2. 每个实体定义 required_fields（构建时必须填充）和 optional_fields
3. Schema 本身是纯数据，不依赖 NetworkX
4. 关系定义中标注了方向和语义约束

用法:
    from backend.ml.knowledge_graph.schema import (
        EntityType, RelationType, SCHEMA,
        EnterpriseEntity, PersonEntity,
    )

    # 创建实体
    ent = EnterpriseEntity(id="e001", name="阿里巴巴")

    # 校验必填字段
    if ent.validate():
        print("实体合规")
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 实体类型枚举
# ---------------------------------------------------------------------------


class EntityType(str, Enum):
    """知识图谱实体类型"""

    ENTERPRISE = "Enterprise"  # 企业
    PERSON = "Person"  # 自然人（法人/股东/高管）
    INDUSTRY = "Industry"  # 行业分类
    PRODUCT = "Product"  # 产品/服务

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"EntityType.{self.name}"


# ---------------------------------------------------------------------------
# 关系类型枚举
# ---------------------------------------------------------------------------


class RelationType(str, Enum):
    """知识图谱关系类型（边标签）"""

    # (Enterprise)-[:INDUSTRY_OF]->(Industry)
    INDUSTRY_OF = "INDUSTRY_OF"
    # (Enterprise)-[:HAS_SHAREHOLDER {ratio, type}]->(Person)
    HAS_SHAREHOLDER = "HAS_SHAREHOLDER"
    # (Enterprise)-[:INVESTED {amount, date}]->(Enterprise)
    INVESTED = "INVESTED"
    # (Enterprise)-[:COMPETES_WITH {strength}]->(Enterprise)
    COMPETES_WITH = "COMPETES_WITH"
    # (Enterprise)-[:SUPPLIES {category}]->(Enterprise)
    SUPPLIES = "SUPPLIES"
    # (Enterprise)-[:HAS_PRODUCT]->(Product)
    HAS_PRODUCT = "HAS_PRODUCT"

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"RelationType.{self.name}"


# ---------------------------------------------------------------------------
# 关系方向约束
# ---------------------------------------------------------------------------

# 每个关系的 (source_type, target_type) 合法配对
RELATION_DIRECTION_MAP: dict[RelationType, tuple[EntityType, EntityType]] = {
    RelationType.INDUSTRY_OF: (EntityType.ENTERPRISE, EntityType.INDUSTRY),
    RelationType.HAS_SHAREHOLDER: (EntityType.ENTERPRISE, EntityType.PERSON),
    RelationType.INVESTED: (EntityType.ENTERPRISE, EntityType.ENTERPRISE),
    RelationType.COMPETES_WITH: (EntityType.ENTERPRISE, EntityType.ENTERPRISE),
    RelationType.SUPPLIES: (EntityType.ENTERPRISE, EntityType.ENTERPRISE),
    RelationType.HAS_PRODUCT: (EntityType.ENTERPRISE, EntityType.PRODUCT),
}


# ---------------------------------------------------------------------------
# 关系属性定义
# ---------------------------------------------------------------------------


@dataclass
class RelationDef:
    """关系定义：属性约束+语义描述"""

    label: str
    source_type: EntityType
    target_type: EntityType
    required_props: list[str] = field(default_factory=list)
    optional_props: list[str] = field(default_factory=list)
    description: str = ""


# ---------------------------------------------------------------------------
# 实体定义（每个实体类型的必填/可选字段）
# ---------------------------------------------------------------------------


@dataclass
class EntityDef:
    """实体类型定义：必填字段 + 可选字段"""

    type: EntityType
    required_fields: list[str] = field(default_factory=list)
    optional_fields: list[str] = field(default_factory=list)
    description: str = ""


# ---------------------------------------------------------------------------
# Schema 常量（集中配置）
# ---------------------------------------------------------------------------

# --- 实体字段定义 ---

ENTERPRISE_ENTITY = EntityDef(
    type=EntityType.ENTERPRISE,
    required_fields=["id", "name"],
    optional_fields=[
        "industry",       # 所属行业名称
        "region",         # 注册地区
        "scale",          # 企业规模（大型/中型/小型/微型）
        "credit_score",   # 信用评分（0-100）
        "legal_person",   # 法定代表人
        "reg_capital",    # 注册资本
        "reg_status",     # 经营状态
        "established",    # 成立日期
    ],
    description="企业法人实体",
)

PERSON_ENTITY = EntityDef(
    type=EntityType.PERSON,
    required_fields=["id", "name"],
    optional_fields=[
        "role",           # 角色：法人/股东/高管/董事/监事
        "gender",
        "position",       # 具体职务
    ],
    description="自然人实体（法人/股东/高管等）",
)

INDUSTRY_ENTITY = EntityDef(
    type=EntityType.INDUSTRY,
    required_fields=["id", "name", "level"],
    optional_fields=[
        "category",       # 大类名称（如：制造业、信息技术）
        "parent_id",      # 上级行业ID（用于构建行业树）
    ],
    description="行业分类节点（三级分类体系）",
)

PRODUCT_ENTITY = EntityDef(
    type=EntityType.PRODUCT,
    required_fields=["id", "name"],
    optional_fields=[
        "category",       # 产品类别
        "enterprise_id",  # 所属企业ID
        "description",    # 产品描述
    ],
    description="产品/服务实体",
)

# --- 关系定义 ---

SHAREHOLDER_REL = RelationDef(
    label=RelationType.HAS_SHAREHOLDER.value,
    source_type=EntityType.ENTERPRISE,
    target_type=EntityType.PERSON,
    required_props=["ratio"],
    optional_props=["type", "amount"],
    description="企业股东关系（含持股比例）",
)

INVESTED_REL = RelationDef(
    label=RelationType.INVESTED.value,
    source_type=EntityType.ENTERPRISE,
    target_type=EntityType.ENTERPRISE,
    required_props=["amount"],
    optional_props=["date", "ratio"],
    description="企业对外投资关系",
)

COMPETES_REL = RelationDef(
    label=RelationType.COMPETES_WITH.value,
    source_type=EntityType.ENTERPRISE,
    target_type=EntityType.ENTERPRISE,
    required_props=["strength"],
    optional_props=[],
    description="竞争关系（根据同行业+同规模推断）",
)

SUPPLIES_REL = RelationDef(
    label=RelationType.SUPPLIES.value,
    source_type=EntityType.ENTERPRISE,
    target_type=EntityType.ENTERPRISE,
    required_props=["category"],
    optional_props=[],
    description="供应链上下游关系",
)

INDUSTRY_REL = RelationDef(
    label=RelationType.INDUSTRY_OF.value,
    source_type=EntityType.ENTERPRISE,
    target_type=EntityType.INDUSTRY,
    required_props=[],
    optional_props=[],
    description="企业所属行业关系",
)

PRODUCT_REL = RelationDef(
    label=RelationType.HAS_PRODUCT.value,
    source_type=EntityType.ENTERPRISE,
    target_type=EntityType.PRODUCT,
    required_props=[],
    optional_props=[],
    description="企业拥有产品/服务关系",
)

# --- 完整 Schema 聚合 ---

SCHEMA = {
    "entities": {
        EntityType.ENTERPRISE: ENTERPRISE_ENTITY,
        EntityType.PERSON: PERSON_ENTITY,
        EntityType.INDUSTRY: INDUSTRY_ENTITY,
        EntityType.PRODUCT: PRODUCT_ENTITY,
    },
    "relations": {
        RelationType.INDUSTRY_OF: INDUSTRY_REL,
        RelationType.HAS_SHAREHOLDER: SHAREHOLDER_REL,
        RelationType.INVESTED: INVESTED_REL,
        RelationType.COMPETES_WITH: COMPETES_REL,
        RelationType.SUPPLIES: SUPPLIES_REL,
        RelationType.HAS_PRODUCT: PRODUCT_REL,
    },
    "version": "1.0.0",
}


# ---------------------------------------------------------------------------
# 辅助验证函数
# ---------------------------------------------------------------------------


def validate_entity_type(entity_type: str) -> bool:
    """检查字符串是否为合法实体类型"""
    try:
        EntityType(entity_type)
        return True
    except ValueError:
        return False


def validate_relation_type(relation_type: str) -> bool:
    """检查字符串是否为合法关系类型"""
    try:
        RelationType(relation_type)
        return True
    except ValueError:
        return False


def get_required_fields(entity_type: EntityType) -> list[str]:
    """获取指定实体类型的必填字段列表"""
    ent_def = SCHEMA["entities"].get(entity_type)
    if ent_def:
        return ent_def.required_fields
    return []


def get_optional_fields(entity_type: EntityType) -> list[str]:
    """获取指定实体类型的可选字段列表"""
    ent_def = SCHEMA["entities"].get(entity_type)
    if ent_def:
        return ent_def.optional_fields
    return []


# ---------------------------------------------------------------------------
# 便捷实体构造器（用于创建合规的实体字典）
# ---------------------------------------------------------------------------


def EnterpriseEntity(
    id: str,
    name: str,
    industry: Optional[str] = None,
    region: Optional[str] = None,
    scale: Optional[str] = None,
    credit_score: Optional[float] = None,
    legal_person: Optional[str] = None,
    reg_capital: Optional[str] = None,
    reg_status: Optional[str] = None,
    established: Optional[str] = None,
    **extra: Any,
) -> dict[str, Any]:
    """创建 Enterprise 类型实体字典

    Args:
        id: 唯一标识
        name: 企业名称
        industry: 所属行业
        region: 注册地区
        scale: 企业规模
        credit_score: 信用评分
        legal_person: 法定代表人
        reg_capital: 注册资本
        reg_status: 经营状态
        established: 成立日期
        **extra: 额外自定义字段

    Returns:
        合规的实体字典（含 _type 和 _id 标记）
    """
    entity = {
        "_type": EntityType.ENTERPRISE.value,
        "_id": id,
        "id": id,
        "name": name,
    }
    if industry is not None:
        entity["industry"] = industry
    if region is not None:
        entity["region"] = region
    if scale is not None:
        entity["scale"] = scale
    if credit_score is not None:
        entity["credit_score"] = credit_score
    if legal_person is not None:
        entity["legal_person"] = legal_person
    if reg_capital is not None:
        entity["reg_capital"] = reg_capital
    if reg_status is not None:
        entity["reg_status"] = reg_status
    if established is not None:
        entity["established"] = established
    entity.update(extra)
    return entity


def PersonEntity(
    id: str,
    name: str,
    role: Optional[str] = None,
    gender: Optional[str] = None,
    position: Optional[str] = None,
    **extra: Any,
) -> dict[str, Any]:
    """创建 Person 类型实体字典"""
    entity = {
        "_type": EntityType.PERSON.value,
        "_id": id,
        "id": id,
        "name": name,
    }
    if role is not None:
        entity["role"] = role
    if gender is not None:
        entity["gender"] = gender
    if position is not None:
        entity["position"] = position
    entity.update(extra)
    return entity


def IndustryEntity(
    id: str,
    name: str,
    level: int,
    category: Optional[str] = None,
    parent_id: Optional[str] = None,
    **extra: Any,
) -> dict[str, Any]:
    """创建 Industry 类型实体字典"""
    entity = {
        "_type": EntityType.INDUSTRY.value,
        "_id": id,
        "id": id,
        "name": name,
        "level": level,
    }
    if category is not None:
        entity["category"] = category
    if parent_id is not None:
        entity["parent_id"] = parent_id
    entity.update(extra)
    return entity


def ProductEntity(
    id: str,
    name: str,
    category: Optional[str] = None,
    enterprise_id: Optional[str] = None,
    description: Optional[str] = None,
    **extra: Any,
) -> dict[str, Any]:
    """创建 Product 类型实体字典"""
    entity = {
        "_type": EntityType.PRODUCT.value,
        "_id": id,
        "id": id,
        "name": name,
    }
    if category is not None:
        entity["category"] = category
    if enterprise_id is not None:
        entity["enterprise_id"] = enterprise_id
    if description is not None:
        entity["description"] = description
    entity.update(extra)
    return entity
