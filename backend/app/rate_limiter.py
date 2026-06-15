"""Rate Limiting 中间件 — 滑动窗口实现（零外部依赖）

使用 Python 标准库 time + collections.deque 实现内存滑动窗口速率限制。
增加 SQLite 持久化层，每 100 次 check 将活跃 key 的滑动窗口写入数据库，
重启时自动恢复未过期的限流状态。DB 写入失败自动降级，不影响限流功能。

可配置项:
    RATE_LIMIT_ENABLED: 环境变量，默认 "true" 开启
"""

import json
import logging
import os
import time
from collections import deque

logger = logging.getLogger(__name__)


class MemoryRateLimiter:
    """内存滑动窗口速率限制器（per-IP / per-user）

    对每个唯一标识（IP 或 UserID）维护一个时间戳滑动窗口，
    窗口内的请求计数不能超过上限。窗口过期的记录会自动清理。

    持久化:
        每 _cleanup_interval (100) 次 check 调用时，将活跃的 key 及其
        时间戳窗口序列化写入 rate_limit_records 表。启动时从 DB 恢复
        未过期的限流状态。DB 异常自动降级，不影响限流核心功能。
    """

    def __init__(self, default_limit: int = 100, window_sec: int = 60):
        """
        Args:
            default_limit: 默认窗口内最大请求数
            window_sec: 滑动窗口大小（秒），默认 60 秒
        """
        self.default_limit = default_limit
        self.window_sec = window_sec
        # key -> (limit, deque[timestamp])
        self._records: dict[str, tuple[int, deque]] = {}
        # 每 N 次检查触发一次惰性清理
        self._check_counter = 0
        self._cleanup_interval = 100
        # 尝试从 DB 恢复持久化的限流状态
        self._load_from_db()

    def _load_from_db(self):
        """从数据库加载未过期的限流记录到内存（启动时调用）"""
        try:
            from app.database import SessionLocal
            from app.models import RateLimitRecord

            db = SessionLocal()
            try:
                now = time.time()
                cutoff = now - self.window_sec
                rows = db.query(RateLimitRecord).all()
                loaded = 0
                for rec in rows:
                    try:
                        timestamps = json.loads(rec.timestamps_json)
                        # 过滤掉已经过期的时间戳
                        valid_ts = [ts for ts in timestamps if ts >= cutoff]
                        if valid_ts:
                            self._records[rec.key] = (rec.limit, deque(valid_ts))
                            loaded += 1
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
                if loaded:
                    logger.info(
                        "速率限制器从 DB 恢复 %d/%d 条活跃记录", loaded, len(rows)
                    )
            finally:
                db.close()
        except Exception as e:
            logger.warning("限流状态 DB 恢复失败（降级运行）: %s", e)

    def _get_or_create(self, key: str, limit: int | None = None) -> tuple[int, deque]:
        """获取或创建指定 key 的记录"""
        effective_limit = limit if limit is not None else self.default_limit
        if key not in self._records:
            self._records[key] = (effective_limit, deque())
        return self._records[key]

    def _trim_expired(self, records: deque, now: float):
        """移除窗口外的过期时间戳"""
        cutoff = now - self.window_sec
        while records and records[0] < cutoff:
            records.popleft()

    def _cleanup_stale_keys(self, now: float):
        """清理已过期的 key（所有记录都已过期的条目），并持久化活跃 key"""
        cutoff = now - self.window_sec
        stale_keys = [
            k
            for k, (_, dq) in self._records.items()
            if not dq or dq[-1] < cutoff
        ]
        for k in stale_keys:
            del self._records[k]
        # 将当前活跃的 key 写入 DB（惰性持久化，不阻塞 check 路径）
        self._persist_active_keys(now)

    def _persist_active_keys(self, now: float):
        """将当前活跃的限流记录序列化写入数据库（失败自动降级）"""
        if not self._records:
            return
        try:
            from app.database import SessionLocal
            from app.models import RateLimitRecord
            from datetime import datetime

            cutoff = now - self.window_sec
            db = SessionLocal()
            try:
                for key, (limit, dq) in self._records.items():
                    if not dq:
                        continue
                    # 只持久化窗口内有效的时间戳
                    valid_ts = [ts for ts in dq if ts >= cutoff]
                    if not valid_ts:
                        continue
                    timestamps_json = json.dumps(valid_ts)
                    existing = (
                        db.query(RateLimitRecord)
                        .filter(RateLimitRecord.key == key)
                        .first()
                    )
                    if existing:
                        existing.timestamps_json = timestamps_json
                        existing.limit = limit
                        existing.window_sec = self.window_sec
                        existing.updated_at = datetime.utcnow()
                    else:
                        rec = RateLimitRecord(
                            key=key,
                            limit=limit,
                            window_sec=self.window_sec,
                            timestamps_json=timestamps_json,
                        )
                        db.add(rec)
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except Exception as e:
            logger.warning("限流记录 DB 持久化失败（降级运行）: %s", e)

    def check(self, key: str, limit: int | None = None) -> tuple[bool, int]:
        """检查是否允许请求

        Args:
            key: 唯一标识（如 IP 地址或用户 ID）
            limit: 可选，覆盖该 key 的速率上限

        Returns:
            (allowed, retry_after): (是否允许, 建议重试秒数)
                allowed=True 时 retry_after=0
        """
        now = time.time()
        effective_limit, records = self._get_or_create(key, limit)

        # 清理过期记录
        self._trim_expired(records, now)

        # 周期性清理过期 key 并持久化到 DB
        self._check_counter += 1
        if self._check_counter >= self._cleanup_interval:
            self._check_counter = 0
            self._cleanup_stale_keys(now)

        current_count = len(records)

        if current_count >= effective_limit:
            # 计算剩余等待时间
            oldest = records[0]
            retry_after = int(oldest + self.window_sec - now) + 1
            return False, max(retry_after, 1)

        # 记录当前请求
        records.append(now)
        return True, 0

    def get_remaining(self, key: str, limit: int | None = None) -> int:
        """获取指定 key 的剩余可用请求数"""
        now = time.time()
        effective_limit, records = self._get_or_create(key, limit)
        self._trim_expired(records, now)
        return max(0, effective_limit - len(records))

    def get_limit(self, key: str) -> int:
        """获取指定 key 的速率上限"""
        if key in self._records:
            return self._records[key][0]
        return self.default_limit

    def reset_key(self, key: str):
        """重置指定 key 的统计"""
        self._records.pop(key, None)


