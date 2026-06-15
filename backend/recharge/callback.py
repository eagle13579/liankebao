"""充值模块 — 支付回调处理"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from recharge.models import UserBalance, RechargeOrder, BalanceLog

# ===== 支付模块 =====
from payment import (
    WxPayCallback,
    WxPayConfig,
    get_config,
    PLATFORM_WXPAY,
)

logger = logging.getLogger(__name__)

# 独立的回调 router（不经过 auth 中间件，微信服务器直接调用）
callback_router = APIRouter(prefix="/api/recharge/callback", tags=["充值回调"])


@callback_router.post("/mock")
async def mock_callback(request: Request):
    """
    Mock 支付回调（开发/测试环境使用）

    无需真实微信签名验证，直接处理支付成功逻辑。
    请求体: {"out_trade_no": "RC...", "transaction_id": "mock_..."}
    """
    body = await request.body()
    try:
        data = json.loads(body)
    except Exception:
        data = {}

    order_no = data.get("out_trade_no", "")
    transaction_id = data.get("transaction_id", f"mock_tx_{order_no}")

    if not order_no:
        return {"code": "FAIL", "message": "缺少订单号"}

    logger.info(f"Mock 回调: order_no={order_no}, transaction_id={transaction_id}")

    db: Session = next(get_db())
    try:
        _process_successful_payment(
            db=db,
            order_no=order_no,
            transaction_id=transaction_id,
            paid_at_str=data.get("success_time", None),
        )
    except HTTPException as e:
        logger.warning(f"Mock 回调处理异常: {e.detail}")
        db.close()
        return {"code": "FAIL", "message": e.detail}
    except Exception as e:
        logger.error(f"Mock 回调异常: {e}", exc_info=True)
        db.rollback()
        db.close()
        return {"code": "FAIL", "message": str(e)}
    finally:
        if db.is_active:
            db.close()

    return {"code": "SUCCESS", "message": "Mock 支付成功"}


@callback_router.post("/wxpay")
async def wxpay_callback(request: Request):
    """
    微信支付回调通知处理

    流程：
    1. 验签：验证 Wechatpay-Signature
    2. 解密 resource 获取支付结果
    3. 幂等保护：order_no 唯一约束 + 状态机检查（只能 pending→paid）
    4. 事务：更新订单状态 + 行锁更新余额 + 写入流水
    """
    # 1. 获取回调请求头
    wechatpay_signature = request.headers.get("Wechatpay-Signature", "")
    wechatpay_serial = request.headers.get("Wechatpay-Serial", "")
    wechatpay_timestamp = request.headers.get("Wechatpay-Timestamp", "")
    wechatpay_nonce = request.headers.get("Wechatpay-Nonce", "")

    if not all([wechatpay_signature, wechatpay_serial, wechatpay_timestamp, wechatpay_nonce]):
        logger.warning("微信回调缺少验签请求头")
        return {"code": "FAIL", "message": "缺少验签参数"}

    # 2. 读取请求体
    body = await request.body()

    # 3. 验签 + 解密
    try:
        callback = WxPayCallback()
        plaintext = callback.verify_and_decrypt(
            body=body,
            wechatpay_signature=wechatpay_signature,
            wechatpay_serial=wechatpay_serial,
            wechatpay_timestamp=wechatpay_timestamp,
            wechatpay_nonce=wechatpay_nonce,
        )
    except Exception as e:
        logger.error(f"微信回调验签异常: {e}", exc_info=True)
        return {"code": "FAIL", "message": "验签异常"}

    if plaintext is None:
        logger.error("微信回调验签失败")
        return {"code": "FAIL", "message": "验签失败"}

    # 4. 解析支付结果
    out_trade_no = plaintext.get("out_trade_no", "")
    transaction_id = plaintext.get("transaction_id", "")
    trade_state = plaintext.get("trade_state", "")  # SUCCESS / REFUND / NOTPAY / CLOSED
    success_time = plaintext.get("success_time", None)  # RFC 3339 格式: 2024-01-01T10:00:00+08:00

    if not out_trade_no:
        logger.error("回调数据中缺少 out_trade_no")
        return {"code": "FAIL", "message": "缺少订单号"}

    if trade_state != "SUCCESS":
        logger.info(f"支付未成功，跳过处理: out_trade_no={out_trade_no}, trade_state={trade_state}")
        return {"code": "SUCCESS", "message": "收到通知"}

    # 5. 处理支付成功逻辑（事务）
    db: Session = next(get_db())
    try:
        _process_successful_payment(
            db=db,
            order_no=out_trade_no,
            transaction_id=transaction_id,
            paid_at_str=success_time,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"支付成功处理异常: {e}", exc_info=True)
        db.rollback()
        return {"code": "FAIL", "message": f"处理失败: {str(e)}"}
    finally:
        db.close()

    # 6. 返回微信要求的成功响应
    return {"code": "SUCCESS", "message": "成功"}


def _process_successful_payment(
    db: Session,
    order_no: str,
    transaction_id: str,
    paid_at_str: Optional[str] = None,
):
    """
    支付成功处理（事务内执行）

    幂等保护：
    - 只处理 pending 状态的订单（状态机检查）
    - order_no 有唯一约束，不会重复
    - 使用行级锁更新余额
    """
    # 查询充值订单（带行锁）
    order = db.query(RechargeOrder).filter(
        RechargeOrder.order_no == order_no
    ).with_for_update().first()

    if not order:
        logger.error(f"充值订单不存在: order_no={order_no}")
        raise HTTPException(status_code=404, detail="充值订单不存在")

    # 幂等保护：状态机检查（只能 pending→paid）
    if order.status == "paid":
        logger.info(f"订单已支付，幂等跳过: order_no={order_no}")
        return
    if order.status != "pending":
        logger.warning(f"订单状态不允许支付: order_no={order_no}, status={order.status}")
        raise HTTPException(status_code=400, detail=f"订单状态不允许支付: {order.status}")

    # 解析支付时间
    paid_at = None
    if paid_at_str:
        try:
            # RFC 3339 格式解析
            paid_at = datetime.fromisoformat(paid_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            paid_at = datetime.utcnow()
    else:
        paid_at = datetime.utcnow()

    user_id = order.user_id
    amount = order.amount

    # 获取用户余额（带行锁）
    bal = db.query(UserBalance).filter(
        UserBalance.user_id == user_id
    ).with_for_update().first()

    if not bal:
        # 首次充值，创建余额记录
        bal = UserBalance(
            user_id=user_id,
            balance=amount,
            total_recharged=amount,
            total_consumed=0.00,
            frozen_amount=0.00,
            version=1,
        )
        db.add(bal)
        balance_before = 0.00
        balance_after = amount
    else:
        balance_before = bal.balance
        balance_after = balance_before + amount
        # 行锁更新：使用 Python 计算后赋值（SQLite 兼容）
        bal.balance = balance_after
        bal.total_recharged = bal.total_recharged + amount
        bal.version += 1

    # 更新订单状态
    order.status = "paid"
    order.paid_at = paid_at

    # 写入余额流水
    log = BalanceLog(
        user_id=user_id,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        direction="IN",
        biz_type="recharge",
        biz_id=order_no,
        remark=f"充值支付成功: {order_no}",
    )
    db.add(log)

    db.commit()
    logger.info(
        f"充值支付成功: order_no={order_no}, user_id={user_id}, "
        f"amount={amount}, balance_after={balance_after}"
    )
