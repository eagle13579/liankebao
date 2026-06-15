"""Redis缓存层 — @cached 装饰器，用于高频读取的API端点"""
import json
import hashlib
from functools import wraps
from typing import Optional, Callable, Any

import redis.asyncio as aioredis
from fastapi import Request

REDIS_URL = "redis://localhost:6379/0"
CACHE_ENABLED = True
DEFAULT_TTL = 300  # 5 minutes

_redis_client = None

def get_redis() -> Optional[Any]:
    """获取Redis客户端（惰性初始化）"""
    global _redis_client
    if not CACHE_ENABLED:
        return None
    if _redis_client is None:
        try:
            _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        except Exception:
            return None
    return _redis_client

def cache_key(prefix: str, request: Request = None, **kwargs) -> str:
    """生成缓存键"""
    raw = f"{prefix}:{json.dumps(kwargs, sort_keys=True, default=str)}"
    return f"chainke:{hashlib.md5(raw.encode()).hexdigest()[:16]}"

def cached(ttl: int = DEFAULT_TTL):
    """缓存装饰器 — 用于高频读取的API端点"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            r = get_redis()
            if r is None:
                return await func(*args, **kwargs)
            try:
                key = cache_key(func.__name__, **{k: v for k, v in kwargs.items() if k != 'db'})
                cached_data = await r.get(key)
                if cached_data:
                    return json.loads(cached_data)
            except Exception:
                pass
            result = await func(*args, **kwargs)
            try:
                serializable = result
                if hasattr(result, 'body'):
                    serializable = json.loads(result.body)
                elif hasattr(result, '__dict__'):
                    serializable = result.__dict__
                await r.setex(key, ttl, json.dumps(serializable, default=str))
            except Exception:
                pass
            return result
        return wrapper
    return decorator

CACHE_POINTS = {
    "products_list":    {"route": "/api/products",      "ttl": 120, "desc": "产品列表"},
    "recommend":        {"route": "/api/recommend",     "ttl": 300, "desc": "推荐结果"},
    "matching":         {"route": "/api/matching",      "ttl": 300, "desc": "匹配结果"},
    "search_results":   {"route": "/api/search",        "ttl": 60,  "desc": "搜索结果"},
    "user_profile":     {"route": "/api/auth/profile",  "ttl": 30,  "desc": "用户信息"},
}