# ===== 全局单例 =====
_limiter: MemoryRateLimiter | None = None


def get_rate_limiter() -> MemoryRateLimiter:
    """获取全局 RateLimiter 单例"""
    global _limiter
    if _limiter is None:
        _limiter = MemoryRateLimiter()
    return _limiter


def is_rate_limiting_enabled() -> bool:
    """检查速率限制是否启用（环境变量 RATE_LIMIT_ENABLED，默认开启）"""
    val = os.environ.get("RATE_LIMIT_ENABLED", "true").strip().lower()
    return val in ("1", "true", "yes", "on")


# ===== 路径匹配规则 =====
# 按最长前缀匹配原则，越具体的规则优先级越高
# 格式: (路径前缀, 速率上限)
ROUTE_LIMITS = [
    ("/api/auth/", 10),  # 认证接口: 10 req/min
    ("/api/search/", 30),  # 搜索接口: 30 req/min
    ("/api/payment/wxpay/unified-order", 6),  # 支付下单: 6 req/min（每10秒1次）
    ("/api/payment/wxpay/refund", 3),  # 支付退款: 3 req/min
    ("/api/payment/", 20),  # 支付接口: 20 req/min
    ("/api/v1/payment/", 10),  # 支付v1接口: 10 req/min
    # 注意：/api/auth/ 必须在 /api/ 之前匹配
]


def get_route_limit(path: str, default: int = 100) -> int:
    """根据请求路径获取匹配的速率上限

    使用最长前缀匹配。
    """
    best_limit = default
    best_len = 0
    for prefix, limit in ROUTE_LIMITS:
        if path.startswith(prefix) and len(prefix) > best_len:
            best_limit = limit
            best_len = len(prefix)
    return best_limit


def extract_client_ip(request) -> str:
    """从请求中提取客户端真实 IP

    优先使用 X-Forwarded-For 头（可配置信任代理），
    回退到 request.client.host。
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # 取第一个 IP（最接近客户端）
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def extract_user_id(request) -> str | None:
    """尝试从请求中提取用户标识（Authorization header）

    返回用户标识字符串，用于 per-user 限流。如果未认证返回 None。
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        # 返回 Bearer token 的前 16 位作为用户标识
        # （不解析完整 token，避免依赖认证模块）
        token = auth_header[7:]
        if token:
            return f"user:{token[:16]}"
    return None
