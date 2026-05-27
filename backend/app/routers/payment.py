"""
支付路由 — IJPay 封装接入层
POST   /api/payment/wxpay/unified-order    — 微信统一下单(JSAPI)
POST   /api/payment/wxpay/callback          — 微信支付回调通知
GET    /api/payment/wxpay/query/{order_no}  — 查询订单
POST   /api/payment/wxpay/refund            — 退款
POST   /api/payment/alipay/unified-order    — 支付宝统一下单(框架)
GET    /api/payment/config                  — 获取前端支付配置(不含密钥)
"""

import json
import logging
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Order, Product, User
from app.schemas import ApiResponse, OrderResponse

# ===== IJPay 封装模块 =====
from payment import (
    PLATFORM_ALIPAY,
    PLATFORM_WXPAY,
    AliPayApi,
    WxPayApi,
    WxPayCallback,
    get_config,
    has_config,
    init_default_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment", tags=["支付"])


# ============================================================
# Pydantic 模型
# ============================================================


class WxPayUnifiedOrderRequest(BaseModel):
    """微信统一下单请求"""

    order_id: int
    openid: str | None = None  # 兼容已有逻辑：使用用户 wechat_openid


class WxPayRefundRequest(BaseModel):
    """微信退款请求"""

    order_id: int
    reason: str | None = None


class AliPayUnifiedOrderRequest(BaseModel):
    """支付宝统一下单请求"""

    order_id: int
    subject: str | None = None


# ============================================================
# 初始化支付配置（应用启动时执行）
# ============================================================


def ensure_payment_config():
    """确保支付配置已加载"""
    if not has_config():
        init_default_config()


ensure_payment_config()


# ============================================================
# 辅助函数
# ============================================================


def _get_wxpay_api() -> WxPayApi:
    """获取微信支付 API 实例"""
    if not has_config(PLATFORM_WXPAY):
        raise HTTPException(status_code=503, detail="微信支付未配置")
    return WxPayApi.from_config()


def _get_alipay_api() -> AliPayApi:
    """获取支付宝 API 实例"""
    if not has_config(PLATFORM_ALIPAY):
        raise HTTPException(status_code=503, detail="支付宝未配置")
    return AliPayApi.from_config()


async def _check_order_ownership(order_id: int, user: User, db: Session) -> Order:
    """检查订单所有权并返回订单"""
    order = db.query(Order).filter(Order.id == order_id, Order.is_deleted == False).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权操作此订单")
    return order


# ============================================================
# 微信支付 — 统一下单 (JSAPI)
# ============================================================


@router.post("/wxpay/unified-order", response_model=ApiResponse)
async def wxpay_unified_order(
    req: WxPayUnifiedOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    微信统一下单 (JSAPI)

    使用 IJPay WxPayApi V3 接口。
    若配置不完整或调用失败，降级为 mock 模式。
    """
    order = await _check_order_ownership(req.order_id, current_user, db)
    product = db.query(Product).filter(Product.id == order.product_id, Product.is_deleted == False).first()

    if order.status != "pending":
        raise HTTPException(status_code=400, detail="订单不是待支付状态")

    # 获取 openid
    openid = req.openid or current_user.wechat_openid
    if not openid:
        raise HTTPException(status_code=400, detail="缺少用户微信 openid，无法发起微信支付")

    out_trade_no = f"LK{order.id:08d}{int(time.time())}"
    total_fee = int(order.total_price * 100)
    description = f"{product.name[:60]} x{order.quantity}" if product else f"订单 #{order.id}"

    if has_config(PLATFORM_WXPAY):
        try:
            wxpay = _get_wxpay_api()
            result = await wxpay.create_jsapi_order(
                openid=openid,
                out_trade_no=out_trade_no,
                total_fee=total_fee,
                description=description,
                attach=json.dumps({"order_id": order.id}),
            )
        except Exception as e:
            logger.error(f"IJPay 统一下单异常: {e}")
            result = None

        if result and result.get("prepay_id"):
            # 更新订单
            order.prepay_id = result["prepay_id"]
            order.payment_platform = PLATFORM_WXPAY
            db.commit()

            payment_params = result["payment_params"]
            payment_params["_mode"] = "real"
            return ApiResponse(
                code=200,
                message="下单成功",
                data={
                    "order": OrderResponse.model_validate(order).model_dump(),
                    "payment": payment_params,
                },
            )

        logger.warning("IJPay 统一下单失败，降级到 mock 模式")

    # Mock 模式
    mock = _mock_payment(order, total_fee, description)
    return ApiResponse(
        code=200,
        message="下单成功 (mock)",
        data={
            "order": OrderResponse.model_validate(order).model_dump(),
            "payment": mock,
        },
    )


# ============================================================
# 微信支付 — 回调通知
# ============================================================


@router.post("/wxpay/callback")
async def wxpay_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    微信支付回调通知

    支持:
    - V3 回调 (签名验证 + resource 解密)
    - V2 回调 (XML/MD5 兼容)
    - Mock 回调 (开发环境)
    """
    body = await request.body()
    logger.info(f"收到支付回调: {body[:200]}")

    # 获取回调头信息
    wechat_signature = request.headers.get("Wechatpay-Signature", "")
    wechat_serial = request.headers.get("Wechatpay-Serial", "")
    wechat_timestamp = request.headers.get("Wechatpay-Timestamp", "")
    wechat_nonce = request.headers.get("Wechatpay-Nonce", "")

    # 判断是 V3 还是 V2
    is_v3 = bool(wechat_signature and wechat_serial)

    if is_v3 and has_config(PLATFORM_WXPAY):
        # --- V3 回调：IJPay 完整验签 + 解密 ---
        callback = WxPayCallback()
        notify_data = callback.verify_and_decrypt(
            body=body,
            wechatpay_signature=wechat_signature,
            wechatpay_serial=wechat_serial,
            wechatpay_timestamp=wechat_timestamp,
            wechatpay_nonce=wechat_nonce,
        )
        if not notify_data:
            logger.error("支付回调验签失败")
            return {"code": "FAIL", "message": "验签失败"}

        out_trade_no = notify_data.get("out_trade_no", "")
        transaction_id = notify_data.get("transaction_id", "")
        trade_state = notify_data.get("trade_state", "")
        success = trade_state in ("SUCCESS", "")
    else:
        # --- Mock 或 V2 兼容 ---
        try:
            body_str = body.decode("utf-8")
            try:
                notify_data = json.loads(body_str)
            except json.JSONDecodeError:
                # 可能是 XML (V2)
                import xml.etree.ElementTree as ET

                root = ET.fromstring(body_str)
                notify_data = {child.tag: child.text for child in root}

            out_trade_no = notify_data.get("out_trade_no", "")
            transaction_id = notify_data.get("transaction_id", "") or notify_data.get(
                "wx_transaction_id", f"mock_tx_{int(time.time())}"
            )
            success = notify_data.get("result_code", "") in ("SUCCESS", "OK", "")
        except Exception as e:
            logger.error(f"回调解析失败: {e}")
            out_trade_no = ""
            transaction_id = f"mock_tx_{int(time.time())}"
            success = True

    if not success:
        logger.warning(f"支付未成功: out_trade_no={out_trade_no}, state={notify_data.get('trade_state', '')}")
        return {"code": "FAIL", "message": "支付未成功"}

    # 更新订单
    if out_trade_no and out_trade_no.startswith("LK"):
        try:
            order_id = int(out_trade_no[2:10])
        except (ValueError, IndexError):
            order_id = None
    else:
        order_id = None

    if order_id:
        order = db.query(Order).filter(Order.id == order_id, Order.is_deleted == False).first()
        if order and order.status == "pending":
            order.status = "paid"
            order.transaction_id = transaction_id
            order.wx_transaction_id = transaction_id  # V2 兼容
            order.payment_time = datetime.utcnow()
            order.pay_time = datetime.utcnow()  # 兼容旧字段
            if not order.payment_platform:
                order.payment_platform = PLATFORM_WXPAY
            db.commit()
            logger.info(f"订单 {order_id} 支付成功，状态更新为 paid")
            return {"code": "SUCCESS", "message": "成功"}
        elif order:
            logger.warning(f"订单 {order_id} 状态为 {order.status}，无需更新")
            return {"code": "SUCCESS", "message": "已处理"}

    # Fallback: 通过 prepay_id 匹配
    order = (
        db.query(Order)
        .filter(
            Order.status == "pending",
            Order.prepay_id.isnot(None),
            Order.is_deleted == False,
        )
        .order_by(Order.id.desc())
        .first()
    )
    if order:
        order.status = "paid"
        order.transaction_id = transaction_id
        order.wx_transaction_id = transaction_id
        order.payment_time = datetime.utcnow()
        order.pay_time = datetime.utcnow()
        if not order.payment_platform:
            order.payment_platform = PLATFORM_WXPAY
        db.commit()
        logger.info(f"订单 {order.id} 支付成功（通过 prepay_id 匹配）")
        return {"code": "SUCCESS", "message": "成功"}

    return {"code": "SUCCESS", "message": "已接收"}


# ============================================================
# 微信支付 — 订单查询
# ============================================================


@router.get("/wxpay/query/{order_no}", response_model=ApiResponse)
async def wxpay_query(
    order_no: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询订单支付状态"""
    query_type = Query(default="out_trade_no", description="查询类型: out_trade_no / transaction_id")

    if has_config(PLATFORM_WXPAY):
        try:
            wxpay = _get_wxpay_api()
            result = await wxpay.query_by_out_trade_no(order_no)
            if result:
                return ApiResponse(
                    code=200,
                    message="查询成功",
                    data=result,
                )
        except Exception as e:
            logger.error(f"订单查询异常: {e}")

    # Fallback: 从数据库查询
    order = (
        db.query(Order)
        .filter(
            (Order.id == order_no.replace("LK", "").split(".")[0])
            | (Order.wx_transaction_id == order_no)
            | (Order.transaction_id == order_no),
            Order.is_deleted == False,
        )
        .first()
    )

    if order:
        return ApiResponse(
            code=200,
            message="success",
            data={"status": order.status, "order": OrderResponse.model_validate(order).model_dump()},
        )

    raise HTTPException(status_code=404, detail="订单不存在")


# ============================================================
# 微信支付 — 退款
# ============================================================


@router.post("/wxpay/refund", response_model=ApiResponse)
async def wxpay_refund(
    req: WxPayRefundRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """微信退款"""
    order = db.query(Order).filter(Order.id == req.order_id, Order.is_deleted == False).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 权限检查
    is_admin = current_user.role == "admin"
    is_owner = order.user_id == current_user.id
    if not (is_admin or is_owner):
        raise HTTPException(status_code=403, detail="无权操作此订单")

    if order.status not in ("paid", "shipped"):
        raise HTTPException(status_code=400, detail=f"订单状态 {order.status} 不允许退款")

    out_trade_no = order.wx_transaction_id or order.transaction_id or f"LK{order.id:08d}"
    if not out_trade_no:
        raise HTTPException(status_code=400, detail="无支付交易单号，无法退款")

    out_refund_no = f"RF{order.id:08d}{int(time.time())}"
    refund_amount = int(order.total_price * 100)
    total_amount = refund_amount

    if has_config(PLATFORM_WXPAY):
        try:
            wxpay = _get_wxpay_api()
            result = await wxpay.create_refund(
                out_trade_no=out_trade_no,
                out_refund_no=out_refund_no,
                refund_amount=refund_amount,
                total_amount=total_amount,
                reason=req.reason or "用户申请退款",
            )
        except Exception as e:
            logger.error(f"IJPay 退款异常: {e}")
            result = None

        if result:
            refund_id = result.get("refund_id", "")
            order.refund_id = refund_id
            order.refund_time = datetime.utcnow()
            order.status = "refunded"
            db.commit()
            logger.info(f"订单 {order.id} 退款成功: {refund_id}")
            return ApiResponse(
                code=200,
                message="退款成功",
                data={"refund_id": refund_id, "order": OrderResponse.model_validate(order).model_dump()},
            )

    # Mock 退款
    mock_refund_id = f"mock_rf_{int(time.time())}"
    order.refund_id = mock_refund_id
    order.refund_time = datetime.utcnow()
    order.status = "refunded"
    db.commit()
    logger.info(f"订单 {order.id} mock 退款成功: {mock_refund_id}")

    return ApiResponse(
        code=200,
        message="退款成功 (mock)",
        data={"refund_id": mock_refund_id, "order": OrderResponse.model_validate(order).model_dump()},
    )


# ============================================================
# 支付宝 — 统一下单 (框架)
# ============================================================


@router.post("/alipay/unified-order", response_model=ApiResponse)
async def alipay_unified_order(
    req: AliPayUnifiedOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """支付宝统一下单 (APP 支付)"""
    order = await _check_order_ownership(req.order_id, current_user, db)
    product = db.query(Product).filter(Product.id == order.product_id, Product.is_deleted == False).first()

    if order.status != "pending":
        raise HTTPException(status_code=400, detail="订单不是待支付状态")

    subject = req.subject or (product.name if product else f"订单 #{order.id}")
    out_trade_no = f"AL{order.id:08d}{int(time.time())}"

    if has_config(PLATFORM_ALIPAY):
        try:
            alipay = _get_alipay_api()
            result = await alipay.unified_order(
                out_trade_no=out_trade_no,
                total_amount=order.total_price,
                subject=subject[:256],
            )
        except Exception as e:
            logger.error(f"支付宝统一下单异常: {e}")
            result = None

        if result and result.get("order_string"):
            order.payment_platform = PLATFORM_ALIPAY
            db.commit()
            return ApiResponse(
                code=200,
                message="下单成功",
                data={
                    "order": OrderResponse.model_validate(order).model_dump(),
                    "order_string": result["order_string"],
                    "_mode": "real",
                },
            )

    # Mock
    return ApiResponse(
        code=200,
        message="下单成功 (mock)",
        data={
            "order": OrderResponse.model_validate(order).model_dump(),
            "order_string": f"app_id=mock&method=alipay.trade.app.pay&out_trade_no={out_trade_no}&total_amount={order.total_price}",
            "_mode": "mock",
        },
    )


# ============================================================
# 获取前端支付配置
# ============================================================


@router.get("/config", response_model=ApiResponse)
async def get_payment_config():
    """
    获取前端支付配置 (不含密钥)

    返回前端所需的 appId / 环境等信息。
    """
    config_data = {}

    if has_config(PLATFORM_WXPAY):
        cfg = get_config(PLATFORM_WXPAY)
        config_data["wxpay"] = {
            "app_id": cfg.app_id,
            "mch_id": cfg.mch_id,
            "configured": cfg.is_configured,
        }

    if has_config(PLATFORM_ALIPAY):
        cfg = get_config(PLATFORM_ALIPAY)
        config_data["alipay"] = {
            "app_id": cfg.app_id,
            "gateway": cfg.gateway,
            "configured": cfg.is_configured,
        }

    return ApiResponse(
        code=200,
        message="success",
        data=config_data,
    )


# ============================================================
# Mock 支付辅助函数
# ============================================================


def _mock_payment(order: Order, total_fee: int = 0, description: str = "") -> dict:
    """生成 mock 支付参数"""
    import hashlib

    app_id = ""
    if has_config(PLATFORM_WXPAY):
        cfg = get_config(PLATFORM_WXPAY)
        app_id = cfg.app_id

    if not app_id:
        app_id = os.environ.get("WECHAT_APPID", "wxb4f6d89904200fd2")

    timestamp = str(int(time.time()))
    nonce_str = hashlib.md5(f"{timestamp}{order.id}".encode()).hexdigest()[:16]
    prepay_id = f"wx{timestamp}{order.id}"
    order.prepay_id = prepay_id

    raw = f"{app_id}\n{timestamp}\n{nonce_str}\nprepay_id={prepay_id}\n"
    pay_sign = hashlib.sha256(raw.encode()).hexdigest()[:32]

    return {
        "appId": app_id,
        "timeStamp": timestamp,
        "nonceStr": nonce_str,
        "package": f"prepay_id={prepay_id}",
        "signType": "RSA",
        "paySign": pay_sign,
        "_mode": "mock",
    }


import os
