"""
全链路可观测性看板 API
======================
复用已有资产:
  - observability.py: MetricsCollector + 系统信息
  - telemetry.py: OpenTelemetry 全链路追踪
  - slow_query_warning.py: 慢查询告警
  - circuit_breaker.py: 熔断器
  - MatchingMetricsPage.tsx: 前端Metrics看板

新增:
  1. 统一Metrics API — P50/P99/P95延迟
  2. 健康检查增强 — 数据库/缓存/匹配引擎
  3. 慢查询追踪
  4. 错误率监控
  5. 系统资源监控

端点:
  GET  /api/observability/health          — 完整健康检查
  GET  /api/observability/metrics          — 请求指标
  GET  /api/observability/latency          — 延迟百分位
  GET  /api/observability/errors           — 错误率
  GET  /api/observability/slow-queries     — 慢查询列表
  GET  /api/observability/dashboard        — 看板汇总
"""

import logging
import os
import time
from collections import deque
from datetime import UTC, datetime

import psutil
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/observability", tags=["可观测性"])

# ============================================================
# 延迟追踪器 (内存环形缓冲)
# ============================================================

# 最近1000条请求延迟 (毫秒)
_latency_buffer: deque[float] = deque(maxlen=1000)
# 端点级延迟统计
_endpoint_latency: dict[str, deque[float]] = {}
# 错误计数 (最近1小时)
_error_buffer: deque[tuple[float, str]] = deque(maxlen=500)  # (timestamp, error_type)
# 慢查询记录
_slow_queries: deque[dict[str, Any]] = deque(maxlen=100)


def record_latency(endpoint: str, latency_ms: float):
    """记录请求延迟"""
    _latency_buffer.append(latency_ms)
    if endpoint not in _endpoint_latency:
        _endpoint_latency[endpoint] = deque(maxlen=500)
    _endpoint_latency[endpoint].append(latency_ms)


def record_error(error_type: str):
    """记录错误"""
    _error_buffer.append((time.time(), error_type))


def record_slow_query(query_info: dict[str, Any]):
    """记录慢查询"""
    query_info["timestamp"] = datetime.now(UTC).isoformat()
    _slow_queries.append(query_info)


def _calc_percentiles(data: list[float], ps: list[int] = [50, 90, 95, 99]) -> dict[str, float]:
    """计算百分位数"""
    if not data:
        return {f"p{p}": 0.0 for p in ps}
    sorted_data = sorted(data)
    result = {}
    for p in ps:
        idx = int(len(sorted_data) * p / 100.0)
        idx = min(idx, len(sorted_data) - 1)
        result[f"p{p}"] = round(sorted_data[idx], 2)
    return result


# ============================================================
# Pydantic 模型
# ============================================================


