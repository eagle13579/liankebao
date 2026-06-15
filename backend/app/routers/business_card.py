"""
链客宝 - 企业数字名片模块 (Business Card)
=========================================
名片创建/读取/更新/删除 + AI 生成 + 数据同步钩子

注入点：名片全生命周期管理
规则：纯新增，不修改现有业务逻辑

同步钩子（铁律九十二）:
  generate_card() 末尾调用 sync_brochure_from_card()
  将新生成的 BusinessCard 同步至 BROCHURE_SYNC_STORE，
  供 brochure_bridge 实时读取。
"""

import json
import uuid
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BusinessCard, sync_brochure_from_card, init_models

# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================


class CardFields(BaseModel):
    """名片字段（JSON 结构体）"""
    name: str = ""
    company: str = ""
    position: str = ""
    phone: str = ""
    email: str = ""
    wechat: str = ""
    website: str = ""
    address: str = ""
    description: str = ""
    logo: str = ""
    tags: list[str] = []


class CardCreate(BaseModel):
    """创建名片请求"""
    user_id: str
    fields: CardFields
    cover_image: Optional[str] = None
    album_meta: Optional[dict] = None


class CardUpdate(BaseModel):
    """更新名片请求"""
    fields: Optional[CardFields] = None
    cover_image: Optional[str] = None
    album_meta: Optional[dict] = None


