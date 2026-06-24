"""
链客宝开发者门户 API (v2 — DB持久化)
====================================
提供:
  1. API Key管理 — 创建/撤销/查询 (DB持久化, 权限分级)
  2. Webhook订阅管理 — CRUD + 测试
  3. API文档 — 自动从FastAPI路由生成, 交互式可测试
  4. 用量统计 — 调用次数/错误率/延迟, 按API Key维度

端点:
  GET    /api/developer/portal                    — 开发者门户首页
  POST   /api/developer/api-keys                  — 创建API Key
  GET    /api/developer/api-keys                  — 查询API Keys
  DELETE /api/developer/api-keys/{key_id}         — 撤销API Key
  POST   /api/developer/api-keys/{key_id}/renew   — 续期/重新生成
  POST   /api/developer/webhooks                  — 创建Webhook订阅
  GET    /api/developer/webhooks                  — 查询Webhook订阅
  GET    /api/developer/webhooks/{sub_id}         — 查询单个Webhook
  PUT    /api/developer/webhooks/{sub_id}         — 更新Webhook
  DELETE /api/developer/webhooks/{sub_id}         — 删除Webhook订阅
  POST   /api/developer/webhooks/test             — 发送测试事件
  GET    /api/developer/docs                      — API文档 (OpenAPI JSON)
  GET    /api/developer/docs/swagger              — Swagger UI 页面
  GET    /api/developer/usage                     — 用量统计
  GET    /api/developer/usage/timeline            — 用量时间线 (按小时)
"""

