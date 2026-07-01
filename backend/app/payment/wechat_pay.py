"""
微信支付 V3 SDK — 链客宝集成层
================================
基于自建 V3 签名工具 (cryptography) + httpx，无外部支付 SDK 依赖。

功能：
  - 下单 (JSAPI / APP / H5 / Native)
  - 退款
  - 订单查询
  - 退款查询
  - 关闭订单
  - 回调验证 (签名验签 + resource AES-GCM 解密)
  - 平台证书下载与缓存

配置 (环境变量 / .env):
  WECHAT_MCHID         — 商户号
  WECHAT_API_KEY       — APIv2 密钥 (V2 兼容)
  WECHAT_API_V3_KEY    — APIv3 密钥 (AES-GCM 解密用)
  WECHAT_CERT_PATH     — 商户私钥证书路径 (apiclient_key.pem)
  WECHAT_CERT_SERIAL   — 商户证书序列号
  WECHAT_NOTIFY_URL    — 支付回调通知 URL
  WECHAT_APPID         — 公众号/小程序 AppID
"""

# ---------------------------------------------------------------------------
# 自建 V3 签名工具 (零外部依赖，仅使用 cryptography)
# ---------------------------------------------------------------------------
import base64
import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# =========================================================================
# 常量
# =========================================================================

WECHAT_API_BASE = "https://api.mch.weixin.qq.com"
WECHAT_V3_BASE = "https://api.mch.weixin.qq.com/v3"

V3_JSAPI_PAY = "/v3/pay/transactions/jsapi"
V3_APP_PAY = "/v3/pay/transactions/app"
V3_H5_PAY = "/v3/pay/transactions/h5"
V3_NATIVE_PAY = "/v3/pay/transactions/native"
V3_ORDER_QUERY_BY_OUT = "/v3/pay/transactions/out-trade-no/%s"
V3_ORDER_QUERY_BY_ID = "/v3/pay/transactions/id/%s"
V3_CLOSE_ORDER = "/v3/pay/transactions/out-trade-no/%s/close"
V3_REFUND = "/v3/refund/domestic/refunds"
V3_REFUND_QUERY = "/v3/refund/domestic/refunds/%s"
V3_CERTIFICATES = "/v3/certificates"

TRADE_STATE_SUCCESS = "SUCCESS"
TRADE_STATE_REFUND = "REFUND"
TRADE_STATE_NOTPAY = "NOTPAY"
TRADE_STATE_CLOSED = "CLOSED"
TRADE_STATE_REVOKED = "REVOKED"
TRADE_STATE_USERPAYING = "USERPAYING"
TRADE_STATE_PAYERROR = "PAYERROR"


# =========================================================================
# 工具函数
# =========================================================================


