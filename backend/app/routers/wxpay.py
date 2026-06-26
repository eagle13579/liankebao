"""链客宝 — 微信支付 API 路由
=================================
从旧版链客宝 payment/wxpay/__init__.py 提取微信支付逻辑，适配 chainke-full 架构。

端点:
  POST /api/payment/wxpay/create       — 创建微信支付订单 (V3 JSAPI)
  POST /api/payment/wxpay/callback     — 微信支付异步回调通知 (V3)
  POST /api/payment/wxpay/refund       — 微信退款
  GET  /api/payment/wxpay/query/{out_trade_no}  — 查询订单
  POST /api/payment/wxpay/close/{out_trade_no}  — 关闭订单

注意:
  - 金额单位：分
  - V3 回调验签使用 RSA-SHA256 + AES-GCM 解密
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from payment.providers.wxpay import WxPayConfig, WxPayProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment/wxpay", tags=["微信支付"])


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================


class WxpayCreateRequest(BaseModel):
    """创建微信支付订单请求"""
    out_trade_no: str = Field(..., min_length=1, max_length=64, description="商户订单号")
    total_fee: int = Field(..., ge=1, description="订单金额（单位：分）")
    description: str = Field(..., min_length=1, max_length=128, description="商品描述")
    openid: str = Field(..., min_length=1, description="用户微信 openid")
    attach: str = Field(default="", max_length=127, description="附加数据")
    time_expire: str = Field(default="", description="订单过期时间 (RFC 3339)")
    goods_tag: str = Field(default="", description="商品标记")


class WxpayRefundRequest(BaseModel):
    """微信退款请求"""
    out_trade_no: str = Field(..., description="商户订单号")
    out_refund_no: str = Field(..., description="退款请求号（商户侧唯一）")
    refund_amount: int = Field(..., ge=1, description="退款金额（单位：分）")
    total_amount: int = Field(..., ge=1, description="原订单总金额（单位：分）")
    reason: str = Field(default="", description="退款原因")
    notify_url: str = Field(default="", description="退款结果通知 URL")


class ApiResponse(BaseModel):
    """统一 API 响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")
    data: Optional[dict] = Field(default=None, description="响应数据")


# ===================================================================
# 工具函数
# ===================================================================


def get_wxpay_provider() -> WxPayProvider:
    """获取微信支付提供者实例"""
    config = WxPayConfig.from_env()
    if not config.is_configured:
        logger.warning("微信支付未完整配置，使用 mock 模式")
    return WxPayProvider(config=config)


# ===================================================================
# POST /api/payment/wxpay/create   — 创建支付订单
# ===================================================================


@router.post("/create", response_model=ApiResponse)
async def wxpay_create_order(req: WxpayCreateRequest):
    """创建微信 V3 JSAPI 支付订单

    返回 prepay_id 及 JSAPI 调起支付所需参数。
    """
    try:
        provider = get_wxpay_provider()
        kwargs = {}
        if req.attach:
            kwargs["attach"] = req.attach
        if req.time_expire:
            kwargs["time_expire"] = req.time_expire
        if req.goods_tag:
            kwargs["goods_tag"] = req.goods_tag

        result = await provider.pay(
            openid=req.openid,
            out_trade_no=req.out_trade_no,
            total_fee=req.total_fee,
            description=req.description,
            **kwargs,
        )

        if result.success:
            return ApiResponse(
                code=0,
                message="success",
                data={
                    "out_trade_no": result.out_trade_no,
                    "prepay_id": (result.data or {}).get("prepay_id", ""),
                    "payment_params": (result.data or {}).get("payment_params", {}),
                },
            )
        else:
            return ApiResponse(
                code=1,
                message=result.message,
            )

    except Exception as e:
        logger.error(f"微信创建订单失败: {e}")
        return ApiResponse(code=500, message=f"创建订单失败: {str(e)}")


# ===================================================================
# POST /api/payment/wxpay/callback  — 微信支付异步回调
# ===================================================================


@router.post("/callback", response_model=ApiResponse)
async def wxpay_callback(request: Request):
    """微信支付 V3 异步回调通知处理

    验签 -> 解密 resource -> 更新订单状态。
    返回 {"code": "SUCCESS"} 给微信服务器。
    """
    try:
        body_bytes = await request.body()
        provider = get_wxpay_provider()

        # 验签
        cb_result = await provider.callback_verify(
            body=body_bytes,
            headers=dict(request.headers),
        )

        if not cb_result.verified:
            logger.warning(f"微信回调验签失败: {cb_result.message}")
            return ApiResponse(code=400, message="验签失败")

        # 解密后的回调数据
        event_data = cb_result.data or {}
        out_trade_no = event_data.get("out_trade_no", "")
        transaction_id = event_data.get("transaction_id", "")
        trade_state = event_data.get("trade_state", "")
        trade_type = event_data.get("trade_type", "")
        amount_info = event_data.get("amount", {})
        total_fee = amount_info.get("total", 0) if isinstance(amount_info, dict) else 0

        logger.info(
            f"微信回调: out_trade_no={out_trade_no}, "
            f"transaction_id={transaction_id}, "
            f"trade_state={trade_state}"
        )

        # 处理交易状态
        if trade_state == "SUCCESS":
            # TODO: 更新数据库订单状态
            logger.info(f"微信订单支付成功: {out_trade_no}")
            return ApiResponse(
                code=0,
                message="success",
                data={
                    "out_trade_no": out_trade_no,
                    "transaction_id": transaction_id,
                    "trade_state": trade_state,
                    "total_fee": total_fee,
                },
            )

        # 其他状态（如 REFUND/CLOSED/NOTPAY）记录日志后返回成功
        return ApiResponse(code=0, message=f"received: {trade_state}")

    except Exception as e:
        logger.error(f"微信回调处理失败: {e}")
        return ApiResponse(code=500, message=f"回调处理失败: {str(e)}")


