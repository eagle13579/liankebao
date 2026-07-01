"""
AI 数字名片缓存层 — Redis-backed 缓存装饰器 + 工具函数
（向后兼容层：保留旧 API 的同时暴露新的 CacheProtocol 架构）

提供:
  - @cache(ttl=300) — 方法/函数级缓存装饰器
  - invalidate(prefix) — 按前缀失效缓存
  - cached_property — 缓存属性（进程内 + Redis 双层）

用法:
    from app.cache import cache, invalidate

    @cache(ttl=600)
    def expensive_query(db, user_id: int) -> dict:
        ...

    # 数据变更时失效
    invalidate("match", user_id_1, user_id_2)

New architecture (Protocol-based):
    from app.cache.interfaces import CacheProtocol, CacheConfig
    from app.cache.adapters.memory_adapter import InMemoryCache
"""

import asyncio
import functools
import hashlib
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

# ── 缓存键分隔符 ───────────────────────────────────────────────────────────
KEY_SEP = ":"

# ── 运行时：惰性导入 redis 客户端（避免循环依赖） ────────────────────────


def _get_client():
    """惰性获取 Redis 客户端（线程安全）"""
    from app.cache.redis import get_redis

    return get_redis()


# ── 导入 metrics 工具函数（惰性，避免循环导入） ────


def _record_cache_hit():
    try:
        from app.middleware.metrics import record_cache_hit as _rch

        _rch()
    except Exception:
        pass


def _record_cache_miss():
    try:
        from app.middleware.metrics import record_cache_miss as _rcm

        _rcm()
    except Exception:
        pass


# ── 缓存键构建 ─────────────────────────────────────────────────────────────


def _build_cache_key(prefix: str, args: tuple, kwargs: dict) -> str:
    """构建唯一的缓存键

    策略:
      prefix:args_sha256
    其中 args_sha256 是对所有位置参数和关键字参数的确定性哈希。

    这样保证:
      - 相同输入 → 相同缓存键
      - 键长度可控（SHA256 截断前 16 位）
    """
    # 过滤掉 self/cls 和 db Session（不可序列化）
    sig_parts = []
    for arg in args:
        # 跳过数据库会话和大型 ORM 对象
        if _is_skip_arg(arg):
            continue
        try:
            sig_parts.append(json.dumps(arg, sort_keys=True, default=str))
        except (TypeError, ValueError):
            sig_parts.append(repr(arg))

    for k, v in sorted(kwargs.items()):
        if _is_skip_arg(v):
            continue
        try:
            sig_parts.append(f"{k}={json.dumps(v, sort_keys=True, default=str)}")
        except (TypeError, ValueError):
            sig_parts.append(f"{k}={repr(v)}")

    signature = KEY_SEP.join(sig_parts)
    hashed = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{hashed}"


def _is_skip_arg(arg: Any) -> bool:
    """判断是否应跳过此参数（数据库 session、大对象等）"""
    # SQLAlchemy Session
    if hasattr(arg, "query") and hasattr(arg, "commit"):
        return True
    # 大型 ORM 模型列表
    if isinstance(arg, (list, tuple)) and len(arg) > 100:
        return True
    # numpy arrays
    if type(arg).__module__ == "numpy":
        return True
    return False


# ── 缓存装饰器 ─────────────────────────────────────────────────────────────


