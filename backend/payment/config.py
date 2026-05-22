"""
ApiConfigKit — 多平台支付配置注册中心
基于 IJPay ch-01 (ContextVar 模式)
支持 WxPay / AliPay / UnionPay 多平台
"""

import os
import logging
from contextvars import ContextVar
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ============================================================
# 支付配置数据类
# ============================================================

@dataclass
class WxPayConfig:
    """微信支付配置"""
    app_id: str = ""
    mch_id: str = ""
    api_key: str = ""           # V2 密钥 (MD5)
    api_v3_key: str = ""        # V3 密钥 (AES-256-GCM 解密)
    private_key_path: str = ""  # apiclient_key.pem 路径 (V3 签名)
    cert_serial_no: str = ""    # 证书序列号 (V3 签名)
    notify_url: str = ""
    refund_notify_url: str = ""
    cert_path: str = ""         # apiclient_cert.pem (双向证书)
    root_ca_path: str = ""      # rootca.pem

    @classmethod
    def from_env(cls, prefix: str = "WECHAT_") -> "WxPayConfig":
        """从环境变量读取配置"""
        return cls(
            app_id=os.environ.get(f"{prefix}APPID", ""),
            mch_id=os.environ.get(f"{prefix}MCH_ID", ""),
            api_key=os.environ.get(f"{prefix}API_KEY", ""),
            api_v3_key=os.environ.get(f"{prefix}API_V3_KEY", ""),
            private_key_path=os.environ.get(f"{prefix}PRIVATE_KEY_PATH", ""),
            cert_serial_no=os.environ.get(f"{prefix}CERT_SERIAL_NO", ""),
            notify_url=os.environ.get(f"{prefix}NOTIFY_URL", ""),
            refund_notify_url=os.environ.get(f"{prefix}REFUND_NOTIFY_URL", ""),
            cert_path=os.environ.get(f"{prefix}CERT_PATH", ""),
            root_ca_path=os.environ.get(f"{prefix}ROOT_CA_PATH", ""),
        )

    @property
    def is_configured(self) -> bool:
        """检查配置是否完整（至少需要 app_id + mch_id + api_key）"""
        return bool(self.app_id and self.mch_id and self.api_key)


@dataclass
class AliPayConfig:
    """支付宝支付配置"""
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


# ============================================================
# ApiConfigKit — 配置注册中心
# ============================================================

_DEFAULT_KEY = "__default__"
_config_registry: Dict[str, Any] = {}
_platform_var: ContextVar[str] = ContextVar("payment_platform", default="")

# 平台名称常量
PLATFORM_WXPAY = "wxpay"
PLATFORM_ALIPAY = "alipay"
PLATFORM_UNIONPAY = "unionpay"


def register(platform: str, config: Any, *, set_default: bool = False) -> None:
    """
    注册支付配置

    Args:
        platform: 平台名称 (wxpay / alipay / unionpay)
        config: 配置对象 (WxPayConfig / AliPayConfig)
        set_default: 是否设为默认配置
    """
    _config_registry[platform] = config
    if set_default or not _config_registry.get(_DEFAULT_KEY):
        _config_registry[_DEFAULT_KEY] = config
    logger.info(f"支付配置已注册: platform={platform}, type={type(config).__name__}")


def get_config(platform: Optional[str] = None) -> Any:
    """
    获取支付配置

    优先级:
    1. 传入的 platform 参数
    2. 当前 ContextVar 中的平台名称
    3. 默认配置

    Args:
        platform: 平台名称，None 时使用 ContextVar 或默认

    Returns:
        配置对象
    """
    key = platform or _platform_var.get() or _DEFAULT_KEY
    config = _config_registry.get(key)
    if config is None:
        config = _config_registry.get(_DEFAULT_KEY)
    if config is None:
        raise RuntimeError(
            f"支付配置未注册: platform={key}。"
            f"请先调用 payment.config.register() 注册配置。"
        )
    return config


def set_current_platform(platform: str) -> None:
    """
    设置当前线程/协程的支付平台（ContextVar）

    Args:
        platform: 平台名称
    """
    _platform_var.set(platform)


def get_current_platform() -> str:
    """获取当前线程/协程的支付平台"""
    return _platform_var.get()


def remove_config(platform: str) -> None:
    """
    移除指定平台的配置

    Args:
        platform: 平台名称
    """
    _config_registry.pop(platform, None)
    if _config_registry.get(_DEFAULT_KEY) and platform == _DEFAULT_KEY:
        _config_registry.pop(_DEFAULT_KEY, None)


def has_config(platform: Optional[str] = None) -> bool:
    """检查指定平台或默认配置是否存在"""
    key = platform or _DEFAULT_KEY
    return key in _config_registry


def list_platforms() -> list:
    """列出所有已注册的平台"""
    return [k for k in _config_registry.keys() if k != _DEFAULT_KEY]


# ============================================================
# FastAPI 中间件 — 自动注入平台上下文
# ============================================================

from fastapi import Request, Response


async def payment_platform_middleware(request: Request, call_next):
    """
    FastAPI 中间件：根据请求路径自动设置支付平台 ContextVar

    规则:
        /api/payment/wxpay/*  →  wxpay
        /api/payment/alipay/* →  alipay

    用法:
        app.middleware("http")(payment_platform_middleware)
    """
    path = request.url.path
    if "/wxpay/" in path:
        set_current_platform(PLATFORM_WXPAY)
    elif "/alipay/" in path:
        set_current_platform(PLATFORM_ALIPAY)
    response: Response = await call_next(request)
    return response


# ============================================================
# 便捷初始化
# ============================================================

def init_default_config() -> None:
    """
    从环境变量初始化默认支付配置

    环境变量前缀:
        WECHAT_* — 微信支付
        ALIPAY_* — 支付宝

    如果对应的环境变量存在，则自动注册。
    """
    wx_config = WxPayConfig.from_env("WECHAT_")
    if wx_config.is_configured:
        register(PLATFORM_WXPAY, wx_config, set_default=True)
        logger.info("微信支付配置已从环境变量加载")

    ali_config = AliPayConfig.from_env("ALIPAY_")
    if ali_config.is_configured:
        register(PLATFORM_ALIPAY, ali_config)
        logger.info("支付宝配置已从环境变量加载")

    if not has_config():
        logger.warning("未从环境变量检测到任何支付配置，支付功能将不可用")
