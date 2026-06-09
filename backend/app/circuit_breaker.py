"""
链客宝AI Circuit Breaker 熔断器

三态熔断器实现:
  - CLOSED: 正常状态，请求通过
  - OPEN: 熔断状态，请求直接拒绝
  - HALF_OPEN: 半开状态，允许有限请求尝试恢复

装饰器: @circuit_breaker("payment"), @circuit_breaker("matching")
API: GET /api/circuit-breakers (管理员查看各 breaker 状态)
"""

import asyncio
import functools
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# ============================================================
# 配置常量
# ============================================================

DEFAULT_FAILURE_THRESHOLD = 5  # 连续失败 N 次后熔断
DEFAULT_RECOVERY_TIMEOUT = 30  # 熔断后等待 N 秒进入 HALF_OPEN
DEFAULT_HALF_OPEN_MAX = 3  # HALF_OPEN 状态下最多允许 N 次请求
DEFAULT_SUCCESS_THRESHOLD = 3  # HALF_OPEN 下连续成功 N 次后恢复 CLOSED


# ============================================================
# 状态枚举
# ============================================================


class CircuitState(str, Enum):
    CLOSED = "CLOSED"  # 正常
    OPEN = "OPEN"  # 熔断
    HALF_OPEN = "HALF_OPEN"  # 半开（尝试恢复）


# ============================================================
# 熔断器实例
# ============================================================


@dataclass
class CircuitBreakerInstance:
    """单个熔断器实例的状态和数据"""

    name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    last_state_change_time: float = 0.0
    total_requests: int = 0
    total_failures: int = 0
    total_successes: int = 0
    total_rejected: int = 0
    consecutive_successes: int = 0  # HALF_OPEN 下连续成功次数
    consecutive_failures: int = 0  # CLOSED 下连续失败次数

    # 可配置参数
    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD
    recovery_timeout: int = DEFAULT_RECOVERY_TIMEOUT
    half_open_max: int = DEFAULT_HALF_OPEN_MAX
    success_threshold: int = DEFAULT_SUCCESS_THRESHOLD

    # 滑动窗口记录（最近 N 次调用的成功/失败）
    recent_results: list[bool] = field(default_factory=list)
    max_recent_results: int = 100

    def reset(self) -> None:
        """重置熔断器到 CLOSED 状态"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.last_state_change_time = time.time()
        self.recent_results.clear()

    def to_dict(self) -> dict[str, Any]:
        """导出为序列化字典"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "total_rejected": self.total_rejected,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "half_open_max": self.half_open_max,
            "success_threshold": self.success_threshold,
            "failure_rate": self._failure_rate(),
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "last_state_change_time": self.last_state_change_time,
            "uptime_sec": round(time.time() - self.last_state_change_time, 2),
        }

    def _failure_rate(self) -> float:
        """计算最近 N 次请求的失败率"""
        if not self.recent_results:
            return 0.0
        failures = sum(1 for r in self.recent_results if not r)
        return round(failures / len(self.recent_results), 4)


# ============================================================
# 熔断器注册表
# ============================================================


