"""
链客宝 - 微信集成 API 路由
=============================
提供 JS-SDK 配置、网页授权登录、小程序登录等 HTTP 端点。

端点列表：
  POST /api/wechat/js-config          — 生成 JS-SDK config（前端调用 wx.config 前调用）
  POST /api/wechat/oauth/login        — 网页授权登录（code → userinfo）
  POST /api/wechat/qrconnect-url      — 开放平台扫码登录 URL（PC 端扫码用）
  POST /api/wechat/miniapp/login      — 小程序 code 登录（code → openid/session_key）
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.wechat_sdk import (
    WeChatOAuth,
    WeChatJSConfig,
    WeChatMiniProgram,
    OAuthUserInfo,
    MiniProgramLoginResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wechat", tags=["微信集成"])

# ===================================================================
# 请求 / 响应模型
# ===================================================================


# ── JS-SDK Config ──────────────────────────────────────────────────


class JSConfigRequest(BaseModel):
    url: str = Field(..., description="当前网页的完整 URL（需去除 # 部分）")


class JSConfigResponse(BaseModel):
    appid: str = Field(..., description="公众号 APPID")
    noncestr: str = Field(..., description="随机字符串")
    timestamp: int = Field(..., description="时间戳（秒）")
    signature: str = Field(..., description="SHA1 签名")


# ── OAuth 网页授权 ─────────────────────────────────────────────────


class OAuthLoginRequest(BaseModel):
    code: str = Field(..., description="微信回调 URL 中获取的授权 code")
    state: Optional[str] = Field(default="", description="自定义状态参数（可选）")


class OAuthLoginResponse(BaseModel):
    openid: str = Field(..., description="用户唯一标识")
    nickname: str = Field(default="", description="用户昵称")
    sex: int = Field(default=0, description="性别: 0=未知, 1=男, 2=女")
    province: str = Field(default="", description="省份")
    city: str = Field(default="", description="城市")
    country: str = Field(default="", description="国家")
    headimgurl: str = Field(default="", description="用户头像 URL")
    unionid: str = Field(default="", description="开放平台 UnionID（如果绑定了开放平台）")


# ── 小程序登录 ─────────────────────────────────────────────────────


class MiniAppLoginRequest(BaseModel):
    code: str = Field(..., description="小程序 wx.login() 获取的临时登录 code")


class MiniAppLoginResponse(BaseModel):
    openid: str = Field(..., description="用户唯一标识")
    session_key: str = Field(..., description="会话密钥（注意：请勿直接返回给前端）")
    unionid: str = Field(default="", description="开放平台 UnionID（已绑定时才返回）")


# ── 开放平台扫码登录 ──────────────────────────────────────────────


class QrConnectUrlRequest(BaseModel):
    redirect_uri: str = Field(..., description="扫码登录后微信回调的 URL")
    state: Optional[str] = Field(default="", description="CSRF 校验 state")


class QrConnectUrlResponse(BaseModel):
    url: str = Field(..., description="开放平台扫码登录 URL")
    appid: str = Field(..., description="开放平台 APPID")


# ── 统一错误响应 ────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    detail: str


# ===================================================================
# 路由实现
# ===================================================================


@router.post(
    "/js-config",
    summary="获取 JS-SDK 配置",
    description="生成 wx.config() 所需的签名参数，前端在调用 JS-SDK 接口前调用此接口获取配置。",
    response_model=JSConfigResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def js_config(req: JSConfigRequest):
    """
    获取 JS-SDK 配置（签名）

    前端调用方式:
        1. 页面加载后，POST /api/wechat/js-config { "url": location.href.split('#')[0] }
        2. 使用返回的 appid, noncestr, timestamp, signature 调用 wx.config()

    Note:
        url 参数需传当前页面的完整 URL，不含 # 及其后面的部分。
    """
    try:
        js_sdk = WeChatJSConfig()
        config = js_sdk.get_config(req.url)
        return JSConfigResponse(
            appid=config.appid,
            noncestr=config.noncestr,
            timestamp=config.timestamp,
            signature=config.signature,
        )
    except RuntimeError as e:
        logger.error(f"[WeChatRouter] JS-SDK config 生成失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/oauth/login",
    summary="微信网页授权登录",
    description="使用微信回调 code 换取用户信息（需 scope=snsapi_userinfo）。",
    response_model=OAuthLoginResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def oauth_login(req: OAuthLoginRequest):
    """
    微信网页授权登录

    流程:
        1. 前端引导用户访问 WeChatOAuth.get_authorize_url() 生成的 URL
        2. 用户授权后，微信回调 redirect_uri?code=xxx&state=xxx
        3. 前端将 code 传给此接口
        4. 后端完成 code → access_token → userinfo
    """
    try:
        oauth = WeChatOAuth()
        if not oauth.validate_oauth_config():
            raise HTTPException(
                status_code=500,
                detail="微信 OAuth 配置缺失，请在环境变量中设置 WECHAT_APPID 和 WECHAT_SECRET",
            )

        # ── code → access_token ──
        token_data = oauth.get_access_token(req.code)

        # ── access_token → userinfo ──
        user = oauth.get_userinfo(token_data["access_token"], token_data["openid"])

        logger.info(
            f"[WeChatRouter] OAuth 登录成功: openid={user.openid[:8]}..., "
            f"nickname={user.nickname}"
        )

        return OAuthLoginResponse(
            openid=user.openid,
            nickname=user.nickname,
            sex=user.sex,
            province=user.province,
            city=user.city,
            country=user.country,
            headimgurl=user.headimgurl,
            unionid=user.unionid,
        )
    except RuntimeError as e:
        logger.error(f"[WeChatRouter] OAuth 登录失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/qrconnect-url",
    summary="获取开放平台扫码登录 URL",
    description="PC端使用微信扫码登录时, 先调用此接口获取 qrconnect URL, 然后 302 跳转。",
    response_model=QrConnectUrlResponse,
    responses={500: {"model": ErrorResponse}},
)
async def get_qrconnect_url(req: QrConnectUrlRequest):
    """
    获取开放平台扫码登录 URL

    流程:
      1. PC 端调用此接口, 传入当前页面 URL 作为 redirect_uri
      2. 后端返回 qrconnect URL (含 appid, redirect_uri, scope=snsapi_login)
      3. PC 端跳转到此 URL, 显示二维码
      4. 用户用微信扫码 → 手机端确认授权
      5. 微信重定向到 redirect_uri?code=xxx&state=xxx
      6. 页面加载后, 前端检测到 code 参数, 调 POST /api/wechat/oauth/login 完成登录
    """
    try:
        oauth = WeChatOAuth.for_qrconnect()
        url = oauth.get_qrconnect_url(
            redirect_uri=req.redirect_uri,
            state=req.state,
        )
        return QrConnectUrlResponse(
            url=url,
            appid=oauth.appid,
        )
    except RuntimeError as e:
        logger.error(f"[WeChatRouter] 获取 qrconnect URL 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/miniapp/login",
    summary="小程序登录",
    description="使用小程序 wx.login() 获取的 code 换取 openid 和 session_key。",
    response_model=MiniAppLoginResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def miniapp_login(req: MiniAppLoginRequest):
    """
    小程序登录

    流程:
        1. 小程序端调用 wx.login() 获取临时 code
        2. 小程序端将 code 传给此接口
        3. 后端通过 code 换取 openid 和 session_key

    ⚠️ 安全提醒: session_key 不应直接返回给前端或明文传输。
       建议在后端用 session_key 解密用户数据后，返回业务所需内容。
    """
    try:
        mp = WeChatMiniProgram()
        if not mp.validate_config():
            raise HTTPException(
                status_code=500,
                detail="小程序配置缺失，请在环境变量中设置 WECHAT_APPID 和 WECHAT_SECRET",
            )

        result = mp.code2session(req.code)

        if result.errcode != 0:
            error_map = {
                -1: "微信系统繁忙，请稍后重试",
                40029: "无效的 code（需重新调用 wx.login）",
                45011: "API 调用频率超限，请稍后重试",
                40226: "高风险用户，被微信临时禁止登录",
            }
            detail = error_map.get(result.errcode, f"微信登录失败（错误码: {result.errcode}）")
            logger.warning(f"[WeChatRouter] 小程序登录失败: [{result.errcode}] {detail}")
            raise HTTPException(status_code=400, detail=detail)

        logger.info(
            f"[WeChatRouter] 小程序登录成功: openid={result.openid[:8]}..."
        )

        return MiniAppLoginResponse(
            openid=result.openid,
            session_key=result.session_key,
            unionid=result.unionid,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[WeChatRouter] 小程序登录异常: {e}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


# ── 启动提示 ─────────────────────────────────────────────────────

print("[WeChatRouter] 微信集成路由已加载 ✓")
print("[WeChatRouter] 端点列表:")
print("  POST /api/wechat/js-config          — JS-SDK 配置")
print("  POST /api/wechat/oauth/login        — 网页授权登录")
print("  POST /api/wechat/qrconnect-url      — 开放平台扫码登录 URL")
print("  POST /api/wechat/miniapp/login      — 小程序登录")
