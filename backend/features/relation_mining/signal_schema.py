"""关系信号数据模型"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class SignalType(str, Enum):
    """关系信号类型"""
    CONTRACT_COLLABORATION = "contract_collaboration"  # 同一合同中的甲乙双方
    ORDER_PARTICIPATION = "order_participation"        # 同一商机的参与方
    ENTERPRISE_QUERY = "enterprise_query"              # 同一企业被多次查询
    CRM_PIPELINE_SHARED = "crm_pipeline_shared"        # CRM管道中同一客户
    SIX_DEGREE_EXTENSION = "six_degree_extension"      # 共同好友推荐
    SAME_ORGANIZATION = "same_organization"             # 同一组织的成员


class SignalSource(str, Enum):
    """信号来源"""
    CONTRACTS = "contracts"
    ORDERS = "orders"
    ENTERPRISE_CRAWLER = "enterprise_crawler"
    CRM_PIPELINE = "crm_pipeline"
    USER_RELATIONS = "user_relations"


@dataclass
class RelationSignal:
    """关系信号 — 表示两个实体之间可能存在的关系"""
    source_type: SignalType
    source: SignalSource
    from_entity_id: int
    from_entity_type: str  # "user" / "enterprise"
    to_entity_id: int
    to_entity_type: str
    signal_strength: float  # 0.0 ~ 1.0
    evidence: str          # 证据描述
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)
