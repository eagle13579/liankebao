"""支付宝回调验签服务

从旧版链客宝 payment/alipay/__init__.py 中的 AliPayApi.verify_notify 和
alipay.py 路由中的 alipay_callback 逻辑迁移。

验签委托给 payment/providers/alipay.py 的 AliPayProvider.callback_verify()。
验签通过后调用 recharge_callback.process_successful_payment() 更新订单/余额。
"""

import json
import logging
from typing import Optional

from fastapi import Request

logger = logging.getLogger(__name__)


class AliPayCallbackService:
    """支付宝回调验签服务

    封装支付宝异步通知的验签、业务处理流程。
    不直接依赖 FastAPI Request，可测试。
    """

    def __init__(self, alipay_provider=None):
        """初始化支付宝回调服务

        Args:
            alipay_provider: AliPayProvider 实例。为 None 时延迟初始化。
        """
        self._provider = alipay_provider

    def _get_provider(self):
        """获取 AliPayProvider 实例（延迟加载）"""
        if self._provider is None:
            from payment.providers.alipay import AliPayConfig, AliPayProvider

            config = AliPayConfig.from_env()
            self._provider = AliPayProvider(config=config)
        return self._provider

    async def verify_and_process(
        self,
        request: Request,
        body: Optional[bytes] = None,
        on_payment_success=None,
    ) -> dict:
        """支付宝异步通知验签 + 业务处理

        流程:
            1. 读取请求体（表单格式）
            2. 调用 provider.callback_verify() 验签
            3. 解析验签后的参数 (out_trade_no, trade_no, trade_status)
            4. 判断交易状态 (TRADE_SUCCESS / TRADE_FINISHED)
            5. 调用 on_payment_success 回调处理业务

        Args:
            request: FastAPI Request 对象
            body: 预读取的请求体字节（可选，不传则自动读取）
            on_payment_success: 支付成功回调函数
                async def on_payment_success(order_no, transaction_id, trade_status, success_time)
                返回 {"success": bool, "message": str}

        Returns:
            处理结果字典: {"code": "SUCCESS"/"FAIL", "message": str, "data": dict}
        """
        # 1. 读取请求体
        if body is None:
            body = await request.body()

        # 2. 验签
        provider = self._get_provider()
        cb_result = await provider.callback_verify(body=body)

        if not cb_result.verified:
            logger.warning(f"支付宝回调验签失败: {cb_result.message}")
            return {"code": "FAIL", "message": cb_result.message}

        params = cb_result.data or {}
        out_trade_no = params.get("out_trade_no", "")
        trade_no = params.get("trade_no", "")        # 支付宝交易号
        trade_status = params.get("trade_status", "")
        total_amount = params.get("total_amount", "0")
        gmt_payment = params.get("gmt_payment", None)  # 支付时间

        if not out_trade_no:
            logger.error("支付宝回调中缺少 out_trade_no")
            return {"code": "FAIL", "message": "缺少订单号"}

        logger.info(
            f"支付宝回调: out_trade_no={out_trade_no}, "
            f"trade_no={trade_no}, status={trade_status}"
        )

        # 3. 处理交易状态
        # TRADE_SUCCESS — 交易支付成功
        # TRADE_FINISHED — 交易完结（无法再退款）
        if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
            if on_payment_success:
                result = await on_payment_success(
                    order_no=out_trade_no,
                    transaction_id=trade_no,
                    trade_status=trade_status,
                    success_time=gmt_payment,
                )
                if not result.get("success", False):
                    return {"code": "FAIL", "message": result.get("message", "处理失败")}

            return {
                "code": "SUCCESS",
                "message": "成功",
                "data": {
                    "out_trade_no": out_trade_no,
                    "trade_no": trade_no,
                    "trade_status": trade_status,
                },
            }

        # 其他状态: WAIT_BUYER_PAY / TRADE_CLOSED 等，仅记录
        logger.info(f"支付宝回调非支付成功状态: trade_status={trade_status}")
        return {"code": "SUCCESS", "message": "收到通知"}

    @staticmethod
    async def build_on_payment_success(db_session_factory, payment_order_model, user_balance_model, balance_log_model):
        """构建支付成功回调处理函数

        使用工厂模式创建闭包，避免在路由层直接依赖 ORM 模型。

        Args:
            db_session_factory: 数据库会话工厂 (可调用，返回 Session)
            payment_order_model: 支付订单 ORM 模型类
            user_balance_model: 用户余额 ORM 模型类
            balance_log_model: 余额流水 ORM 模型类

        Returns:
            async callable: on_payment_success(order_no, transaction_id, success_time)
        """
        from .recharge_callback import process_successful_payment

        async def _handler(order_no, transaction_id, trade_status=None, success_time=None):
            """支付成功回调处理"""
            db = db_session_factory()
            try:
                result = process_successful_payment(
                    db=db,
                    order_no=order_no,
                    transaction_id=transaction_id,
                    paid_at_str=success_time,
                    payment_order_model=payment_order_model,
                    user_balance_model=user_balance_model,
                    balance_log_model=balance_log_model,
                )
                return result
            except Exception as e:
                logger.error(f"支付宝支付成功处理异常: {e}", exc_info=True)
                db.rollback()
                return {"success": False, "order_no": order_no, "message": str(e)}
            finally:
                if db.is_active:
                    db.close()

        return _handler
