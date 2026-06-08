"""
六度人脉 — 关系图数据模型

设计原则：
- 所有关系存储在一张 `user_relations` 表中（邻接表模型），兼容 SQLite/PostgreSQL
- 信任度 (trust_score) 0.0~1.0，每次交互后更新
- 关系有方向：邀请人→被邀请人为正向，也可建立双向关系 (bidirectional=True)
- 六度路径缓存表 `six_degree_paths` 用于存储高频查询结果
"""
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float,
    ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import DB_TYPE, Base

_IS_MULTI_TENANT = DB_TYPE == "postgres"


def _org_fk():
    if not _IS_MULTI_TENANT:
        return Column(Integer, nullable=True, default=None)
    return Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)


class UserRelation(Base):
    """用户关系边（信任连接）

    存储用户之间的直接关系，构成六度人脉图的基础边。
    每条边代表一个信任/连接关系，包含信任度评分。
    """
    __tablename__ = "user_relations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="关系发起方")
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="关系接收方")

    # 关系类型
    relation_type = Column(
        String(20), nullable=False, default="invite",
        comment="关系类型: invite(邀请)/contact(通讯录)/brochure(名片交换)/coop(合作)/refer(推荐)",
    )
    label = Column(String(100), nullable=True, comment="关系标签/备注")

    # 信任度评分 (0.0 ~ 1.0)
    trust_score = Column(Float, nullable=False, default=0.5, comment="信任度 0.0~1.0")
    interaction_count = Column(Integer, nullable=False, default=1, comment="交互次数")
    last_interaction_at = Column(DateTime, nullable=True, comment="最近一次交互时间")

    # 方向控制
    bidirectional = Column(Boolean, nullable=False, default=False, comment="是否为双向关系")
    is_active = Column(Boolean, nullable=False, default=True, comment="关系是否有效")

    # 来源追踪
    source = Column(String(30), nullable=True, default="invite", comment="来源: invite/import/wechat/manual")
    source_detail = Column(String(200), nullable=True, comment="来源详情，如导入批次ID")

    # 乐观锁 & 软删除
    version = Column(BigInteger, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)

    # 多租户
    organization_id = _org_fk()

    # 关系映射
    from_user = relationship("User", foreign_keys=[from_user_id], lazy="joined")
    to_user = relationship("User", foreign_keys=[to_user_id], lazy="joined")

    # 唯一约束：同一对用户之间只能有一条正向关系
    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", name="uq_user_relation_pair"),
        Index("idx_user_relation_active", "from_user_id", "is_active", "trust_score"),
        Index("idx_user_relation_to", "to_user_id", "is_active"),
    )


class RelationEvent(Base):
    """关系事件日志

    记录用户关系变更（建立、断开、信任度变化等），用于信任度计算和审计。
    """
    __tablename__ = "relation_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    relation_id = Column(Integer, ForeignKey("user_relations.id"), nullable=False, index=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_type = Column(
        String(30), nullable=False,
        comment="事件类型: created/trust_updated/deactivated/reactivated/score_decayed",
    )
    old_trust_score = Column(Float, nullable=True, comment="变更前信任度")
    new_trust_score = Column(Float, nullable=True, comment="变更后信任度")
    reason = Column(String(200), nullable=True, comment="变更原因描述")
    metadata_json = Column(Text, nullable=True, comment="附加元数据 JSON")

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # 关系
    relation = relationship("UserRelation", foreign_keys=[relation_id], lazy="joined")


class SixDegreePathCache(Base):
    """六度路径缓存表

    缓存高频查询的六度路径结果，避免重复 BFS 计算。
    以 source -> target 的哈希为键，TTL 过期后自动失效。
    """
    __tablename__ = "six_degree_path_cache"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    path_json = Column(Text, nullable=False, comment="路径 JSON: [{user_id, name, company, trust_score}, ...]")
    path_length = Column(Integer, nullable=False, comment="路径长度(跳数)")
    total_trust_score = Column(Float, nullable=False, default=0.0, comment="路径总信任度")
    hit_count = Column(Integer, nullable=False, default=1, comment="被命中次数")
    expires_at = Column(DateTime, nullable=False, comment="缓存过期时间")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 唯一约束
    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", name="uq_path_cache_pair"),
        Index("idx_path_cache_expires", "expires_at"),
    )


class ReferralLink(Base):
    """邀请链接/二维码

    用于追踪六度人脉中的邀请关系链。
    """
    __tablename__ = "referral_links"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code = Column(String(32), unique=True, nullable=False, index=True, comment="邀请码")
    title = Column(String(100), nullable=True, comment="链接标题")
    description = Column(String(500), nullable=True, comment="链接描述")
    invite_type = Column(String(20), nullable=False, default="direct", comment="邀请类型: direct/brochure/product")
    redirect_url = Column(String(500), nullable=True, comment="跳转目标URL")
    scan_count = Column(Integer, nullable=False, default=0, comment="扫码次数")
    register_count = Column(Integer, nullable=False, default=0, comment="通过此链接注册数")
    is_active = Column(Boolean, nullable=False, default=True)
    expires_at = Column(DateTime, nullable=True, comment="过期时间")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", foreign_keys=[owner_user_id], lazy="joined")

    __table_args__ = (
        Index("idx_referral_owner", "owner_user_id", "is_active"),
    )
