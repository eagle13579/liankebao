"""
工作流引擎 - API 路由

提供 RESTful 接口用于：
  - 触发事件 (手动/测试)
  - 查询规则和执行历史
  - 管理规则 (启用/禁用)
  - 手动执行规则
  - 查询通知
"""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from modules.workflow.workflow_engine import WorkflowEngine, RuleNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflow", tags=["workflow"])

# 全局引擎实例（由应用初始化时设置）
engine: WorkflowEngine | None = None


def get_engine() -> WorkflowEngine:
    """获取引擎实例"""
    if engine is None:
        raise HTTPException(status_code=503, detail="工作流引擎未初始化")
    return engine


# ── 请求/响应模型 ─────────────────────────────────────────────


class EventPayload(BaseModel):
    """事件触发请求"""
    event_type: str = Field(..., description="事件类型")
    entity_type: str | None = Field(None, description="实体类型 (deal/order/contact/product)")
    entity_id: int | None = Field(None, description="实体ID")
    payload: dict | None = Field(None, description="事件载荷")


class RuleEnableRequest(BaseModel):
    """规则启用/禁用请求"""
    enabled: bool = True


class EventResponse(BaseModel):
    """事件触发响应"""
    status: str
    message: str
    matched_rules: int
    results: list[dict] = []


# ── 事件触发 ─────────────────────────────────────────────────


@router.post("/events", summary="触发事件")
async def trigger_event(body: EventPayload):
    """手动触发一个事件，引擎将评估并执行匹配的规则"""
    eng = get_engine()
    results = eng.fire_event(
        event_type=body.event_type,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        payload=body.payload,
    )
    return EventResponse(
        status="ok",
        message=f"事件 {body.event_type} 已处理",
        matched_rules=len(results),
        results=results,
    )


# ── 规则管理 ─────────────────────────────────────────────────


@router.get("/rules", summary="获取所有规则")
async def list_rules(enabled: bool | None = Query(None, description="按启用状态筛选")):
    """获取所有已加载的规则列表"""
    eng = get_engine()
    all_rules = eng.get_all_rules()
    if enabled is not None:
        all_rules = [r for r in all_rules if r.get("enabled", True) == enabled]
    return {"status": "ok", "count": len(all_rules), "rules": all_rules}


@router.get("/rules/{rule_name}", summary="获取规则详情")
async def get_rule(rule_name: str):
    """获取单条规则详情"""
    eng = get_engine()
    rule = eng.get_rule(rule_name)
    if not rule:
        raise HTTPException(status_code=404, detail=f"规则 '{rule_name}' 不存在")
    return {"status": "ok", "rule": rule}


@router.put("/rules/{rule_name}/toggle", summary="启用/禁用规则")
async def toggle_rule(rule_name: str, body: RuleEnableRequest):
    """启用或禁用一条规则"""
    eng = get_engine()
    try:
        eng.enable_rule(rule_name, body.enabled)
    except RuleNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "status": "ok",
        "rule_name": rule_name,
        "enabled": body.enabled,
    }


@router.post("/rules/reload", summary="重新加载规则")
async def reload_rules():
    """从 YAML 文件重新加载所有规则"""
    eng = get_engine()
    eng.load_rules(reload=True)
    return {"status": "ok", "message": "规则已重新加载", "count": len(eng.get_all_rules())}


# ── 执行历史 ─────────────────────────────────────────────────


@router.get("/executions", summary="查询执行历史")
async def list_executions(
    rule_name: str | None = Query(None, description="按规则名筛选"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """查询工作流执行历史"""
    eng = get_engine()
    records = eng.get_execution_history(rule_name=rule_name, limit=limit, offset=offset)
    return {"status": "ok", "count": len(records), "executions": records}


# ── 事件日志 ─────────────────────────────────────────────────


@router.get("/events", summary="查询事件日志")
async def list_events(limit: int = Query(50, ge=1, le=500)):
    """查询引擎记录的事件"""
    eng = get_engine()
    events = eng.get_recent_events(limit=limit)
    return {"status": "ok", "count": len(events), "events": events}


# ── 手动执行 ─────────────────────────────────────────────────


class ManualExecutionRequest(BaseModel):
    """手动执行规则请求"""
    rule_name: str = Field(..., description="规则名称")
    context: dict | None = Field(None, description="自定义上下文")


@router.post("/execute", summary="手动执行规则")
async def manual_execute(body: ManualExecutionRequest):
    """手动执行指定规则（用于测试）"""
    eng = get_engine()
    rule = eng.get_rule(body.rule_name)
    if not rule:
        raise HTTPException(status_code=404, detail=f"规则 '{body.rule_name}' 不存在")
    if not rule.get("enabled", True):
        raise HTTPException(status_code=400, detail=f"规则 '{body.rule_name}' 当前已禁用")

    context = body.context or {"event": {"type": "manual", "rule": body.rule_name}}
    actions = rule.get("actions", [])
    results = eng._execute_actions(actions, context)

    eng._record_execution(
        rule_name=body.rule_name,
        trigger_type="manual",
        trigger_source="api",
        status="success",
        result=results,
    )

    return {
        "status": "ok",
        "rule_name": body.rule_name,
        "actions_count": len(results),
        "results": results,
    }


# ── 健康检查 ─────────────────────────────────────────────────


@router.get("/health", summary="引擎健康检查")
async def health():
    """工作流引擎健康检查"""
    eng = get_engine()
    rules_count = len(eng.get_all_rules())
    return {
        "status": "ok",
        "engine": "workflow_engine",
        "version": "1.0.0",
        "rules_loaded": rules_count,
        "db_path": eng._db_path,
    }


# ── 站内通知查询 ────────────────────────────────────────────


@router.get("/notifications/{user_id}", summary="查询用户通知")
async def list_notifications(
    user_id: int,
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """获取用户的通知列表"""
    eng = get_engine()
    notifications = eng.notifier.get_user_notifications(
        user_id=user_id, unread_only=unread_only, limit=limit, offset=offset
    )
    unread_count = eng.notifier.count_unread(user_id)
    return {
        "status": "ok",
        "count": len(notifications),
        "unread_count": unread_count,
        "notifications": notifications,
    }


@router.put("/notifications/{notification_id}/read", summary="标记通知已读")
async def mark_read(notification_id: int):
    """标记单条通知为已读"""
    eng = get_engine()
    ok = eng.notifier.mark_read(notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"通知 {notification_id} 不存在")
    return {"status": "ok", "notification_id": notification_id}


@router.put("/notifications/read-all/{user_id}", summary="标记全部已读")
async def mark_all_read(user_id: int):
    """标记用户所有通知为已读"""
    eng = get_engine()
    count = eng.notifier.mark_all_read(user_id)
    return {"status": "ok", "user_id": user_id, "marked_read": count}


# ── 初始化函数 ───────────────────────────────────────────────


def init_workflow_engine(app=None, rules_dir: str | None = None):
    """初始化工作流引擎，可选挂载到 FastAPI 应用

    Args:
        app:      FastAPI 应用实例（可选）
        rules_dir: 规则目录路径

    Returns:
        初始化后的 WorkflowEngine 实例
    """
    global engine

    eng = WorkflowEngine(rules_dir=rules_dir)

    # 创建种子规则文件
    eng.seed_rules()

    # 从 YAML 加载规则
    eng.load_rules()

    engine = eng
    logger.info("工作流引擎初始化完成, 已加载 %d 条规则", len(eng.get_all_rules()))

    if app is not None:
        app.include_router(router)
        logger.info("工作流引擎 API 路由已挂载")

    return eng
