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

from app.database import get_db
from app.models import Contract, MembershipOrder, Order, PaymentTransaction, Product, User
from app.rbac import require_roles
from app.retry_engine import RetryTask, get_retry_engine
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

# ===== OpenTelemetry 自定义追踪 =====
from app.telemetry import tracer

router = APIRouter(prefix="/api/payment", tags=["支付"])

# 支付接口需要 admin 或 member 角色
_payment_access = require_roles(["admin", "member", "buyer"])


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
    current_user: User = Depends(_payment_access),
):
    """
    微信统一下单 (JSAPI)

    使用 IJPay WxPayApi V3 接口。
    若配置不完整或调用失败，降级为 mock 模式。
    """
    with tracer.start_as_current_span("payment.wxpay_unified_order") as span:
        span.set_attribute("order_id", req.order_id)
        span.set_attribute("user_id", current_user.id)
        # 兼容会员订单: 先查 Order, 再查 MembershipOrder
        is_membership = False
        try:
            order = await _check_order_ownership(req.order_id, current_user, db)
            product = db.query(Product).filter(Product.id == order.product_id, Product.is_deleted == False).first()
            membership_order = None
        except HTTPException:
            # 不是普通订单, 尝试会员订单
            membership_order = (
                db.query(MembershipOrder)
                .filter(
                    MembershipOrder.id == req.order_id,
                    MembershipOrder.user_id == current_user.id,
                )
                .first()
            )
            if not membership_order:
                raise HTTPException(status_code=404, detail="订单不存在")
            if membership_order.status != "pending":
                raise HTTPException(status_code=400, detail="订单不是待支付状态")
            is_membership = True
            order = membership_order  # 统一用 order 变量
            product = None

        if order.status != "pending":
            span.set_attribute("error", "order_not_pending")
            span.set_attribute("order_status", order.status)
            raise HTTPException(status_code=400, detail="订单不是待支付状态")

        # 获取 openid
        openid = req.openid or current_user.wechat_openid
        if not openid:
            span.set_attribute("error", "missing_openid")
            raise HTTPException(status_code=400, detail="缺少用户微信 openid，无法发起微信支付")

        prefix = "LKM" if is_membership else "LK"
        out_trade_no = f"{prefix}{order.id:08d}{int(time.time())}"
        total_fee = int(order.amount * 100) if is_membership else int(order.total_price * 100)
        description = (
            f"会员升级-{order.tier}"
            if is_membership
            else (f"{product.name[:60]} x{order.quantity}" if product else f"订单 #{order.id}")
        )

        span.set_attribute("is_membership_order", is_membership)
        span.set_attribute("out_trade_no", out_trade_no)
        span.set_attribute("total_fee_cents", total_fee)
        span.set_attribute("product_name", description)

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
                span.set_attribute("ijpay_result", bool(result and result.get("prepay_id")))
            except Exception as e:
                logger.error(f"IJPay 统一下单异常: {e}")
                span.record_exception(e)
                span.set_attribute("ijpay_error", str(e))
                result = None

            if result and result.get("prepay_id"):
                # 更新订单
                order.prepay_id = result["prepay_id"]
                order.payment_platform = PLATFORM_WXPAY
                db.commit()

                payment_params = result["payment_params"]
                payment_params["_mode"] = "real"
                span.set_attribute("payment_mode", "real")
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
        span.set_attribute("payment_mode", "mock")
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

    with tracer.start_as_current_span("payment.wxpay_callback") as span:
        # 获取回调头信息
        wechat_signature = request.headers.get("Wechatpay-Signature", "")
        wechat_serial = request.headers.get("Wechatpay-Serial", "")
        wechat_timestamp = request.headers.get("Wechatpay-Timestamp", "")
        wechat_nonce = request.headers.get("Wechatpay-Nonce", "")

        span.set_attribute("callback_headers_present", bool(wechat_signature))

        # 判断是 V3 还是 V2
        is_v3 = bool(wechat_signature and wechat_serial)
        span.set_attribute("callback_version", "v3" if is_v3 else "mock/compat")

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
                span.set_attribute("callback_result", "verify_failed")
                # 将回调数据加入重试队列，后续补偿
                _enqueue_retry(body, request)
                return {"code": "FAIL", "message": "验签失败"}

            out_trade_no = notify_data.get("out_trade_no", "")
            transaction_id = notify_data.get("transaction_id", "")
            trade_state = notify_data.get("trade_state", "")
            success = trade_state in ("SUCCESS", "")
            span.set_attribute("out_trade_no", out_trade_no)
            span.set_attribute("trade_state", trade_state)
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
                span.set_attribute("callback_parse_error", str(e))
                # 将回调数据加入重试队列，后续补偿
                _enqueue_retry(body, request)
                out_trade_no = ""
                transaction_id = f"mock_tx_{int(time.time())}"
                success = True

        span.set_attribute("callback_success", success)
        span.set_attribute("out_trade_no", out_trade_no)

        if not success:
            logger.warning(f"支付未成功: out_trade_no={out_trade_no}, state={notify_data.get('trade_state', '')}")
            return {"code": "FAIL", "message": "支付未成功"}

    # 更新订单
    if out_trade_no and (out_trade_no.startswith("LK") or out_trade_no.startswith("LKM")):
        try:
            order_id = int(out_trade_no[2:10] if out_trade_no.startswith("LK") else out_trade_no[3:11])
        except (ValueError, IndexError):
            order_id = None
        is_membership = out_trade_no.startswith("LKM")
    else:
        order_id = None
        is_membership = False

    if order_id:
        if is_membership:
            # 会员订单支付回调
            membership_order = (
                db.query(MembershipOrder)
                .filter(
                    MembershipOrder.id == order_id,
                    MembershipOrder.status == "pending",
                )
                .first()
            )
            if membership_order:
                membership_order.status = "paid"
                membership_order.transaction_id = transaction_id
                membership_order.paid_at = datetime.utcnow()
                if not membership_order.payment_platform:
                    membership_order.payment_platform = PLATFORM_WXPAY
                db.commit()
                # 更新用户会员信息
                _process_membership_payment(membership_order, db)
                logger.info(f"会员订单 {order_id} 支付成功，会员等级已更新")
                # 记录支付交易流水
                _log_payment_transaction(
                    order_id=order_id,
                    user_id=membership_order.user_id,
                    transaction_id=transaction_id,
                    platform=PLATFORM_WXPAY,
                    amount=float(membership_order.amount),
                    status="success",
                    description=f"会员升级-{membership_order.tier}",
                    contract_id=membership_order.contract_id if hasattr(membership_order, "contract_id") else None,
                    db=db,
                )
                return {"code": "SUCCESS", "message": "成功"}
            elif membership_order:
                logger.warning(f"会员订单 {order_id} 状态为 {membership_order.status}，无需更新")
                return {"code": "SUCCESS", "message": "已处理"}
        else:
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
                # 记录支付交易流水
                _log_payment_transaction(
                    order_id=order.id,
                    user_id=order.user_id,
                    transaction_id=transaction_id,
                    platform=PLATFORM_WXPAY,
                    amount=float(order.total_price),
                    status="success",
                    description=f"订单 #{order.id}",
                    db=db,
                )
                # 检查关联合同
                _update_contract_by_order(order.id, db)
                return {"code": "SUCCESS", "message": "成功"}
            elif order:
                logger.warning(f"订单 {order_id} 状态为 {order.status}，无需更新")
                return {"code": "SUCCESS", "message": "已处理"}

    # Fallback: 通过 prepay_id 匹配（先查 Order，再查 MembershipOrder）
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

    # Fallback: 通过 prepay_id 匹配 MembershipOrder
    membership_order = (
        db.query(MembershipOrder)
        .filter(
            MembershipOrder.status == "pending",
            MembershipOrder.prepay_id.isnot(None),
        )
        .order_by(MembershipOrder.id.desc())
        .first()
    )
    if membership_order:
        membership_order.status = "paid"
        membership_order.transaction_id = transaction_id
        membership_order.paid_at = datetime.utcnow()
        if not membership_order.payment_platform:
            membership_order.payment_platform = PLATFORM_WXPAY
        db.commit()
        _process_membership_payment(membership_order, db)
        logger.info(f"会员订单 {membership_order.id} 支付成功（通过 prepay_id 匹配）")
        return {"code": "SUCCESS", "message": "成功"}

    # 未匹配到订单，加入重试队列进行补偿
    _enqueue_retry_for_unmatched(notify_data if is_v3 else notify_data, body, request)
    return {"code": "SUCCESS", "message": "已接收"}


