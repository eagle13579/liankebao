"""
链客宝 - 微信 JS-SDK 集成模块
=================================
提供微信网页授权 (OAuth)、JS-SDK 配置签名、小程序登录能力。

设计原则：
  - 纯 requests 实现，无第三方微信 SDK
  - 环境变量配置：WECHAT_APPID / WECHAT_SECRET（兼容 WX_APPID / WX_SECRET）
  - 模块级缓存：access_token 和 jsapi_ticket 带过期时间
"""

import hashlib
import json
import logging
import os
import random
import string
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ===================================================================
# 微信配置（环境变量）
# ===================================================================

# 优先使用 WECHAT_* 变量，兼容旧的 WX_* 变量
WECHAT_APPID = os.getenv("WECHAT_APPID", "") or os.getenv("WX_APPID", "")
WECHAT_SECRET = os.getenv("WECHAT_SECRET", "") or os.getenv("WX_SECRET", "")

# ── 微信开放平台配置（PC扫码登录）──
OPEN_WECHAT_APPID = os.getenv("OPEN_WECHAT_APPID", "") or os.getenv("OPEN_WX_APPID", "")
OPEN_WECHAT_SECRET = os.getenv("OPEN_WECHAT_SECRET", "") or os.getenv("OPEN_WX_SECRET", "")

# ===================================================================
# 微信 API 端点
# ===================================================================

WECHAT_API_BASE = "https://api.weixin.qq.com"

# ── 基础 Access Token ──
URL_ACCESS_TOKEN = f"{WECHAT_API_BASE}/cgi-bin/token"
# ── JSAPI Ticket ──
URL_JSAPI_TICKET = f"{WECHAT_API_BASE}/cgi-bin/ticket/getticket"
# ── 网页授权 OAuth2 ──
URL_OAUTH2_ACCESS_TOKEN = f"{WECHAT_API_BASE}/sns/oauth2/access_token"
URL_OAUTH2_USERINFO = f"{WECHAT_API_BASE}/sns/userinfo"
URL_OAUTH2_REFRESH = f"{WECHAT_API_BASE}/sns/oauth2/refresh_token"
URL_OAUTH2_AUTH = "https://open.weixin.qq.com/connect/oauth2/authorize"
# ── 开放平台扫码登录 ──
URL_QRCONNECT_AUTH = "https://open.weixin.qq.com/connect/qrconnect"
# ── 小程序登录 ──
URL_JSCODE2SESSION = f"{WECHAT_API_BASE}/sns/jscode2session"


# ===================================================================
# 基础工具：Token 缓存
# ===================================================================


class _TokenCache:
    """简单的内存 Token 缓存，带过期时间"""

    def __init__(self):
        self._token: str = ""
        self._expires_at: int = 0

    def get(self) -> Optional[str]:
        if self._token and time.time() < self._expires_at:
            return self._token
        return None

    def set(self, token: str, expires_in: int = 7200):
        self._token = token
        # 提前 5 分钟过期，避免边界情况
        self._expires_at = int(time.time()) + expires_in - 300

    def invalidate(self):
        self._token = ""
        self._expires_at = 0


_global_token_cache = _TokenCache()
_global_ticket_cache = _TokenCache()


# ===================================================================
# 基础请求封装
# ===================================================================


def _get_access_token() -> str:
    """获取全局 access_token（带缓存）"""
    cached = _global_token_cache.get()
    if cached:
        return cached

    if not WECHAT_APPID or not WECHAT_SECRET:
        raise RuntimeError(
            "微信配置缺失：请在环境变量中设置 WECHAT_APPID 和 WECHAT_SECRET"
        )

    resp = requests.get(
        URL_ACCESS_TOKEN,
        params={
            "grant_type": "client_credential",
            "appid": WECHAT_APPID,
            "secret": WECHAT_SECRET,
        },
        timeout=10,
    )
    data = resp.json()

    if "errcode" in data and data["errcode"] != 0:
        raise RuntimeError(
            f"获取 access_token 失败: [{data.get('errcode')}] {data.get('errmsg', '未知错误')}"
        )

    token = data["access_token"]
    expires_in = data.get("expires_in", 7200)
    _global_token_cache.set(token, expires_in)
    logger.debug(f"[WeChatSDK] 已刷新 access_token, 有效期 {expires_in}s")
    return token


