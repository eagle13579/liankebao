"""
链客宝AI系统配置管理模块
======================

功能:
  1. ConfigItem SQLite模型: key/value/description/updated_at
  2. API:
     - GET /api/admin/config → 列出所有配置
     - PUT /api/admin/config/{key} → 更新配置值
     - GET /api/admin/config/logs → 操作日志
  3. 预设配置项: payment_mode(mock/real), announcement, maintenance_mode, platform_fee_rate

注册方式（在 main.py 中）:
    import admin_config as admin_config_module
    app.include_router(admin_config_module.router)
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text, desc
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import Base, get_db
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/config", tags=["系统配置"])


# ===== SQLAlchemy Model =====


class ConfigItem(Base):
    """系统配置项"""

    __tablename__ = "admin_config"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column(String(100), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=False, default="")
    description = Column(String(500), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "description": self.description,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ConfigLog(Base):
    """配置变更操作日志"""

    __tablename__ = "admin_config_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column(String(100), nullable=False, index=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    operator = Column(String(100), nullable=True)  # 操作人用户名
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "operator": self.operator,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ===== Pydantic Schemas =====


class ConfigUpdateRequest(BaseModel):
    value: str = Field(..., description="新的配置值")


class ConfigLogResponse(BaseModel):
    id: int
    key: str
    old_value: str | None = None
    new_value: str | None = None
    operator: str | None = None
    created_at: str | None = None


class ConfigItemResponse(BaseModel):
    id: int
    key: str
    value: str
    description: str | None = None
    updated_at: str | None = None


# ===== 预设配置项 =====

PRESET_CONFIGS = [
    {
        "key": "payment_mode",
        "value": "mock",
        "description": "支付模式: mock(模拟支付) / real(真实支付)",
    },
    {
        "key": "announcement",
        "value": "",
        "description": "系统公告内容（空字符串表示无公告）",
    },
    {
        "key": "maintenance_mode",
        "value": "false",
        "description": "维护模式: true(维护中) / false(正常运行)",
    },
    {
        "key": "platform_fee_rate",
        "value": "0.10",
        "description": "平台手续费率（小数，如 0.10 表示10%）",
    },
]


def ensure_preset_configs(db: Session):
    """确保预设配置项存在（启动时调用）"""
    for cfg in PRESET_CONFIGS:
        existing = db.query(ConfigItem).filter(ConfigItem.key == cfg["key"]).first()
        if not existing:
            item = ConfigItem(
                key=cfg["key"],
                value=cfg["value"],
                description=cfg["description"],
            )
            db.add(item)
    db.commit()


# ===== API Endpoints =====


@router.get("")
def list_configs(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """列出所有系统配置项（需管理员权限）"""
    configs = db.query(ConfigItem).order_by(ConfigItem.key).all()
    return {
        "code": 200,
        "message": "success",
        "data": [c.to_dict() for c in configs],
    }


@router.put("/{key}")
def update_config(
    key: str,
    req: ConfigUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """更新指定配置项的值（需管理员权限）"""
    config = db.query(ConfigItem).filter(ConfigItem.key == key).first()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"配置项 '{key}' 不存在",
        )

    # 记录变更日志
    log_entry = ConfigLog(
        key=key,
        old_value=config.value,
        new_value=req.value,
        operator=admin.username,
    )
    db.add(log_entry)

    # 更新值
    config.value = req.value
    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)

    logger.info(
        "系统配置已更新",
        extra={"key": key, "old_value": log_entry.old_value, "new_value": req.value, "operator": admin.username},
    )

    return {
        "code": 200,
        "message": "配置已更新",
        "data": config.to_dict(),
    }


@router.get("/logs")
def list_config_logs(
    key: str | None = Query(None, description="按配置键筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """获取配置变更操作日志（需管理员权限）"""
    query = db.query(ConfigLog)
    if key:
        query = query.filter(ConfigLog.key == key)

    total = query.count()
    logs = query.order_by(desc(ConfigLog.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [log.to_dict() for log in logs],
        },
    }
