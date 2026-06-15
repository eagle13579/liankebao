"""
M2 心智模型注入 — 创业=验证假设
===================================
链客宝需求评审门禁：在产品/需求管理流程中加入「核心假设验证」环节。
将一堂 M2「创业=验证假设」模型产品化为可执行的评审流程。

铁律六：只新增不覆盖，独立模块。
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models import User
from app.rbac import require_roles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hypothesis-gate", tags=["M2心智模型-假设验证门禁"])

_admin_only = require_roles(["admin"])


# ============================================================
# 数据模型
# ============================================================

class HypothesisCheck(Base):
    """需求假设验证记录 — 每个需求关联一组核心假设"""
    __tablename__ = "hypothesis_checks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    feature_name = Column(String(200), nullable=False, comment="需求/功能名称")
    hypothesis = Column(Text, nullable=False, comment="核心假设描述（预期）")
    falsification_criteria = Column(Text, nullable=False, comment="证伪标准（什么情况下假设不成立）")
    validation_method = Column(String(100), nullable=False, default="user_interview", comment="验证方式: user_interview/survey/ab_test/data_analysis/prototype_test")
    status = Column(String(20), nullable=False, default="pending", comment="状态: pending/in_progress/validated/falsified")
    evidence = Column(Text, nullable=True, comment="验证证据/数据")
    conclusion = Column(Text, nullable=True, comment="结论与下一步")
    reviewer_id = Column(Integer, nullable=True, comment="评审人ID")
    product_id = Column(Integer, nullable=True, comment="关联产品ID")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================
# Pydantic Schemas
# ============================================================

class HypothesisCreate(BaseModel):
    feature_name: str = Field(..., min_length=1, max_length=200)
    hypothesis: str = Field(..., min_length=1)
    falsification_criteria: str = Field(..., min_length=1)
    validation_method: str = Field(default="user_interview")
    product_id: Optional[int] = None

class HypothesisUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(pending|in_progress|validated|falsified)$")
    evidence: Optional[str] = None
    conclusion: Optional[str] = None

class HypothesisResponse(BaseModel):
    id: int
    feature_name: str
    hypothesis: str
    falsification_criteria: str
    validation_method: str
    status: str
    evidence: Optional[str] = None
    conclusion: Optional[str] = None
    product_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================
# API 路由
# ============================================================

@router.post("/checks", summary="创建假设验证条目", description="为需求/功能新增一条核心假设验证记录")
def create_hypothesis_check(
    body: HypothesisCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """新增一条假设验证记录"""
    record = HypothesisCheck(
        feature_name=body.feature_name,
        hypothesis=body.hypothesis,
        falsification_criteria=body.falsification_criteria,
        validation_method=body.validation_method,
        product_id=body.product_id,
        status="pending",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info(f"[M2假设验证] 创建: {record.feature_name} | 假设: {record.hypothesis[:50]}...")
    return {"code": 200, "message": "假设验证条目已创建", "data": HypothesisResponse.model_validate(record).model_dump()}


@router.get("/checks", summary="列出假设验证条目", description="按状态筛选所有假设验证记录")
def list_hypothesis_checks(
    status: Optional[str] = Query(None, pattern=r"^(pending|in_progress|validated|falsified)$"),
    product_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """分页列出假设验证条目"""
    q = db.query(HypothesisCheck)
    if status:
        q = q.filter(HypothesisCheck.status == status)
    if product_id:
        q = q.filter(HypothesisCheck.product_id == product_id)
    total = q.count()
    items = q.order_by(HypothesisCheck.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [HypothesisResponse.model_validate(i).model_dump() for i in items],
        },
    }


@router.put("/checks/{check_id}", summary="更新假设验证状态", description="更新验证结果（验证通过/证伪/进行中）")
def update_hypothesis_check(
    check_id: int,
    body: HypothesisUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """更新假设验证状态和结论"""
    record = db.query(HypothesisCheck).filter(HypothesisCheck.id == check_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="假设验证条目不存在")

    record.status = body.status
    if body.evidence is not None:
        record.evidence = body.evidence
    if body.conclusion is not None:
        record.conclusion = body.conclusion
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)

    action = "验证通过" if body.status == "validated" else ("证伪" if body.status == "falsified" else "更新")
    logger.info(f"[M2假设验证] {action}: {record.feature_name} → {body.status}")
    return {"code": 200, "message": f"假设验证已{action}", "data": HypothesisResponse.model_validate(record).model_dump()}


@router.get("/checks/stats", summary="假设验证统计", description="统计各项验证状态的数量")
def hypothesis_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """返回假设验证看板统计数据"""
    total = db.query(HypothesisCheck).count()
    pending = db.query(HypothesisCheck).filter(HypothesisCheck.status == "pending").count()
    in_progress = db.query(HypothesisCheck).filter(HypothesisCheck.status == "in_progress").count()
    validated = db.query(HypothesisCheck).filter(HypothesisCheck.status == "validated").count()
    falsified = db.query(HypothesisCheck).filter(HypothesisCheck.status == "falsified").count()
    validation_rate = round(validated / total * 100, 1) if total > 0 else 0.0

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": total,
            "pending": pending,
            "in_progress": in_progress,
            "validated": validated,
            "falsified": falsified,
            "validation_rate": validation_rate,
        },
    }
