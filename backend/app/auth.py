"""JWT认证 + 密码哈希 + 微信登录"""

import hashlib
import os
import uuid
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.hash import bcrypt as bcrypt_hasher
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

# JWT配置
SECRET_KEY = os.environ.get("SECRET_KEY", "liankebao-jwt-secret-key-2024-nous")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # access token 有效期 30 分钟
REFRESH_TOKEN_EXPIRE_MINUTES = 30 * 24 * 7  # refresh token 有效期 7 天

# Token过期时间（小时）
TOKEN_EXPIRE_HOURS = 72

# 旧SHA256密码兼容（过渡期）
HASH_SALT_OLD = "digital_brochure_v2"

# HTTP Bearer token 安全方案
security = HTTPBearer(auto_error=False)

# Token黑名单（内存+DB双重持久化）
# 内存缓存加速查询，DB持久化防止重启丢失
_token_blacklist: set[str] = set()
_blacklist_loaded: bool = False


def _load_blacklist_from_db():
    """启动/首次使用时从DB加载已吊销token到内存"""
    global _blacklist_loaded
    if _blacklist_loaded:
        return
    try:
        from app.database import SessionLocal
        from app.models import RevokedToken

        db = SessionLocal()
        revoked = db.query(RevokedToken.jti).all()
        for (jti,) in revoked:
            _token_blacklist.add(jti)
        db.close()
        _blacklist_loaded = True
    except Exception:
        pass  # DB表可能还不存在（首次启动），静默跳过


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码 - 先bcrypt验证, 失败则回退SHA256兼容旧密码"""
    # 先尝试bcrypt验证
    try:
        if bcrypt_hasher.verify(plain_password, hashed_password):
            return True
    except Exception:
        pass
    # 兼容旧SHA256密码（digital_brochure_v2:password）
    try:
        old_hash = hashlib.sha256(f"{HASH_SALT_OLD}:{plain_password}".encode()).hexdigest()
        return old_hash == hashed_password
    except Exception:
        return False


def hash_password(password: str) -> str:
    """哈希密码"""
    return bcrypt_hasher.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """创建JWT access token（短有效期）"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update(
        {
            "exp": expire,
            "type": "access",
            "jti": str(uuid.uuid4()),
        }
    )
    # 如果用户有 organization_id，注入 JWT
    user_id = data.get("sub")
    if user_id:
        from app.database import SessionLocal, is_multi_tenant

        if is_multi_tenant():
            try:
                db = SessionLocal()
                user = db.query(User).filter(User.username == user_id).first()
                if user:
                    if user.organization_id:
                        to_encode["org_id"] = user.organization_id
                    # 注入角色信息
                    to_encode["role"] = user.role or "viewer"
                db.close()
            except Exception:
                pass
        else:
            # SQLite 模式：直接从数据库查角色
            try:
                db = SessionLocal()
                user = db.query(User).filter(User.username == user_id).first()
                if user:
                    to_encode["role"] = user.role or "viewer"
                db.close()
            except Exception:
                pass
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """创建JWT refresh token（长有效期，用于静默续期）"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES))
    to_encode.update(
        {
            "exp": expire,
            "type": "refresh",
            "jti": str(uuid.uuid4()),
        }
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str, expected_type: str | None = None) -> dict | None:
    """
    验证JWT token，返回 payload。
    同时检查黑名单。可指定期望的 token type（access/refresh）。
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # 检查黑名单（先确保从DB加载过）
        _load_blacklist_from_db()
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
    """将 token 加入黑名单（通过 jti 识别），同时持久化到 DB"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if jti:
            _token_blacklist.add(jti)
            # 持久化到 DB
            try:
                from app.database import SessionLocal
                from app.models import RevokedToken

                db = SessionLocal()
                existing = db.query(RevokedToken).filter(RevokedToken.jti == jti).first()
                if not existing:
                    expires_at = datetime.fromtimestamp(payload.get("exp")) if payload.get("exp") else None
                    db.add(
                        RevokedToken(
                            jti=jti,
                            expires_at=expires_at,
                        )
                    )
                    db.commit()
                db.close()
            except Exception:
                pass  # DB不可用时至少内存黑名单生效
            return True
        return False
    except JWTError:
        return False


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
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

    user = db.query(User).filter(User.username == username, User.is_deleted == False).first()
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
