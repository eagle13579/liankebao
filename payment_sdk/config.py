"""支付配置数据类 — 纯数据类，无全局状态

从 payment/config.py 提取，遵循 C-PAY-003 移除全局注册中心。
仅保留数据类 + 环境变量加载功能。

对比原始 payment/config.py:
    - 保留: WxPayConfig, AliPayConfig, from_env, is_configured, is_real_mode
    - 移除: _config_registry, ContextVar, register(), get_config()
    - 移除: FastAPI 中间件 payment_platform_middleware
"""

import os
from dataclasses import dataclass

# ============================================================
# 支付模式开关
# ============================================================

PAYMENT_MODE_REAL = "real"
PAYMENT_MODE_MOCK = "mock"


def is_real_mode() -> bool:
    """检查支付模式是否为真实模式（PAYMENT_MODE=real）"""
    mode = os.environ.get("PAYMENT_MODE", PAYMENT_MODE_MOCK).strip().lower()
    return mode == PAYMENT_MODE_REAL


# ============================================================
# 微信支付配置 (WxPayConfig)
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
# 支付宝配置 (AliPayConfig)
# ============================================================


@dataclass
class AliPayConfig:
    """支付宝支付配置 (纯数据类)

    Attributes:
        app_id: 支付宝 AppID
        private_key: 应用私钥 (PEM 字符串)
        alipay_public_key: 支付宝公钥 (PEM 字符串)
        gateway: API 网关地址
        charset: 字符编码
        sign_type: 签名类型 (RSA2)
        notify_url: 回调通知 URL
        is_cert_mode: 是否证书模式
        app_cert_path: 应用公钥证书路径
        alipay_cert_path: 支付宝公钥证书路径
        alipay_root_cert_path: 支付宝根证书路径
    """

    app_id: str = ""
    private_key: str = ""
    alipay_public_key: str = ""
    gateway: str = "https://openapi.alipay.com/gateway.do"
    charset: str = "UTF-8"
    sign_type: str = "RSA2"
    notify_url: str = ""
    is_cert_mode: bool = False
    app_cert_path: str = ""
    alipay_cert_path: str = ""
    alipay_root_cert_path: str = ""

    @classmethod
    def from_env(cls, prefix: str = "ALIPAY_") -> "AliPayConfig":
        """从环境变量读取配置"""
        return cls(
            app_id=os.environ.get(f"{prefix}APP_ID", ""),
            private_key=os.environ.get(f"{prefix}PRIVATE_KEY", ""),
            alipay_public_key=os.environ.get(f"{prefix}PUBLIC_KEY", ""),
            gateway=os.environ.get(f"{prefix}GATEWAY", "https://openapi.alipay.com/gateway.do"),
            charset=os.environ.get(f"{prefix}CHARSET", "UTF-8"),
            sign_type=os.environ.get(f"{prefix}SIGN_TYPE", "RSA2"),
            notify_url=os.environ.get(f"{prefix}NOTIFY_URL", ""),
            app_cert_path=os.environ.get(f"{prefix}APP_CERT_PATH", ""),
            alipay_cert_path=os.environ.get(f"{prefix}ALIPAY_CERT_PATH", ""),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.app_id and self.private_key)