def generate_nonce(length: int = 32) -> str:
    """生成安全随机字符串"""
    return secrets.token_hex(length // 2)[:length]


def sha256(data: str) -> str:
    """SHA-256 哈希"""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def build_v3_sign_str(method: str, url: str, timestamp: str, nonce: str, body: str) -> str:
    """构建微信 V3 签名串"""
    return f"{method}\n{url}\n{timestamp}\n{nonce}\n{body}\n"


def build_v3_response_sign_str(timestamp: str, nonce: str, body: str) -> str:
    """构建微信回调响应签名串 (用于验签)"""
    return f"{timestamp}\n{nonce}\n{body}\n"


def _load_private_key(key_path: str) -> rsa.RSAPrivateKey:
    """从 PEM 文件加载 RSA 私钥"""
    with open(key_path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())


def rsa_sign(content: str, private_key_path: str) -> str:
    """RSA-SHA256 签名 → Base64"""
    private_key = _load_private_key(private_key_path)
    signature = private_key.sign(
        content.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def rsa_sign_with_key(content: str, private_key_pem: bytes) -> str:
    """RSA-SHA256 签名 (使用 PEM 字节, 无需文件路径)"""
    private_key = serialization.load_pem_private_key(private_key_pem, password=None, backend=default_backend())
    signature = private_key.sign(
        content.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def rsa_verify(content: str, signature_b64: str, public_key_pem: bytes) -> bool:
    """RSA-SHA256 验签"""
    try:
        public_key = serialization.load_pem_public_key(public_key_pem, backend=default_backend())
        signature = base64.b64decode(signature_b64)
        public_key.verify(
            signature,
            content.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception as e:
        logger.warning(f"验签失败: {e}")
        return False


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


# =========================================================================
# 数据模型
# =========================================================================


@dataclass
class WeChatPayConfig:
    """微信支付配置 (从环境变量加载)"""

    mch_id: str = ""
    api_key: str = ""  # V2 密钥
    api_v3_key: str = ""  # V3 密钥 (32字节, AES-GCM 解密用)
    app_id: str = ""
    cert_path: str = ""  # 商户私钥证书路径
    cert_serial_no: str = ""  # 商户证书序列号
    notify_url: str = ""  # 支付回调地址
    refund_notify_url: str = ""  # 退款回调地址 (可选)
    platform_cert_dir: str = ""  # 平台证书缓存目录

    @classmethod
    def from_env(cls, prefix: str = "WECHAT_") -> "WeChatPayConfig":
        """从环境变量加载配置"""
        return cls(
            mch_id=os.environ.get(f"{prefix}MCHID", ""),
            api_key=os.environ.get(f"{prefix}API_KEY", ""),
            api_v3_key=os.environ.get(f"{prefix}API_V3_KEY", ""),
            app_id=os.environ.get(f"{prefix}APPID", ""),
            cert_path=os.environ.get(f"{prefix}CERT_PATH", ""),
            cert_serial_no=os.environ.get(f"{prefix}CERT_SERIAL", ""),
            notify_url=os.environ.get(f"{prefix}NOTIFY_URL", ""),
            refund_notify_url=os.environ.get(f"{prefix}REFUND_NOTIFY_URL", ""),
            platform_cert_dir=os.environ.get(f"{prefix}PLATFORM_CERT_DIR", "/tmp/wechat_certs"),
        )

    def is_ready(self) -> bool:
        """检查配置是否足以发起真实支付"""
        missing = []
        if not self.mch_id:
            missing.append("WECHAT_MCHID")
        if not self.api_v3_key:
            missing.append("WECHAT_API_V3_KEY")
        if not self.cert_path:
            missing.append("WECHAT_CERT_PATH")
        if not os.path.isfile(self.cert_path):
            missing.append(f"WECHAT_CERT_PATH 文件不存在 ({self.cert_path})")
        if not self.app_id:
            missing.append("WECHAT_APPID")
        return missing, missing

    def to_dict(self) -> dict:
        """转为字典 (隐藏密钥)"""
        return {
            "mch_id": self.mch_id,
            "app_id": self.app_id,
            "notify_url": self.notify_url,
            "cert_path": self.cert_path,
            "cert_serial_no": self.cert_serial_no,
            "has_api_v3_key": bool(self.api_v3_key),
            "has_api_key": bool(self.api_key),
            "ready": bool(self.mch_id and self.api_v3_key and self.cert_path and self.app_id),
        }


# =========================================================================
# V3 鉴权头生成
# =========================================================================


class V3Auth:
    """微信 V3 API Authorization 头生成器"""

    def __init__(self, config: WeChatPayConfig):
        self._config = config

    def get_headers(self, method: str, url_path: str, body: str = "") -> dict:
        timestamp = str(int(time.time()))
        nonce = generate_nonce(32)
        sign_str = build_v3_sign_str(method, url_path, timestamp, nonce, body)
        signature = rsa_sign(sign_str, self._config.cert_path)

        auth_value = (
            f"WECHATPAY2-SHA256-RSA2048 "
            f'mchid="{self._config.mch_id}",'
            f'nonce_str="{nonce}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{self._config.cert_serial_no}",'
            f'signature="{signature}"'
        )
        return {
            "Authorization": auth_value,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "liankebao-wechatpay/1.0",
        }


# =========================================================================
# 请求客户端
# =========================================================================


class WeChatPayClient:
    """
    微信支付 V3 HTTP 客户端

    包装 httpx.AsyncClient，自动注入 V3 鉴权头。
    """

    def __init__(self, config: WeChatPayConfig):
        self._config = config
        self._auth = V3Auth(config)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=WECHAT_V3_BASE,
                timeout=httpx.Timeout(15.0, connect=10.0),
                verify=True,
            )
        return self._client

    async def request(self, method: str, url_path: str, body: dict | None = None) -> dict:
        """发起 V3 API 请求，自动注入鉴权头"""
        client = await self._get_client()
        body_json = json.dumps(body, ensure_ascii=False) if body else ""
        headers = self._auth.get_headers(method, url_path, body_json)

        response = await client.request(
            method=method,
            url=url_path,
            content=body_json if body else None,
            headers=headers,
        )

        try:
            result = response.json()
        except Exception:
            result = {"raw_body": response.text}

        if response.is_success:
            return result
        else:
            logger.error(f"微信请求失败: {method} {url_path} → {response.status_code}: {response.text[:500]}")
            result["_http_status"] = response.status_code
            result["_success"] = False
            return result

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


# =========================================================================
# 核心 API
# =========================================================================


class WeChatPay:
    """
    微信支付 V3 主操作类

    使用方式:
        config = WeChatPayConfig.from_env()
        pay = WeChatPay(config)
        result = await pay.create_jsapi_order(openid="xxx", ...)
    """

    def __init__(self, config: WeChatPayConfig | None = None):
        self.config = config or WeChatPayConfig.from_env()
        self._client: WeChatPayClient | None = None

    def _get_client(self) -> WeChatPayClient:
        if self._client is None:
            self._client = WeChatPayClient(self.config)
        return self._client

    # ---- 下单 ----

    async def create_jsapi_order(
        self,
        openid: str,
        out_trade_no: str,
        total_fee: int,  # 单位: 分
        description: str,
        attach: str | None = None,
        time_expire: str | None = None,
        goods_tag: str | None = None,
    ) -> dict:
        """
        JSAPI 下单 (公众号/小程序内支付)

        返回:
            {
                "prepay_id": "...",
                "payment_params": { appId, timeStamp, nonceStr, package, signType, paySign }
            }
        """
        body = {
            "appid": self.config.app_id,
            "mchid": self.config.mch_id,
            "description": description[:127],
            "out_trade_no": out_trade_no,
            "notify_url": self.config.notify_url,
            "amount": {"total": total_fee, "currency": "CNY"},
            "payer": {"openid": openid},
        }
        if attach:
            body["attach"] = attach[:127]
        if time_expire:
            body["time_expire"] = time_expire
        if goods_tag:
            body["goods_tag"] = goods_tag

        client = self._get_client()
        result = await client.request("POST", V3_JSAPI_PAY, body)
        prepay_id = result.get("prepay_id", "")

        if prepay_id:
            payment_params = self._build_jsapi_payment_params(prepay_id)
            return {"prepay_id": prepay_id, "payment_params": payment_params}

        return result

    async def create_app_order(
        self,
        out_trade_no: str,
        total_fee: int,
        description: str,
        attach: str | None = None,
    ) -> dict:
        """APP 下单"""
        body = {
            "appid": self.config.app_id,
            "mchid": self.config.mch_id,
            "description": description[:127],
            "out_trade_no": out_trade_no,
            "notify_url": self.config.notify_url,
            "amount": {"total": total_fee, "currency": "CNY"},
        }
        if attach:
            body["attach"] = attach[:127]

        client = self._get_client()
        result = await client.request("POST", V3_APP_PAY, body)
        prepay_id = result.get("prepay_id", "")

        if prepay_id:
            payment_params = self._build_app_payment_params(prepay_id)
            return {"prepay_id": prepay_id, "payment_params": payment_params}

        return result

    async def create_native_order(
        self,
        out_trade_no: str,
        total_fee: int,
        description: str,
        attach: str | None = None,
    ) -> dict:
        """Native 下单 (返回二维码链接 code_url)"""
        body = {
            "appid": self.config.app_id,
            "mchid": self.config.mch_id,
            "description": description[:127],
            "out_trade_no": out_trade_no,
            "notify_url": self.config.notify_url,
            "amount": {"total": total_fee, "currency": "CNY"},
        }
        if attach:
            body["attach"] = attach[:127]

        client = self._get_client()
        result = await client.request("POST", V3_NATIVE_PAY, body)
        return result  # 包含 code_url 字段

    async def create_h5_order(
        self,
        out_trade_no: str,
        total_fee: int,
        description: str,
        attach: str | None = None,
        h5_type: str = "Wap",
        h5_app_name: str = "链客宝",
        h5_app_url: str = "",
    ) -> dict:
        """H5 下单"""
        body = {
            "appid": self.config.app_id,
            "mchid": self.config.mch_id,
            "description": description[:127],
            "out_trade_no": out_trade_no,
            "notify_url": self.config.notify_url,
            "amount": {"total": total_fee, "currency": "CNY"},
            "scene_info": {
                "payer_client_ip": "",
                "h5_info": {
                    "type": h5_type,
                    "app_name": h5_app_name,
                    "app_url": h5_app_url,
                },
            },
        }
        if attach:
            body["attach"] = attach[:127]

        client = self._get_client()
        result = await client.request("POST", V3_H5_PAY, body)
        return result  # 包含 h5_url 字段

    # ---- 查询 ----

    async def query_by_out_trade_no(self, out_trade_no: str) -> dict:
        """根据商户订单号查询订单"""
        url_path = V3_ORDER_QUERY_BY_OUT % out_trade_no
        url_path_with_params = f"{url_path}?mchid={self.config.mch_id}"
        client = self._get_client()
        return await client.request("GET", url_path_with_params)

    async def query_by_transaction_id(self, transaction_id: str) -> dict:
        """根据微信支付订单号查询订单"""
        url_path = V3_ORDER_QUERY_BY_ID % transaction_id
        url_path_with_params = f"{url_path}?mchid={self.config.mch_id}"
        client = self._get_client()
        return await client.request("GET", url_path_with_params)

    # ---- 关闭 ----

    async def close_order(self, out_trade_no: str) -> bool:
        """关闭订单"""
        url_path = V3_CLOSE_ORDER % out_trade_no
        body = {"mchid": self.config.mch_id}
        client = self._get_client()
        result = await client.request("POST", url_path, body)
        return result.get("_http_status", 200) < 400 or result.get("_success") is not False

    # ---- 退款 ----

    async def create_refund(
        self,
        out_trade_no: str,
        out_refund_no: str,
        refund_amount: int,  # 退款金额 (分)
        total_amount: int,  # 原订单金额 (分)
        reason: str | None = None,
        notify_url: str | None = None,
    ) -> dict:
        """申请退款"""
        body = {
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
        body["notify_url"] = notify_url or self.config.refund_notify_url or self.config.notify_url

        client = self._get_client()
        return await client.request("POST", V3_REFUND, body)

    async def query_refund(self, out_refund_no: str) -> dict:
        """查询退款"""
        url_path = V3_REFUND_QUERY % out_refund_no
        client = self._get_client()
        return await client.request("GET", url_path)

    # ---- 参数构建 (前端调起支付) ----

    def _build_jsapi_payment_params(self, prepay_id: str) -> dict:
        """构建 JSAPI 调起支付参数 (小程序 / 公众号)"""
        timestamp = str(int(time.time()))
        nonce = generate_nonce(32)
        package = f"prepay_id={prepay_id}"
        sign_str = f"{self.config.app_id}\n{timestamp}\n{nonce}\n{package}\n"
        pay_sign = rsa_sign(sign_str, self.config.cert_path)
        return {
            "appId": self.config.app_id,
            "timeStamp": timestamp,
            "nonceStr": nonce,
            "package": package,
            "signType": "RSA",
            "paySign": pay_sign,
        }

    def _build_app_payment_params(self, prepay_id: str) -> dict:
        """构建 APP 调起支付参数"""
        timestamp = str(int(time.time()))
        nonce = generate_nonce(32)
        sign_str = f"{self.config.app_id}\n{timestamp}\n{nonce}\nprepay_id={prepay_id}\n"
        pay_sign = rsa_sign(sign_str, self.config.cert_path)
        return {
            "appid": self.config.app_id,
            "partnerid": self.config.mch_id,
            "prepayid": prepay_id,
            "package": "Sign=WXPay",
            "noncestr": nonce,
            "timestamp": timestamp,
            "sign": pay_sign,
        }

    # ---- 回调验证 ----

    def verify_callback(
        self,
        body: bytes,
        wechatpay_signature: str,
        wechatpay_serial: str,
        wechatpay_timestamp: str,
        wechatpay_nonce: str,
        platform_cert_pem: bytes | None = None,
    ) -> dict | None:
        """
        验证微信支付回调并解密 resource

        参数:
            body: 原始请求体 (bytes)
            wechatpay_signature: Wechatpay-Signature 头
            wechatpay_serial: Wechatpay-Serial 头
            wechatpay_timestamp: Wechatpay-Timestamp 头
            wechatpay_nonce: Wechatpay-Nonce 头
            platform_cert_pem: 微信平台证书 PEM 字节 (可选, 缺省从缓存目录加载)

        返回:
            解密后的回调数据字典, 验签失败返回 None
        """
        body_str = body.decode("utf-8") if isinstance(body, bytes) else body
        sign_str = build_v3_response_sign_str(wechatpay_timestamp, wechatpay_nonce, body_str)

        # 获取平台证书
        pub_key = platform_cert_pem or self._load_platform_cert(wechatpay_serial)
        if not pub_key:
            logger.error(f"回调验签失败: 未找到平台证书 serial={wechatpay_serial}")
            return None

        if not rsa_verify(sign_str, wechatpay_signature, pub_key):
            logger.error("回调验签失败: 签名不匹配")
            return None

        # 解析 resource
        try:
            notify_data = json.loads(body_str)
        except json.JSONDecodeError:
            logger.error("回调 body 不是有效 JSON")
            return None

        resource = notify_data.get("resource", {})
        ciphertext = resource.get("ciphertext", "")
        nonce = resource.get("nonce", "")
        associated_data = resource.get("associated_data", "")

        if not ciphertext or not self.config.api_v3_key:
            logger.warning("回调无加密数据或 V3 密钥未配置, 返回原始数据")
            return notify_data

        plaintext = aes_gcm_decrypt(ciphertext, self.config.api_v3_key, nonce, associated_data)
        if plaintext is None:
            logger.error("回调 resource AES-GCM 解密失败")
            return None

        try:
            return json.loads(plaintext)
        except json.JSONDecodeError:
            logger.error("解密后数据不是有效 JSON")
            return plaintext

    # ---- 平台证书管理 ----

    def _load_platform_cert(self, serial_no: str) -> bytes | None:
        """从缓存目录加载平台证书"""
        cert_path = os.path.join(self.config.platform_cert_dir, f"wechat_platform_{serial_no}.pem")
        try:
            with open(cert_path, "rb") as f:
                return f.read()
        except (FileNotFoundError, OSError):
            pass
        logger.warning(f"平台证书未缓存: serial={serial_no}")
        return None

    async def download_platform_certs(self) -> list:
        """
        下载微信平台证书(公钥), 用于回调验签

        首次使用时调用一次即可, 证书缓存到 platform_cert_dir。
        """
        client = self._get_client()
        result = await client.request("GET", V3_CERTIFICATES)

        certs = result.get("data", [])
        os.makedirs(self.config.platform_cert_dir, exist_ok=True)
        downloaded = []

        for cert_info in certs:
            serial_no = cert_info.get("serial_no", "")
            encrypt_cert = cert_info.get("encrypt_certificate", {})
            ciphertext = encrypt_cert.get("ciphertext", "")
            nonce = encrypt_cert.get("nonce", "")
            associated_data = encrypt_cert.get("associated_data", "")

            plain_pem = aes_gcm_decrypt(ciphertext, self.config.api_v3_key, nonce, associated_data)
            if plain_pem:
                cert_path = os.path.join(self.config.platform_cert_dir, f"wechat_platform_{serial_no}.pem")
                with open(cert_path, "w") as f:
                    f.write(plain_pem)
                downloaded.append({"serial_no": serial_no, "path": cert_path})
                logger.info(f"平台证书已缓存: serial={serial_no} → {cert_path}")
            else:
                logger.error(f"平台证书解密失败: serial={serial_no}")

        return downloaded

    # ---- 快捷方法 ----

    def get_payment_params_for_frontend(self, prepay_id: str, trade_type: str = "JSAPI") -> dict:
        """获取前端调起支付参数"""
        if trade_type == "APP":
            return self._build_app_payment_params(prepay_id)
        return self._build_jsapi_payment_params(prepay_id)

    @classmethod
    def from_env(cls) -> "WeChatPay":
        """从环境变量创建实例 (快捷方法)"""
        return cls(WeChatPayConfig.from_env())


# =========================================================================
# 安装检查
# =========================================================================


def check_wechat_pay_ready() -> list:
    """
    检查微信支付配置完整性

    返回缺失项的列表, 空列表表示就绪。
    """
    config = WeChatPayConfig.from_env()
    missing, _ = config.is_ready()
    return missing


# =========================================================================
# 单例 & 快捷引用
# =========================================================================

# 全局配置实例 (惰性加载)
_global_config: WeChatPayConfig | None = None


def get_wechat_pay_config() -> WeChatPayConfig:
    """获取全局微信支付配置"""
    global _global_config
    if _global_config is None:
        _global_config = WeChatPayConfig.from_env()
    return _global_config


def reset_wechat_pay_config():
    """重置全局配置 (用于热加载)"""
    global _global_config
    _global_config = None
