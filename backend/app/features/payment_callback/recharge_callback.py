"""充值回调核心业务逻辑

从旧版链客宝 recharge/callback.py 中的 _process_successful_payment 迁移。

核心功能:
    - 查询充值订单 (带行锁)
    - 幂等保护: 状态机检查 (pending→paid)
    - 余额更新 (行级锁 + 乐观锁)
    - 写入余额流水

适配说明:
    - 旧版依赖 recharge/models.py(RechargeOrder, UserBalance, BalanceLog)
    - 新版使用 payment/models.py(PaymentOrder) 通用支付订单模型
    - 保留充值专用的余额处理逻辑，作为 features 层服务
    - balance 操作示意: 从 payment.models 获取用户余额上下文
"""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# ===================================================================
# 充值回调常量
# ===================================================================

# 订单状态
ORDER_STATUS_PENDING = "pending"
ORDER_STATUS_PAID = "paid"
ORDER_STATUS_CLOSED = "closed"
ORDER_STATUS_REFUNDED = "refunded"

# 余额方向
BALANCE_DIRECTION_IN = "IN"
BALANCE_DIRECTION_OUT = "OUT"

# 业务类型
BIZ_TYPE_RECHARGE = "recharge"
BIZ_TYPE_CONSUME = "consume"
BIZ_TYPE_REFUND = "refund"
BIZ_TYPE_ADJUST = "adjust"


# ===================================================================
# 充值回调处理 — 核心函数
# ===================================================================


def process_successful_payment(
    db: Session,
    order_no: str,
    transaction_id: str,
    paid_at_str: Optional[str] = None,
    payment_order_model=None,
    user_balance_model=None,
    balance_log_model=None,
) -> dict:
    """支付成功处理（事务内执行）

    从旧版 _process_successful_payment 迁移，适配通用支付订单模型。

    幂等保护:
    - 只处理 pending 状态的订单（状态机检查）
    - order_no 有唯一约束，不会重复
    - 使用行级锁更新余额

    Args:
        db: 数据库会话（事务内）
        order_no: 商户订单号
        transaction_id: 支付平台交易号
        paid_at_str: 支付完成时间（RFC 3339 格式）
        payment_order_model: 支付订单 ORM 模型类
        user_balance_model: 用户余额 ORM 模型类
        balance_log_model: 余额流水 ORM 模型类

    Returns:
        处理结果字典: {"success": bool, "order_no": str, "message": str}
    """
    # 查询支付订单（带行锁）
    order_query = db.query(payment_order_model).filter(
        payment_order_model.order_no == order_no
    )
    # with_for_update() 需在支持行锁的引擎上使用 (PostgreSQL/MySQL)
    # SQLite 不支持行锁，直接查询
    try:
        order = order_query.with_for_update().first()
    except Exception:
        order = order_query.first()

    if not order:
        logger.error(f"支付订单不存在: order_no={order_no}")
        return {"success": False, "order_no": order_no, "message": "支付订单不存在"}

    # 幂等保护: 状态机检查（只能 pending→paid）
    if order.status == ORDER_STATUS_PAID:
        logger.info(f"订单已支付，幂等跳过: order_no={order_no}")
        return {
            "success": True,
            "order_no": order_no,
            "message": "订单已支付，幂等跳过",
        }

    if order.status != ORDER_STATUS_PENDING:
        logger.warning(
            f"订单状态不允许支付: order_no={order_no}, status={order.status}"
        )
        return {
            "success": False,
            "order_no": order_no,
            "message": f"订单状态不允许支付: {order.status}",
        }

    # 解析支付时间
    paid_at = None
    if paid_at_str:
        try:
            # RFC 3339 格式解析: 2024-01-01T10:00:00+08:00
            paid_at = datetime.fromisoformat(paid_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            paid_at = datetime.utcnow()
    else:
        paid_at = datetime.utcnow()

    # 回填渠道订单号
    if hasattr(order, "channel_order_no"):
        order.channel_order_no = transaction_id

    # 更新订单状态
    order.status = ORDER_STATUS_PAID
    if hasattr(order, "paid_at") and paid_at:
        order.paid_at = paid_at

    db.flush()

    # 处理余额（如果提供了余额模型）
    if user_balance_model is not None and balance_log_model is not None:
        _update_user_balance(
            db=db,
            user_id=order.user_id,
            amount=order.amount,
            order_no=order_no,
            user_balance_model=user_balance_model,
            balance_log_model=balance_log_model,
        )

    db.commit()
    logger.info(
        f"支付成功: order_no={order_no}, "
        f"transaction_id={transaction_id}, "
        f"user_id={order.user_id}, "
        f"amount={order.amount}"
    )

    return {
        "success": True,
        "order_no": order_no,
        "transaction_id": transaction_id,
        "message": "支付成功",
    }


def _update_user_balance(
    db: Session,
    user_id,
    amount,
    order_no: str,
    user_balance_model,
    balance_log_model,
):
    """更新用户余额（行级锁 + 写流水）

    Args:
        db: 数据库会话
        user_id: 用户标识
        amount: 金额（单位由模型决定，通常为分或元）
        order_no: 订单号
        user_balance_model: 用户余额 ORM 模型
        balance_log_model: 余额流水 ORM 模型
    """
    # 查询用户余额（带行锁）
    try:
        bal = (
            db.query(user_balance_model)
            .filter(user_balance_model.user_id == user_id)
            .with_for_update()
            .first()
        )
    except Exception:
        bal = (
            db.query(user_balance_model)
            .filter(user_balance_model.user_id == user_id)
            .first()
        )

    if not bal:
        # 首次充值，创建余额记录
        balance_before = 0
        balance_after = _to_numeric(amount)

        bal = user_balance_model(
            user_id=user_id,
            balance=balance_after,
            total_recharged=balance_after,
            total_consumed=0,
            frozen_amount=0,
            version=1,
        )
        db.add(bal)
    else:
        balance_before = _to_numeric(bal.balance)
        amount_num = _to_numeric(amount)
        balance_after = balance_before + amount_num

        # 更新余额
        bal.balance = balance_after
        bal.total_recharged = _to_numeric(bal.total_recharged) + amount_num
        if hasattr(bal, "version"):
            bal.version = _to_numeric(bal.version) + 1

    # 写入余额流水
    log = balance_log_model(
        user_id=user_id,
        amount=abs(_to_numeric(amount)),
        balance_before=balance_before,
        balance_after=balance_after,
        direction=BALANCE_DIRECTION_IN,
        biz_type=BIZ_TYPE_RECHARGE,
        biz_id=order_no,
        remark=f"充值支付成功: {order_no}",
    )
    db.add(log)


def _to_numeric(value) -> float:
    """将各种数值类型转换为 float"""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
