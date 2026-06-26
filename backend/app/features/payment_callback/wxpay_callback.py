"""微信支付回调验签服务

从旧版链客宝 recharge/callback.py 中的 wxpay_callback 路由逻辑迁移。

验签委托给 payment/providers/wxpay.py 的 WxPayProvider.callback_verify()。
验签通过后调用 recharge_callback.process_successful_payment() 更新订单/余额。
"""

import json
import logging
from typing import Optional

from fastapi import Request

logger = logging.getLogger(__name__)


class WxPayCallbackService:
    """微信支付回调验签服务

    封装微信 V3 回调的验签、解密、业务处理流程。
    不直接依赖 FastAPI Request，可测试。
    """

    def __init__(self, wxpay_provider=None):
        """初始化微信回调服务

        Args:
            wxpay_provider: WxPayProvider 实例。为 None 时延迟初始化。
        """
        self._provider = wxpay_provider

    def _get_provider(self):
        """获取 WxPayProvider 实例（延迟加载）"""
        if self._provider is None:
            from payment.providers.wxpay import WxPayConfig, WxPayProvider

            config = WxPayConfig.from_env()
            self._provider = WxPayProvider(config=config)
        return self._provider

    async def verify_and_process(
        self,
        request: Request,
        body: Optional[bytes] = None,
        on_payment_success=None,
        **provider_kwargs,
    ) -> dict:
        """微信支付回调验签 + 解密 + 业务处理

        流程:
            1. 获取请求头 (Wechatpay-Signature/Serial/Timestamp/Nonce)
            2. 读取请求体
            3. 调用 provider.callback_verify() 验签 + 解密
            4. 解析解密后的支付结果
            5. 调用 on_payment_success 回调处理业务

        Args:
            request: FastAPI Request 对象
            body: 预读取的请求体字节（可选，不传则自动读取）
            on_payment_success: 支付成功回调函数
                async def on_payment_success(order_no, transaction_id, trade_state, success_time)
                返回 {"success": bool, "message": str}
            **provider_kwargs: 传递给 provider.callback_verify 的额外参数
                platform_cert_map: {serial_no: pem_bytes}
                decrypt: 是否解密 resource (默认 True)

        Returns:
            处理结果字典: {"code": "SUCCESS"/"FAIL", "message": str}
        """
        # 1. 获取请求头
        wechatpay_signature = request.headers.get("Wechatpay-Signature", "")
        wechatpay_serial = request.headers.get("Wechatpay-Serial", "")
        wechatpay_timestamp = request.headers.get("Wechatpay-Timestamp", "")
        wechatpay_nonce = request.headers.get("Wechatpay-Nonce", "")

        if not all([wechatpay_signature, wechatpay_serial, wechatpay_timestamp, wechatpay_nonce]):
            logger.warning("微信回调缺少验签请求头")
            return {"code": "FAIL", "message": "缺少验签参数"}

        # 2. 读取请求体
        if body is None:
            body = await request.body()

        # 3. 验签 + 解密
        provider = self._get_provider()
        headers_dict = {
            "Wechatpay-Signature": wechatpay_signature,
            "Wechatpay-Serial": wechatpay_serial,
            "Wechatpay-Timestamp": wechatpay_timestamp,
            "Wechatpay-Nonce": wechatpay_nonce,
        }

        cb_result = await provider.callback_verify(
            body=body,
            headers=headers_dict,
            **provider_kwargs,
        )

        if not cb_result.verified:
            logger.error(f"微信回调验签失败: {cb_result.message}")
            return {"code": "FAIL", "message": cb_result.message}

        # 4. 解析支付结果
        plaintext = cb_result.data or {}
        out_trade_no = plaintext.get("out_trade_no", "")
        transaction_id = plaintext.get("transaction_id", "")
        trade_state = plaintext.get("trade_state", "")
        success_time = plaintext.get("success_time", None)

        if not out_trade_no:
            logger.error("回调数据中缺少 out_trade_no")
            return {"code": "FAIL", "message": "缺少订单号"}

        if trade_state != "SUCCESS":
            logger.info(
                f"支付未成功，跳过处理: out_trade_no={out_trade_no}, "
                f"trade_state={trade_state}"
            )
            return {"code": "SUCCESS", "message": "收到通知"}

        # 5. 业务处理
        if on_payment_success:
            result = await on_payment_success(
                order_no=out_trade_no,
                transaction_id=transaction_id,
                trade_state=trade_state,
                success_time=success_time,
            )
            if not result.get("success", False):
                return {"code": "FAIL", "message": result.get("message", "处理失败")}

        # 6. 返回微信要求的成功响应
        return {"code": "SUCCESS", "message": "成功"}

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

        async def _handler(order_no, transaction_id, trade_state, success_time=None):
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
                logger.error(f"支付成功处理异常: {e}", exc_info=True)
                db.rollback()
                return {"success": False, "order_no": order_no, "message": str(e)}
            finally:
                if db.is_active:
                    db.close()

        return _handler
