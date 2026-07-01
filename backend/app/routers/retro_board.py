"""
F1-F9 心智模型注入 — 深度复盘模型
====================================
链客宝复盘模板与操作日志追踪系统：后台加入F1-F9九步复盘模板和操作日志追踪。
将一堂「深度复盘」模型产品化为可执行的复盘流程工具。

铁律六：只新增不覆盖，独立模块。
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text, desc
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models import User
from app.rbac import require_roles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/retro", tags=["F1-F9心智模型-深度复盘"])

_admin_only = require_roles(["admin"])


# ============================================================
# F1-F9 九步复盘框架
# ============================================================
RETRO_STEPS = {
    "F1": {"name": "目标回顾", "prompt": "当初设定的目标是什么？SMART原则是否清晰？"},
    "F2": {"name": "结果对比", "prompt": "实际结果与目标对比：哪些达标、哪些未达标？"},
    "F3": {"name": "事实陈述", "prompt": "客观描述发生了什么，不带评判和情绪。"},
    "F4": {"name": "差距分析", "prompt": "目标与结果之间的差距是多少？差距的本质是什么？"},
    "F5": {"name": "原因追问", "prompt": "连续问5个为什么，找到根本原因。"},
    "F6": {"name": "规律提炼", "prompt": "从这件事中能提炼出什么可复用的规律或原则？"},
    "F7": {"name": "经验清单", "prompt": "列出具体可执行的改进措施（To Do / Not To Do）。"},
    "F8": {"name": "知识归档", "prompt": "将提炼的规律/原则存入知识库，便于后续调用。"},
    "F9": {"name": "行动跟踪", "prompt": "设定后续跟踪节点，确保改进措施落地。"},
}


# ============================================================
# 数据模型
# ============================================================

class RetroBoard(Base):
    """复盘看板 — 一次完整的复盘记录"""
    __tablename__ = "retro_boards"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(200), nullable=False, comment="复盘标题")
    context = Column(Text, nullable=True, comment="复盘背景/上下文")
    owner_id = Column(Integer, nullable=False, comment="复盘负责人ID")
    owner_name = Column(String(100), nullable=True, comment="负责人姓名")
    status = Column(String(20), nullable=False, default="draft", comment="状态: draft/in_progress/completed")
    tags = Column(String(500), nullable=True, comment="标签（逗号分隔）")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RetroStep(Base):
    """复盘步骤 — F1-F9 每个步骤的内容"""
    __tablename__ = "retro_steps"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    board_id = Column(Integer, nullable=False, index=True, comment="关联复盘看板ID")
    step_key = Column(String(5), nullable=False, comment="步骤编号: F1-F9")
    content = Column(Text, nullable=True, comment="该步骤的复盘内容")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RetroActionLog(Base):
    """操作日志 — 系统操作追踪"""
    __tablename__ = "retro_action_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    board_id = Column(Integer, nullable=True, index=True, comment="关联复盘看板ID")
    action = Column(String(50), nullable=False, comment="操作类型: create/update/complete/delete")
    operator_id = Column(Integer, nullable=True, comment="操作人ID")
    operator_name = Column(String(100), nullable=True, comment="操作人姓名")
    detail = Column(Text, nullable=True, comment="操作详情")
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# Pydantic Schemas
# ============================================================

class RetroBoardCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    context: Optional[str] = None
    tags: Optional[str] = None

class RetroBoardUpdate(BaseModel):
    title: Optional[str] = None
    context: Optional[str] = None
    status: Optional[str] = Field(None, pattern=r"^(draft|in_progress|completed)$")
    tags: Optional[str] = None

class RetroStepUpdate(BaseModel):
    content: str = ""


# ============================================================
# API 路由
# ============================================================

@router.get("/framework", summary="获取F1-F9复盘框架", description="返回F1-F9九步复盘模板的定义和提示")
def get_framework():
    """返回F1-F9复盘框架"""
    return {
        "code": 200,
        "message": "success",
        "data": {
            "total_steps": len(RETRO_STEPS),
            "steps": [{"key": k, "name": v["name"], "prompt": v["prompt"]} for k, v in RETRO_STEPS.items()],
            "description": "F1-F9 深度复盘模型 — 从目标回顾到行动跟踪的完整复盘闭环",
        },
    }


@router.post("/boards", summary="创建复盘看板", description="创建一个新的F1-F9复盘记录")
def create_retro_board(
    body: RetroBoardCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """创建复盘"""
    board = RetroBoard(
        title=body.title,
        context=body.context,
        owner_id=admin.id,
        owner_name=admin.name,
        tags=body.tags,
        status="draft",
    )
    db.add(board)
    db.flush()

    # 自动创建F1-F9空步骤
    for step_key in sorted(RETRO_STEPS.keys()):
        step = RetroStep(board_id=board.id, step_key=step_key, content="")
        db.add(step)

    # 记录操作日志
    log = RetroActionLog(
        board_id=board.id,
        action="create",
        operator_id=admin.id,
        operator_name=admin.name,
        detail=f"创建复盘: {body.title}",
    )
    db.add(log)
    db.commit()
    db.refresh(board)

    logger.info(f"[F1-F9复盘] 创建: {board.title} (ID={board.id})")
    return {
        "code": 200,
        "message": "复盘已创建，F1-F9步骤已初始化",
        "data": {"id": board.id, "title": board.title, "status": board.status, "created_at": board.created_at.isoformat()},
    }


@router.get("/boards", summary="列出复盘看板", description="分页列出所有复盘记录")
def list_retro_boards(
    status: Optional[str] = Query(None, pattern=r"^(draft|in_progress|completed)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """列出复盘看板"""
    q = db.query(RetroBoard)
    if status:
        q = q.filter(RetroBoard.status == status)
    total = q.count()
    items = q.order_by(desc(RetroBoard.updated_at)).offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for b in items:
        # 获取完成进度
        steps_done = db.query(RetroStep).filter(
            RetroStep.board_id == b.id,
            RetroStep.content != "",
            RetroStep.content.isnot(None),
        ).count()
        result.append({
            "id": b.id,
            "title": b.title,
            "context": b.context,
            "owner_name": b.owner_name,
            "status": b.status,
            "tags": b.tags,
            "progress": f"{steps_done}/9",
            "created_at": b.created_at.isoformat(),
            "updated_at": b.updated_at.isoformat() if b.updated_at else None,
        })

    return {"code": 200, "message": "success", "data": {"total": total, "page": page, "page_size": page_size, "items": result}}


@router.get("/boards/{board_id}", summary="获取复盘详情", description="获取复盘详情及其F1-F9各步骤内容")
def get_retro_board(
    board_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """获取复盘详情"""
    board = db.query(RetroBoard).filter(RetroBoard.id == board_id).first()
    if not board:
        raise HTTPException(status_code=404, detail="复盘看板不存在")

    steps = db.query(RetroStep).filter(RetroStep.board_id == board_id).order_by(RetroStep.step_key).all()
    steps_data = []
    for s in steps:
        framework = RETRO_STEPS.get(s.step_key, {})
        steps_data.append({
            "step_key": s.step_key,
            "step_name": framework.get("name", ""),
            "prompt": framework.get("prompt", ""),
            "content": s.content,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })

    # 操作日志
    logs = db.query(RetroActionLog).filter(RetroActionLog.board_id == board_id).order_by(desc(RetroActionLog.created_at)).limit(20).all()

    return {
        "code": 200,
        "message": "success",
        "data": {
            "board": {
                "id": board.id,
                "title": board.title,
                "context": board.context,
                "owner_name": board.owner_name,
                "status": board.status,
                "tags": board.tags,
                "created_at": board.created_at.isoformat(),
                "updated_at": board.updated_at.isoformat() if board.updated_at else None,
            },
            "steps": steps_data,
            "logs": [
                {
                    "action": l.action,
                    "operator_name": l.operator_name,
                    "detail": l.detail,
                    "created_at": l.created_at.isoformat(),
                }
                for l in logs
            ],
        },
    }


@router.put("/boards/{board_id}", summary="更新复盘看板", description="更新复盘标题/状态等基本信息")
def update_retro_board(
    board_id: int,
    body: RetroBoardUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """更新复盘"""
    board = db.query(RetroBoard).filter(RetroBoard.id == board_id).first()
    if not board:
        raise HTTPException(status_code=404, detail="复盘看板不存在")

    if body.title is not None:
        board.title = body.title
    if body.context is not None:
        board.context = body.context
    if body.status is not None:
        board.status = body.status
    if body.tags is not None:
        board.tags = body.tags

    log_detail = f"更新复盘: {body.model_dump(exclude_none=True)}"
    log = RetroActionLog(
        board_id=board_id,
        action="update",
        operator_id=admin.id,
        operator_name=admin.name,
        detail=log_detail,
    )
    db.add(log)
    db.commit()

    return {"code": 200, "message": "复盘已更新"}


@router.put("/boards/{board_id}/steps/{step_key}", summary="更新复盘步骤", description="更新某一步(F1-F9)的复盘内容")
def update_retro_step(
    board_id: int,
    step_key: str,
    body: RetroStepUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """更新复盘步骤内容"""
    if step_key not in RETRO_STEPS:
        raise HTTPException(status_code=400, detail=f"无效步骤: {step_key}，有效值为 F1-F9")

    step = db.query(RetroStep).filter(
        RetroStep.board_id == board_id,
        RetroStep.step_key == step_key,
    ).first()
    if not step:
        raise HTTPException(status_code=404, detail="步骤不存在")

    step.content = body.content
    step.updated_at = datetime.utcnow()

    # ── F8 知识归档：自动写入盖娅进化大脑 ─────────────────────
    if step_key == "F8" and body.content.strip():
        try:
            from app.ai.gaia_evolution_brain import get_gaia_brain
            from app.database import AsyncSession, engine

            brain = get_gaia_brain()

            async def _archive_to_gaia():
                async with AsyncSession(engine) as gaia_db:
                    await brain.ingest_knowledge(
                        db=gaia_db,
                        source="retrospective",
                        source_id=str(board_id),
                        knowledge_type="pattern",
                        title=f"复盘归档: {body.content[:76]}",
                        content=body.content,
                        tags=["retrospective", "F8", "knowledge_archive"],
                        confidence=0.8,
                    )
                    await gaia_db.commit()

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_archive_to_gaia())
            except RuntimeError:
                asyncio.run(_archive_to_gaia())

            logger.info("[Gaia] F8 知识已自动归档到盖娅进化大脑 (board_id=%s)", board_id)
        except (ImportError, Exception) as e:
            logger.warning("[Gaia] 知识归档失败，盖娅进化大脑不可用: %s", e)
    # ────────────────────────────────────────────────────────

    log = RetroActionLog(
        board_id=board_id,
        action="update_step",
        operator_id=admin.id,
        operator_name=admin.name,
        detail=f"更新步骤 {step_key} ({RETRO_STEPS[step_key]['name']})",
    )
    db.add(log)
    db.commit()

    return {"code": 200, "message": f"步骤 {step_key} 已更新"}


@router.get("/logs", summary="操作日志", description="查看系统操作日志（支持按复盘筛选）")
def list_action_logs(
    board_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    """列出操作日志"""
    q = db.query(RetroActionLog)
    if board_id:
        q = q.filter(RetroActionLog.board_id == board_id)
    logs = q.order_by(desc(RetroActionLog.created_at)).limit(limit).all()
    return {
        "code": 200,
        "message": "success",
        "data": [
            {
                "id": l.id,
                "board_id": l.board_id,
                "action": l.action,
                "operator_name": l.operator_name,
                "detail": l.detail,
                "created_at": l.created_at.isoformat(),
            }
            for l in logs
        ],
    }