import hashlib
import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.middleware.api_key_auth import hash_api_key
from app.models import (
    ApiKey as ApiKeyModel,
)
from app.models import (
    ApiUsageLog,
    User,
    WebhookDeliveryLog,
    WebhookSubscriptionDB,
)
from app.webhook_v2 import (
    EventType,
    WebhookDispatcher,
    WebhookEvent,
    create_subscription,
    delete_subscription,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/developer", tags=["开发者门户"])

# ============================================================
# API Key 权限分级配置
# ============================================================

TIER_CONFIG = {
    "free": {
        "rate_limit": 100,
        "scopes": ["read"],
        "name": "免费版",
    },
    "pro": {
        "rate_limit": 1000,
        "scopes": ["read", "write"],
        "name": "专业版",
    },
    "enterprise": {
        "rate_limit": 10000,
        "scopes": ["read", "write", "admin"],
        "name": "企业版",
    },
}

ALLOWED_TIERS = list(TIER_CONFIG.keys())

# ============================================================
# Pydantic 模型
# ============================================================


class CreateApiKeyRequest(BaseModel):
    name: str = Field(..., description="API Key 名称", max_length=100)
    scopes: list[str] = Field(default=["read"], description="权限范围")
    tier: str = Field(default="free", description=f"API等级: {', '.join(ALLOWED_TIERS)}")


class UpdateApiKeyRequest(BaseModel):
    name: str | None = Field(None, max_length=100)
    scopes: list[str] | None = None
    tier: str | None = None


class ApiKeyResponse(BaseModel):
    key_id: str
    name: str
    key_prefix: str
    scopes: list[str]
    tier: str
    is_active: bool
    created_at: str
    last_used_at: str | None = None

    class Config:
        from_attributes = True


class ApiKeyCreatedResponse(BaseModel):
    key_id: str
    name: str
    key: str  # 仅创建时返回
    key_prefix: str
    scopes: list[str]
    tier: str
    warning: str = "请立即保存此Key，之后无法再次查看完整Key"


class CreateWebhookRequest(BaseModel):
    url: str = Field(..., description="Webhook 回调URL", max_length=1024)
    events: list[str] = Field(..., description="订阅事件类型列表")
    secret: str | None = Field(None, description="签名密钥(可选,自动生成)")
    active: bool = Field(default=True, description="是否启用")


class UpdateWebhookRequest(BaseModel):
    url: str | None = Field(None, max_length=1024)
    events: list[str] | None = None
    secret: str | None = None
    active: bool | None = None


class WebhookResponse(BaseModel):
    sub_id: str
    url: str
    events: list[str]
    active: bool
    created_at: str
    last_delivery_at: str | None = None
    last_delivery_status: str | None = None

    class Config:
        from_attributes = True


class UsageStatsResponse(BaseModel):
    total_calls: int
    success_count: int
    error_count: int
    error_rate: float
    avg_latency_ms: float
    period: str
    by_endpoint: list[dict[str, Any]] = []


class UsageTimelinePoint(BaseModel):
    time: str
    calls: int
    errors: int
    avg_latency: float


# ============================================================
# 开发者门户首页
# ============================================================


@router.get("/portal")
def developer_portal():
    """开发者门户首页 — 提供SDK/文档/API Keys/Webhook入口"""
    return {
        "code": 0,
        "message": "欢迎使用链客宝开发者平台",
        "data": {
            "name": "链客宝 API",
            "version": "1.0.0",
            "base_url": "https://www.go-aiport.com/api",
            "docs": {
                "swagger": "/docs",
                "redoc": "/redoc",
                "openapi_json": "/openapi.json",
                "developer_swagger": "/api/developer/docs/swagger",
            },
            "sdks": {
                "typescript": "npm install @liankebao/sdk",
                "python": "pip install liankebao-payment-sdk",
                "generate": "python scripts/generate_api_sdk.py",
            },
            "authentication": {
                "method": "Bearer Token (JWT) + API Key",
                "header": "Authorization: Bearer <jwt_token>",
                "api_key_header": "X-API-Key: <api_key>",
                "get_started": "/api/developer/api-keys",
            },
            "api_tiers": TIER_CONFIG,
            "webhooks": {
                "signature": "HMAC-SHA256",
                "header": "X-Liankebao-Signature: sha256=<signature>",
                "format": "CloudEvents v1.0",
                "max_retries": 3,
                "retry_backoff": "指数退避 (2s, 4s, 8s)",
                "dead_letter": "支持死信队列",
            },
            "rate_limits": {tier: config["rate_limit"] for tier, config in TIER_CONFIG.items()},
            "endpoints": {
                "api_keys": "/api/developer/api-keys",
                "webhooks": "/api/developer/webhooks",
                "usage": "/api/developer/usage",
                "docs": "/api/developer/docs",
            },
            "event_types": [
                {
                    "type": e.value,
                    "description": _get_event_description(e),
                }
                for e in EventType
            ],
        },
    }


def _get_event_description(event_type: EventType) -> str:
    """获取事件类型的中文描述"""
    descriptions = {
        EventType.MATCH_CREATED: "匹配创建",
        EventType.MATCH_ACCEPTED: "匹配接受",
        EventType.MATCH_REJECTED: "匹配拒绝",
        EventType.MATCH_COMPLETED: "匹配完成",
        EventType.ORDER_CREATED: "订单创建",
        EventType.ORDER_PAID: "订单支付",
        EventType.ORDER_SHIPPED: "订单发货",
        EventType.ORDER_COMPLETED: "订单完成",
        EventType.ORDER_CANCELLED: "订单取消",
        EventType.PAYMENT_SUCCEEDED: "支付成功",
        EventType.PAYMENT_FAILED: "支付失败",
        EventType.PAYMENT_REFUNDED: "支付退款",
        EventType.USER_REGISTERED: "用户注册",
        EventType.USER_VERIFIED: "用户认证",
        EventType.USER_TRUST_CHANGED: "信任分变更",
        EventType.ENTERPRISE_VERIFIED: "企业认证",
        EventType.ENTERPRISE_UPDATED: "企业信息更新",
        EventType.CARD_CREATED: "名片创建",
        EventType.CARD_UPDATED: "名片更新",
        EventType.CARD_VIEWED: "名片被查看",
    }
    return descriptions.get(event_type, event_type.value)


# ============================================================
# API Key 管理 (DB持久化)
# ============================================================


def _generate_api_key() -> tuple[str, str, str]:
    """生成API Key: 返回 (raw_key, key_id, prefix)"""
    raw = secrets.token_hex(32)
    key_id = f"lk_{secrets.token_hex(6)}"
    prefix = raw[:8]
    return raw, key_id, prefix


def _validate_scopes(scopes: list[str]) -> list[str]:
    """验证并规范化权限范围"""
    valid_scopes = {"read", "write", "admin"}
    normalized = [s.strip().lower() for s in scopes if s.strip().lower() in valid_scopes]
    if not normalized:
        normalized = ["read"]
    return normalized


@router.post("/api-keys", response_model=dict)
def create_api_key(
    req: CreateApiKeyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建 API Key（DB持久化）"""
    # 验证 tier
    tier = req.tier.lower()
    if tier not in ALLOWED_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"无效API等级: {tier}，可选: {', '.join(ALLOWED_TIERS)}",
        )

    # 验证 scopes
    scopes = _validate_scopes(req.scopes)

    raw_key, key_id, prefix = _generate_api_key()
    key_hash = hash_api_key(raw_key)

    tier_config = TIER_CONFIG[tier]

    key_record = ApiKeyModel(
        key_id=key_id,
        key_hash=key_hash,
        key_prefix=prefix,
        name=req.name,
        user_id=current_user.id,
        scopes=",".join(scopes),
        tier=tier,
        rate_limit_per_hour=tier_config["rate_limit"],
        is_active=True,
    )
    db.add(key_record)
    db.commit()
    db.refresh(key_record)

    logger.info(f"API Key 创建成功: {key_id} (用户: {current_user.id}, 等级: {tier})")

    return {
        "code": 0,
        "message": "API Key 创建成功",
        "data": ApiKeyCreatedResponse(
            key_id=key_id,
            name=req.name,
            key=raw_key,
            key_prefix=prefix,
            scopes=scopes,
            tier=tier,
            warning="请立即保存此Key，之后无法再次查看完整Key",
        ).model_dump(),
    }


@router.get("/api-keys", response_model=dict)
def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询当前用户的所有 API Keys"""
    keys = (
        db.query(ApiKeyModel)
        .filter(ApiKeyModel.user_id == current_user.id)
        .order_by(ApiKeyModel.created_at.desc())
        .all()
    )
    result = []
    for k in keys:
        result.append(
            ApiKeyResponse(
                key_id=k.key_id,
                name=k.name,
                key_prefix=k.key_prefix,
                scopes=k.scopes.split(",") if k.scopes else ["read"],
                tier=k.tier,
                is_active=k.is_active and k.revoked_at is None,
                created_at=k.created_at.isoformat() if k.created_at else "",
                last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
            ).model_dump()
        )
    return {"code": 0, "data": result, "total": len(result)}


@router.delete("/api-keys/{key_id}", response_model=dict)
def revoke_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """撤销 API Key"""
    key = (
        db.query(ApiKeyModel)
        .filter(
            ApiKeyModel.key_id == key_id,
            ApiKeyModel.user_id == current_user.id,
        )
        .first()
    )
    if not key:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    key.is_active = False
    key.revoked_at = datetime.utcnow()
    db.commit()

    logger.info(f"API Key 已撤销: {key_id}")
    return {"code": 0, "message": f"API Key {key_id} 已撤销"}


@router.post("/api-keys/{key_id}/renew", response_model=dict)
def renew_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """重新生成 API Key（保留原配置，更换密钥）"""
    key = (
        db.query(ApiKeyModel)
        .filter(
            ApiKeyModel.key_id == key_id,
            ApiKeyModel.user_id == current_user.id,
        )
        .first()
    )
    if not key:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    # 生成新密钥
    raw_key, new_key_id, prefix = _generate_api_key()
    key.key_hash = hash_api_key(raw_key)
    key.key_prefix = prefix
    key.is_active = True
    key.revoked_at = None
    db.commit()

    return {
        "code": 0,
        "message": "API Key 已重新生成",
        "data": ApiKeyCreatedResponse(
            key_id=key.key_id,
            name=key.name,
            key=raw_key,
            key_prefix=prefix,
            scopes=key.scopes.split(",") if key.scopes else ["read"],
            tier=key.tier,
            warning="旧Key已失效，请立即保存新Key",
        ).model_dump(),
    }


# ============================================================
# Webhook 订阅管理 (DB持久化)
# ============================================================


@router.post("/webhooks", response_model=dict)
def create_webhook(
    req: CreateWebhookRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建 Webhook 订阅（DB持久化）"""
    # 验证事件类型
    try:
        event_types = [EventType(e) for e in req.events]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效事件类型: {e}")

    sub_id = f"wh_{secrets.token_hex(8)}"

    # 生成或使用提供的 secret
    if req.secret:
        secret = req.secret
    else:
        secret = hashlib.sha256(f"{sub_id}-{time.time()}".encode()).hexdigest()[:32]

    # 同时存入内存存储（给webhook_v2使用）和DB
    sub = create_subscription(
        sub_id=sub_id,
        url=req.url,
        events=event_types,
        secret=secret,
    )
    sub.active = req.active

    # DB持久化
    db_sub = WebhookSubscriptionDB(
        sub_id=sub_id,
        url=req.url,
        events=json.dumps([e.value for e in event_types]),
        secret=secret,
        active=req.active,
        user_id=current_user.id,
    )
    db.add(db_sub)
    db.commit()

    logger.info(f"Webhook订阅创建成功: {sub_id} → {req.url}")

    return {
        "code": 0,
        "message": "Webhook 订阅创建成功",
        "data": WebhookResponse(
            sub_id=sub.id,
            url=sub.url,
            events=[e.value for e in sub.events],
            active=sub.active,
            created_at=sub.created_at,
        ).model_dump(),
    }


@router.get("/webhooks", response_model=dict)
def list_webhooks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询 Webhook 订阅列表"""
    subs = (
        db.query(WebhookSubscriptionDB)
        .filter(WebhookSubscriptionDB.user_id == current_user.id)
        .order_by(WebhookSubscriptionDB.created_at.desc())
        .all()
    )
    result = []
    for s in subs:
        events = json.loads(s.events) if s.events else []
        result.append(
            WebhookResponse(
                sub_id=s.sub_id,
                url=s.url,
                events=events,
                active=s.active,
                created_at=s.created_at.isoformat() if s.created_at else "",
                last_delivery_at=s.last_delivery_at.isoformat() if s.last_delivery_at else None,
                last_delivery_status=s.last_delivery_status,
            ).model_dump()
        )
    return {"code": 0, "data": result, "total": len(result)}


@router.get("/webhooks/{sub_id}", response_model=dict)
def get_webhook(
    sub_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询单个 Webhook 订阅详情"""
    s = (
        db.query(WebhookSubscriptionDB)
        .filter(
            WebhookSubscriptionDB.sub_id == sub_id,
            WebhookSubscriptionDB.user_id == current_user.id,
        )
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Webhook订阅不存在")

    events = json.loads(s.events) if s.events else []
    # 获取投递日志
    delivery_logs = (
        db.query(WebhookDeliveryLog)
        .filter(WebhookDeliveryLog.subscription_id == s.id)
        .order_by(WebhookDeliveryLog.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "code": 0,
        "data": {
            **WebhookResponse(
                sub_id=s.sub_id,
                url=s.url,
                events=events,
                active=s.active,
                created_at=s.created_at.isoformat() if s.created_at else "",
                last_delivery_at=s.last_delivery_at.isoformat() if s.last_delivery_at else None,
                last_delivery_status=s.last_delivery_status,
            ).model_dump(),
            "secret": s.secret,
            "delivery_logs": [
                {
                    "event_type": log.event_type,
                    "event_id": log.event_id,
                    "status": log.status,
                    "attempt": log.attempt,
                    "response_code": log.response_code,
                    "error_message": log.error_message,
                    "created_at": log.created_at.isoformat() if log.created_at else "",
                }
                for log in delivery_logs
            ],
        },
    }


@router.put("/webhooks/{sub_id}", response_model=dict)
def update_webhook(
    sub_id: str,
    req: UpdateWebhookRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新 Webhook 订阅"""
    s = (
        db.query(WebhookSubscriptionDB)
        .filter(
            WebhookSubscriptionDB.sub_id == sub_id,
            WebhookSubscriptionDB.user_id == current_user.id,
        )
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Webhook订阅不存在")

    updated = False
    if req.url is not None:
        s.url = req.url
        updated = True
    if req.events is not None:
        try:
            [EventType(e) for e in req.events]  # 验证
            s.events = json.dumps(req.events)
            updated = True
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"无效事件类型: {e}")
    if req.secret is not None:
        s.secret = req.secret
        updated = True
    if req.active is not None:
        s.active = req.active
        updated = True

    if updated:
        db.commit()
        # 同步更新内存存储
        from app.webhook_v2 import _subscriptions

        if sub_id in _subscriptions:
            mem_sub = _subscriptions[sub_id]
            if req.url is not None:
                mem_sub.url = req.url
            if req.events is not None:
                mem_sub.events = [EventType(e) for e in req.events]
            if req.secret is not None:
                mem_sub.secret = req.secret
            if req.active is not None:
                mem_sub.active = req.active

    return {"code": 0, "message": "Webhook订阅已更新"}


@router.delete("/webhooks/{sub_id}", response_model=dict)
def delete_webhook(
    sub_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除 Webhook 订阅"""
    s = (
        db.query(WebhookSubscriptionDB)
        .filter(
            WebhookSubscriptionDB.sub_id == sub_id,
            WebhookSubscriptionDB.user_id == current_user.id,
        )
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Webhook订阅不存在")

    db.delete(s)
    db.commit()

    # 同步删除内存存储
    delete_subscription(sub_id)

    return {"code": 0, "message": f"Webhook订阅 {sub_id} 已删除"}


@router.post("/webhooks/test", response_model=dict)
def test_webhook(
    event_type: str = Query(..., description="测试事件类型"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发送测试 Webhook 事件"""
    try:
        ev_type = EventType(event_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效事件类型: {event_type}")

    event = WebhookEvent(
        id=str(uuid.uuid4()),
        type=ev_type,
        data={"test": True, "user_id": current_user.id, "message": "这是一个测试事件"},
        subject=str(current_user.id),
    )

    dispatcher = WebhookDispatcher()
    result = dispatcher.dispatch(event)

    # 记录投递日志
    for detail in result.get("details", []):
        log = WebhookDeliveryLog(
            subscription_id=0,  # 测试事件无真实sub_id
            event_type=event_type,
            event_id=event.id,
            status="success" if detail.get("success") else "failed",
            attempt=detail.get("attempt", 1),
            error_message=detail.get("status", ""),
        )
        db.add(log)
    db.commit()

    return {"code": 0, "message": "测试事件已发送", "data": result}


# ============================================================
# API Docs — 自动从FastAPI路由生成
# ============================================================


@router.get("/docs")
def get_api_docs(request: Request):
    """返回API文档汇总 (OpenAPI兼容格式)"""
    # 从FastAPI app获取路由信息
    app = request.app
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    routes.append(
                        {
                            "path": route.path,
                            "method": method,
                            "name": route.name or "",
                            "summary": getattr(route, "summary", ""),
                        }
                    )

    return {
        "code": 0,
        "data": {
            "title": "链客宝 API 文档",
            "version": "1.0.0",
            "base_url": str(request.base_url).rstrip("/"),
            "openapi_json": "/openapi.json",
            "swagger_ui": "/docs",
            "redoc_ui": "/redoc",
            "developer_swagger": "/api/developer/docs/swagger",
            "total_endpoints": len(routes),
            "endpoints": routes[:200],  # 限制数量
            "authentication": {
                "jwt": {
                    "header": "Authorization: Bearer <token>",
                    "description": "JWT Bearer Token，通过 /api/auth/login 获取",
                },
                "api_key": {
                    "header": "X-API-Key: <key>",
                    "description": "API Key，通过 /api/developer/api-keys 创建",
                    "tiers": TIER_CONFIG,
                },
            },
            "event_types": [
                {
                    "type": e.value,
                    "description": _get_event_description(e),
                }
                for e in EventType
            ],
        },
    }


@router.get("/docs/swagger", response_class=HTMLResponse)
def swagger_ui_html():
    """内嵌 Swagger UI 页面 (交互式可测试)"""
    return HTMLResponse(r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>链客宝 API 文档 — Swagger UI</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.11.8/swagger-ui.min.css" />
  <style>
    body { margin: 0; background: #1a1a2e; }
    .swagger-ui .topbar { display: none; }
    .swagger-ui .info .title { color: #e0e0e0; }
    .swagger-ui .scheme-container { background: #16213e; }
    .swagger-ui .opblock-tag { color: #e0e0e0; }
    .swagger-ui .opblock .opblock-summary-path { color: #64ffda; }
    .swagger-ui .opblock .opblock-summary-description { color: #b0b0b0; }
    .swagger-ui .opblock-description-wrapper p { color: #ccc; }
    .swagger-ui .parameter__name { color: #e0e0e0; }
    .swagger-ui .parameter__type { color: #aaa; }
    .swagger-ui label { color: #ccc; }
    .swagger-ui .response-col_status { color: #ccc; }
    .swagger-ui .response-col_description { color: #ccc; }
    .swagger-ui .model-box { color: #ccc; }
    .swagger-ui table thead tr td, .swagger-ui table thead tr th { color: #ccc; }
    .swagger-ui .btn { color: #e0e0e0; }
    .swagger-ui select { color: #e0e0e0; background: #1a1a2e; }
    .swagger-ui input { color: #e0e0e0; background: #1a1a2e; border-color: #333; }
    .swagger-ui textarea { color: #e0e0e0; background: #1a1a2e; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.11.8/swagger-ui-bundle.min.js"><\/script>
  <script>
    SwaggerUIBundle({
      url: "/openapi.json",
      dom_id: "#swagger-ui",
      deepLinking: true,
      presets: [
        SwaggerUIBundle.presets.apis,
        SwaggerUIBundle.SwaggerUIStandalonePreset,
      ],
      plugins: [SwaggerUIBundle.plugins.DownloadUrl],
      layout: "BaseLayout",
      docExpansion: "list",
      filter: true,
      tryItOutEnabled: true,
      requestInterceptor: function(request) {
        const token = localStorage.getItem('token');
        if (token && !request.headers['Authorization']) {
          request.headers['Authorization'] = 'Bearer ' + token;
        }
        return request;
      },
    });
  </script>
</body>
</html>""")


# ============================================================
# 用量统计
# ============================================================


@router.get("/usage", response_model=dict)
def get_usage_stats(
    period: str = Query("24h", regex="^(1h|24h|7d|30d)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取 API 用量统计"""
    now = datetime.utcnow()
    if period == "1h":
        since = now - timedelta(hours=1)
    elif period == "7d":
        since = now - timedelta(days=7)
    elif period == "30d":
        since = now - timedelta(days=30)
    else:
        since = now - timedelta(hours=24)

    logs = (
        db.query(ApiUsageLog)
        .filter(
            ApiUsageLog.user_id == current_user.id,
            ApiUsageLog.created_at >= since,
        )
        .all()
    )

    total = len(logs)
    errors = sum(1 for l in logs if l.status_code >= 400)
    latency_sum = sum(l.latency_ms for l in logs)
    success = total - errors

    # 按端点聚合
    endpoint_stats: dict[str, dict] = {}
    for l in logs:
        key = f"{l.method} {l.endpoint}"
        if key not in endpoint_stats:
            endpoint_stats[key] = {"calls": 0, "errors": 0, "latency_sum": 0}
        endpoint_stats[key]["calls"] += 1
        if l.status_code >= 400:
            endpoint_stats[key]["errors"] += 1
        endpoint_stats[key]["latency_sum"] += l.latency_ms

    by_endpoint = [
        {
            "endpoint": ep,
            "calls": stats["calls"],
            "errors": stats["errors"],
            "avg_latency_ms": round(stats["latency_sum"] / max(stats["calls"], 1), 2),
        }
        for ep, stats in sorted(endpoint_stats.items(), key=lambda x: -x[1]["calls"])
    ]

    return {
        "code": 0,
        "data": UsageStatsResponse(
            total_calls=total,
            success_count=success,
            error_count=errors,
            error_rate=round(errors / max(total, 1) * 100, 2),
            avg_latency_ms=round(latency_sum / max(total, 1), 2),
            period=period,
            by_endpoint=by_endpoint,
        ).model_dump(),
    }


@router.get("/usage/timeline", response_model=dict)
def get_usage_timeline(
    period: str = Query("24h", regex="^(1h|24h|7d|30d)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取用量时间线 (按小时聚合)"""
    now = datetime.utcnow()
    if period == "1h":
        since = now - timedelta(hours=1)
        bucket = "minute"
    elif period == "7d":
        since = now - timedelta(days=7)
        bucket = "hour"
    elif period == "30d":
        since = now - timedelta(days=30)
        bucket = "day"
    else:
        since = now - timedelta(hours=24)
        bucket = "hour"

    logs = (
        db.query(ApiUsageLog)
        .filter(
            ApiUsageLog.user_id == current_user.id,
            ApiUsageLog.created_at >= since,
        )
        .order_by(ApiUsageLog.created_at.asc())
        .all()
    )

    # 按时间聚合
    timeline: dict[str, dict] = {}
    for l in logs:
        if bucket == "minute":
            key = l.created_at.strftime("%Y-%m-%d %H:%M")
        elif bucket == "hour":
            key = l.created_at.strftime("%Y-%m-%d %H:00")
        else:
            key = l.created_at.strftime("%Y-%m-%d")

        if key not in timeline:
            timeline[key] = {"calls": 0, "errors": 0, "latency_sum": 0, "count": 0}
        timeline[key]["calls"] += 1
        if l.status_code >= 400:
            timeline[key]["errors"] += 1
        timeline[key]["latency_sum"] += l.latency_ms
        timeline[key]["count"] += 1

    points = [
        UsageTimelinePoint(
            time=t,
            calls=data["calls"],
            errors=data["errors"],
            avg_latency=round(data["latency_sum"] / max(data["count"], 1), 2),
        )
        for t, data in sorted(timeline.items())
    ]

    return {"code": 0, "data": {"bucket": bucket, "points": [p.model_dump() for p in points]}}


# ============================================================
# Dashboard 概览
# ============================================================


@router.get("/dashboard")
def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """开发者控制台 Dashboard 概览数据"""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # API Keys 统计
    total_keys = db.query(ApiKeyModel).filter(ApiKeyModel.user_id == current_user.id).count()
    active_keys = (
        db.query(ApiKeyModel)
        .filter(
            ApiKeyModel.user_id == current_user.id,
            ApiKeyModel.is_active == True,
            ApiKeyModel.revoked_at.is_(None),
        )
        .count()
    )

    # Webhook 统计
    total_webhooks = db.query(WebhookSubscriptionDB).filter(WebhookSubscriptionDB.user_id == current_user.id).count()
    active_webhooks = (
        db.query(WebhookSubscriptionDB)
        .filter(
            WebhookSubscriptionDB.user_id == current_user.id,
            WebhookSubscriptionDB.active == True,
        )
        .count()
    )

    # 今日调用
    today_calls = (
        db.query(ApiUsageLog)
        .filter(
            ApiUsageLog.user_id == current_user.id,
            ApiUsageLog.created_at >= today_start,
        )
        .count()
    )

    # 今日错误
    today_errors = (
        db.query(ApiUsageLog)
        .filter(
            ApiUsageLog.user_id == current_user.id,
            ApiUsageLog.created_at >= today_start,
            ApiUsageLog.status_code >= 400,
        )
        .count()
    )

    return {
        "code": 0,
        "data": {
            "api_keys": {"total": total_keys, "active": active_keys},
            "webhooks": {"total": total_webhooks, "active": active_webhooks},
            "today": {
                "calls": today_calls,
                "errors": today_errors,
                "error_rate": round(today_errors / max(today_calls, 1) * 100, 2),
            },
        },
    }
