"""链客宝 — 支付宝支付 API 路由
===================================
从旧版链客宝 recharge/routes.py 提取支付宝支付逻辑，适配 chainke-full 架构。

端点:
  POST /api/payment/alipay/create       — 创建支付宝支付订单
  POST /api/payment/alipay/callback     — 支付宝异步回调通知
  POST /api/payment/alipay/refund       — 支付宝退款
  GET  /api/payment/alipay/query/{out_trade_no}  — 查询订单

注意:
  - 金额单位：分（接口内部自动转换元）
  - 回调验签使用 RSA2
"""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from payment.providers.alipay import AliPayConfig, AliPayProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment/alipay", tags=["支付宝支付"])


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================


class AlipayCreateRequest(BaseModel):
    """创建支付宝支付订单请求"""
    out_trade_no: str = Field(..., min_length=1, max_length=64, description="商户订单号")
    total_fee: int = Field(..., ge=1, description="订单金额（单位：分）")
    subject: str = Field(..., min_length=1, max_length=128, description="商品标题")
    description: str = Field(default="", max_length=256, description="商品描述")
    trade_type: str = Field(default="APP", pattern="^(APP|PAGE|WAP)$", description="交易类型")
    buyer_id: str = Field(default="", description="买家支付宝用户ID")
    timeout_express: str = Field(default="30m", description="超时时间")
    passback_params: str = Field(default="", description="公共回传参数")
    return_url: str = Field(default="", description="同步跳转URL (PAGE/WAP)")
    quit_url: str = Field(default="", description="用户退出URL (WAP)")


