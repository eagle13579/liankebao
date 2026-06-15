"""
支付宝模块 (Alipay)
基于 IJPay AliPay API 设计

功能:
    - AliPayApiConfig — 支付宝配置
    - AliPayApi — 统一下单框架
    - 签名生成与验签
"""

import json
import time
import logging
from typing import Optional, Dict, Any

from payment.config import AliPayConfig, get_config, PLATFORM_ALIPAY
from payment.http_delegate import HttpDelegate

logger = logging.getLogger(__name__)


# ============================================================
# AliPayCore — 支付宝核心工具
# ============================================================

class AliPayCore:
    """支付宝核心工具：签名生成与验证"""

    @staticmethod
    def sign(params: Dict[str, str], private_key_pem: str) -> str:
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
        filtered = {
            k: v for k, v in params.items()
            if k not in ("sign", "sign_type") and v is not None and v != ""
        }
        return "&".join(f"{k}={filtered[k]}" for k in sorted(filtered.keys()))


# ============================================================
# AliPayApi — 支付宝 API
# ============================================================

class AliPayApi:
    """支付宝 API 封装"""

    def __init__(
        self,
        config: Optional[AliPayConfig] = None,
        http_delegate: Optional[HttpDelegate] = None,
    ):
        self._config = config
        self._http = http_delegate or HttpDelegate.default()

    def _get_config(self) -> AliPayConfig:
        if self._config:
            return self._config
        cfg = get_config(PLATFORM_ALIPAY)
        if not isinstance(cfg, AliPayConfig):
            raise TypeError(f"期望 AliPayConfig，实际 {type(cfg)}")
        return cfg

    def _build_public_params(self, method: str) -> Dict[str, str]:
        config = self._get_config()
        return {
            "app_id": config.app_id,
            "method": method,
            "format": "JSON",
            "charset": config.charset,
            "sign_type": config.sign_type,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "version": "1.0",
        }

    async def unified_order(
        self,
        out_trade_no: str,
        total_amount: float,
        subject: str,
        product_code: str = "QUICK_MSECURITY_PAY",
        body: Optional[str] = None,
        passback_params: Optional[str] = None,
        timeout_express: str = "30m",
    ) -> Optional[Dict[str, Any]]:
        config = self._get_config()
        method = "alipay.trade.app.pay"

        params = self._build_public_params(method)
        biz_content = {
            "out_trade_no": out_trade_no,
            "total_amount": str(total_amount),
            "subject": subject,
            "product_code": product_code,
            "timeout_express": timeout_express,
        }
        if body:
            biz_content["body"] = body
        if passback_params:
            biz_content["passback_params"] = passback_params

        params["biz_content"] = json.dumps(biz_content, ensure_ascii=False)

        if config.private_key:
            params["sign"] = AliPayCore.sign(params, config.private_key)

        order_string = "&".join(f"{k}={v}" for k, v in params.items() if v)
        return {"order_string": order_string, "params": params}

    async def verify_notify(self, params: Dict[str, str]) -> bool:
        config = self._get_config()
        signature = params.get("sign", "")
        if not signature:
            logger.warning("支付宝通知中无 sign 字段")
            return False
        if not config.alipay_public_key:
            logger.warning("未配置支付宝公钥，无法验签")
            return False
        return AliPayCore.verify(params, config.alipay_public_key, signature)

    @classmethod
    def from_config(cls, config: Optional[AliPayConfig] = None) -> "AliPayApi":
        return cls(config=config)


__all__ = [
    "AliPayCore",
    "AliPayApi",
]
