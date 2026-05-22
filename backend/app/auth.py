"""JWT认证 + 密码哈希 + 微信登录"""
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, Set

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.hash import bcrypt as bcrypt_hasher
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

# JWT配置
SECRET_KEY = os.environ.get("SECRET_KEY", "liankebao-jwt-secret-key-2024-nous")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30           # access token 有效期 30 分钟
REFRESH_TOKEN_EXPIRE_MINUTES = 30 * 24 * 7  # refresh token 有效期 7 天

# HTTP Bearer token 安全方案
security = HTTPBearer(auto_error=False)

# Token黑名单（内存中，生产环境建议改为 Redis）
# 使用 set 存储已失效的 token jti
_token_blacklist: Set[str] = set()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    try:
        return bcrypt_hasher.verify(plain_password, hashed_password)
    except Exception:
        return False


def hash_password(password: str) -> str:
    """哈希密码"""
    return bcrypt_hasher.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建JWT access token（短有效期）"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({
        "exp": expire,
        "type": "access",
        "jti": str(uuid.uuid4()),
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建JWT refresh token（长有效期，用于静默续期）"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES))
    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str, expected_type: Optional[str] = None) -> Optional[dict]:
    """
    验证JWT token，返回 payload。
    同时检查黑名单。可指定期望的 token type（access/refresh）。
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # 检查黑名单
        jti = payload.get("jti")
        if jti and jti in _token_blacklist:
            return None
        # 检查 token 类型
        if expected_type and payload.get("type") != expected_type:
            return None
        return payload
    except JWTError:
        return None


def add_token_to_blacklist(token: str) -> bool:
    """将 token 加入黑名单（通过 jti 识别）"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if jti:
            _token_blacklist.add(jti)
            return True
        return False
    except JWTError:
        return False


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """依赖注入：从请求中获取当前用户"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要提供认证令牌",
        )

    token = credentials.credentials
    payload = verify_token(token, expected_type="access")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
        )

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    return user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """依赖注入：确保当前用户是管理员"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user
