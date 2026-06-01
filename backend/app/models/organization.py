"""
多租户组织模型

Organization      — 组织/租户实体
OrganizationMember — 组织成员关联（角色）
Invite            — 组织邀请（邮件+令牌）
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Organization(Base):
    """组织模型 — 多租户核心实体"""

    __tablename__ = "organizations"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="组织名称")
    slug = Column(String(100), unique=True, nullable=False, index=True, comment="唯一标识符（用于 URL）")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="创建者/所有者")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 关系
    owner = relationship("User", foreign_keys=[owner_id])
    members = relationship("OrganizationMember", back_populates="organization", cascade="all, delete-orphan")
    invites = relationship("Invite", back_populates="organization", cascade="all, delete-orphan")


class OrganizationMember(Base):
    """组织成员关联模型"""

    __tablename__ = "organization_members"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, comment="组织 ID")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="用户 ID")
    role = Column(String(20), nullable=False, default="member", comment="角色: admin/member")
    joined_at = Column(DateTime, default=datetime.utcnow, comment="加入时间")

    # 关系
    organization = relationship("Organization", back_populates="members")
    user = relationship("User", foreign_keys=[user_id], back_populates="memberships")


class Invite(Base):
    """组织邀请模型"""

    __tablename__ = "organization_invites"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, comment="组织 ID")
    email = Column(String(255), nullable=False, comment="受邀邮箱")
    token = Column(String(64), unique=True, nullable=False, index=True, comment="邀请令牌")
    status = Column(String(20), nullable=False, default="pending", comment="状态: pending/accepted/expired")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 关系
    organization = relationship("Organization", back_populates="invites")
