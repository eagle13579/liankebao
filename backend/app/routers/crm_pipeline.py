"""
CRM管道工作流 - API路由
实现用户粘性机制的管道视图接口
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.models import User
from app.services.crm_pipeline import (
    PIPELINE_STAGES,
    add_note,
    create_lead,
    get_lead,
    get_leads,
    get_pipeline,
    get_stale_leads,
    update_stage,
)
from app.services.crm_pipeline import get_my_leads as svc_get_my_leads

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm", tags=["CRM管道工作流"])


# ============================================================
# 辅助函数
# ============================================================


def _validate_stage(stage: str) -> str:
    """校验并归一化阶段名称"""
    s = stage.lower().strip()
    if s not in PIPELINE_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"无效阶段: {stage}，有效值: {', '.join(PIPELINE_STAGES)}",
        )
    return s


def _ensure_lead_exists(lead_id: int) -> dict:
    """获取线索，不存在则抛 404"""
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="线索不存在")
    return lead


# ============================================================
# GET  /api/v1/crm/pipeline  — 管道概览
# ============================================================


@router.get("/pipeline", summary="管道概览", description="获取CRM管道各阶段数量及总额")
def api_get_pipeline(current_user: User = Depends(get_current_user)):
    """管道概览：各阶段数量 + 总额"""
    data = get_pipeline()
    return {"code": 200, "message": "success", "data": data}


# ============================================================
# GET  /api/v1/crm/leads  — 全部线索（支持筛选）
# ============================================================


@router.get("/leads", summary="线索列表", description="获取全部线索，支持阶段、搜索、分页筛选")
def api_list_leads(
    stage: str | None = Query(None, description="按阶段筛选"),
    search: str | None = Query(None, description="搜索关键词（姓名/公司/电话）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """获取线索列表（支持 stage 过滤、搜索、分页）"""
    if stage:
        stage = _validate_stage(stage)
    data = get_leads(stage=stage, search=search or "", page=page, page_size=page_size)
    return {"code": 200, "message": "success", "data": data}


# ============================================================
# POST  /api/v1/crm/leads  — 新建线索
# ============================================================


@router.post("/leads", summary="新建线索", description="创建新线索，自动进入「新线索」阶段", status_code=201)
def api_create_lead(
    name: str = Query(..., min_length=1, description="姓名"),
    company: str = Query("", description="公司"),
    phone: str = Query("", description="手机号"),
    source: str = Query("manual", description="来源"),
    next_action: str = Query("", description="下一步行动"),
    value: float = Query(0.0, description="预计金额"),
    notes: str = Query("", description="备注"),
    current_user: User = Depends(get_current_user),
):
    """新建线索"""
    assigned_name = current_user.name or ""
    data = create_lead(
        name=name,
        company=company,
        phone=phone,
        source=source,
        assigned_to=current_user.id,
        assigned_name=assigned_name,
        next_action=next_action,
        value=value,
        notes=notes,
    )
    if data:
        data.pop("notes_list", None)
    return {"code": 201, "message": "创建成功", "data": data}


# ============================================================
# PUT  /api/v1/crm/leads/{id}/stage  — 更新阶段
# ============================================================


@router.put("/leads/{lead_id}/stage", summary="更新阶段", description="推进或回退线索到指定管道阶段")
def api_update_stage(
    lead_id: int,
    stage: str = Query(..., description="目标阶段"),
    current_user: User = Depends(get_current_user),
):
    """更新线索阶段（核心管道推进）"""
    _ensure_lead_exists(lead_id)
    stage = _validate_stage(stage)
    data = update_stage(
        lead_id=lead_id,
        stage=stage,
        user_id=current_user.id,
        user_name=current_user.name or "",
    )
    if data:
        data.pop("notes_list", None)
    return {"code": 200, "message": "阶段更新成功", "data": data}


# ============================================================
# GET  /api/v1/crm/leads/{id}  — 线索详情
# ============================================================


@router.get("/leads/{lead_id}", summary="线索详情", description="获取线索详细信息（含所有跟进记录）")
def api_get_lead(
    lead_id: int,
    current_user: User = Depends(get_current_user),
):
    """线索详情（含跟进记录）"""
    data = _ensure_lead_exists(lead_id)
    return {"code": 200, "message": "success", "data": data}


# ============================================================
# POST  /api/v1/crm/leads/{id}/note  — 添加跟进记录
# ============================================================


@router.post("/leads/{lead_id}/note", summary="添加跟进记录", description="为指定线索添加一条跟进记录", status_code=201)
def api_add_note(
    lead_id: int,
    content: str = Query(..., min_length=1, description="跟进内容"),
    current_user: User = Depends(get_current_user),
):
    """添加跟进记录"""
    _ensure_lead_exists(lead_id)
    data = add_note(
        lead_id=lead_id,
        content=content,
        user_id=current_user.id,
        user_name=current_user.name or "",
    )
    if data:
        data.pop("notes_list", None)
    return {"code": 201, "message": "跟进记录已添加", "data": data}


# ============================================================
# 扩展：粘性机制相关接口
# ============================================================


@router.get("/leads/stale", summary="待跟进线索", description="获取超过指定天数未更新的线索")
def api_stale_leads(
    days: int = Query(7, ge=1, le=90, description="N天未更新"),
    current_user: User = Depends(get_current_user),
):
    """获取待跟进线索（超时未更新的），用于触发跟进提醒"""
    leads = get_stale_leads(days_threshold=days)
    return {"code": 200, "message": "success", "data": {"days": days, "count": len(leads), "items": leads}}


@router.get("/leads/my", summary="我的线索", description="获取分配给当前用户的线索列表")
def api_my_leads(
    stage: str | None = Query(None, description="按阶段筛选"),
    current_user: User = Depends(get_current_user),
):
    """获取我的线索"""
    if stage:
        stage = _validate_stage(stage)
    data = svc_get_my_leads(user_id=current_user.id, stage=stage)
    return {"code": 200, "message": "success", "data": data}