def _enqueue_retry_for_unmatched(notify_data: dict, body: bytes, request: Request) -> None:
    """
    当回调数据无法匹配到订单时，加入重试队列
    """
    try:
        out_trade_no = notify_data.get("out_trade_no", "") if isinstance(notify_data, dict) else ""
        import json

        payload = json.dumps(
            {
                "body": body.decode("utf-8", errors="replace"),
                "headers": {
                    "Wechatpay-Signature": request.headers.get("Wechatpay-Signature", ""),
                    "Wechatpay-Serial": request.headers.get("Wechatpay-Serial", ""),
                    "Wechatpay-Timestamp": request.headers.get("Wechatpay-Timestamp", ""),
                    "Wechatpay-Nonce": request.headers.get("Wechatpay-Nonce", ""),
                },
                "mode": _detect_callback_mode(request),
                "out_trade_no": out_trade_no,
            },
            ensure_ascii=False,
        )

        from payment import PLATFORM_WXPAY, get_config, has_config

        if has_config(PLATFORM_WXPAY):
            cfg = get_config(PLATFORM_WXPAY)
            target_url = cfg.notify_url
        else:
            target_url = ""
        if not target_url:
            scheme = request.headers.get("X-Forwarded-Proto", "https")
            host = request.headers.get("X-Forwarded-Host", request.headers.get("Host", "localhost:7800"))
            target_url = f"{scheme}://{host}/api/payment/wxpay/callback"

        retry_engine = get_retry_engine()
        task = RetryTask(target_url=target_url, payload=payload, max_retries=3)
        retry_engine.add_task(task)
        logger.info(f"未匹配订单的回调已加入重试队列: task_id={task.task_id}, out_trade_no={out_trade_no}")
    except Exception as e:
        logger.error(f"加入未匹配回调重试队列失败: {e}")


