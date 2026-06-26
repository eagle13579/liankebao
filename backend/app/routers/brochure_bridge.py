"""
链客宝 - 电子画册桥接模块 (Brochure Bridge)
==============================================
小程序 /api/brochures/{userId} 数据源。
从 BusinessCard 模型读取名片数据，按画册格式组装返回。

注入点：小程序画册首页 → 名片数据展示
规则：纯新增，不修改现有业务逻辑

修复记录（铁律九十二）:
  1. 原代码引用了不存在的 CardProfile 模型 → 修正为 BusinessCard
  2. 数据来源: BROCHURE_SYNC_STORE (由 business_card.generate_card 同步写入)
  3. 同时支持数据库直接回退查询
  4. 3个端点: GET /api/brochure/{user_id}, GET /api/brochures/{user_id}, GET /api/brochure/t/{share_token}
"""

import json
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BusinessCard, get_brochure_from_store

logger = logging.getLogger(__name__)

# ===================================================================
# FastAPI 路由定义
# ===================================================================

router = APIRouter(prefix="/api", tags=["电子画册桥接"])


# ── 单数路径: /api/brochure/{user_id} ──────────────────────────────


@router.get("/brochure/{user_id}", summary="获取用户电子画册（单数路径）")
async def get_brochure_singular(user_id: str, db: Session = Depends(get_db)):
    """通过 user_id 获取用户的电子画册数据

    优先从 BROCHURE_SYNC_STORE 内存同步桥读取，
    若不存在则回退查询数据库 BusinessCard 表。
    """
    return _get_brochure_data(user_id, db)


# ── 复数路径: /api/brochures/{user_id} ─────────────────────────────
# 小程序 brochure/index.js 调用的是 /api/brochures/{userId}（复数）
# 此端点作为主入口，与单数路径返回相同数据


@router.get("/brochures/{user_id}", summary="获取用户电子画册（复数路径，小程序入口）")
async def get_brochure_plural(user_id: str, db: Session = Depends(get_db)):
    """小程序入口：获取用户电子画册数据（复数路径）

    小程序 brochure/index.js 调用的 /api/brochures/{userId}
    对接此端点，返回与 /api/brochure/{userId} 一致的数据结构。
    """
    return _get_brochure_data(user_id, db)


# ── 分享令牌路径 ──────────────────────────────────────────────────


@router.get("/brochure/t/{share_token}", summary="通过分享令牌获取电子画册")
async def get_brochure_by_token(share_token: str, db: Session = Depends(get_db)):
    """通过 share_token 公开访问电子画册（无需登录）"""
    card = db.query(BusinessCard).filter(
        BusinessCard.share_token == share_token
    ).first()

    if not card:
        raise HTTPException(status_code=404, detail="画册不存在或链接已失效")

    return _assemble_brochure_response(card)


# ── 内部逻辑 ─────────────────────────────────────────────────────


def _get_brochure_data(user_id: str, db: Session) -> dict:
    """内部：获取 brochure 数据（内存桥优先 + 数据库回退）"""
    # 1) 尝试从内存同步桥读取（实时同步）
    store = get_brochure_from_store(user_id)
    if store is not None:
        return _assemble_brochure_response_from_store(store, source="sync_store")

    # 2) 回退：查询数据库 BusinessCard 表
    card = db.query(BusinessCard).filter(
        BusinessCard.user_id == user_id
    ).order_by(BusinessCard.updated_at.desc()).first()

    if not card:
        raise HTTPException(
            status_code=404,
            detail=f"未找到用户 {user_id} 的电子画册，请先生成名片"
        )

    return _assemble_brochure_response(card, source="database")


def _assemble_brochure_response(card: BusinessCard, source: str = "database") -> dict:
    """将 BusinessCard 组装为电子画册响应格式"""
    fields = card.fields if isinstance(card.fields, dict) else {}
    album = card.album_meta if isinstance(card.album_meta, dict) else {}

    return {
        "id": card.id,
        "user_id": card.user_id,
        "title": fields.get("company", fields.get("name", "我的电子画册")),
        "subtitle": fields.get("position", ""),
        "contact": {
            "phone": fields.get("phone", ""),
            "email": fields.get("email", ""),
            "wechat": fields.get("wechat", ""),
            "website": fields.get("website", ""),
        },
        "address": fields.get("address", ""),
        "description": fields.get("description", ""),
        "cover_image": card.cover_image or fields.get("logo", ""),
        "share_token": card.share_token,
        "album_meta": album,
        "pages": album.get("pages", []),
        "style": album.get("style", {}),
        "created_at": card.created_at.isoformat() if card.created_at else None,
        "updated_at": card.updated_at.isoformat() if card.updated_at else None,
        "_source": source,
    }


def _assemble_brochure_response_from_store(store: dict, source: str = "sync_store") -> dict:
    """从同步桥存储组装响应"""
    fields = store.get("fields", {})
    album = store.get("album_meta", {})

    return {
        "id": store.get("id"),
        "user_id": store.get("user_id"),
        "title": fields.get("company", fields.get("name", "我的电子画册")),
        "subtitle": fields.get("position", ""),
        "contact": {
            "phone": fields.get("phone", ""),
            "email": fields.get("email", ""),
            "wechat": fields.get("wechat", ""),
            "website": fields.get("website", ""),
        },
        "address": fields.get("address", ""),
        "description": fields.get("description", ""),
        "cover_image": store.get("cover_image") or fields.get("logo", ""),
        "share_token": store.get("share_token"),
        "album_meta": album,
        "pages": album.get("pages", []),
        "style": album.get("style", {}),
        "created_at": store.get("created_at"),
        "updated_at": store.get("updated_at"),
        "synced_at": store.get("synced_at"),
        "_source": source,
    }


# ── 启动提示 ─────────────────────────────────────────────────────

print("[BrochureBridge] 电子画册桥接路由已加载 ✓")
print("[BrochureBridge] 端点: GET /api/brochure/{user_id}")
print("[BrochureBridge] 端点: GET /api/brochures/{user_id} (小程序入口)")
print("[BrochureBridge] 端点: GET /api/brochure/t/{share_token}")
print("[BrochureBridge] 模型引用: BusinessCard (原 CardProfile 已修正)")
