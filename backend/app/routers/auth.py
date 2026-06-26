"""链客宝 - 认证与微信小程序 API
================================
提供微信登录、手机号解密等认证相关端点。

规则：纯新增，不修改现有业务逻辑
"""

import base64
import datetime
import json
import os
import uuid
import logging

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import httpx
from Crypto.Cipher import AES

from app.database import get_db
from app.models import User, hash_password, verify_password

logger = logging.getLogger(__name__)

# ===================================================================
# JWT 配置（与 auth_middleware 保持一致）
# ===================================================================
JWT_SECRET = os.getenv("JWT_SECRET", "chainke-dev-secret-key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

# ===================================================================
# 微信小程序配置（从环境变量读取，需在 .env 或环境变量中设置）
# ===================================================================
WX_APPID = os.getenv("WX_APPID", "")
WX_SECRET = os.getenv("WX_SECRET", "")

WEIXIN_JSCODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"

# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================


class DecryptPhoneRequest(BaseModel):
    """微信手机号解密请求"""
    code: str = Field(..., description="wx.login 获取的临时登录 code")
    encrypted_data: str = Field(..., description="微信 getUserInfo/getPhoneNumber 返回的加密数据")
    iv: str = Field(..., description="加密算法的初始向量")


class DecryptPhoneResponse(BaseModel):
    """微信手机号解密响应"""
    phone_number: str = Field(..., description="完整手机号")
    pure_phone_number: str = Field(..., description="纯手机号（无国家码）")
    country_code: str = Field(default="", description="国家码")


class ErrorResponse(BaseModel):
    """错误响应"""
    detail: str


class LoginRequest(BaseModel):
    """开发环境登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class LoginResponse(BaseModel):
    """登录成功响应"""
    token: str = Field(..., description="JWT 兼容 Token")
    user: dict = Field(..., description="用户信息")


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=2, max_length=64, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    name: str = Field("", max_length=64, description="姓名")
    phone: str = Field("", max_length=20, description="手机号")
    company: str = Field("", max_length=128, description="公司")
    position: str = Field("", max_length=64, description="职位")


class RegisterResponse(BaseModel):
    """注册成功响应"""
    token: str = Field(..., description="JWT Token")
    user: dict = Field(..., description="用户信息")
    message: str = Field("注册成功", description="提示信息")


# ===================================================================
# FastAPI 路由
# ===================================================================

router = APIRouter(prefix="/api/auth", tags=["认证与微信解密"])


# ── Dev 登录 ──────────────────────────────────────────────────────

DEV_CREDENTIALS = {
    "admin": {"password": "admin123", "role": "admin"},
    "dev": {"password": "dev123", "role": "developer"},
}


@router.post(
    "/login",
    summary="开发环境登录（用户名密码）",
    response_model=LoginResponse,
    responses={401: {"model": ErrorResponse}},
)
async def dev_login(req: LoginRequest):
    """
    开发环境登录接口 — **仅用于开发/测试阶段**

    支持两组固定账号:
      - admin / admin123  → 角色: admin
      - dev   / dev123    → 角色: developer

    返回 JWT 格式的 token 字符串（HS256 签名，24h 过期）。
    """
    user_info = DEV_CREDENTIALS.get(req.username)
    if not user_info or user_info["password"] != req.password:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # ── 签发真实 JWT token ─────────────────────────────────────────
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": req.username,
        "role": user_info["role"],
        "iat": now,
        "exp": now + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
    }
    token = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return LoginResponse(
        token=token,
        user={"username": req.username, "role": user_info["role"]},
    )


# ── 用户注册 ─────────────────────────────────────────────────────


@router.post(
    "/register",
    summary="用户注册（H5 手动注册）",
    response_model=RegisterResponse,
    responses={400: {"model": ErrorResponse}},
)
async def register(req: RegisterRequest, db=Depends(get_db)):
    """
    H5 手动注册接口

    创建新用户，自动签发 JWT token 并返回用户信息。
    与小程序微信静默登录共享同一 User 表。
    """
    # 检查用户名是否已存在
    existing = db.query(User).filter(
        User.username == req.username,
        User.is_deleted == False,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 创建用户
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        name=req.name or "",
        phone=req.phone or "",
        company=req.company or "",
        position=req.position or "",
        role="user",
        avatar=f"https://api.dicebear.com/7.x/avataaars/svg?seed={req.username}",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 签发 JWT
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": user.username,
        "user_id": user.id,
        "role": user.role,
        "iat": now,
        "exp": now + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
    }
    token = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return RegisterResponse(
        token=token,
        user=user.to_dict(),
        message="注册成功",
    )


# ── 微信手机号解密 ────────────────────────────────────────────────


@router.post(
    "/decrypt-phone",
    summary="微信手机号解密",
    response_model=DecryptPhoneResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def decrypt_phone(req: DecryptPhoneRequest):
    """
    微信小程序手机号解密接口

    流程:
      1. 小程序端调用 wx.login() 获取临时 code
      2. 小程序端调用 wx.getPhoneNumber() 获取 encryptedData 和 iv
      3. 后端将 code 发送至微信服务器换取 session_key
      4. 使用 session_key 解密 encryptedData 得到手机号

    ⚠️ 使用前需在环境变量中设置 WX_APPID 和 WX_SECRET
    """
    # ── 1. 参数校验 ─────────────────────────────────────────────────
    if not WX_APPID or not WX_SECRET:
        logger.error("[Auth] 微信小程序配置缺失: WX_APPID / WX_SECRET 未设置")
        raise HTTPException(
            status_code=500,
            detail="服务器微信小程序配置缺失，请联系管理员设置 WX_APPID 和 WX_SECRET",
        )

    # ── 2. 换取 session_key ─────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                WEIXIN_JSCODE2SESSION_URL,
                params={
                    "appid": WX_APPID,
                    "secret": WX_SECRET,
                    "js_code": req.code,
                    "grant_type": "authorization_code",
                },
            )
            wx_resp = resp.json()
    except httpx.RequestError as e:
        logger.error(f"[Auth] 微信 jscode2session 请求失败: {e}")
        raise HTTPException(status_code=502, detail="微信服务请求失败，请稍后重试")

    # ── 3. 检查微信返回结果 ────────────────────────────────────────
    if "errcode" in wx_resp and wx_resp["errcode"] != 0:
        errcode = wx_resp.get("errcode")
        errmsg = wx_resp.get("errmsg", "未知错误")
        logger.warning(f"[Auth] 微信 jscode2session 返回错误: code={errcode}, msg={errmsg}")

        error_map = {
            -1: "微信系统繁忙，请稍后重试",
            40029: "无效的 code（需重新调用 wx.login）",
            45011: "API 调用频率超限，请稍后重试",
            40226: "高风险用户，被微信临时禁止登录",
        }
        detail = error_map.get(errcode, f"微信登录失败（错误码: {errcode}）")
        raise HTTPException(status_code=400, detail=detail)

    session_key = wx_resp.get("session_key")
    if not session_key:
        logger.error(f"[Auth] 微信返回缺失 session_key: {wx_resp}")
        raise HTTPException(status_code=502, detail="微信服务异常，无法获取会话密钥")

    # ── 4. AES-CBC 解密 ────────────────────────────────────────────
    try:
        phone_info = _decrypt_wechat_data(req.encrypted_data, session_key, req.iv)
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        logger.error(f"[Auth] 手机号解密失败: {e}")
        raise HTTPException(status_code=400, detail="手机号解密失败，请检查 encryptedData 是否有效")

    # ── 5. 返回解密结果 ────────────────────────────────────────────
    return DecryptPhoneResponse(
        phone_number=phone_info.get("phoneNumber", ""),
        pure_phone_number=phone_info.get("purePhoneNumber", ""),
        country_code=phone_info.get("countryCode", ""),
    )


# ===================================================================
# 内部辅助函数
# ===================================================================


def _decrypt_wechat_data(encrypted_data: str, session_key: str, iv: str) -> dict:
    """使用 AES-128-CBC 解密微信加密数据

    Args:
        encrypted_data: 微信返回的加密数据（Base64 编码）
        session_key:    微信会话密钥（Base64 编码）
        iv:             加密初始向量（Base64 编码）

    Returns:
        解密后的 JSON 字典

    Raises:
        ValueError: 解密失败或数据损坏
    """
    try:
        key = base64.b64decode(session_key)
        iv_bytes = base64.b64decode(iv)
        cipher = AES.new(key, AES.MODE_CBC, iv_bytes)

        decrypted_bytes = cipher.decrypt(base64.b64decode(encrypted_data))

        # ── 移除 PKCS7 填充 ──
        pad_len = decrypted_bytes[-1]
        if pad_len < 1 or pad_len > 16:
            raise ValueError("无效的 PKCS7 填充长度")
        decrypted_bytes = decrypted_bytes[:-pad_len]

        # ── 解析 JSON ──
        result = json.loads(decrypted_bytes.decode("utf-8"))
        return result
    except Exception as e:
        raise ValueError(f"微信数据解密失败: {e}")


# ── 启动提示 ─────────────────────────────────────────────────────

print("[Auth] 认证与微信解密路由已加载 ✅")
print("[Auth] 端点: POST /api/auth/login (开发环境登录)")
print("[Auth] 端点: POST /api/auth/register (用户注册)")
print("[Auth] 端点: POST /api/auth/decrypt-phone (微信手机号解密)")
if not WX_APPID or not WX_SECRET:
    print("[Auth] ⚠️  微信配置未设置: 请在环境变量中配置 WX_APPID 和 WX_SECRET")
else:
    print(f"[Auth] 微信 APPID: {WX_APPID[:4]}...{WX_APPID[-4:]}")