class CircuitBreakerRegistry:
    """全局熔断器注册表，管理所有熔断器实例"""

    def __init__(self):
        self._lock = threading.RLock()
        self._breakers: dict[str, CircuitBreakerInstance] = {}

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        recovery_timeout: int = DEFAULT_RECOVERY_TIMEOUT,
        half_open_max: int = DEFAULT_HALF_OPEN_MAX,
        success_threshold: int = DEFAULT_SUCCESS_THRESHOLD,
    ) -> CircuitBreakerInstance:
        """获取或创建熔断器实例"""
        with self._lock:
            if name not in self._breakers:
                cb = CircuitBreakerInstance(
                    name=name,
                    failure_threshold=failure_threshold,
                    recovery_timeout=recovery_timeout,
                    half_open_max=half_open_max,
                    success_threshold=success_threshold,
                )
                cb.last_state_change_time = time.time()
                self._breakers[name] = cb
                logger.info(f"熔断器已创建: {name} (threshold={failure_threshold}, timeout={recovery_timeout}s)")
            return self._breakers[name]

    def get(self, name: str) -> CircuitBreakerInstance | None:
        """获取熔断器实例"""
        with self._lock:
            return self._breakers.get(name)

    def get_all(self) -> dict[str, CircuitBreakerInstance]:
        """获取所有熔断器实例"""
        with self._lock:
            return dict(self._breakers)

    def get_all_states(self) -> dict[str, dict[str, Any]]:
        """获取所有熔断器的状态摘要"""
        result = {}
        with self._lock:
            for name, cb in self._breakers.items():
                result[name] = cb.to_dict()
        return result

    def reset(self, name: str) -> bool:
        """重置指定熔断器"""
        with self._lock:
            cb = self._breakers.get(name)
            if cb:
                cb.reset()
                logger.info(f"熔断器已手动重置: {name}")
                return True
            return False

    def reset_all(self) -> int:
        """重置所有熔断器"""
        count = 0
        with self._lock:
            for name, cb in self._breakers.items():
                cb.reset()
                count += 1
        logger.info(f"所有熔断器已重置 ({count}个)")
        return count

    def record_success(self, name: str) -> None:
        """记录一次成功调用"""
        with self._lock:
            cb = self._breakers.get(name)
            if cb is None:
                return
            cb.total_requests += 1
            cb.total_successes += 1
            cb.last_success_time = time.time()
            cb.recent_results.append(True)
            if len(cb.recent_results) > cb.max_recent_results:
                cb.recent_results.pop(0)

            if cb.state == CircuitState.HALF_OPEN:
                cb.consecutive_successes += 1
                cb.consecutive_failures = 0
                if cb.consecutive_successes >= cb.success_threshold:
                    logger.info(f"熔断器恢复: {name} (HALF_OPEN→CLOSED, 连续成功{cb.consecutive_successes}次)")
                    cb.state = CircuitState.CLOSED
                    cb.consecutive_failures = 0
                    cb.consecutive_successes = 0
                    cb.last_state_change_time = time.time()
            elif cb.state == CircuitState.CLOSED:
                cb.consecutive_successes += 1
                cb.consecutive_failures = 0

    def record_failure(self, name: str) -> None:
        """记录一次失败调用"""
        with self._lock:
            cb = self._breakers.get(name)
            if cb is None:
                return
            cb.total_requests += 1
            cb.total_failures += 1
            cb.last_failure_time = time.time()
            cb.recent_results.append(False)
            if len(cb.recent_results) > cb.max_recent_results:
                cb.recent_results.pop(0)

            if cb.state == CircuitState.CLOSED:
                cb.consecutive_failures += 1
                cb.consecutive_successes = 0
                if cb.consecutive_failures >= cb.failure_threshold:
                    logger.warning(f"熔断器触发: {name} (CLOSED→OPEN, 连续失败{cb.consecutive_failures}次)")
                    cb.state = CircuitState.OPEN
                    cb.last_state_change_time = time.time()
            elif cb.state == CircuitState.HALF_OPEN:
                cb.consecutive_failures += 1
                cb.consecutive_successes = 0
                # HALF_OPEN 下失败立即回到 OPEN
                logger.warning(f"熔断器恢复失败: {name} (HALF_OPEN→OPEN, 半开状态下失败)")
                cb.state = CircuitState.OPEN
                cb.last_state_change_time = time.time()

    def should_allow(self, name: str) -> tuple[bool, str | None]:
        """判断请求是否应该被允许通过

        Returns:
            (允许通过, 拒绝原因)
        """
        with self._lock:
            cb = self._breakers.get(name)
            if cb is None:
                return True, None

            if cb.state == CircuitState.CLOSED:
                return True, None

            if cb.state == CircuitState.OPEN:
                # 检查是否达到恢复超时时间
                elapsed = time.time() - cb.last_state_change_time
                if elapsed >= cb.recovery_timeout:
                    logger.info(f"熔断器尝试恢复: {name} (OPEN→HALF_OPEN, 等待{elapsed:.1f}s > {cb.recovery_timeout}s)")
                    cb.state = CircuitState.HALF_OPEN
                    cb.consecutive_successes = 0
                    cb.consecutive_failures = 0
                    cb.last_state_change_time = time.time()
                    return True, None
                return False, f"circuit_breaker '{name}' is OPEN (retry after {cb.recovery_timeout - elapsed:.0f}s)"

            if cb.state == CircuitState.HALF_OPEN:
                # HALF_OPEN 下限制通过请求数
                if cb.total_requests - cb.last_state_change_time < cb.half_open_max:
                    # 粗略估算：检查最近 half_open_max 个请求中有多少是在 HALF_OPEN 状态下
                    # 简单实现：直接统计当前半开期间的总请求数
                    half_open_requests = cb.total_requests + cb.total_rejected - cb.last_state_change_time
                    # 更准确：使用一个计数器追踪半开期间的请求
                    if not hasattr(cb, "_half_open_count"):
                        cb._half_open_count = 0
                    if cb._half_open_count < cb.half_open_max:
                        cb._half_open_count += 1
                        return True, None
                return False, f"circuit_breaker '{name}' is HALF_OPEN (limited to {cb.half_open_max} requests)"

            return True, None

    def mark_rejected(self, name: str) -> None:
        """记录一次被拒绝的请求"""
        with self._lock:
            cb = self._breakers.get(name)
            if cb:
                cb.total_rejected += 1


