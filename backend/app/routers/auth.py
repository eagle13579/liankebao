"""认证路由：登录/注册/微信登录/获取当前用户 + JWT加固"""

import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.auth import (
    add_token_to_blacklist,
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    verify_password,
    verify_token,
)
from app.database import get_db
from app.models import User
from app.schemas import (
    ApiResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    UserResponse,
    WechatLoginRequest,
)

router = APIRouter(prefix="/api/auth", tags=["认证"])

# 微信小程序配置
WECHAT_APPID = "wxb4f6d89904200fd2"
# 优先用环境变量，否则读 .env 文件
_env_secret = os.environ.get("WECHAT_APP_SECRET", "")
if not _env_secret:
    try:
        _env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        with open(_env_path) as _f:
            for _line in _f:
                if _line.strip().startswith("WECHAT_APP_SECRET="):
                    _env_secret = _line.strip().split("=", 1)[1]
                    break
    except Exception:
        pass
WECHAT_SECRET = _env_secret
WECHAT_LOGIN_URL = "https://api.weixin.qq.com/sns/jscode2session"

# ===== 登录频率限制 =====
# 同一IP 5分钟内最多10次登录尝试
_LOGIN_RATE_LIMIT = 10  # 最大尝试次数
_LOGIN_RATE_WINDOW = 300  # 时间窗口（秒）= 5分钟
_login_attempts: dict[str, list[datetime]] = defaultdict(list)


def _check_login_rate_limit(ip: str) -> None:
    """检查登录频率限制，超过则拒绝"""
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=_LOGIN_RATE_WINDOW)

    # 清理过期记录
    _login_attempts[ip] = [t for t in _login_attempts[ip] if t > cutoff]

    if len(_login_attempts[ip]) >= _LOGIN_RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录尝试过于频繁，请在{_LOGIN_RATE_WINDOW // 60}分钟后重试",
        )

    _login_attempts[ip].append(now)


def _get_client_ip(request: Request) -> str:
    """从请求中获取客户端真实IP"""
    # 优先取 X-Forwarded-For（反向代理），否则取 remote_addr
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ===== 邮箱/手机号正则 =====
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


def _validate_email_or_phone(value: str) -> bool:
    """校验是否是合法邮箱或手机号"""
    if "@" in value:
        return bool(_EMAIL_RE.match(value))
    else:
        return bool(_PHONE_RE.match(value))


# ===== API 端点 =====


@router.post("/login", response_model=ApiResponse)
def login(
    req: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """用户登录（带频率限制）"""
    # 频率限制
    ip = _get_client_ip(request)
    _check_login_rate_limit(ip)

    user = db.query(User).filter(User.username == req.username, User.is_deleted == False).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # 签发 access token 和 refresh token
    token_data = {"sub": user.username, "role": user.role}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return ApiResponse(
        code=200,
        message="登录成功",
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": UserResponse.model_validate(user).model_dump(),
        },
    )


@router.post("/register", response_model=ApiResponse)
def register(
    req: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """用户注册（含手机号/邮箱格式校验、密码强度校验）"""
    # 频率限制（注册也算在内）
    ip = _get_client_ip(request)
    _check_login_rate_limit(ip)

    # 校验手机号或邮箱格式（username字段）已由 Pydantic schema 的 @field_validator 处理
    # 此处仅做重复性检查，不重复格式校验

    # 密码强度校验
    if len(req.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码长度不能少于8位",
        )

    existing = db.query(User).filter(User.username == req.username, User.is_deleted == False).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        name=req.name,
        phone=req.phone,
        company=req.company,
        position=req.position,
        role=req.role,
        avatar=f"https://api.dicebear.com/7.x/avataaars/svg?seed={req.username}",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return ApiResponse(
        code=200,
        message="注册成功",
        data=UserResponse.model_validate(user).model_dump(),
    )


@router.get("/me", response_model=ApiResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return ApiResponse(
        code=200,
        message="success",
        data=UserResponse.model_validate(current_user).model_dump(),
    )


@router.post("/refresh", response_model=ApiResponse)
def refresh_token(req: RefreshTokenRequest):
    """
    刷新access token（refresh token轮换）
    接收 refresh_token，验证后返回新的 access_token + refresh_token
    """
    payload = verify_token(req.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或已过期的 refresh token",
        )

    username = payload.get("sub")
    role = payload.get("role", "buyer")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 refresh token",
        )

    # 将旧 refresh token 加入黑名单（轮换：旧token作废）
    add_token_to_blacklist(req.refresh_token)

    # 签发全新的 access + refresh token 对
    token_data = {"sub": username, "role": role}
    new_access_token = create_access_token(data=token_data)
    new_refresh_token = create_refresh_token(data=token_data)

    return ApiResponse(
        code=200,
        message="token刷新成功",
        data={
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
        },
    )


@router.post("/logout", response_model=ApiResponse)
def logout(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    退出登录
    将当前请求携带的 access token 加入黑名单（立即失效）
    """
    # 从请求头提取 token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 Authorization 头部",
        )

    token = auth_header[7:]  # 去掉 "Bearer "
    added = add_token_to_blacklist(token)

    return ApiResponse(
        code=200,
        message="退出登录成功" if added else "token 已失效",
    )


@router.post("/wechat-login", response_model=ApiResponse)
def wechat_login(
    req: WechatLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """微信登录 - 通过code获取openid并登录/注册"""
    # 微信登录也限频
    ip = _get_client_ip(request)
    _check_login_rate_limit(ip)

    # 调用微信服务器获取openid
    if not WECHAT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="微信支付尚未配置（缺少 WECHAT_APP_SECRET）",
        )

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                WECHAT_LOGIN_URL,
                params={
                    "appid": WECHAT_APPID,
                    "secret": WECHAT_SECRET,
                    "js_code": req.code,
                    "grant_type": "authorization_code",
                },
            )
            data = resp.json()
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"调用微信服务器失败: {str(e)}",
        )

    # 检查微信返回的errcode
    if "errcode" in data and data["errcode"] != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"微信登录失败: {data.get('errmsg', '未知错误')}",
        )

    openid = data.get("openid")
    session_key = data.get("session_key")
    if not openid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="微信登录失败: 未获取到openid",
        )

    # 查找或创建用户
    user = db.query(User).filter(User.wechat_openid == openid, User.is_deleted == False).first()
    if not user:
        # 新用户 - 用openid创建
        username = f"wx_{openid[:12]}"
        name = f"微信用户_{openid[:8]}"
        user = User(
            username=username,
            password_hash=hash_password(openid),  # 用openid作为密码
            wechat_openid=openid,
            name=name,
            role="buyer",
            avatar=f"https://api.dicebear.com/7.x/avataaars/svg?seed={openid}",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # 签发 access token + refresh token
    token_data = {"sub": user.username, "role": user.role}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return ApiResponse(
        code=200,
        message="微信登录成功",
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": UserResponse.model_validate(user).model_dump(),
            "openid": openid,
            "session_key": session_key,
        },
    )
