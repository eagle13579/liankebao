"""链客宝 — 用户模型

提供 User ORM 模型，用于注册/登录的用户数据持久化。
规则：纯新增，不修改现有业务逻辑
"""

import hashlib
import os
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, func
from app.database import Base


def hash_password(password: str, salt: str | None = None) -> str:
    """PBKDF2-SHA256 密码哈希"""
    if salt is None:
        salt = os.urandom(16).hex()
    # 简单的 SHA256 + salt 哈希（可后续升级为 bcrypt）
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${h.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """验证密码"""
    try:
        salt, _ = hashed.split("$", 1)
        return hash_password(password, salt) == hashed
    except (ValueError, AttributeError):
        return False


class User(Base):
    """平台用户"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True, comment="用户名")
    password_hash = Column(String(256), nullable=False, comment="密码哈希")
    name = Column(String(64), nullable=True, comment="姓名")
    phone = Column(String(20), nullable=True, comment="手机号")
    company = Column(String(128), nullable=True, comment="公司")
    position = Column(String(64), nullable=True, comment="职位")
    role = Column(String(20), nullable=False, default="user", comment="角色: user/admin")
    avatar = Column(String(512), nullable=True, comment="头像 URL")
    is_active = Column(Boolean, default=True, comment="是否激活")
    is_deleted = Column(Boolean, default=False, comment="是否删除（软删除）")
    created_at = Column(DateTime, default=func.now(), comment="注册时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "name": self.name or "",
            "phone": self.phone or "",
            "company": self.company or "",
            "position": self.position or "",
            "role": self.role,
            "avatar": self.avatar or "",
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
