"""
链客宝 — 外部集成模块 API 路由
=================================
迁移自旧版链客宝 backend/modules/external/
适配 chainke-full 架构。

端点:
  POST   /api/external/webhook/{module_name}      — 接收外部系统 Webhook 事件
  GET    /api/external/modules                     — 列出已注册的外部模块
  POST   /api/external/modules                     — 注册新的外部模块
  GET    /api/external/modules/{module_name}        — 查询外部模块详情
  DELETE /api/external/modules/{module_name}        — 注销外部模块
  POST   /api/external/modules/{module_name}/install   — 安装外部模块
  GET    /api/external/modules/{module_name}/health    — 健康检查

使用方式（在其他路由中注册适配器）:
    from features.external.services.webhook import WebhookReceiver
    receiver = WebhookReceiver()
    receiver.register_module("my_module", my_adapter_instance)

    然后通过 /api/external/webhook/my_module 接收事件。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from features.external.models.external_module import ExternalModule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/external", tags=["外部集成模块"])

# ── 全局 WebhookReceiver 实例 ────────────────────────────────
# 其他模块可导入此实例并注册适配器:
#   from app.routers.external import webhook_receiver
#   webhook_receiver.register_module("xxx", adapter)
from features.external.services.webhook import WebhookReceiver

webhook_receiver = WebhookReceiver()


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================


class RegisterModuleRequest(BaseModel):
    """注册外部模块请求"""
    name: str = Field(..., min_length=1, max_length=100, description="外部模块唯一名称")
    version: str = Field(default="1.0.0", max_length=20, description="模块版本号")
    description: str | None = Field(default=None, description="模块描述")
    api_key: str | None = Field(default=None, max_length=255, description="API Key")
    api_secret: str | None = Field(default=None, max_length=255, description="API Secret")
    webhook_url: str | None = Field(default=None, max_length=500, description="外部回调地址")
    webhook_secret: str | None = Field(default=None, max_length=255, description="Webhook 签名密钥")
    webhook_algo: str = Field(default="hmac-sha256", max_length=20, description="签名算法")


class ApiResponse(BaseModel):
    """统一 API 响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")
    data: dict | None = Field(default=None, description="响应数据")


# ===================================================================
# 路由实现
# ===================================================================


@router.post("/webhook/{module_name}", response_model=ApiResponse)
async def receive_webhook(
    module_name: str,
    request: Request,
):
    """接收外部系统 Webhook 事件

    将请求体解析为 JSON，通过 WebhookReceiver 分发给对应适配器。
    可选签名验证（需在注册模块时配置 webhook_secret 和 webhook_algo）。
    """
    try:
        raw_body = await request.body()
        data = await request.json()
        event = data.get("event", "unknown")

        # 尝试获取模块注册信息以获取签名密钥
        signature = request.headers.get("X-Signature")
        secret = None
        algo = "hmac-sha256"

        # 检查已注册适配器
        adapter = webhook_receiver.get_module(module_name)
        if adapter is None:
            return ApiResponse(
                code=404,
                message=f"外部模块 '{module_name}' 未注册适配器，请先调用 register_module()",
            )

        result = await webhook_receiver.dispatch(
            module_name=module_name,
            event=event,
            data=data,
            raw_body=raw_body,
            signature=signature,
            secret=secret,
            algo=algo,
            verify=False,  # 签名验证需根据模块配置动态启用
        )
        return ApiResponse(code=0 if result.get("status") == "ok" else 1, data=result)
    except Exception as e:
        logger.exception("Webhook 处理失败: %s", e)
        return ApiResponse(code=500, message=f"Webhook 处理失败: {str(e)}")


