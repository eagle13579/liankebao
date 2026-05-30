"""支付宝支付提供者 — IPaymentProvider 预留实现

从 payment/alipay/__init__.py 提取核心逻辑 (AliPayCore, AliPayApi 框架)。
当前为预留桩 (stub)，只实现签名工具和 API 框架，await 方法为 NotImplemented。

后续计划:
    - 实现完整 alipay.trade.app.pay 统一下单
    - 实现 alipay.trade.query 订单查询
    - 实现 alipay.trade.refund 退款
    - 实现回调验签

注意: 本文件遵守 C-PAY-001，不依赖 backend/app/ 下的任何业务模块。
"""

import json
import logging
from typing import Any, Dict, Optional

from payment_sdk.config import AliPayConfig
from payment_sdk.payment_provider import IPaymentProvider, PaymentResult, CallbackResult

logger = logging.getLogger(__name__)


# ============================================================
# AliPayCore — 支付宝核心工具 (纯函数)
# ============================================================


class AliPayCore:
    """支付宝核心工具：签名生成与验证

    从 payment/alipay/__init__.py 提取，不做修改。
    """

    @staticmethod
    def sign(params: Dict[str, str], private_key_pem: str) -> str:
        """支付宝 RSA2 签名

        Args:
            params: 参数字典 (不含 sign/sign_type)
            private_key_pem: 应用私钥 PEM 字符串

        Returns:
            Base64 编码的签名
        """
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend
        import base64

        content = AliPayCore._build_sign_content(params)
        key_bytes = private_key_pem.encode("utf-8")
        private_key = serialization.load_pem_private_key(
            key_bytes, password=None, backend=default_backend(),
        )
        signature = private_key.sign(
            content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    @staticmethod
    def verify(params: Dict[str, str], public_key_pem: str, signature: str) -> bool:
        """支付宝 RSA2 验签

        Args:
            params: 参数字典
            public_key_pem: 支付宝公钥 PEM 字符串
            signature: Base64 编码的签名

        Returns:
            验签是否通过
        """
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend
        import base64

        content = AliPayCore._build_sign_content(params)
        try:
            public_key = serialization.load_pem_public_key(
                public_key_pem.encode("utf-8"), backend=default_backend(),
            )
            public_key.verify(
                base64.b64decode(signature),
                content.encode("utf-8"),
                padding.PKCS1v15(), hashes.SHA256(),
            )
            return True
        except Exception as e:
            logger.warning(f"支付宝验签失败: {e}")
            return False

    @staticmethod
    def _build_sign_content(params: Dict[str, str]) -> str:
        """构建待签名字符串 (key=value&... 按 key 升序)"""
        filtered = {
            k: v for k, v in params.items()
            if k not in ("sign", "sign_type") and v is not None and v != ""
        }
        return "&".join(f"{k}={filtered[k]}" for k in sorted(filtered.keys()))


# ============================================================
# AliPayProvider — 支付宝提供者 (预留桩)
# ============================================================


class AliPayProvider(IPaymentProvider):
    """支付宝支付提供者 (预留)

    当前为预留实现，pay/refund/query 方法返回 NotImplemented。
    callback_verify 已实现基础验签功能。

    用法:
        provider = AliPayProvider(config=AliPayConfig.from_env())
        result = await provider.callback_verify(body=..., headers=...)
    """

    def __init__(
        self,
        config: Optional[AliPayConfig] = None,
    ):
        """初始化支付宝提供者

        Args:
            config: 支付宝配置。为 None 时从环境变量自动加载。
        """
        self._config = config or AliPayConfig.from_env()

    async def pay(
        self,
        openid: str,
        out_trade_no: str,
        total_fee: int,
        description: str,
        **kwargs: Any,
    ) -> PaymentResult:
        """支付宝统一下单 (预留)

        待实现: alipay.trade.app.pay / alipay.trade.page.pay / alipay.trade.wap.pay
        """
        raise NotImplementedError(
            "支付宝支付功能尚未实现。"
            "请使用微信支付提供者 WxPayV2Provider 或 WxPayV3Provider。"
        )

    async def refund(
        self,
        out_trade_no: str,
        out_refund_no: str,
        refund_amount: int,
        total_amount: int,
        reason: Optional[str] = None,
        **kwargs: Any,
    ) -> PaymentResult:
        """支付宝退款 (预留)

        待实现: alipay.trade.refund
        """
        raise NotImplementedError(
            "支付宝退款功能尚未实现。"
            "请使用微信支付提供者。"
        )

    async def query(
        self,
        out_trade_no: str,
        **kwargs: Any,
    ) -> PaymentResult:
        """支付宝订单查询 (预留)

        待实现: alipay.trade.query
        """
        raise NotImplementedError(
            "支付宝订单查询功能尚未实现。"
            "请使用微信支付提供者。"
        )

    async def callback_verify(
        self,
        body: bytes,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> CallbackResult:
        """支付宝回调验签

        支付宝回调通过 POST 表单传递参数 (application/x-www-form-urlencoded)。
        使用 RSA2 验签。

        Args:
            body: 回调请求体 (表单字节)
            headers: 请求头
            **kwargs: 可选参数:
                params: 预解析的参数字典 (直接传入可跳过 body 解析)

        Returns:
            CallbackResult
        """
        cfg = self._config

        # 支持直接传入 params
        params = kwargs.get("params")
        if params is None:
            # 尝试从 body 解析表单
            import urllib.parse
            body_str = body.decode("utf-8") if isinstance(body, bytes) else body
            params = dict(urllib.parse.parse_qsl(body_str))

        if not params:
            return CallbackResult(verified=False, message="无回调参数")

        signature = params.get("sign", "")
        if not signature:
            return CallbackResult(verified=False, data=params, message="回调中无 sign 字段")

        if not cfg.alipay_public_key:
            return CallbackResult(verified=False, data=params, message="未配置支付宝公钥")

        is_valid = AliPayCore.verify(params, cfg.alipay_public_key, signature)
        if is_valid:
            return CallbackResult(
                verified=True,
                data=params,
                raw=params,
                message="支付宝回调验签通过",
            )

        return CallbackResult(
            verified=False,
            data=params,
            raw=params,
            message="支付宝回调验签失败",
        )

    @property
    def config(self) -> AliPayConfig:
        """获取当前配置"""
        return self._config