class ApiResponse(BaseModel):
    """统一 API 响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")
    data: Optional[dict] = Field(default=None, description="响应数据")


# ===================================================================
# 工具函数
# ===================================================================


def get_alipay_provider() -> AliPayProvider:
    """获取支付宝提供者实例"""
    config = AliPayConfig.from_env()
    if not config.is_configured:
        logger.warning("支付宝未完整配置，使用 mock 模式")
    return AliPayProvider(config=config)


# ===================================================================
# POST /api/payment/alipay/create   — 创建支付订单
# ===================================================================


@router.post("/create", response_model=ApiResponse)
async def alipay_create_order(req: AlipayCreateRequest):
    """创建支付宝支付订单

    支持三种交易类型:
    - APP: 返回 order_string (App SDK 调起)
    - PAGE: 返回 form_html (电脑网站支付)
    - WAP: 返回 form_html (手机网站支付)
    """
    try:
        provider = get_alipay_provider()
        result = await provider.pay(
            openid=req.buyer_id,
            out_trade_no=req.out_trade_no,
            total_fee=req.total_fee,
            description=req.description or req.subject,
            trade_type=req.trade_type,
            subject=req.subject,
            timeout_express=req.timeout_express,
            passback_params=req.passback_params or None,
            return_url=req.return_url or None,
            quit_url=req.quit_url or None,
        )

        if result.success:
            return ApiResponse(
                code=0,
                message="success",
                data={
                    "out_trade_no": result.out_trade_no,
                    **(result.data or {}),
                },
            )
        else:
            return ApiResponse(
                code=1,
                message=result.message,
            )

    except Exception as e:
        logger.error(f"支付宝创建订单失败: {e}")
        return ApiResponse(code=500, message=f"创建订单失败: {str(e)}")


# ===================================================================
# POST /api/payment/alipay/callback  — 支付宝异步回调
# ===================================================================


@router.post("/callback", response_model=ApiResponse)
async def alipay_callback(request: Request):
    """支付宝异步回调通知处理

    支付宝通过 POST 表单提交回调参数。
    验签通过后更新订单状态。
    """
    try:
        body_bytes = await request.body()
        provider = get_alipay_provider()

        # 验签
        cb_result = await provider.callback_verify(body=body_bytes)

        if not cb_result.verified:
            logger.warning(f"支付宝回调验签失败: {cb_result.message}")
            return ApiResponse(code=400, message="验签失败")

        params = cb_result.data or {}
        out_trade_no = params.get("out_trade_no", "")
        trade_no = params.get("trade_no", "")
        trade_status = params.get("trade_status", "")
        total_amount = params.get("total_amount", "0")

        logger.info(
            f"支付宝回调: out_trade_no={out_trade_no}, "
            f"trade_no={trade_no}, status={trade_status}"
        )

        # 处理交易状态
        if trade_status == "TRADE_SUCCESS" or trade_status == "TRADE_FINISHED":
            # TODO: 更新数据库订单状态
            logger.info(f"支付宝订单支付成功: {out_trade_no}")
            return ApiResponse(
                code=0,
                message="success",
                data={
                    "out_trade_no": out_trade_no,
                    "trade_no": trade_no,
                    "trade_status": trade_status,
                },
            )

        return ApiResponse(code=0, message="received")

    except Exception as e:
        logger.error(f"支付宝回调处理失败: {e}")
        return ApiResponse(code=500, message=f"回调处理失败: {str(e)}")


# ===================================================================
# POST /api/payment/alipay/refund    — 退款
# ===================================================================


class AlipayRefundRequest(BaseModel):
    """支付宝退款请求"""
    out_trade_no: str = Field(..., description="商户订单号")
    out_refund_no: str = Field(..., description="退款请求号（商户侧唯一）")
    refund_amount: int = Field(..., ge=1, description="退款金额（单位：分）")
    total_amount: int = Field(..., ge=1, description="原订单总金额（单位：分）")
    reason: str = Field(default="", description="退款原因")
    trade_no: str = Field(default="", description="支付宝交易号（二选一）")


@router.post("/refund", response_model=ApiResponse)
async def alipay_refund(req: AlipayRefundRequest):
    """支付宝退款
    
    支持部分退款和全额退款。
    """
    try:
        provider = get_alipay_provider()
        result = await provider.refund(
            out_trade_no=req.out_trade_no,
            out_refund_no=req.out_refund_no,
            refund_amount=req.refund_amount,
            total_amount=req.total_amount,
            reason=req.reason or None,
            trade_no=req.trade_no or None,
        )

        if result.success:
            return ApiResponse(
                code=0,
                message="success",
                data={
                    "out_trade_no": result.out_trade_no,
                    "trade_no": result.provider_order_id,
                    **(result.data or {}),
                },
            )
        else:
            return ApiResponse(code=1, message=result.message)

    except Exception as e:
        logger.error(f"支付宝退款失败: {e}")
        return ApiResponse(code=500, message=f"退款失败: {str(e)}")


# ===================================================================
# GET /api/payment/alipay/query/{out_trade_no}  — 查询订单
# ===================================================================


@router.get("/query/{out_trade_no}", response_model=ApiResponse)
async def alipay_query_order(out_trade_no: str, trade_no: str = ""):
    """查询支付宝订单状态

    Args:
        out_trade_no: 商户订单号
        trade_no: 支付宝交易号（可选）
    """
    try:
        provider = get_alipay_provider()
        kwargs = {}
        if trade_no:
            kwargs["trade_no"] = trade_no

        result = await provider.query(out_trade_no=out_trade_no, **kwargs)

        if result.success:
            return ApiResponse(
                code=0,
                message="success",
                data={
                    "out_trade_no": result.out_trade_no,
                    "trade_no": result.provider_order_id,
                    **(result.data or {}),
                },
            )
        else:
            return ApiResponse(code=1, message=result.message)

    except Exception as e:
        logger.error(f"支付宝订单查询失败: {e}")
        return ApiResponse(code=500, message=f"查询失败: {str(e)}")


# ===================================================================
# GET /api/payment/alipay/query_refund/{out_trade_no}  — 查询退款
# ===================================================================


@router.get("/query_refund/{out_trade_no}", response_model=ApiResponse)
async def alipay_query_refund(
    out_trade_no: str,
    out_refund_no: str = "",
    trade_no: str = "",
):
    """查询支付宝退款状态"""
    try:
        provider = get_alipay_provider()
        kwargs = {}
        if trade_no:
            kwargs["trade_no"] = trade_no

        result = await provider.query_refund(
            out_trade_no=out_trade_no,
            out_refund_no=out_refund_no or None,
            **kwargs,
        )

        if result.success:
            return ApiResponse(
                code=0,
                message="success",
                data={
                    "out_trade_no": result.out_trade_no,
                    **(result.data or {}),
                },
            )
        else:
            return ApiResponse(code=1, message=result.message)

    except Exception as e:
        logger.error(f"支付宝退款查询失败: {e}")
        return ApiResponse(code=500, message=f"退款查询失败: {str(e)}")


# ===================================================================
# POST /api/payment/alipay/close/{out_trade_no}  — 关闭订单
# ===================================================================


@router.post("/close/{out_trade_no}", response_model=ApiResponse)
async def alipay_close_order(out_trade_no: str, trade_no: str = ""):
    """关闭未支付的支付宝订单

    Args:
        out_trade_no: 商户订单号
        trade_no: 支付宝交易号（可选）
    """
    try:
        provider = get_alipay_provider()
        kwargs = {}
        if trade_no:
            kwargs["trade_no"] = trade_no

        success = await provider.close_order(
            out_trade_no=out_trade_no, **kwargs
        )

        if success:
            return ApiResponse(
                code=0,
                message="success",
                data={"out_trade_no": out_trade_no},
            )
        else:
            return ApiResponse(code=1, message="关闭失败")

    except Exception as e:
        logger.error(f"支付宝订单关闭失败: {e}")
        return ApiResponse(code=500, message=f"关闭失败: {str(e)}")


# ===================================================================
# 健康检查
# ===================================================================


@router.get("/health", tags=["支付宝支付"])
async def alipay_health():
    """支付宝支付模块健康检查"""
    config = AliPayConfig.from_env()
    return {
        "status": "ok",
        "module": "alipay",
        "configured": config.is_configured,
        "gateway": config.gateway,
    }
