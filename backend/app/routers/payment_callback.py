"""链客宝 — 支付回调统一路由

====================================================
从旧版链客宝 recharge/callback.py + payment/alipay/__init__.py 迁移。
适配 chainke-full 架构，使用 features/payment_callback/ 下的业务逻辑。

端点:
  POST /api/payment/callback/wxpay     — 微信支付异步回调通知
  POST /api/payment/callback/alipay    — 支付宝异步回调通知
  POST /api/payment/callback/wxpay/mock — Mock 微信回调（开发测试）

设计说明:
  - 回调验签委托给 payment/providers/ 下的 Provider
  - 充值业务逻辑在 features/payment_callback/recharge_callback.py
  - 不经过 auth 中间件（支付平台直接调用）
  - 返回格式兼容微信/支付宝要求
====================================================
"""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment/callback", tags=["支付回调"])


# ===================================================================
# 数据库会话 & 模型工厂
# ===================================================================


def _get_db():
    """获取 payment 模块的数据库会话"""
    try:
        from payment.models import get_db
        for db in get_db():
            yield db
    except Exception as e:
        logger.error(f"获取数据库会话失败: {e}")
        raise


def _get_payment_order_model():
    """获取支付订单模型"""
    try:
        from payment.models import PaymentOrder
        return PaymentOrder
    except ImportError:
        logger.warning("payment.models.PaymentOrder 不可用")
        return None


def _get_user_balance_model():
    """获取用户余额模型（可选，如无则跳过余额更新）"""
    try:
        # 尝试从 app 层加载
        from app.models import UserBalance
        return UserBalance
    except ImportError:
        pass
    try:
        # 尝试从 payment 层加载
        from payment.models import UserBalance
        return UserBalance
    except ImportError:
        logger.warning("UserBalance 模型不可用，跳过余额更新")
        return None


def _get_balance_log_model():
    """获取余额流水模型（可选）"""
    try:
        from app.models import BalanceLog
        return BalanceLog
    except ImportError:
        pass
    try:
        from payment.models import BalanceLog
        return BalanceLog
    except ImportError:
        logger.warning("BalanceLog 模型不可用，跳过余额流水")
        return None


# ===================================================================
# POST /api/payment/callback/wxpay  — 微信支付回调
# ===================================================================


@router.post("/wxpay")
async def wxpay_callback(request: Request):
    """微信支付回调通知处理

    流程:
    1. 验签: 验证 Wechatpay-Signature
    2. 解密 resource 获取支付结果
    3. 幂等保护: order_no 唯一约束 + 状态机检查（只能 pending→paid）
    4. 事务: 更新订单状态 + 更新余额 + 写入流水

    请求头:
      Wechatpay-Signature  — Base64 签名
      Wechatpay-Serial     — 平台证书序列号
      Wechatpay-Timestamp  — 时间戳
      Wechatpay-Nonce      — 随机串

    响应:
      {"code": "SUCCESS", "message": "成功"}  — 微信要求格式
    """
    from features.payment_callback.wxpay_callback import WxPayCallbackService

    def _db_factory():
        return next(_get_db())

    PaymentOrder = _get_payment_order_model()
    UserBalance = _get_user_balance_model()
    BalanceLog = _get_balance_log_model()

    # 构建支付成功回调
    on_success = await WxPayCallbackService.build_on_payment_success(
        db_session_factory=_db_factory,
        payment_order_model=PaymentOrder,
        user_balance_model=UserBalance,
        balance_log_model=BalanceLog,
    )

    service = WxPayCallbackService()
    result = await service.verify_and_process(
        request=request,
        on_payment_success=on_success,
    )

    if result["code"] == "FAIL":
        logger.warning(f"微信回调处理失败: {result['message']}")

    return result


# ===================================================================
# POST /api/payment/callback/alipay  — 支付宝回调
# ===================================================================


@router.post("/alipay")
async def alipay_callback(request: Request):
    """支付宝异步回调通知处理

    支付宝通过 POST 表单提交回调参数。

    流程:
    1. 读取表单参数
    2. RSA2 验签
    3. 判断 trade_status (TRADE_SUCCESS / TRADE_FINISHED)
    4. 更新订单状态 + 余额

    响应:
      {"code": "SUCCESS", "message": "成功"}
    """
    from features.payment_callback.alipay_callback import AliPayCallbackService

    def _db_factory():
        return next(_get_db())

    PaymentOrder = _get_payment_order_model()
    UserBalance = _get_user_balance_model()
    BalanceLog = _get_balance_log_model()

    # 构建支付成功回调
    on_success = await AliPayCallbackService.build_on_payment_success(
        db_session_factory=_db_factory,
        payment_order_model=PaymentOrder,
        user_balance_model=UserBalance,
        balance_log_model=BalanceLog,
    )

    service = AliPayCallbackService()
    result = await service.verify_and_process(
        request=request,
        on_payment_success=on_success,
    )

    if result["code"] == "FAIL":
        logger.warning(f"支付宝回调处理失败: {result['message']}")

    return result


# ===================================================================
# POST /api/payment/callback/wxpay/mock  — Mock 支付回调（开发测试）
# ===================================================================


@router.post("/wxpay/mock")
async def mock_wxpay_callback(request: Request):
    """Mock 微信支付回调（开发/测试环境使用）

    无需真实微信签名验证，直接处理支付成功逻辑。

    请求体:
      {"out_trade_no": "RC...", "transaction_id": "mock_...", "success_time": "..."}

    响应:
      {"code": "SUCCESS", "message": "Mock 支付成功"}
    """
    body = await request.body()
    try:
        data = json.loads(body)
    except Exception:
        data = {}

    order_no = data.get("out_trade_no", "")
    transaction_id = data.get("transaction_id", f"mock_tx_{order_no}")
    success_time = data.get("success_time", None)

    if not order_no:
        return {"code": "FAIL", "message": "缺少订单号"}

    logger.info(f"Mock 回调: order_no={order_no}, transaction_id={transaction_id}")

    # 处理支付成功逻辑
    from features.payment_callback.recharge_callback import process_successful_payment

    PaymentOrder = _get_payment_order_model()
    UserBalance = _get_user_balance_model()
    BalanceLog = _get_balance_log_model()

    db = next(_get_db())
    try:
        result = process_successful_payment(
            db=db,
            order_no=order_no,
            transaction_id=transaction_id,
            paid_at_str=success_time,
            payment_order_model=PaymentOrder,
            user_balance_model=UserBalance,
            balance_log_model=BalanceLog,
        )
        if not result["success"]:
            return {"code": "FAIL", "message": result["message"]}
    except Exception as e:
        logger.error(f"Mock 回调异常: {e}", exc_info=True)
        db.rollback()
        return {"code": "FAIL", "message": str(e)}
    finally:
        if db.is_active:
            db.close()

    return {"code": "SUCCESS", "message": "Mock 支付成功"}
