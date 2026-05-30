"""
CRM管道路由：商机列表/创建/详情/更新/活动/管道概览
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.auth import get_current_user
from app.database import get_db
from app.models import User, Deal, DealActivity
from app.schemas import DealCreate, DealUpdate, DealActivityCreate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm", tags=["CRM管道"])

PIPELINE_STAGES = ["leads", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]
STAGE_NAMES = {"leads":"初步接触","qualified":"需求确认","proposal":"方案报价","negotiation":"商务谈判","closed_won":"已成交","closed_lost":"已流失"}

def _normalize_stage(stage: str) -> str:
    s = stage.lower().strip()
    for valid in PIPELINE_STAGES:
        if valid.startswith(s) or s.startswith(valid):
            return valid
    return stage

def _get_brief(user: User) -> dict:
    return {"id": user.id, "name": user.name, "company": user.company or ""}

@router.get("/deals")
def list_deals(
    stage: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    owner_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Deal)
    if stage: q = q.filter(Deal.stage == _normalize_stage(stage))
    if search: q = q.filter(Deal.title.ilike(f"%{search}%"))
    if owner_id: q = q.filter(Deal.owner_id == owner_id)
    if not current_user.role == "admin":
        q = q.filter((Deal.user_id == current_user.id) | (Deal.owner_id == current_user.id))
    total = q.count()
    deals = q.order_by(Deal.updated_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"code": 200, "data": [{
        "id": d.id, "title": d.title, "value": d.value, "stage": d.stage,
        "stage_name": STAGE_NAMES.get(d.stage, d.stage),
        "probability": d.probability, "notes": d.notes,
        "owner_id": d.owner_id, "user_id": d.user_id,
        "expected_close_date": d.expected_close_date.isoformat() if d.expected_close_date else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    } for d in deals], "total": total, "page": page, "page_size": page_size}

@router.post("/deals", status_code=201)
def create_deal(
    data: DealCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stage = _normalize_stage(data.stage)
    if stage not in PIPELINE_STAGES:
        raise HTTPException(400, f"无效阶段: {data.stage}")
    deal = Deal(title=data.title, value=data.value, stage=stage, user_id=current_user.id,
                owner_id=data.owner_id or current_user.id, probability=data.probability,
                expected_close_date=datetime.fromisoformat(data.expected_close_date) if data.expected_close_date else None,
                notes=data.notes)
    db.add(deal); db.commit(); db.refresh(deal)
    db.add(DealActivity(deal_id=deal.id, user_id=current_user.id, action_type="stage_change",
                         summary=f"创建商机 → {STAGE_NAMES.get(stage, stage)}"))
    db.commit()
    return {"code": 201, "data": {"id": deal.id, "title": deal.title, "stage": deal.stage}}

@router.get("/deals/{deal_id}")
def get_deal(deal_id: int, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal: raise HTTPException(404, "商机不存在")
    activities = db.query(DealActivity).filter(DealActivity.deal_id == deal_id).order_by(DealActivity.created_at.desc()).all()
    owner = db.query(User).filter(User.id == deal.owner_id).first()
    return {"code": 200, "data": {
        "id": deal.id, "title": deal.title, "value": deal.value, "stage": deal.stage,
        "stage_name": STAGE_NAMES.get(deal.stage, deal.stage),
        "probability": deal.probability, "notes": deal.notes,
        "owner": _get_brief(owner) if owner else None,
        "expected_close_date": deal.expected_close_date.isoformat() if deal.expected_close_date else None,
        "created_at": deal.created_at.isoformat() if deal.created_at else None,
        "activities": [{
            "id": a.id, "action_type": a.action_type, "summary": a.summary,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        } for a in activities]}}

@router.patch("/deals/{deal_id}")
def update_deal(deal_id: int, data: DealUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal: raise HTTPException(404, "商机不存在")
    old_stage = deal.stage
    if data.title is not None: deal.title = data.title
    if data.value is not None: deal.value = data.value
    if data.stage is not None:
        ns = _normalize_stage(data.stage)
        if ns not in PIPELINE_STAGES: raise HTTPException(400, f"无效阶段: {data.stage}")
        deal.stage = ns
    if data.owner_id is not None: deal.owner_id = data.owner_id
    if data.probability is not None: deal.probability = data.probability
    if data.expected_close_date is not None:
        deal.expected_close_date = datetime.fromisoformat(data.expected_close_date)
    if data.notes is not None: deal.notes = data.notes
    deal.updated_at = datetime.utcnow()
    if old_stage != deal.stage:
        db.add(DealActivity(deal_id=deal.id, user_id=current_user.id, action_type="stage_change",
                             summary=f"{STAGE_NAMES.get(old_stage,old_stage)} → {STAGE_NAMES.get(deal.stage,deal.stage)}"))
    db.commit()
    return {"code": 200, "data": {"id": deal.id, "title": deal.title, "stage": deal.stage}}

@router.post("/deals/{deal_id}/activities", status_code=201)
def create_deal_activity(deal_id: int, data: DealActivityCreate, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal: raise HTTPException(404, "商机不存在")
    act = DealActivity(deal_id=deal.id, user_id=current_user.id, action_type=data.action_type,
                        summary=data.summary, detail=data.detail)
    db.add(act); db.commit()
    return {"code": 201, "data": {"id": act.id, "summary": act.summary, "action_type": act.action_type}}

@router.get("/pipeline")
def get_pipeline(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    stages = []
    for s in PIPELINE_STAGES:
        cnt = db.query(Deal).filter(Deal.stage == s).count()
        val = db.query(func.coalesce(func.sum(Deal.value), 0)).filter(Deal.stage == s).scalar()
        stages.append({"stage": s, "name": STAGE_NAMES.get(s, s), "count": cnt, "value": float(val)})
    total = sum(s["count"] for s in stages)
    total_value = sum(s["value"] for s in stages)
    return {"code": 200, "data": {"stages": stages, "total": total, "total_value": total_value}}