# ===================================================================
# POST /api/payment/wxpay/refund    — 退款
# ===================================================================


@router.post("/refund", response_model=ApiResponse)
async def wxpay_refund(req: WxpayRefundRequest):
    """微信 V3 退款

    支持部分退款和全额退款。
    退款需要商户证书 (双向 SSL)。
    """
    try:
        provider = get_wxpay_provider()
        kwargs = {}
        if req.notify_url:
            kwargs["notify_url"] = req.notify_url

        result = await provider.refund(
            out_trade_no=req.out_trade_no,
            out_refund_no=req.out_refund_no,
            refund_amount=req.refund_amount,
            total_amount=req.total_amount,
            reason=req.reason or None,
            **kwargs,
        )

        if result.success:
            return ApiResponse(
                code=0,
                message="success",
                data={
                    "out_trade_no": result.out_trade_no,
                    "refund_id": result.provider_order_id,
                    **(result.data or {}),
                },
            )
        else:
            return ApiResponse(code=1, message=result.message)

    except Exception as e:
        logger.error(f"微信退款失败: {e}")
        return ApiResponse(code=500, message=f"退款失败: {str(e)}")


# ===================================================================
# GET /api/payment/wxpay/query/{out_trade_no}  — 查询订单
# ===================================================================


@router.get("/query/{out_trade_no}", response_model=ApiResponse)
async def wxpay_query_order(out_trade_no: str, transaction_id: str = ""):
    """查询微信支付订单状态

    Args:
        out_trade_no: 商户订单号
        transaction_id: 微信支付订单号（可选，优先使用）
    """
    try:
        provider = get_wxpay_provider()
        kwargs = {}
        if transaction_id:
            kwargs["transaction_id"] = transaction_id

        result = await provider.query(
            out_trade_no=out_trade_no, **kwargs
        )

        if result.success:
            return ApiResponse(
                code=0,
                message="success",
                data={
                    "out_trade_no": result.out_trade_no,
                    "transaction_id": result.provider_order_id,
                    **(result.data or {}),
                },
            )
        else:
            return ApiResponse(code=1, message=result.message)

    except Exception as e:
        logger.error(f"微信订单查询失败: {e}")
        return ApiResponse(code=500, message=f"查询失败: {str(e)}")


# ===================================================================
# POST /api/payment/wxpay/close/{out_trade_no}  — 关闭订单
# ===================================================================


@router.post("/close/{out_trade_no}", response_model=ApiResponse)
async def wxpay_close_order(out_trade_no: str):
    """关闭未支付的微信订单

    Args:
        out_trade_no: 商户订单号
    """
    try:
        provider = get_wxpay_provider()
        success = await provider.close_order(out_trade_no=out_trade_no)

        if success:
            return ApiResponse(
                code=0,
                message="success",
                data={"out_trade_no": out_trade_no},
            )
        else:
            return ApiResponse(code=1, message="关闭失败")

    except Exception as e:
        logger.error(f"微信订单关闭失败: {e}")
        return ApiResponse(code=500, message=f"关闭失败: {str(e)}")


# ===================================================================
# GET /api/payment/wxpay/query_refund/{out_refund_no}  — 查询退款
# ===================================================================


@router.get("/query_refund/{out_refund_no}", response_model=ApiResponse)
async def wxpay_query_refund(out_refund_no: str):
    """查询微信退款状态

    Args:
        out_refund_no: 商户退款单号
    """
    try:
        provider = get_wxpay_provider()
        result = await provider.query_refund(out_refund_no=out_refund_no)

        if result.success:
            return ApiResponse(
                code=0,
                message="success",
                data={
                    "out_refund_no": result.out_trade_no,
                    "refund_id": result.provider_order_id,
                    **(result.data or {}),
                },
            )
        else:
            return ApiResponse(code=1, message=result.message)

    except Exception as e:
        logger.error(f"微信退款查询失败: {e}")
        return ApiResponse(code=500, message=f"退款查询失败: {str(e)}")


# ===================================================================
# 健康检查
# ===================================================================


@router.get("/health", tags=["微信支付"])
async def wxpay_health():
    """微信支付模块健康检查"""
    config = WxPayConfig.from_env()
    return {
        "status": "ok",
        "module": "wxpay",
        "configured": config.is_configured,
        "mch_id": config.mch_id if config.mch_id else "(not set)",
    }
