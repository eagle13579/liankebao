"""
链客宝 - SQLAlchemy 数据模型
================================
所有 ORM 模型集中定义，供路由模块引用。
规则：纯新增，不修改现有业务逻辑

BusinessCard (第 304 行附近)
  字段: id, user_id, fields(JSON), share_token, cover_image, album_meta, created_at, updated_at
"""

import json
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, func, text
from sqlalchemy.orm import relationship

from app.database import Base


# ===================================================================
# BusinessCard — 企业数字名片（核心模型）
# ===================================================================
# 映射表: business_cards
# 字段说明:
#   user_id     - 所属用户 ID
#   fields      - JSON 格式的名片字段（公司名、职位、电话、邮箱等）
#   share_token - 分享令牌，用于 H5 页面的公开访问
#   cover_image - 封面图 URL
#   album_meta  - 电子画册配置元信息（翻页样式、背景音乐等）
# ===================================================================

class BusinessCard(Base):
    """企业数字名片"""
    __tablename__ = "business_cards"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True, comment="所属用户ID")
    fields = Column(JSON, nullable=False, default=dict, comment="名片字段 JSON")
    share_token = Column(String(128), unique=True, nullable=True, comment="分享令牌")
    cover_image = Column(String(512), nullable=True, comment="封面图 URL")
    album_meta = Column(JSON, nullable=True, default=dict, comment="电子画册配置")
    source = Column(String(20), nullable=False, server_default=text("'web_upload'"), comment="来源: web_upload/web_manual/miniapp_wechat")
    created_at = Column(DateTime, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self):
        return f"<BusinessCard(id={self.id}, user_id={self.user_id})>"

    def to_dict(self):
        """转为可序列化字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "fields": self.fields if isinstance(self.fields, dict) else json.loads(self.fields or "{}"),
            "share_token": self.share_token,
            "cover_image": self.cover_image,
            "album_meta": self.album_meta if isinstance(self.album_meta, dict) else json.loads(self.album_meta or "{}"),
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ===================================================================
# 数据同步桥 — 内存共享存储
# ===================================================================
# brochure_bridge 与 business_card 之间通过此内存字典解耦同步。
# business_card.generate_card 写入后自动同步到此桥，
# brochure_bridge 从中读取最新的 brochure 数据。
# 后续可替换为 Redis / 数据库触发器。
# ===================================================================

BROCHURE_SYNC_STORE: dict[str, dict] = {}
"""
BROCHURE_SYNC_STORE[user_id] = {
    "id": <BusinessCard.id>,
    "user_id": <str>,
    "fields": {...},
    "share_token": <str>,
    "cover_image": <str>,
    "album_meta": {...},
    "synced_at": <isoformat>,
}
"""


def sync_brochure_from_card(card: BusinessCard) -> dict:
    """将 BusinessCard 实例同步至 brochure 共享存储"""
    data = card.to_dict()
    data["synced_at"] = datetime.utcnow().isoformat() + "Z"
    BROCHURE_SYNC_STORE[card.user_id] = data
    return data


def get_brochure_from_store(user_id: str) -> dict | None:
    """从共享存储读取 brochure 数据"""
    return BROCHURE_SYNC_STORE.get(user_id)


# ===================================================================
# 创建所有表（供初始化使用）
# ===================================================================

from app.database import engine as _engine


def init_models():
    """创建所有 ORM 表（幂等操作）"""
    Base.metadata.create_all(bind=_engine)
    print("[Models] 数据库表已就绪 ✓")


print("[Models] 数据模型已加载 ✓")
print(f"[Models] BusinessCard → {BusinessCard.__tablename__}")
