"""微信支付提供者 — IPaymentProvider 完整实现

从旧版 payment/wxpay/__init__.py + payment_sdk/providers/wxpay_v3.py 提取核心逻辑
适配到 chainke-full 项目结构。

已实现功能:
    - JSAPI 统一下单 (V3)
    - 订单查询 (按商户订单号 / 微信交易号)
    - 关闭订单 (V3)
    - 退款 (V3)
    - 退款查询 (V3)
    - 回调验签 + resource 解密 (AES-256-GCM)

设计原则:
    - 不依赖 backend/app/ 下的任何业务模块
    - 纯函数 + 依赖注入
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)


# ============================================================
# 结构化结果类型 (PaymentResult / CallbackResult)
# ============================================================


@dataclass
class PaymentResult:
    """支付操作统一结果"""

    success: bool = False
    code: str = ""
    message: str = ""
    data: dict[str, Any] | None = None
    provider_order_id: str = ""
    out_trade_no: str = ""

    @classmethod
    def ok(cls, **kwargs) -> "PaymentResult":
        return cls(success=True, code="SUCCESS", **kwargs)

    @classmethod
    def fail(cls, message: str = "", code: str = "FAIL", **kwargs) -> "PaymentResult":
        return cls(success=False, code=code, message=message, **kwargs)


@dataclass
class CallbackResult:
    """支付回调验证结果"""

    verified: bool = False
    data: dict[str, Any] | None = None
    raw: Any = None
    message: str = ""


# ============================================================
# 常量
# ============================================================

WECHAT_V3_BASE = "https://api.mch.weixin.qq.com/v3"
WECHAT_API_BASE = "https://api.mch.weixin.qq.com"

# V3 API 路径
V3_JSAPI_PAY = "/v3/pay/transactions/jsapi"
V3_ORDER_QUERY_BY_OUT_TRADE_NO = "/v3/pay/transactions/out-trade-no/%s"
V3_ORDER_QUERY_BY_TRANSACTION_ID = "/v3/pay/transactions/id/%s"
V3_CLOSE_ORDER = "/v3/pay/transactions/out-trade-no/%s/close"
V3_REFUND = "/v3/refund/domestic/refunds"
V3_REFUND_QUERY = "/v3/refund/domestic/refunds/%s"
V3_CERTIFICATES = "/v3/certificates"

# V2 API 路径
V2_UNIFIED_ORDER = f"{WECHAT_API_BASE}/pay/unifiedorder"
V2_ORDER_QUERY = f"{WECHAT_API_BASE}/pay/orderquery"
V2_REFUND = f"{WECHAT_API_BASE}/secapi/pay/refund"
V2_REFUND_QUERY = f"{WECHAT_API_BASE}/pay/refundquery"
V2_CLOSE_ORDER_URL = f"{WECHAT_API_BASE}/pay/closeorder"


# ============================================================
# WxPayConfig — 微信支付配置数据类
# ============================================================


# 环境变量前缀及字段名映射表（WXPAY_* 优先，WECHAT_* 后备）
_WXPAY_ENV_SUFFIXES = {
    "app_id": ["APPID", "APP_ID"],
    "mch_id": ["MCH_ID", "MCHID"],
    "api_key": ["API_KEY", "KEY"],
    "api_v3_key": ["API_V3_KEY", "APIV3_KEY"],
    "private_key_path": ["PRIVATE_KEY_PATH"],
    "cert_serial_no": ["CERT_SERIAL_NO"],
    "notify_url": ["NOTIFY_URL"],
    "refund_notify_url": ["REFUND_NOTIFY_URL"],
    "cert_path": ["CERT_PATH"],
    "root_ca_path": ["ROOT_CA_PATH"],
}


def _get_env_dual(key_name: str) -> str:
    """读取环境变量，同时支持 WXPAY_* 和 WECHAT_* 两种前缀"""
    suffixes = _WXPAY_ENV_SUFFIXES.get(key_name, [key_name.upper()])
    for suffix in suffixes:
        for prefix in ("WXPAY_", "WECHAT_"):
            val = os.environ.get(f"{prefix}{suffix}")
            if val:
                return val
    return ""


@dataclass
class WxPayConfig:
    """微信支付配置 (纯数据类)

    Attributes:
        app_id: 小程序/公众号 AppID
        mch_id: 商户号
        api_key: V2 密钥 (MD5)
        api_v3_key: V3 密钥 (AES-256-GCM 解密)
        private_key_path: apiclient_key.pem 路径 (V3 签名)
        cert_serial_no: 证书序列号 (V3 签名)
        notify_url: 支付回调通知 URL
        refund_notify_url: 退款回调通知 URL
        cert_path: apiclient_cert.pem (双向证书)
        root_ca_path: rootca.pem
    """

    app_id: str = ""
    mch_id: str = ""
    api_key: str = ""
    api_v3_key: str = ""
    private_key_path: str = ""
    cert_serial_no: str = ""
    notify_url: str = ""
    refund_notify_url: str = ""
    cert_path: str = ""
    root_ca_path: str = ""

    @classmethod
    def from_env(cls, prefix: str = "WECHAT_") -> "WxPayConfig":
        """从环境变量读取配置。同时支持 WXPAY_* 和 WECHAT_* 前缀。"""
        return cls(
            app_id=_get_env_dual("app_id"),
            mch_id=_get_env_dual("mch_id"),
            api_key=_get_env_dual("api_key"),
            api_v3_key=_get_env_dual("api_v3_key"),
            private_key_path=_get_env_dual("private_key_path"),
            cert_serial_no=_get_env_dual("cert_serial_no"),
            notify_url=_get_env_dual("notify_url"),
            refund_notify_url=_get_env_dual("refund_notify_url"),
            cert_path=_get_env_dual("cert_path"),
            root_ca_path=_get_env_dual("root_ca_path"),
        )

    @property
    def is_configured(self) -> bool:
        """检查配置是否完整（至少需要 app_id + mch_id + api_key）"""
        return bool(self.app_id and self.mch_id and self.api_key)


# ============================================================
# WxPayCore — 微信支付核心工具 (纯函数)
# ============================================================


class WxPayCore:
    """微信支付核心工具：签名生成与验证、AES-GCM 解密

    从旧版 payment/wxpay/__init__.py + payment_sdk/sign.py 提取。
    """

    @staticmethod
    def generate_nonce(length: int = 32) -> str:
        """生成随机字符串"""
        return secrets.token_hex(length // 2)[:length]

    @staticmethod
    def build_v3_sign_str(method: str, url: str, timestamp: str, nonce: str, body: str) -> str:
        """构造微信 V3 签名串

        格式:
            HTTP动词\\n
            请求网址\\n
            请求时间戳\\n
            请求随机串\\n
            请求报文主体\\n
        """
        return f"{method}\n{url}\n{timestamp}\n{nonce}\n{body}\n"

    @staticmethod
    def build_v3_response_sign_str(timestamp: str, nonce: str, body: str) -> str:
        """构造微信 V3 回调响应签名串

        格式:
            时间戳\\n
            随机串\\n
            报文主体\\n
        """
        return f"{timestamp}\n{nonce}\n{body}\n"

    @staticmethod
    def rsa_sign(content: str, private_key_path: str) -> str:
        """RSA-SHA256 签名 (微信 V3)"""
        try:
            with open(private_key_path, "rb") as f:
                private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=default_backend(),
                )
        except Exception as e:
            logger.error(f"加载私钥失败: {private_key_path} — {e}")
            raise

        signature = private_key.sign(
            content.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    @staticmethod
    def rsa_verify_with_key(content: str, signature_b64: str, public_key_pem: bytes) -> bool:
        """RSA-SHA256 验签 (使用 PEM 字节)"""
        try:
            public_key = serialization.load_pem_public_key(
                public_key_pem, backend=default_backend()
            )
            signature = base64.b64decode(signature_b64)
            public_key.verify(
                signature,
                content.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except Exception as e:
            logger.warning(f"RSA 验签失败: {e}")
            return False

    @staticmethod
    def aes_gcm_decrypt(ciphertext_b64: str, key: str, nonce: str, associated_data: str) -> str | None:
        """AES-256-GCM 解密 (微信 V3 回调 resource 解密)"""
        try:
            key_bytes = key.encode("utf-8")
            nonce_bytes = nonce.encode("utf-8")
            aad_bytes = associated_data.encode("utf-8")
            ciphertext = base64.b64decode(ciphertext_b64)

            aesgcm = AESGCM(key_bytes)
            plaintext = aesgcm.decrypt(nonce_bytes, ciphertext, aad_bytes)
            return plaintext.decode("utf-8")
        except Exception as e:
            logger.error(f"AES-GCM 解密失败: {e}")
            return None

    @staticmethod
    def md5_upper(data: str) -> str:
        """MD5 哈希 (16进制大写) — 微信 V2 签名格式"""
        return hashlib.md5(data.encode("utf-8")).hexdigest().upper()

    @staticmethod
    def hmac_sha256_upper(data: str, key: str) -> str:
        """HMAC-SHA256 (16进制大写) — 微信 V2 签名格式"""
        h = hmac.new(key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256)
        return h.hexdigest().upper()

    @staticmethod
    def build_v2_sign(params: dict, api_key: str, sign_type: str = "MD5") -> str:
        """构建微信 V2 签名"""
        filtered = {
            k: v
            for k, v in params.items()
            if v != "" and v is not None and k != "sign"
        }
        sorted_keys = sorted(filtered.keys())
        parts = [f"{k}={filtered[k]}" for k in sorted_keys]
        sign_str = "&".join(parts) + f"&key={api_key}"

        if sign_type == "HMAC-SHA256":
            return WxPayCore.hmac_sha256_upper(sign_str, api_key)
        else:
            return WxPayCore.md5_upper(sign_str)

    @staticmethod
    def verify_v2_sign(params: dict, api_key: str, sign_type: str = "MD5") -> bool:
        """验证微信 V2 签名"""
        received_sign = params.get("sign", "")
        if not received_sign:
            logger.warning("V2 回调中无 sign 字段")
            return False

        calculated = WxPayCore.build_v2_sign(params, api_key, sign_type)
        if calculated == received_sign:
            return True

        # 如果指定了 MD5，尝试 HMAC-SHA256 (微信可能混合使用)
        if sign_type == "MD5":
            calculated2 = WxPayCore.build_v2_sign(params, api_key, "HMAC-SHA256")
            if calculated2 == received_sign:
                return True

        return False


# ============================================================
# WxPayProvider — 微信支付提供者 (完整实现)
# ============================================================


class WxPayProvider:
    """微信支付提供者

    支持 V3 JSAPI 统一下单、订单查询、关闭订单、退款、退款查询、回调验签。
    所有 V3 操作使用 JSON 格式 + WECHATPAY2-SHA256-RSA2048 签名。

    用法:
        provider = WxPayProvider(
            config=WxPayConfig.from_env(),
        )
        result = await provider.pay(openid="...", out_trade_no="...", total_fee=100, description="...")
    """

    def __init__(
        self,
        config: WxPayConfig | None = None,
    ):
        """初始化微信支付提供者

        Args:
            config: 微信支付配置。为 None 时从环境变量自动加载。
        """
        self._config = config or WxPayConfig.from_env()
        self._http = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "chainke-payment/1.0",
                "Accept": "application/json",
            },
        )

    @property
    def config(self) -> WxPayConfig:
        """获取当前配置"""
        return self._config

    # ==================== 鉴权头生成 (V3) ====================

    def _get_auth_headers(self, method: str, url_path: str, body: str = "") -> dict[str, str]:
        """生成微信 V3 API 鉴权头

        Authorization: WECHATPAY2-SHA256-RSA2048 mchid="...",nonce_str="...",...
        """
        cfg = self._config
        timestamp = str(int(time.time()))
        nonce = WxPayCore.generate_nonce(32)
        sign_str = WxPayCore.build_v3_sign_str(method, url_path, timestamp, nonce, body)
        signature = WxPayCore.rsa_sign(sign_str, cfg.private_key_path)

        auth = (
            f"WECHATPAY2-SHA256-RSA2048 "
            f'mchid="{cfg.mch_id}",'
            f'nonce_str="{nonce}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{cfg.cert_serial_no}",'
            f'signature="{signature}"'
        )
        return {
            "Authorization": auth,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "chainke-payment/1.0",
        }

    # ==================== 支付接口 ====================

    async def pay(
        self,
        openid: str,
        out_trade_no: str,
        total_fee: int,
        description: str,
        **kwargs: Any,
    ) -> PaymentResult:
        """微信 V3 JSAPI 统一下单

        Args:
            openid: 用户微信 openid
            out_trade_no: 商户订单号
            total_fee: 订单金额 (单位: 分)
            description: 商品描述 (最长 127 字符)
            **kwargs: 可选参数:
                attach: 附加数据 (最长 127 字符)
                time_expire: 订单过期时间 (RFC 3339 格式)
                goods_tag: 商品标记

        Returns:
            PaymentResult
                - data.prepay_id: 预支付 ID
                - data.payment_params: JSAPI 调起支付参数
        """
        cfg = self._config

        body: dict[str, Any] = {
            "appid": cfg.app_id,
            "mchid": cfg.mch_id,
            "description": description[:127],
            "out_trade_no": out_trade_no,
            "notify_url": cfg.notify_url,
            "amount": {"total": total_fee, "currency": "CNY"},
            "payer": {"openid": openid},
        }

        if "attach" in kwargs:
            body["attach"] = kwargs["attach"][:127]
        if "time_expire" in kwargs:
            body["time_expire"] = kwargs["time_expire"]
        if "goods_tag" in kwargs:
            body["goods_tag"] = kwargs["goods_tag"]

        body_json = json.dumps(body, ensure_ascii=False)
        headers = self._get_auth_headers("POST", V3_JSAPI_PAY, body_json)

        url = f"{WECHAT_V3_BASE}{V3_JSAPI_PAY}"

        try:
            resp = await self._http.post(url, content=body_json, headers=headers)
        except httpx.HTTPError as e:
            logger.error(f"微信 V3 JSAPI 统一下单请求失败: {e}")
            return PaymentResult.fail(message=f"微信支付请求失败: {e}")

        if resp.is_success:
            result = resp.json()
            prepay_id = result.get("prepay_id", "") if result else ""
            if prepay_id:
                payment_params = self._build_jsapi_payment_params(prepay_id)
                return PaymentResult.ok(
                    data={
                        "prepay_id": prepay_id,
                        "payment_params": payment_params,
                    },
                    provider_order_id=prepay_id,
                    out_trade_no=out_trade_no,
                )

        logger.error(
            f"V3 JSAPI 统一下单失败: status={resp.status_code}, body={resp.text}"
        )
        return PaymentResult.fail(
            message=f"统一下单失败: HTTP {resp.status_code}"
        )

    async def refund(
        self,
        out_trade_no: str,
        out_refund_no: str,
        refund_amount: int,
        total_amount: int,
        reason: str | None = None,
        **kwargs: Any,
    ) -> PaymentResult:
        """微信 V3 退款

        Args:
            out_trade_no: 原商户订单号
            out_refund_no: 退款单号
            refund_amount: 退款金额 (分)
            total_amount: 原订单总金额 (分)
            reason: 退款原因
            **kwargs: 可选参数:
                notify_url: 退款结果通知 URL

        Returns:
            PaymentResult
        """
        cfg = self._config

        body: dict[str, Any] = {
            "out_trade_no": out_trade_no,
            "out_refund_no": out_refund_no,
            "amount": {
                "refund": refund_amount,
                "total": total_amount,
                "currency": "CNY",
            },
        }
        if reason:
            body["reason"] = reason
        body["notify_url"] = kwargs.get(
            "notify_url", cfg.refund_notify_url or cfg.notify_url
        )

        body_json = json.dumps(body, ensure_ascii=False)
        headers = self._get_auth_headers("POST", V3_REFUND, body_json)

        # V3 退款需要双向 SSL (使用商户证书)
        ssl_cert = None
        if cfg.cert_path and cfg.private_key_path:
            ssl_cert = (cfg.cert_path, cfg.private_key_path)

        url = f"{WECHAT_V3_BASE}{V3_REFUND}"

        try:
            http_client = httpx.AsyncClient(
                cert=ssl_cert,
                timeout=30.0,
                headers=headers,
            )
            resp = await http_client.post(url, content=body_json)
            await http_client.aclose()
        except httpx.HTTPError as e:
            logger.error(f"微信 V3 退款请求失败: {e}")
            return PaymentResult.fail(message=f"微信退款请求失败: {e}")

        if resp.is_success:
            result = resp.json()
            logger.info(f"V3 退款申请成功: out_refund_no={out_refund_no}")
            return PaymentResult.ok(
                data=result,
                provider_order_id=result.get("refund_id", ""),
                out_trade_no=out_trade_no,
            )

        logger.error(
            f"V3 退款申请失败: status={resp.status_code}, body={resp.text}"
        )
        return PaymentResult.fail(
            message=f"退款失败: HTTP {resp.status_code}"
        )

    async def query(
        self,
        out_trade_no: str,
        **kwargs: Any,
    ) -> PaymentResult:
        """微信 V3 订单查询

        Args:
            out_trade_no: 商户订单号
            **kwargs: 可选参数:
                transaction_id: 微信支付订单号 (优先使用)

        Returns:
            PaymentResult
        """
        cfg = self._config

        if "transaction_id" in kwargs:
            url_path = V3_ORDER_QUERY_BY_TRANSACTION_ID % kwargs["transaction_id"]
        else:
            url_path = V3_ORDER_QUERY_BY_OUT_TRADE_NO % out_trade_no
            url_path = f"{url_path}?mchid={cfg.mch_id}"

        headers = self._get_auth_headers("GET", url_path)
        url = f"{WECHAT_V3_BASE}{url_path}"

        try:
            resp = await self._http.get(url, headers=headers)
        except httpx.HTTPError as e:
            logger.error(f"微信 V3 订单查询请求失败: {e}")
            return PaymentResult.fail(message=f"订单查询请求失败: {e}")

        if resp.is_success:
            result = resp.json()
            return PaymentResult.ok(
                data=result,
                provider_order_id=(result or {}).get("transaction_id", ""),
                out_trade_no=out_trade_no,
            )

        logger.error(
            f"V3 订单查询失败: {out_trade_no}, status={resp.status_code}"
        )
        return PaymentResult.fail(
            message=f"订单查询失败: HTTP {resp.status_code}"
        )

    async def callback_verify(
        self,
        body: bytes,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> CallbackResult:
        """微信 V3 回调验签

        V3 回调包含:
            - Wechatpay-Signature: Base64 签名
            - Wechatpay-Serial: 平台证书序列号
            - Wechatpay-Timestamp: 时间戳
            - Wechatpay-Nonce: 随机串
            - body: 回调 JSON (含加密的 resource)

        Args:
            body: 回调请求体 (原始字节)
            headers: 请求头 (含 Wechatpay-* 签名相关头)
            **kwargs: 可选参数:
                platform_cert_map: {serial_no: pem_bytes} 平台证书映射
                decrypt: 是否解密 resource (默认 True)

        Returns:
            CallbackResult
        """
        cfg = self._config
        hdrs = headers or {}

        wechatpay_signature = hdrs.get("Wechatpay-Signature", "")
        wechatpay_serial = hdrs.get("Wechatpay-Serial", "")
        wechatpay_timestamp = hdrs.get("Wechatpay-Timestamp", "")
        wechatpay_nonce = hdrs.get("Wechatpay-Nonce", "")

        if not wechatpay_signature or not wechatpay_serial:
            return CallbackResult(verified=False, message="缺少 Wechatpay 签名头")

        # 获取平台证书
        platform_cert_map = kwargs.get("platform_cert_map", {})
        pub_key_pem = platform_cert_map.get(wechatpay_serial)
        if not pub_key_pem:
            pub_key_pem = self._load_platform_cert(wechatpay_serial)
        if not pub_key_pem:
            return CallbackResult(
                verified=False,
                message=f"未找到平台证书: serial={wechatpay_serial}",
            )

        body_str = (
            body.decode("utf-8") if isinstance(body, bytes) else body
        )
        sign_str = WxPayCore.build_v3_response_sign_str(
            wechatpay_timestamp, wechatpay_nonce, body_str
        )

        if not WxPayCore.rsa_verify_with_key(
            sign_str, wechatpay_signature, pub_key_pem
        ):
            return CallbackResult(
                verified=False, raw=body_str, message="签名验证失败"
            )

        # 解析 body JSON
        try:
            notify_data = json.loads(body_str)
        except json.JSONDecodeError:
            return CallbackResult(
                verified=False, raw=body_str, message="body 不是有效 JSON"
            )

        # 解密 resource (默认解密)
        decrypt = kwargs.get("decrypt", True)
        if decrypt:
            resource = notify_data.get("resource", {})
            ciphertext = resource.get("ciphertext", "")
            nonce = resource.get("nonce", "")
            associated_data = resource.get("associated_data", "")

            if ciphertext and cfg.api_v3_key:
                plaintext = WxPayCore.aes_gcm_decrypt(
                    ciphertext, cfg.api_v3_key, nonce, associated_data
                )
                if plaintext is None:
                    return CallbackResult(
                        verified=True,
                        data=notify_data,
                        raw=body_str,
                        message="签名通过但 resource 解密失败",
                    )
                try:
                    decrypted_data = json.loads(plaintext)
                except json.JSONDecodeError:
                    decrypted_data = plaintext

                return CallbackResult(
                    verified=True,
                    data=decrypted_data,
                    raw=notify_data,
                    message="验签通过",
                )

        return CallbackResult(
            verified=True,
            data=notify_data,
            raw=notify_data,
            message="验签通过 (未解密)",
        )

    # ==================== 附加方法 ====================

    async def close_order(self, out_trade_no: str) -> bool:
        """微信 V3 关闭订单"""
        cfg = self._config
        body = json.dumps({"mchid": cfg.mch_id})
        headers = self._get_auth_headers(
            "POST", V3_CLOSE_ORDER % out_trade_no, body
        )
        url = f"{WECHAT_V3_BASE}{V3_CLOSE_ORDER % out_trade_no}"

        try:
            resp = await self._http.post(
                url, content=body, headers=headers
            )
        except httpx.HTTPError as e:
            logger.error(f"微信 V3 关闭订单请求失败: {e}")
            return False

        if resp.is_success:
            logger.info(f"V3 订单关闭成功: {out_trade_no}")
            return True

        logger.error(
            f"V3 订单关闭失败: {out_trade_no}, status={resp.status_code}"
        )
        return False

    async def query_refund(self, out_refund_no: str) -> PaymentResult:
        """微信 V3 退款查询"""
        url_path = V3_REFUND_QUERY % out_refund_no
        headers = self._get_auth_headers("GET", url_path)
        url = f"{WECHAT_V3_BASE}{url_path}"

        try:
            resp = await self._http.get(url, headers=headers)
        except httpx.HTTPError as e:
            logger.error(f"微信 V3 退款查询请求失败: {e}")
            return PaymentResult.fail(message=f"退款查询请求失败: {e}")

        if resp.is_success:
            result = resp.json()
            return PaymentResult.ok(
                data=result,
                provider_order_id=(result or {}).get("refund_id", ""),
                out_trade_no=out_refund_no,
            )

        logger.error(
            f"V3 退款查询失败: {out_refund_no}, status={resp.status_code}"
        )
        return PaymentResult.fail(
            message=f"退款查询失败: HTTP {resp.status_code}"
        )

    # ==================== V2 兼容接口 ====================

    async def create_order_v2(
        self,
        openid: str,
        out_trade_no: str,
        total_fee: int,
        description: str,
        spbill_create_ip: str = "127.0.0.1",
    ) -> dict | None:
        """微信 V2 统一下单 (XML 格式)"""
        import xml.etree.ElementTree as ET

        cfg = self._config
        params: dict[str, str] = {
            "appid": cfg.app_id,
            "mch_id": cfg.mch_id,
            "nonce_str": WxPayCore.generate_nonce(32),
            "body": description[:127],
            "out_trade_no": out_trade_no,
            "total_fee": str(total_fee),
            "spbill_create_ip": spbill_create_ip,
            "notify_url": cfg.notify_url,
            "trade_type": "JSAPI",
            "openid": openid,
        }
        params["sign"] = WxPayCore.build_v2_sign(params, cfg.api_key)

        root = ET.Element("xml")
        for k, v in params.items():
            child = ET.SubElement(root, k)
            child.text = str(v)
        xml_data = ET.tostring(root, encoding="utf-8").decode("utf-8")

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "Accept": "text/xml",
        }
        try:
            resp = await self._http.post(
                V2_UNIFIED_ORDER, content=xml_data, headers=headers
            )
            root = ET.fromstring(resp.text)
            return {child.tag: child.text for child in root}
        except Exception as e:
            logger.error(f"V2 统一下单 XML 解析失败: {e}")
            return None

    # ==================== 内部方法 ====================

    def _build_jsapi_payment_params(self, prepay_id: str) -> dict[str, str]:
        """构建 JSAPI 调起支付参数"""
        cfg = self._config
        timestamp = str(int(time.time()))
        nonce = WxPayCore.generate_nonce(32)
        package = f"prepay_id={prepay_id}"
        sign_str = f"{cfg.app_id}\n{timestamp}\n{nonce}\n{package}\n"
        pay_sign = WxPayCore.rsa_sign(sign_str, cfg.private_key_path)
        return {
            "appId": cfg.app_id,
            "timeStamp": timestamp,
            "nonceStr": nonce,
            "package": package,
            "signType": "RSA",
            "paySign": pay_sign,
        }

    def _load_platform_cert(self, serial_no: str) -> bytes | None:
        """尝试从本地缓存加载微信平台证书"""
        cert_path = f"/certs/wechat_platform_{serial_no}.pem"
        try:
            with open(cert_path, "rb") as f:
                return f.read()
        except (FileNotFoundError, OSError):
            pass
        return None


__all__ = [
    "WxPayProvider",
    "WxPayConfig",
    "WxPayCore",
    "PaymentResult",
    "CallbackResult",
    "WECHAT_V3_BASE",
    "V3_JSAPI_PAY",
    "V3_ORDER_QUERY_BY_OUT_TRADE_NO",
    "V3_ORDER_QUERY_BY_TRANSACTION_ID",
    "V3_CLOSE_ORDER",
    "V3_REFUND",
    "V3_REFUND_QUERY",
    "V3_CERTIFICATES",
]