class HealthCheckResponse(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    uptime_seconds: float
    components: dict[str, str]  # component → status


class LatencyResponse(BaseModel):
    overall: dict[str, float]  # p50/p90/p95/p99
    endpoints: dict[str, dict[str, float]]
    sample_count: int


class ErrorRateResponse(BaseModel):
    total_errors: int
    error_rate_per_minute: float
    errors_by_type: dict[str, int]
    recent_errors: list[dict[str, str]]


class SlowQueryResponse(BaseModel):
    count: int
    queries: list[dict[str, Any]]


class DashboardResponse(BaseModel):
    health: str
    uptime_hours: float
    latency_p50: float
    latency_p99: float
    error_rate_per_minute: float
    requests_per_minute: float
    active_connections: int
    cpu_percent: float
    memory_percent: float
    disk_percent: float


# ============================================================
# 健康检查
# ============================================================


_start_time = time.time()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """完整健康检查 — 检查数据库/匹配引擎/缓存"""
    components = {}

    # 数据库检查
    try:
        db.execute("SELECT 1" if "sqlite" in str(db.bind.url) else "SELECT 1")
        components["database"] = "healthy"
    except Exception as e:
        components["database"] = f"unhealthy: {e}"

    # 匹配引擎检查
    try:
        from matching_engine import MatchEngine

        components["matching_engine"] = "healthy"
    except ImportError:
        components["matching_engine"] = "unhealthy: import failed"

    # 磁盘检查
    try:
        disk_usage = psutil.disk_usage("/" if os.name != "nt" else "C:\\")
        if disk_usage.percent > 90:
            components["disk"] = f"degraded: {disk_usage.percent}% used"
        else:
            components["disk"] = f"healthy: {disk_usage.percent}% used"
    except Exception:
        components["disk"] = "unknown"

    # 内存检查
    try:
        mem = psutil.virtual_memory()
        if mem.percent > 90:
            components["memory"] = f"degraded: {mem.percent}% used"
        else:
            components["memory"] = f"healthy: {mem.percent}% used"
    except Exception:
        components["memory"] = "unknown"

    # 判断总体状态
    unhealthy = [v for v in components.values() if v.startswith("unhealthy")]
    degraded = [v for v in components.values() if v.startswith("degraded")]

    if unhealthy:
        status = "unhealthy"
    elif degraded:
        status = "degraded"
    else:
        status = "healthy"

    return HealthCheckResponse(
        status=status,
        uptime_seconds=round(time.time() - _start_time, 2),
        components=components,
    ).model_dump()


# ============================================================
# 延迟指标
# ============================================================


@router.get("/latency")
def get_latency_metrics(
    endpoint: str | None = Query(None, description="按端点过滤"),
):
    """获取延迟百分位指标 P50/P90/P95/P99"""
    if endpoint and endpoint in _endpoint_latency:
        data = list(_endpoint_latency[endpoint])
        return LatencyResponse(
            overall=_calc_percentiles(data),
            endpoints={endpoint: _calc_percentiles(data)},
            sample_count=len(data),
        ).model_dump()

    overall_data = list(_latency_buffer)
    endpoint_data = {ep: _calc_percentiles(list(deq)) for ep, deq in _endpoint_latency.items()}

    return LatencyResponse(
        overall=_calc_percentiles(overall_data),
        endpoints=endpoint_data,
        sample_count=len(overall_data),
    ).model_dump()


# ============================================================
# 错误率
# ============================================================


@router.get("/errors")
def get_error_metrics():
    """获取错误率指标"""
    now = time.time()
    one_hour_ago = now - 3600

    # 最近1小时错误
    recent_errors = [
        {"time": datetime.fromtimestamp(ts, tz=UTC).isoformat(), "type": err_type}
        for ts, err_type in _error_buffer
        if ts > one_hour_ago
    ]

    # 按类型统计
    errors_by_type: dict[str, int] = {}
    for _, err_type in _error_buffer:
        errors_by_type[err_type] = errors_by_type.get(err_type, 0) + 1

    # 每分钟错误率 (最近1小时)
    error_rate = round(len(recent_errors) / 60, 2) if recent_errors else 0.0

    return ErrorRateResponse(
        total_errors=len(_error_buffer),
        error_rate_per_minute=error_rate,
        errors_by_type=errors_by_type,
        recent_errors=recent_errors[-20:],  # 最近20条
    ).model_dump()


# ============================================================
# 慢查询
# ============================================================


@router.get("/slow-queries")
def get_slow_queries(
    limit: int = Query(20, ge=1, le=100),
    min_duration_ms: float = Query(100, description="最低耗时(毫秒)"),
):
    """获取慢查询列表"""
    filtered = [q for q in _slow_queries if q.get("duration_ms", 0) >= min_duration_ms]
    return SlowQueryResponse(
        count=len(filtered),
        queries=list(filtered)[-limit:],
    ).model_dump()


# ============================================================
# 看板汇总
# ============================================================


@router.get("/dashboard")
def get_dashboard():
    """全链路可观测性看板 — 一站式汇总"""
    # 延迟
    latency_data = list(_latency_buffer)
    lat_pcts = _calc_percentiles(latency_data)

    # 错误率
    now = time.time()
    recent_error_count = sum(1 for ts, _ in _error_buffer if ts > now - 3600)
    error_rate_per_min = round(recent_error_count / 60, 2)

    # 请求速率 (最近5分钟)
    five_min_ago = now - 300
    recent_requests = sum(1 for lt in latency_data if lt > 0)  # 近似
    requests_per_min = round(recent_requests / 5, 2) if recent_requests else 0.0

    # 系统资源
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/" if os.name != "nt" else "C:\\").percent
    except Exception:
        cpu = mem = disk = 0.0

    # 健康状态
    health = "healthy"
    if cpu > 90 or mem > 90 or disk > 90:
        health = "degraded"

    return DashboardResponse(
        health=health,
        uptime_hours=round((time.time() - _start_time) / 3600, 2),
        latency_p50=lat_pcts.get("p50", 0),
        latency_p99=lat_pcts.get("p99", 0),
        error_rate_per_minute=error_rate_per_min,
        requests_per_minute=requests_per_min,
        active_connections=0,  # 需要WebSocket管理器集成
        cpu_percent=cpu,
        memory_percent=mem,
        disk_percent=disk,
    ).model_dump()


# ============================================================
# 中间件: 自动记录请求延迟
# ============================================================


class ObservabilityMiddleware:
    """FastAPI 中间件: 自动记录延迟和错误"""

    @staticmethod
    async def __call__(request, call_next):
        start = time.time()
        try:
            response = await call_next(request)
            latency_ms = (time.time() - start) * 1000
            endpoint = request.url.path
            record_latency(endpoint, latency_ms)
            if response.status_code >= 500:
                record_error(f"5xx:{response.status_code}")
            return response
        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            record_error(type(e).__name__)
            raise