def _get_jsapi_ticket(access_token: Optional[str] = None) -> str:
    """获取 jsapi_ticket（带缓存）"""
    cached = _global_ticket_cache.get()
    if cached:
        return cached

    token = access_token or _get_access_token()
    resp = requests.get(
        URL_JSAPI_TICKET,
        params={"access_token": token, "type": "jsapi"},
        timeout=10,
    )
    data = resp.json()

    if data.get("errcode") != 0:
        raise RuntimeError(
            f"获取 jsapi_ticket 失败: [{data.get('errcode')}] {data.get('errmsg', '未知错误')}"
        )

    ticket = data["ticket"]
    expires_in = data.get("expires_in", 7200)
    _global_ticket_cache.set(ticket, expires_in)
    logger.debug(f"[WeChatSDK] 已刷新 jsapi_ticket, 有效期 {expires_in}s")
    return ticket


def _generate_nonce_str(length: int = 16) -> str:
    """生成随机字符串"""
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


# ===================================================================
# WeChatOAuth — 网页授权 (OAuth2.0)
# ===================================================================


@dataclass
class OAuthUserInfo:
    """微信网页授权获取的用户信息"""
    openid: str
    nickname: str = ""
    sex: int = 0
    province: str = ""
    city: str = ""
    country: str = ""
    headimgurl: str = ""
    unionid: str = ""
    privilege: list = field(default_factory=list)