def _enqueue_retry(body: bytes, request: Request) -> None:
    """
    将支付回调数据加入重试队列，以便后续补偿处理
    """
    try:
        # 获取本机回调地址（优先使用配置的 notify_url，其次从请求构造）
        from payment import PLATFORM_WXPAY, get_config, has_config

        if has_config(PLATFORM_WXPAY):
            cfg = get_config(PLATFORM_WXPAY)
            target_url = cfg.notify_url
        else:
            target_url = ""
        if not target_url:
            # 从请求构造本地回调地址
            scheme = request.headers.get("X-Forwarded-Proto", "https")
            host = request.headers.get("X-Forwarded-Host", request.headers.get("Host", "localhost:7800"))
            target_url = f"{scheme}://{host}/api/payment/wxpay/callback"

        # 构造重试任务：payload 包含原始请求体 + 回调头信息
        import json

        payload = json.dumps(
            {
                "body": body.decode("utf-8", errors="replace"),
                "headers": {
                    "Wechatpay-Signature": request.headers.get("Wechatpay-Signature", ""),
                    "Wechatpay-Serial": request.headers.get("Wechatpay-Serial", ""),
                    "Wechatpay-Timestamp": request.headers.get("Wechatpay-Timestamp", ""),
                    "Wechatpay-Nonce": request.headers.get("Wechatpay-Nonce", ""),
                },
                "mode": _detect_callback_mode(request),
            },
            ensure_ascii=False,
        )

        retry_engine = get_retry_engine()
        task = RetryTask(
            target_url=target_url,
            payload=payload,
            max_retries=3,
        )
        retry_engine.add_task(task)
        logger.info(f"支付回调已加入重试队列: task_id={task.task_id}, target_url={target_url}")
    except Exception as e:
        logger.error(f"加入支付回调重试队列失败: {e}")


def _detect_callback_mode(request: Request) -> str:
    """检测回调模式: v3 / v2 / mock"""
    from payment import PLATFORM_WXPAY, has_config

    sig = request.headers.get("Wechatpay-Signature", "")
    serial = request.headers.get("Wechatpay-Serial", "")
    if sig and serial and has_config(PLATFORM_WXPAY):
        return "v3"
    return "v2_or_mock"


# ============================================================
# 微信支付 — 订单查询
# ============================================================


