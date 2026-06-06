"""
觅迹 Mijü · 翻页图册 API 桥接路由
映射到链客宝 CardProfile 模型
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CardProfile, DemandItem, SupplyItem, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/brochure", tags=["觅迹·翻页图册"])


@router.get("/{user_id}")
def get_brochure(user_id: int, db: Session = Depends(get_db)):
    profile = db.query(CardProfile).filter(CardProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="图册不存在")

    user = db.query(User).filter(User.id == user_id).first()
    supplies = db.query(SupplyItem).filter(SupplyItem.user_id == user_id, SupplyItem.status == "active").all()
    demands = db.query(DemandItem).filter(DemandItem.user_id == user_id, DemandItem.status == "open").all()

    def safe_json(val):
        if not val:
            return []
        if isinstance(val, list):
            return val
        try:
            return json.loads(val) if isinstance(val, str) else []
        except Exception:
            return [str(val)] if val else []

    data = {
        "id": user_id,
        "user_id": user_id,
        "title": f"{user.name if user else ''} 的数字名片",
        "cover": profile.avatar_url or profile.banner_url or "",
        "pages": [
            {"type": "text", "content": profile.bio or ""},
            {"type": "text", "content": f"联系方式: {profile.contact_phone or ''} {profile.contact_wechat or ''}"},
        ],
        "pages_count": 2,
        "status": "published",
        "profile": {
            "name": user.name if user else "",
            "company": user.company if user else "",
            "position": user.position if user else "",
            "avatar": profile.avatar_url
            or (f"https://api.dicebear.com/7.x/avataaars/svg?seed={user.name}" if user else ""),
            "headline": profile.headline or profile.display_name or "",
            "tags": safe_json(profile.tags),
            "phone": profile.contact_phone or (user.phone if user else ""),
        },
        "supplies": [{"title": s.title, "description": s.description, "category": s.category} for s in supplies],
        "demands": [{"title": d.title, "description": d.description, "category": d.category} for d in demands],
        "view_count": 0,
    }
    return {"code": 200, "data": data}


@router.post("/{user_id}/visit")
def record_visit(user_id: int, db: Session = Depends(get_db)):
    return {"code": 200, "message": "已记录"}


@router.post("/{user_id}/interest")
def record_interest(user_id: int, db: Session = Depends(get_db)):
    return {"code": 200, "message": "已收到意向，我们会尽快联系您"}


@router.put("/{user_id}")
def update_brochure(user_id: int, data: dict, db: Session = Depends(get_db)):
    """更新名片资料（bio/tags/联系方式）"""
    profile = db.query(CardProfile).filter(CardProfile.user_id == user_id).first()
    if not profile:
        profile = CardProfile(user_id=user_id)
        db.add(profile)
    if "bio" in data:
        profile.bio = data["bio"]
    if "contact_phone" in data:
        profile.contact_phone = data["contact_phone"]
    if "contact_wechat" in data:
        profile.contact_wechat = data["contact_wechat"]
    if "headline" in data:
        profile.headline = data["headline"]
    if "display_name" in data:
        profile.display_name = data["display_name"]
    if "tags" in data:
        profile.tags = json.dumps(data["tags"])
    if "avatar_url" in data:
        profile.avatar_url = data["avatar_url"]
    db.commit()
    return {"code": 200, "message": "已更新"}


@router.delete("/{user_id}")
def delete_brochure(user_id: int, db: Session = Depends(get_db)):
    """删除名片资料"""
    profile = db.query(CardProfile).filter(CardProfile.user_id == user_id).first()
    if profile:
        db.delete(profile)
        db.commit()
    return {"code": 200, "message": "已删除"}