class WeChatOAuth:
    """
    微信网页授权 (OAuth2.0)

    流程:
      1. 引导用户访问授权 URL → 获取 code
      2. code → access_token + openid
      3. access_token → userinfo

    使用示例:
        >>> oauth = WeChatOAuth()
        >>> # 生成授权 URL
        >>> url = oauth.get_authorize_url("https://example.com/callback", "snsapi_userinfo")
        >>> # 回调处理
        >>> result = oauth.get_access_token("code_from_wechat")
        >>> user = oauth.get_userinfo(result["access_token"], result["openid"])
    """

    def __init__(self, appid: str = "", secret: str = ""):
        self.appid = appid or WECHAT_APPID
        self.secret = secret or WECHAT_SECRET

    def get_authorize_url(
        self,
        redirect_uri: str,
        scope: str = "snsapi_base",
        state: str = "",
    ) -> str:
        """
        生成网页授权 URL

        Args:
            redirect_uri: 回调地址（需 URL 编码后的地址，函数内部会自动编码）
            scope:        snsapi_base（静默，仅 openid） 或 snsapi_userinfo（弹窗，含用户信息）
            state:        自定义参数，回调时会原样返回（用于 CSRF 校验）

        Returns:
            授权页面 URL，引导用户跳转
        """
        import urllib.parse

        params = {
            "appid": self.appid,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
        }
        # 微信要求 redirect_uri 做 URL 编码后再拼接到 URL 中
        query = urllib.parse.urlencode(params)
        return f"{URL_OAUTH2_AUTH}?{query}#wechat_redirect"

    def get_access_token(self, code: str) -> dict:
        """
        用授权 code 换取 access_token 和 openid

        Args:
            code: 用户授权后回调 URL 中携带的 code

        Returns:
            {
                "access_token": "...",
                "expires_in": 7200,
                "refresh_token": "...",
                "openid": "...",
                "scope": "...",
                "unionid": "...",  # 仅在公众号绑定了开放平台时返回
            }

        Raises:
            RuntimeError: 微信接口返回错误
        """
        resp = requests.get(
            URL_OAUTH2_ACCESS_TOKEN,
            params={
                "appid": self.appid,
                "secret": self.secret,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        data = resp.json()

        if "errcode" in data and data["errcode"] != 0:
            errcode = data.get("errcode")
            errmsg = data.get("errmsg", "未知错误")
            logger.warning(f"[WeChatOAuth] 获取 access_token 失败: [{errcode}] {errmsg}")
            raise RuntimeError(f"OAuth 授权失败: [{errcode}] {errmsg}")

        return data

    def refresh_access_token(self, refresh_token: str) -> dict:
        """
        刷新 access_token（access_token 有效期 2 小时，refresh_token 有效期 30 天）

        Args:
            refresh_token: 通过 get_access_token 获取的 refresh_token

        Returns:
            新的 token 信息（结构与 get_access_token 相同）
        """
        resp = requests.get(
            URL_OAUTH2_REFRESH,
            params={
                "appid": self.appid,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=10,
        )
        data = resp.json()

        if "errcode" in data and data["errcode"] != 0:
            errcode = data.get("errcode")
            errmsg = data.get("errmsg", "未知错误")
            logger.warning(f"[WeChatOAuth] 刷新 token 失败: [{errcode}] {errmsg}")
            raise RuntimeError(f"刷新 token 失败: [{errcode}] {errmsg}")

        return data

    def get_userinfo(self, access_token: str, openid: str, lang: str = "zh_CN") -> OAuthUserInfo:
        """
        拉取用户信息（需 scope 为 snsapi_userinfo）

        Args:
            access_token: 网页授权接口调用凭证
            openid:       用户的唯一标识
            lang:         语言（zh_CN / zh_TW / en）

        Returns:
            OAuthUserInfo 对象
        """
        resp = requests.get(
            URL_OAUTH2_USERINFO,
            params={
                "access_token": access_token,
                "openid": openid,
                "lang": lang,
            },
            timeout=10,
        )
        data = resp.json()

        if "errcode" in data and data["errcode"] != 0:
            errcode = data.get("errcode")
            errmsg = data.get("errmsg", "未知错误")
            logger.warning(f"[WeChatOAuth] 获取用户信息失败: [{errcode}] {errmsg}")
            raise RuntimeError(f"获取用户信息失败: [{errcode}] {errmsg}")

        return OAuthUserInfo(
            openid=data.get("openid", ""),
            nickname=data.get("nickname", ""),
            sex=data.get("sex", 0),
            province=data.get("province", ""),
            city=data.get("city", ""),
            country=data.get("country", ""),
            headimgurl=data.get("headimgurl", ""),
            unionid=data.get("unionid", ""),
            privilege=data.get("privilege", []),
        )

    def validate_oauth_config(self) -> bool:
        """验证 OAuth 配置是否有效（检查 appid 和 secret 是否已设置）"""
        return bool(self.appid and self.secret)

    # ── 开放平台扫码登录 ─────────────────────────────────────────

    def get_qrconnect_url(
        self,
        redirect_uri: str,
        state: str = "",
    ) -> str:
        """
        生成开放平台扫码登录 URL (PC端使用)

        流程:
          1. PC 浏览器跳转到此 URL, 显示二维码
          2. 用户用微信扫码 → 手机端确认授权
          3. 授权后, 微信重定向到 redirect_uri?code=xxx&state=xxx
          4. 前端将 code 传给 POST /api/wechat/oauth/login 完成登录

        Note: 需要先在微信开放平台创建网站应用
              (https://open.weixin.qq.com/)
        """
        import urllib.parse

        if not self.appid:
            raise RuntimeError(
                "开放平台配置缺失: 请设置 OPEN_WECHAT_APPID 环境变量"
            )

        params = {
            "appid": self.appid,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "snsapi_login",
            "state": state,
        }
        query = urllib.parse.urlencode(params)
        return f"{URL_QRCONNECT_AUTH}?{query}#wechat_redirect"

    @classmethod
    def for_qrconnect(cls) -> "WeChatOAuth":
        """创建用于开放平台扫码登录的 OAuth 实例"""
        return cls(appid=OPEN_WECHAT_APPID, secret=OPEN_WECHAT_SECRET)


# ===================================================================
# WeChatJSConfig — JS-SDK 配置签名
# ===================================================================


@dataclass
class JSConfig:
    """JS-SDK 配置参数（返回给前端）"""
    appid: str
    noncestr: str
    timestamp: int
    signature: str
    jsapi_ticket: str = ""


class WeChatJSConfig:
    """
    JS-SDK 配置生成器

    用于生成 wx.config() 所需的签名参数。
    前端通过 JS-SDK 调用分享、拍照、支付等微信原生能力。

    使用示例:
        >>> js = WeChatJSConfig()
        >>> config = js.get_config("https://example.com/page")
        >>> # 返回给前端，前端调用 wx.config(config)
    """

    def __init__(self, appid: str = ""):
        self.appid = appid or WECHAT_APPID

    def get_config(self, url: str) -> JSConfig:
        """
        生成 JS-SDK 配置（包含签名）

        Args:
            url: 当前网页的完整 URL（# 及其后面部分不计入）

        Returns:
            JSConfig 对象，可直接返回给前端
        """
        noncestr = _generate_nonce_str()
        timestamp = int(time.time())
        ticket = _get_jsapi_ticket()

        # ── 构造签名串 ──
        raw_string = (
            f"jsapi_ticket={ticket}"
            f"&noncestr={noncestr}"
            f"&timestamp={timestamp}"
            f"&url={url}"
        )
        signature = hashlib.sha1(raw_string.encode("utf-8")).hexdigest()

        logger.debug(
            f"[WeChatJSConfig] 生成签名: url={url[:60]}..., "
            f"noncestr={noncestr}, timestamp={timestamp}"
        )

        return JSConfig(
            appid=self.appid,
            noncestr=noncestr,
            timestamp=timestamp,
            signature=signature,
            jsapi_ticket=ticket,
        )

    @staticmethod
    def validate_signature(
        signature: str,
        ticket: str,
        noncestr: str,
        timestamp: int,
        url: str,
    ) -> bool:
        """
        验证签名是否匹配（用于服务端校验）

        Args:
            signature:  前端传入的签名
            ticket:     jsapi_ticket
            noncestr:   随机字符串
            timestamp:  时间戳
            url:        网页 URL

        Returns:
            True 如果签名正确
        """
        raw_string = (
            f"jsapi_ticket={ticket}"
            f"&noncestr={noncestr}"
            f"&timestamp={timestamp}"
            f"&url={url}"
        )
        expected = hashlib.sha1(raw_string.encode("utf-8")).hexdigest()
        return signature == expected


# ===================================================================
# WeChatMiniProgram — 小程序登录
# ===================================================================


@dataclass
class MiniProgramLoginResult:
    """小程序登录结果"""
    openid: str
    session_key: str
    unionid: str = ""
    errcode: int = 0
    errmsg: str = ""


class WeChatMiniProgram:
    """
    微信小程序登录

    流程:
      1. 小程序端调用 wx.login() 获取临时 code
      2. 后端 code → openid + session_key

    使用示例:
        >>> mp = WeChatMiniProgram()
        >>> result = mp.code2session("code_from_wx_login")
    """

    def __init__(self, appid: str = "", secret: str = ""):
        self.appid = appid or WECHAT_APPID
        self.secret = secret or WECHAT_SECRET

    def code2session(self, code: str) -> MiniProgramLoginResult:
        """
        临时登录 code 换取 openid 和 session_key

        Args:
            code: 小程序 wx.login() 获取的临时 code

        Returns:
            MiniProgramLoginResult 对象
        """
        resp = requests.get(
            URL_JSCODE2SESSION,
            params={
                "appid": self.appid,
                "secret": self.secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        data = resp.json()

        result = MiniProgramLoginResult(
            openid=data.get("openid", ""),
            session_key=data.get("session_key", ""),
            unionid=data.get("unionid", ""),
            errcode=data.get("errcode", 0),
            errmsg=data.get("errmsg", ""),
        )

        if result.errcode != 0:
            logger.warning(
                f"[WeChatMiniProgram] code2session 失败: "
                f"[{result.errcode}] {result.errmsg}"
            )

        return result

    def validate_config(self) -> bool:
        """验证小程序配置是否有效"""
        return bool(self.appid and self.secret)


# ===================================================================
# 便捷函数（单例风格调用）
# ===================================================================


def get_js_config(url: str) -> JSConfig:
    """快速生成 JS-SDK 配置"""
    return WeChatJSConfig().get_config(url)


def oauth_get_userinfo(code: str) -> OAuthUserInfo:
    """快速完成 OAuth 授权：code → access_token → userinfo"""
    oauth = WeChatOAuth()
    token_data = oauth.get_access_token(code)
    return oauth.get_userinfo(token_data["access_token"], token_data["openid"])


def mini_program_login(code: str) -> MiniProgramLoginResult:
    """快速完成小程序登录"""
    return WeChatMiniProgram().code2session(code)


# ── 模块加载提示 ─────────────────────────────────────────────────

print("[WeChatSDK] 微信 JS-SDK 集成模块已加载 ✓")
if not WECHAT_APPID or not WECHAT_SECRET:
    print("[WeChatSDK] ⚠️  微信配置未设置: 请在环境变量中配置 WECHAT_APPID 和 WECHAT_SECRET")
else:
    print(f"[WeChatSDK] 微信 APPID: {WECHAT_APPID[:4]}...{WECHAT_APPID[-4:]}")
