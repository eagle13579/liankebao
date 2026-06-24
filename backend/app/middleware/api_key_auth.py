"""
API Key 认证中间件
===================
支持:
  1. X-API-Key header 认证
  2. 权限范围验证
  3. 调用计数 + 速率限制
  4. 自动记录调用日志
"""

import hashlib
import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta

from fastapi import Request
from fastapi.responses import JSONResponse

from app.database import SessionLocal
from app.models import ApiKey, ApiUsageLog

logger = logging.getLogger(__name__)


def hash_api_key(raw_key: str) -> str:
    """对API Key进行SHA256哈希存储"""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def verify_api_key(request: Request) -> dict | None:
    """
    验证请求中的 API Key。
    返回 {user_id, api_key_id, scopes, tier} 或 None。
    """
    api_key_header = request.headers.get("X-API-Key", "")
    if not api_key_header:
        # 也尝试 Query 参数
        api_key_header = request.query_params.get("api_key", "")
    if not api_key_header:
        return None

    key_hash = hash_api_key(api_key_header)
    db = SessionLocal()
    try:
        key_record = (
            db.query(ApiKey)
            .filter(
                ApiKey.key_hash == key_hash,
                ApiKey.is_active == True,
            )
            .first()
        )
        if not key_record:
            return None

        # 检查是否已被吊销
        if key_record.revoked_at:
            return None

        # 更新最后使用时间
        key_record.last_used_at = datetime.utcnow()
        db.commit()

        return {
            "user_id": key_record.user_id,
            "api_key_id": key_record.id,
            "key_id": key_record.key_id,
            "scopes": key_record.scopes.split(",") if key_record.scopes else ["read"],
            "tier": key_record.tier,
            "rate_limit": key_record.rate_limit_per_hour,
        }
    except Exception as e:
        logger.error(f"API Key 验证失败: {e}")
        return None
    finally:
        db.close()


def log_api_call(
    api_key_id: int,
    user_id: int,
    endpoint: str,
    method: str,
    status_code: int,
    latency_ms: int,
    ip_address: str = "",
):
    """记录API调用日志"""
    db = SessionLocal()
    try:
        log = ApiUsageLog(
            api_key_id=api_key_id,
            user_id=user_id,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            latency_ms=latency_ms,
            ip_address=ip_address,
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"记录API调用日志失败: {e}")
    finally:
        db.close()


def check_rate_limit(api_key_id: int, tier: str, rate_limit: int) -> bool:
    """
    检查速率限制。
    返回 True 表示允许通过，False 表示超出限制。
    """
    db = SessionLocal()
    try:
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        count = (
            db.query(ApiUsageLog)
            .filter(
                ApiUsageLog.api_key_id == api_key_id,
                ApiUsageLog.created_at >= one_hour_ago,
            )
            .count()
        )
        return count < rate_limit
    finally:
        db.close()


async def api_key_middleware(request: Request, call_next: Callable):
    """
    FastAPI 中间件: 自动验证 API Key 并记录调用日志。
    仅作用于 /api/developer/ 路径。
    """
    path = request.url.path
    # 仅处理开发者 API 路径
    if not path.startswith("/api/developer/") or path == "/api/developer/portal":
        return await call_next(request)

    # 尝试 API Key 认证
    api_key_info = verify_api_key(request)
    if api_key_info:
        # 检查速率限制
        if not check_rate_limit(
            api_key_info["api_key_id"],
            api_key_info["tier"],
            api_key_info["rate_limit"],
        ):
            return JSONResponse(
                status_code=429,
                content={"code": 429, "message": "速率限制超出，请稍后重试"},
            )
        # 注入到 request.state
        request.state.api_key_info = api_key_info

    start_time = time.time()
    response = await call_next(request)
    elapsed_ms = int((time.time() - start_time) * 1000)

    # 如果有 API Key 信息，记录调用日志
    if hasattr(request.state, "api_key_info") and request.state.api_key_info:
        log_api_call(
            api_key_id=request.state.api_key_info["api_key_id"],
            user_id=request.state.api_key_info["user_id"],
            endpoint=path,
            method=request.method,
            status_code=response.status_code,
            latency_ms=elapsed_ms,
            ip_address=request.client.host if request.client else "",
        )

    return response