@router.get("/modules", response_model=ApiResponse)
async def list_modules(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """列出所有已注册的外部模块（从数据库查询）"""
    try:
        query = db.query(ExternalModule).filter(ExternalModule.is_active == True)
        total = query.count()
        modules = query.offset((page - 1) * limit).limit(limit).all()

        items = []
        for m in modules:
            items.append({
                "id": m.id,
                "name": m.name,
                "version": m.version,
                "description": m.description,
                "is_active": m.is_active,
                "is_installed": m.is_installed,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
                "installed_at": m.installed_at.isoformat() if m.installed_at else None,
            })

        return ApiResponse(
            data={
                "total": total,
                "page": page,
                "page_size": limit,
                "items": items,
            },
        )
    except Exception as e:
        logger.exception("查询外部模块列表失败: %s", e)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/modules", response_model=ApiResponse, status_code=201)
async def register_module(
    req: RegisterModuleRequest,
    db: Session = Depends(get_db),
):
    """注册新的外部模块（写入数据库）"""
    try:
        existing = db.query(ExternalModule).filter(
            ExternalModule.name == req.name,
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"模块 '{req.name}' 已存在")

        module = ExternalModule(
            name=req.name,
            version=req.version,
            description=req.description,
            api_key=req.api_key,
            api_secret=req.api_secret,
            webhook_url=req.webhook_url,
            webhook_secret=req.webhook_secret,
            webhook_algo=req.webhook_algo,
        )
        db.add(module)
        db.commit()
        db.refresh(module)

        logger.info("外部模块 '%s' 已注册到数据库 (id=%s)", req.name, module.id)
        return ApiResponse(
            code=0,
            message="注册成功",
            data={
                "id": module.id,
                "name": module.name,
                "version": module.version,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("注册外部模块失败: %s", e)
        raise HTTPException(status_code=500, detail=f"注册失败: {str(e)}")


@router.get("/modules/{module_name}", response_model=ApiResponse)
async def get_module(
    module_name: str,
    db: Session = Depends(get_db),
):
    """查询外部模块详情"""
    try:
        module = db.query(ExternalModule).filter(
            ExternalModule.name == module_name,
            ExternalModule.is_active == True,
        ).first()
        if module is None:
            raise HTTPException(status_code=404, detail=f"外部模块 '{module_name}' 不存在")

        return ApiResponse(
            data={
                "id": module.id,
                "name": module.name,
                "version": module.version,
                "description": module.description,
                "api_key": module.api_key,
                "webhook_url": module.webhook_url,
                "webhook_algo": module.webhook_algo,
                "is_active": module.is_active,
                "is_installed": module.is_installed,
                "created_at": module.created_at.isoformat() if module.created_at else None,
                "updated_at": module.updated_at.isoformat() if module.updated_at else None,
                "installed_at": module.installed_at.isoformat() if module.installed_at else None,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("查询外部模块失败: %s", e)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.delete("/modules/{module_name}", response_model=ApiResponse)
async def delete_module(
    module_name: str,
    db: Session = Depends(get_db),
):
    """注销外部模块（软删除: 设置 is_active=False）"""
    try:
        module = db.query(ExternalModule).filter(
            ExternalModule.name == module_name,
        ).first()
        if module is None:
            raise HTTPException(status_code=404, detail=f"外部模块 '{module_name}' 不存在")

        module.is_active = False
        db.commit()

        # 同时从内存注册表中移除
        webhook_receiver.unregister_module(module_name)

        logger.info("外部模块 '%s' 已注销", module_name)
        return ApiResponse(code=0, message="注销成功", data={"name": module_name})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("注销外部模块失败: %s", e)
        raise HTTPException(status_code=500, detail=f"注销失败: {str(e)}")


@router.post("/modules/{module_name}/install", response_model=ApiResponse)
async def install_module(
    module_name: str,
    db: Session = Depends(get_db),
):
    """安装外部模块（调用适配器的 install 方法）"""
    try:
        adapter = webhook_receiver.get_module(module_name)
        if adapter is None:
            raise HTTPException(
                status_code=400,
                detail=f"外部模块 '{module_name}' 未注册适配器实例",
            )

        module = db.query(ExternalModule).filter(
            ExternalModule.name == module_name,
        ).first()
        if module is None:
            raise HTTPException(status_code=404, detail=f"外部模块 '{module_name}' 不存在于数据库")

        success = await adapter.install()
        if success:
            module.is_installed = True
            module.installed_at = module.updated_at  # 使用当前时间
            db.commit()
            return ApiResponse(code=0, message=f"模块 '{module_name}' 安装成功")
        else:
            return ApiResponse(code=1, message=f"模块 '{module_name}' 安装失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("安装外部模块失败: %s", e)
        raise HTTPException(status_code=500, detail=f"安装失败: {str(e)}")


@router.get("/modules/{module_name}/health", response_model=ApiResponse)
async def healthcheck_module(
    module_name: str,
):
    """检查外部模块健康状况"""
    try:
        adapter = webhook_receiver.get_module(module_name)
        if adapter is None:
            raise HTTPException(
                status_code=404,
                detail=f"外部模块 '{module_name}' 未注册适配器实例",
            )

        healthy = await adapter.healthcheck()
        return ApiResponse(
            data={
                "module_name": module_name,
                "healthy": healthy,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("健康检查失败: %s", e)
        raise HTTPException(status_code=500, detail=f"健康检查失败: {str(e)}")