@router.get("/wxpay/query/{order_no}", response_model=ApiResponse)
async def wxpay_query(
    order_no: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(_payment_access),
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
    current_user: User = Depends(_payment_access),
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
    current_user: User = Depends(_payment_access),
):
    """支付宝统一下单 (APP 支付)"""
    # 兼容会员订单
    is_membership = False
    try:
        order = await _check_order_ownership(req.order_id, current_user, db)
        product = db.query(Product).filter(Product.id == order.product_id, Product.is_deleted == False).first()
    except HTTPException:
        membership_order = (
            db.query(MembershipOrder)
            .filter(
                MembershipOrder.id == req.order_id,
                MembershipOrder.user_id == current_user.id,
            )
            .first()
        )
        if not membership_order:
            raise HTTPException(status_code=404, detail="订单不存在")
        if membership_order.status != "pending":
            raise HTTPException(status_code=400, detail="订单不是待支付状态")
        is_membership = True
        order = membership_order
        product = None

    if order.status != "pending":
        raise HTTPException(status_code=400, detail="订单不是待支付状态")

    subject = req.subject or (
        f"会员升级-{order.tier}" if is_membership else (product.name if product else f"订单 #{order.id}")
    )
    prefix = "ALM" if is_membership else "AL"
    out_trade_no = f"{prefix}{order.id:08d}{int(time.time())}"
    # 会员订单使用 amount，普通订单使用 total_price
    total_amount = order.amount if is_membership else order.total_price

    if has_config(PLATFORM_ALIPAY):
        try:
            alipay = _get_alipay_api()
            result = await alipay.unified_order(
                out_trade_no=out_trade_no,
                total_amount=total_amount,
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
            "order_string": f"app_id=mock&method=alipay.trade.app.pay&out_trade_no={out_trade_no}&total_amount={total_amount}",
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


def _log_payment_transaction(
    order_id: int | None,
    user_id: int | None,
    transaction_id: str,
    platform: str,
    amount: float,
    status: str,
    description: str = "",
    contract_id: int | None = None,
    db: Session | None = None,
) -> PaymentTransaction | None:
    """记录支付交易到统一流水表"""
    if not db:
        return None
    try:
        from datetime import datetime

        tx = PaymentTransaction(
            user_id=user_id or 0,
            order_id=order_id,
            contract_id=contract_id,
            transaction_no=transaction_id or f"tx_{int(time.time())}",
            platform=platform,
            amount=amount,
            status=status,
            description=description[:200] if description else "",
            paid_at=datetime.utcnow() if status == "success" else None,
        )
        db.add(tx)
        db.commit()
        logger.info(f"支付交易记录已创建: tx={tx.transaction_no}, order={order_id}, status={status}")
        return tx
    except Exception as e:
        logger.error(f"创建支付交易记录失败: {e}")
        return None


def _update_contract_payment_status(contract_id: int, db: Session) -> None:
    """更新合同的支付状态"""
    if not contract_id:
        return
    try:
        contract = db.query(Contract).filter(Contract.id == contract_id, Contract.is_deleted == False).first()
        if contract:
            contract.payment_status = "paid"
            db.commit()
            logger.info(f"合同 {contract_id} 支付状态已更新为 paid")
    except Exception as e:
        logger.error(f"更新合同支付状态失败: {e}")


def _update_contract_by_order(order_id: int, db: Session) -> None:
    """通过订单ID更新关联合同的支付状态"""
    if not order_id:
        return
    try:
        contract = (
            db.query(Contract)
            .filter(
                Contract.related_order_id == order_id,
                Contract.is_deleted == False,
            )
            .first()
        )
        if contract:
            contract.payment_status = "paid"
            db.commit()
            logger.info(f"通过订单 {order_id} 更新合同 {contract.id} 支付状态为 paid")
    except Exception as e:
        logger.error(f"通过订单更新合同支付状态失败: {e}")


def _process_membership_payment(membership_order: MembershipOrder, db: Session) -> None:
    """会员订单支付成功后，更新用户的会员等级、过期时间和对接券数量"""
    from datetime import timedelta

    from app.routers.membership import MEMBERSHIP_TIERS

    user = db.query(User).filter(User.id == membership_order.user_id).first()
    if not user:
        logger.error(f"会员订单 {membership_order.id} 用户 {membership_order.user_id} 不存在")
        return

    tier = membership_order.tier
    tier_config = MEMBERSHIP_TIERS.get(tier)
    if not tier_config:
        logger.error(f"会员订单 {membership_order.id} 未知等级 {tier}")
        return

    # 计算过期时间: 从当前时间起 + duration_days
    duration = tier_config.get("duration_days", 365)
    user.membership_tier = tier
    user.membership_expires_at = datetime.utcnow() + timedelta(days=duration)
    # 更新对接券数量（取最大值，累加）
    user.match_credits = max(user.match_credits or 0, tier_config.get("match_credits", 0))
    db.commit()
    logger.info(
        f"用户 {user.id} 会员升级: tier={tier}, "
        f"expires_at={user.membership_expires_at}, "
        f"match_credits={user.match_credits}"
    )


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


# ============================================================
# 微信支付 V3 — 统一通知回调
# /api/payment/wechat/notify
# ============================================================


@router.post("/wechat/notify")
async def wechat_notify(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    微信支付 V3 统一回调通知

    接收微信支付异步通知, 处理:
      1. 验签 + 解密 (AES-256-GCM)
      2. 更新订单/合同状态
      3. 触发 Webhook 事件

    回调签名验证失败时返回 200 + {"code": "FAIL"}
    避免微信重试导致重复处理。
    """
    body = await request.body()
    logger.info(f"收到微信支付回调: {body[:300]}")

    with tracer.start_as_current_span("payment.wechat_notify") as span:
        wechat_signature = request.headers.get("Wechatpay-Signature", "")
        wechat_serial = request.headers.get("Wechatpay-Serial", "")
        wechat_timestamp = request.headers.get("Wechatpay-Timestamp", "")
        wechat_nonce = request.headers.get("Wechatpay-Nonce", "")

        span.set_attribute("has_v3_headers", bool(wechat_signature and wechat_serial))

        # 尝试用新 SDK 验证 (V3)
        notify_data = None
        try:
            from app.payment.wechat_pay import WeChatPay

            wxpay = WeChatPay.from_env()
            if wxpay.config.is_ready()[0]:  # 配置完整 => 真实验签
                notify_data = wxpay.verify_callback(
                    body=body,
                    wechatpay_signature=wechat_signature,
                    wechatpay_serial=wechat_serial,
                    wechatpay_timestamp=wechat_timestamp,
                    wechatpay_nonce=wechat_nonce,
                )
                if notify_data is None:
                    logger.error("V3 回调验签失败")
                    span.set_attribute("verify_result", "failed")
                    _enqueue_retry(body, request)
                    return {"code": "FAIL", "message": "验签失败"}
                span.set_attribute("verify_result", "success")
        except ImportError:
            logger.debug("app.payment.wechat_pay 未安装, 使用兼容模式")
        except Exception as e:
            logger.warning(f"V3 SDK 回调处理异常: {e}, 降级兼容模式")

        # 降级: 使用现有 IJPay 回调逻辑
        if notify_data is None:
            logger.info("使用兼容模式处理微信回调")
            return await _legacy_wechat_notify(body, request, db, span)

        # ===== V3 回调处理 =====
        out_trade_no = notify_data.get("out_trade_no", "")
        transaction_id = notify_data.get("transaction_id", "")
        trade_state = notify_data.get("trade_state", "")
        success = trade_state in ("SUCCESS",)

        span.set_attribute("out_trade_no", out_trade_no)
        span.set_attribute("trade_state", trade_state)
        span.set_attribute("success", success)

        if not success:
            logger.warning(f"支付未成功: out_trade_no={out_trade_no}, state={trade_state}")
            return {"code": "FAIL", "message": "支付未成功"}

        # 更新订单 + 合同 + Webhook
        _process_successful_payment(out_trade_no, transaction_id, db, span)

        # 触发 webhook
        _fire_payment_webhook("payment.succeeded", {
            "out_trade_no": out_trade_no,
            "transaction_id": transaction_id,
            "trade_state": trade_state,
        })

        return {"code": "SUCCESS", "message": "成功"}


async def _legacy_wechat_notify(
    body: bytes, request: Request, db: Session, span
) -> dict:
    """降级使用现有 IJPay 回调逻辑"""
    body_str = body.decode("utf-8")
    try:
        notify_data = json.loads(body_str)
    except json.JSONDecodeError:
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(body_str)
            notify_data = {child.tag: child.text for child in root}
        except Exception as e:
            logger.error(f"回调解析失败: {e}")
            span.set_attribute("parse_error", str(e))
            _enqueue_retry(body, request)
            return {"code": "FAIL", "message": "解析失败"}

    out_trade_no = notify_data.get("out_trade_no", "")
    transaction_id = notify_data.get("transaction_id", "") or notify_data.get(
        "wx_transaction_id", f"mock_tx_{int(time.time())}"
    )
    success = notify_data.get("result_code", "") in ("SUCCESS", "OK", "")

    if not success:
        return {"code": "FAIL", "message": "支付未成功"}

    _process_successful_payment(out_trade_no, transaction_id, db, span)
    return {"code": "SUCCESS", "message": "成功"}


def _process_successful_payment(
    out_trade_no: str, transaction_id: str, db: Session, span
) -> None:
    """
    支付成功处理:
    1. 解析订单号
    2. 更新订单状态 → paid
    3. 更新合同状态 → paid
    4. 记录支付交易流水
    """
    if out_trade_no.startswith("LK") or out_trade_no.startswith("LKM"):
        is_membership = out_trade_no.startswith("LKM")
        offset = 3 if is_membership else 2
        try:
            order_id = int(out_trade_no[offset:offset + 8])
        except (ValueError, IndexError):
            order_id = None
    else:
        order_id = None
        is_membership = False

    if order_id is None:
        logger.warning(f"无法从 out_trade_no 解析订单ID: {out_trade_no}")
        return

    span.set_attribute("order_id", order_id)
    span.set_attribute("is_membership", is_membership)

    if is_membership:
        membership_order = (
            db.query(MembershipOrder)
            .filter(MembershipOrder.id == order_id, MembershipOrder.status == "pending")
            .first()
        )
        if membership_order:
            membership_order.status = "paid"
            membership_order.transaction_id = transaction_id
            membership_order.paid_at = datetime.utcnow()
            if not membership_order.payment_platform:
                membership_order.payment_platform = PLATFORM_WXPAY
            db.commit()
            _process_membership_payment(membership_order, db)
            _log_payment_transaction(
                order_id=order_id,
                user_id=membership_order.user_id,
                transaction_id=transaction_id,
                platform=PLATFORM_WXPAY,
                amount=float(membership_order.amount),
                status="success",
                description=f"会员升级-{membership_order.tier}",
                contract_id=membership_order.contract_id if hasattr(membership_order, "contract_id") else None,
                db=db,
            )
            span.set_attribute("membership_updated", True)
    else:
        order = (
            db.query(Order)
            .filter(Order.id == order_id, Order.is_deleted == False)
            .first()
        )
        if order and order.status == "pending":
            order.status = "paid"
            order.transaction_id = transaction_id
            order.wx_transaction_id = transaction_id
            order.payment_time = datetime.utcnow()
            order.pay_time = datetime.utcnow()
            if not order.payment_platform:
                order.payment_platform = PLATFORM_WXPAY
            db.commit()
            logger.info(f"订单 {order_id} 支付成功")
            _log_payment_transaction(
                order_id=order.id,
                user_id=order.user_id,
                transaction_id=transaction_id,
                platform=PLATFORM_WXPAY,
                amount=float(order.total_price),
                status="success",
                description=f"订单 #{order.id}",
                db=db,
            )
            # 更新关联合同
            _update_contract_by_order(order.id, db)
            span.set_attribute("order_updated", True)

    # 记录支付事件回调成功
    span.set_attribute("payment_processed", True)
    logger.info(f"支付回调处理完成: out_trade_no={out_trade_no}, tx={transaction_id}")


def _fire_payment_webhook(event_type: str, payload: dict) -> None:
    """触发支付 Webhook 事件"""
    try:
        from app.webhook_v2 import EventType, dispatch_event

        dispatch_event(
            event_type=EventType(event_type),
            data=payload,
            source="payment",
        )
        logger.info(f"Webhook 事件已触发: {event_type}")
    except ImportError:
        logger.debug("webhook_v2 未加载, 跳过 webhook 触发")
    except Exception as e:
        logger.error(f"Webhook 触发失败: {e}")


import os