def cache(
    ttl: int = 300,
    prefix: str | None = None,
    key_builder: Callable | None = None,
    skip_none: bool = True,
) -> Callable:
    """方法/函数级缓存装饰器

    Args:
        ttl: 缓存过期时间（秒），默认 300（5 分钟）
        prefix: 缓存键前缀，默认使用函数名
        key_builder: 自定义键构建函数 fn(func, args, kwargs) -> str
        skip_none: 函数返回 None 时是否跳过缓存（默认 True）

    用法:
        @cache(ttl=600)
        def get_user_profile(db, user_id: int) -> dict:
            ...

        @cache(ttl=60, prefix="hot_match")
        def compute_match(db, user_a: int, user_b: int) -> float:
            ...
    """

    def decorator(func: Callable) -> Callable:
        _prefix = prefix or func.__name__
        _is_async = asyncio.iscoroutinefunction(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # 尝试从缓存读取
            cache_key = _build_cache_key(_prefix, args, kwargs)

            client = _get_client()
            if client is not None:
                try:
                    cached = client.get(cache_key)
                    if cached is not None:
                        _record_cache_hit()
                        logger.debug(f"缓存命中: {cache_key}")
                        return cached
                except Exception:
                    logger.debug(f"缓存读取失败（降级）: {cache_key}")

            # 执行原函数（同步或异步）
            _record_cache_miss()
            logger.debug(f"缓存未命中，执行函数: {_prefix}")
            if _is_async:
                return _async_wrapper(func, cache_key, client, args, kwargs, ttl, skip_none)
            result = func(*args, **kwargs)

            # 写入缓存
            if result is not None or not skip_none:
                if client is not None:
                    try:
                        client.set(cache_key, result, ttl=ttl)
                    except Exception:
                        pass

            return result

        async def _async_wrapper(func, cache_key, client, args, kwargs, ttl, skip_none):
            """异步函数执行 + 缓存写入"""
            result = await func(*args, **kwargs)
            if result is not None or not skip_none:
                if client is not None:
                    try:
                        client.set(cache_key, result, ttl=ttl)
                    except Exception:
                        pass
            return result

        # 暴露清除方法
        def clear_cache(*clr_args, **clr_kwargs) -> bool:
            """手动清除该函数的缓存项"""
            key = _build_cache_key(_prefix, clr_args or args, clr_kwargs or kwargs)
            client = _get_client()
            if client is not None:
                return client.delete(key)
            return False

        wrapper.clear_cache = clear_cache
        wrapper.cache_prefix = _prefix
        return wrapper

    return decorator


# ── 缓存失效工具 ───────────────────────────────────────────────────────────


def invalidate(*prefix_parts: str) -> int:
    """按前缀失效缓存项（scan + delete）

    Args:
        *prefix_parts: 前缀各部分，例如 invalidate("match", 42, 57)
                       会扫描并删除 "match:42:57:*" 的所有键

    Returns:
        删除的键数量
    """
    if not prefix_parts:
        return 0

    pattern = f"{KEY_SEP.join(str(p) for p in prefix_parts)}:{KEY_SEP}*"
    client = _get_client()
    if client is None:
        return 0

    try:
        keys = client.scan_keys(pattern)
        if keys:
            # pipeline 删除
            pipe = client.client.pipeline()
            for key in keys:
                pipe.delete(key)
            pipe.execute()
            logger.info(f"缓存失效: 模式={pattern}, 删除={len(keys)} 个键")
        return len(keys)
    except Exception as e:
        logger.warning(f"缓存失效失败 (pattern={pattern}): {e}")
        return 0


# ── 进程内 LRU + Redis 双层缓存 ──────────────────────────────────────────


class cached_property:
    """缓存属性装饰器（进程内 + Redis 双层）

    适合频繁读取、很少变更的配置类属性。
    进程内缓存避免序列化开销，Redis 层确保多实例一致性。
    """

    def __init__(self, ttl: int = 300):
        self.ttl = ttl
        self._local_cache: dict[str, tuple[Any, float]] = {}

    def __call__(self, func: Callable) -> Callable:
        prefix = func.__name__

        @functools.wraps(func)
        def wrapper(instance) -> Any:
            import time

            cache_key = f"cprop:{prefix}:{id(instance)}"

            # 1. 进程内缓存
            now = time.time()
            local = self._local_cache.get(cache_key)
            if local is not None:
                val, ts = local
                if now - ts < self.ttl:
                    return val

            # 2. Redis 缓存
            client = _get_client()
            if client is not None:
                redis_val = client.get(cache_key)
                if redis_val is not None:
                    self._local_cache[cache_key] = (redis_val, now)
                    return redis_val

            # 3. 执行函数
            result = func(instance)

            # 4. 写入双层缓存
            self._local_cache[cache_key] = (result, now)
            if client is not None:
                client.set(cache_key, result, ttl=self.ttl)

            return result

        return wrapper


# ── 启动时初始化 ─────────────────────────────────────────────────────────


def init_cache(
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_db: int = 0,
    redis_password: str = "",
    redis_max_connections: int = 20,
) -> Any | None:
    """初始化缓存层（供 app 启动时调用）

    用法:
        from app.cache import init_cache
        init_cache(redis_host="redis", redis_port=6379)
    """
    from app.cache.redis import init_redis

    client = init_redis(
        host=redis_host,
        port=redis_port,
        db=redis_db,
        password=redis_password,
        max_connections=redis_max_connections,
    )
    if client:
        logger.info(f"缓存层初始化完成: Redis@{redis_host}:{redis_port}/{redis_db}")
    else:
        logger.warning("缓存层不可用（Redis 未连接），系统以降级模式运行")
    return client


__all__ = [
    "cache",
    "cached_property",
    "invalidate",
    "init_cache",
]