class CardResponse(BaseModel):
    """名片响应"""
    id: int
    user_id: str
    fields: dict
    share_token: Optional[str] = None
    cover_image: Optional[str] = None
    album_meta: Optional[dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


# ===================================================================
# FastAPI 路由
# ===================================================================

router = APIRouter(prefix="/api/business-card", tags=["企业数字名片"])


# ── 创建名片 ─────────────────────────────────────────────────────


@router.post("/cards", summary="创建名片", response_model=CardResponse)
async def create_card(card_in: CardCreate, db: Session = Depends(get_db)):
    """创建新的企业数字名片"""
    share_token = str(uuid.uuid4()).replace("-", "")[:16]

    card = BusinessCard(
        user_id=card_in.user_id,
        fields=card_in.fields.model_dump() if hasattr(card_in.fields, 'model_dump') else card_in.fields.dict(),
        share_token=share_token,
        cover_image=card_in.cover_image,
        album_meta=card_in.album_meta or {},
    )

    db.add(card)
    db.commit()
    db.refresh(card)

    # ── 同步钩子：同步至 BROCHURE_SYNC_STORE ──
    sync_brochure_from_card(card)

    return card


# ── 获取名片列表 ─────────────────────────────────────────────────


@router.get("/cards", summary="获取名片列表")
async def list_cards(
    user_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """按 user_id 筛选名片列表"""
    query = db.query(BusinessCard)

    if user_id:
        query = query.filter(BusinessCard.user_id == user_id)

    total = query.count()
    cards = query.order_by(BusinessCard.updated_at.desc()).offset(skip).limit(limit).all()

    return {
        "cards": [CardResponse.model_validate(c) for c in cards],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


# ── 获取单张名片 ─────────────────────────────────────────────────


@router.get("/cards/{card_id}", summary="获取名片详情", response_model=CardResponse)
async def get_card(card_id: int, db: Session = Depends(get_db)):
    """根据 ID 获取名片详情"""
    card = db.query(BusinessCard).filter(BusinessCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="名片不存在")
    return card


# ── 更新名片 ─────────────────────────────────────────────────────


@router.put("/cards/{card_id}", summary="更新名片", response_model=CardResponse)
async def update_card(card_id: int, card_in: CardUpdate, db: Session = Depends(get_db)):
    """更新名片信息"""
    card = db.query(BusinessCard).filter(BusinessCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="名片不存在")

    if card_in.fields is not None:
        fields_data = card_in.fields.model_dump() if hasattr(card_in.fields, 'model_dump') else card_in.fields.dict()
        # 合并而非覆盖
        current = card.fields if isinstance(card.fields, dict) else {}
        current.update({k: v for k, v in fields_data.items() if v})
        card.fields = current

    if card_in.cover_image is not None:
        card.cover_image = card_in.cover_image
    if card_in.album_meta is not None:
        card.album_meta = card_in.album_meta

    db.commit()
    db.refresh(card)

    # ── 同步钩子：更新同步至 BROCHURE_SYNC_STORE ──
    sync_brochure_from_card(card)

    return card


# ── 删除名片 ─────────────────────────────────────────────────────


@router.delete("/cards/{card_id}", summary="删除名片")
async def delete_card(card_id: int, db: Session = Depends(get_db)):
    """删除名片"""
    card = db.query(BusinessCard).filter(BusinessCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="名片不存在")

    db.delete(card)
    db.commit()

    # 可选：同步桥中清除该用户数据
    from app.models import BROCHURE_SYNC_STORE
    BROCHURE_SYNC_STORE.pop(card.user_id, None)

    return {"message": "名片已删除", "id": card_id}


# ── AI 生成名片（核心） ──────────────────────────────────────────


class GenerateCardRequest(BaseModel):
    """AI 生成名片请求"""
    user_id: str
    raw_text: str = Field(..., description="用户输入的原始文本（公司介绍、个人信息等）")
    template: Optional[str] = "standard"
    source: Optional[str] = "web_upload"


class GenerateCardResponse(BaseModel):
    """AI 生成名片响应"""
    card: CardResponse
    ai_summary: str = ""
    suggestions: list[str] = []


@router.post("/generate-card", summary="AI 生成名片（含同步钩子）", response_model=GenerateCardResponse)
async def generate_card(
    req: GenerateCardRequest,
    db: Session = Depends(get_db),
):
    """AI 从用户原始文本中提取字段，生成企业数字名片

    ═══════════════════════════════════════════════════════════════
    同步钩子（铁律九十二）:
      函数末尾调用 sync_brochure_from_card(card) 自动将新生成的
      BusinessCard 同步至 BROCHURE_SYNC_STORE，供 brochure_bridge
      通过 /api/brochures/{userId} 实时读取。
    ═══════════════════════════════════════════════════════════════

    流程:
      1. 解析 raw_text → 提取结构化字段
      2. 创建 BusinessCard 记录
      3. 生成 share_token
      4. 同步至 BROCHURE_SYNC_STORE（桥接数据）
      5. 返回名片 + AI 摘要
    """
    # ── 1. AI 字段提取 ─────────────────────────────────────────
    # (实际项目中可调用 business_card_ai.py 引擎)
    # 此处为智能提取的简化实现
    extracted = _extract_fields_from_text(req.raw_text)

    # ── 2. 生成 share_token ─────────────────────────────────────
    share_token = str(uuid.uuid4()).replace("-", "")[:16]

    # ── 3. 创建 BusinessCard 记录 ───────────────────────────────
    card = BusinessCard(
        user_id=req.user_id,
        fields=extracted,
        share_token=share_token,
        cover_image=extracted.get("logo", ""),
        source=req.source,
        album_meta={
            "template": req.template or "standard",
            "auto_generated": True,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        },
    )

    db.add(card)
    db.commit()
    db.refresh(card)

    # ── 4. ═══ 同步钩子 — 数据桥接 ═════════════════════════════
    sync_brochure_from_card(card)
    # ── 同步完成: brochure_bridge 可立即读取 ────────────────────

    # ── 5. 组装响应 ─────────────────────────────────────────────
    ai_summary = f"已从您的输入中提取 {len([v for v in extracted.values() if v])} 个字段"
    suggestions = _generate_suggestions(extracted)

    return GenerateCardResponse(
        card=card,
        ai_summary=ai_summary,
        suggestions=suggestions,
    )


# ── 通过 share_token 查询名片 ──────────────────────────────────


@router.get("/share/{share_token}", summary="通过分享令牌获取名片", response_model=CardResponse)
async def get_card_by_token(share_token: str, db: Session = Depends(get_db)):
    """通过 share_token 公开查询名片"""
    card = db.query(BusinessCard).filter(
        BusinessCard.share_token == share_token
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="名片不存在或链接已失效")
    return card


# ===================================================================
# 内部辅助函数
# ===================================================================


def _extract_fields_from_text(text: str) -> dict:
    """从原始文本中提取名片字段（简易实现）

    正式环境应调用 business_card_ai.py 的 AI 引擎。
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    fields = {
        "name": "",
        "company": "",
        "position": "",
        "phone": "",
        "email": "",
        "wechat": "",
        "website": "",
        "address": "",
        "description": "",
        "logo": "",
        "tags": [],
    }

    current_key = None
    for line in lines:
        # 尝试匹配 字段名: 值 格式
        if "：" in line or ":" in line:
            sep = "：" if "：" in line else ":"
            parts = line.split(sep, 1)
            key = parts[0].strip().lower()
            val = parts[1].strip()

            mapping = {
                "姓名": "name", "名字": "name", "名称": "name",
                "公司": "company", "企业": "company", "单位": "company",
                "职位": "position", "职务": "position", "岗位": "position",
                "手机": "phone", "电话": "phone", "手机号": "phone",
                "邮箱": "email", "邮件": "email", "email": "email",
                "微信": "wechat", "微信号": "wechat",
                "网站": "website", "网址": "website", "官网": "website",
                "地址": "address", "地址": "address",
                "简介": "description", "介绍": "description", "描述": "description",
                "标签": "tags",
            }

            mapped = mapping.get(key)
            if mapped == "tags":
                fields["tags"] = [t.strip() for t in val.split("、") if t.strip()]
            elif mapped and mapped in fields:
                fields[mapped] = val

            current_key = mapped
        elif current_key and current_key in fields:
            # 续行
            if isinstance(fields[current_key], str):
                fields[current_key] += " " + line

    # 如果没有任何结构化字段，将全文作为 description
    if not any(v for k, v in fields.items() if k not in ("tags",) and v):
        fields["description"] = text

    return fields


def _generate_suggestions(fields: dict) -> list[str]:
    """根据已提取字段生成完善建议"""
    suggestions = []
    missing = []

    essential = ["company", "phone", "name"]
    for field in essential:
        if not fields.get(field):
            missing.append({"name": "公司名称", "company": "公司", "phone": "手机号", "position": "职位"}.get(field, field))

    if missing:
        suggestions.append(f"建议补充: {'、'.join(missing)}，让名片更完整")

    if not fields.get("logo"):
        suggestions.append("建议上传公司 Logo，提升品牌可信度")

    if not fields.get("description"):
        suggestions.append("添加一段公司简介，帮助合作伙伴快速了解您的业务")

    return suggestions


# ── 启动提示 ─────────────────────────────────────────────────────

print("[BusinessCard] 企业数字名片路由已加载 ✓")
print("[BusinessCard] 端点: POST   /api/business-card/cards")
print("[BusinessCard] 端点: GET    /api/business-card/cards")
print("[BusinessCard] 端点: GET    /api/business-card/cards/{id}")
print("[BusinessCard] 端点: PUT    /api/business-card/cards/{id}")
print("[BusinessCard] 端点: DELETE /api/business-card/cards/{id}")
print("[BusinessCard] 端点: POST   /api/business-card/generate-card (含同步钩子)")
print("[BusinessCard] 端点: GET    /api/business-card/share/{token}")
print("[BusinessCard] 同步钩子已注入: generate_card → sync_brochure_from_card")