# ============================================================
# 全局单例
# ============================================================

_registry: CircuitBreakerRegistry | None = None


def get_registry() -> CircuitBreakerRegistry:
    """获取全局 CircuitBreakerRegistry 单例"""
    global _registry
    if _registry is None:
        _registry = CircuitBreakerRegistry()
    return _registry


# ============================================================
# 装饰器
# ============================================================


class CircuitBreakerError(Exception):
    """熔断器拒绝请求时抛出的异常"""

    def __init__(self, name: str, reason: str):
        self.name = name
        self.reason = reason
        super().__init__(f"[{name}] {reason}")


def circuit_breaker(
    name: str,
    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
    recovery_timeout: int = DEFAULT_RECOVERY_TIMEOUT,
    half_open_max: int = DEFAULT_HALF_OPEN_MAX,
    success_threshold: int = DEFAULT_SUCCESS_THRESHOLD,
    fallback: Callable | None = None,
):
    """熔断器装饰器

    用法:
        @circuit_breaker("payment")
        async def process_payment(...):
            ...

        @circuit_breaker("matching", failure_threshold=3, recovery_timeout=10)
        def match_business(...):
            ...

        @circuit_breaker("search", fallback=lambda: {"results": []})
        def search_with_fallback(...):
            ...

    Args:
        name: 熔断器名称（唯一标识）
        failure_threshold: 连续失败次数阈值（默认 5）
        recovery_timeout: 熔断后恢复等待秒数（默认 30）
        half_open_max: 半开状态最大请求数（默认 3）
        success_threshold: 半开状态连续成功恢复阈值（默认 3）
        fallback: 熔断时的降级函数
    """

    def decorator(func):
        registry = get_registry()
        cb = registry.get_or_create(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max=half_open_max,
            success_threshold=success_threshold,
        )

        is_async = asyncio.iscoroutinefunction(func)

        if is_async:

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                allowed, reason = registry.should_allow(name)
                if not allowed:
                    registry.mark_rejected(name)
                    if fallback is not None:
                        logger.warning(f"熔断器拒绝请求 {name}，使用降级函数")
                        if asyncio.iscoroutinefunction(fallback):
                            return await fallback(*args, **kwargs)
                        return fallback(*args, **kwargs)
                    raise CircuitBreakerError(name, reason)

                try:
                    result = await func(*args, **kwargs)
                    registry.record_success(name)
                    return result
                except Exception as e:
                    registry.record_failure(name)
                    if fallback is not None:
                        logger.warning(f"熔断器调用失败 {name}，使用降级函数: {e}")
                        if asyncio.iscoroutinefunction(fallback):
                            return await fallback(*args, **kwargs)
                        return fallback(*args, **kwargs)
                    raise

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                allowed, reason = registry.should_allow(name)
                if not allowed:
                    registry.mark_rejected(name)
                    if fallback is not None:
                        logger.warning(f"熔断器拒绝请求 {name}，使用降级函数")
                        return fallback(*args, **kwargs)
                    raise CircuitBreakerError(name, reason)

                try:
                    result = func(*args, **kwargs)
                    registry.record_success(name)
                    return result
                except Exception as e:
                    registry.record_failure(name)
                    if fallback is not None:
                        logger.warning(f"熔断器调用失败 {name}，使用降级函数: {e}")
                        return fallback(*args, **kwargs)
                    raise

            return sync_wrapper

    return decorator


# ============================================================
# FastAPI 路由
# ============================================================

from fastapi import APIRouter

circuit_breaker_router = APIRouter(tags=["circuit_breakers"])


@circuit_breaker_router.get(
    "/api/circuit-breakers",
    summary="查看所有熔断器状态",
    description="管理员查看所有 Circuit Breaker 的当前状态、统计数据",
)
async def list_circuit_breakers(request: Request):
    """查看所有熔断器状态（管理员）"""
    # 权限检查
    user_role = getattr(request.state, "user_role", None)
    if user_role != "admin":
        role_str = request.headers.get("X-User-Role", "")
        if role_str != "admin":
            return JSONResponse(
                status_code=403,
                content={"code": 403, "message": "需要管理员权限"},
            )

    registry = get_registry()
    states = registry.get_all_states()

    # 汇总统计
    total_count = len(states)
    open_count = sum(1 for s in states.values() if s["state"] == "OPEN")
    half_open_count = sum(1 for s in states.values() if s["state"] == "HALF_OPEN")
    closed_count = sum(1 for s in states.values() if s["state"] == "CLOSED")

    return {
        "code": 200,
        "message": "success",
        "data": {
            "breakers": states,
            "summary": {
                "total": total_count,
                "closed": closed_count,
                "open": open_count,
                "half_open": half_open_count,
            },
        },
    }


@circuit_breaker_router.post(
    "/api/circuit-breakers/{name}/reset",
    summary="重置熔断器",
    description="管理员手动重置指定熔断器为 CLOSED 状态",
)
async def reset_circuit_breaker(name: str, request: Request):
    """重置指定熔断器"""
    user_role = getattr(request.state, "user_role", None)
    if user_role != "admin":
        role_str = request.headers.get("X-User-Role", "")
        if role_str != "admin":
            return JSONResponse(
                status_code=403,
                content={"code": 403, "message": "需要管理员权限"},
            )

    registry = get_registry()
    if registry.reset(name):
        return {
            "code": 200,
            "message": "success",
            "data": {"name": name, "state": "CLOSED"},
        }
    return JSONResponse(
        status_code=404,
        content={"code": 404, "message": f"熔断器 '{name}' 不存在"},
    )


@circuit_breaker_router.post(
    "/api/circuit-breakers/reset-all",
    summary="重置所有熔断器",
    description="管理员重置所有熔断器为 CLOSED 状态",
)
async def reset_all_circuit_breakers(request: Request):
    """重置所有熔断器"""
    user_role = getattr(request.state, "user_role", None)
    if user_role != "admin":
        role_str = request.headers.get("X-User-Role", "")
        if role_str != "admin":
            return JSONResponse(
                status_code=403,
                content={"code": 403, "message": "需要管理员权限"},
            )

    registry = get_registry()
    count = registry.reset_all()
    return {
        "code": 200,
        "message": "success",
        "data": {"reset_count": count},
    }


# ============================================================
# 注册函数
# ============================================================


def register_circuit_breakers(app: FastAPI) -> None:
    """注册 Circuit Breaker 路由到 FastAPI 应用"""
    app.include_router(circuit_breaker_router)
    logger.info("Circuit Breaker 路由已注册")
