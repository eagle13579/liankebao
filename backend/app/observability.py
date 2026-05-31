"""
可观测性模块：应用指标收集、健康检查、系统信息
纯 Python stdlib 实现，零外部依赖

包含:
- MetricsCollector: 线程安全的请求指标收集器（请求量/错误率/响应时间）
- get_system_info(): 获取CPU/内存/磁盘/运行时长等系统信息
- check_db_health(): 数据库连接健康检查
"""

import logging
import os
import threading
import time
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

# ============================================================
# 应用启动时间戳（用于计算运行时长）
# ============================================================
_APP_START_TIME = time.time()


def get_uptime() -> float:
    """获取应用运行时长（秒）"""
    return time.time() - _APP_START_TIME


# ============================================================
# 线程安全的请求指标收集器
# ============================================================
class MetricsCollector:
    """
    请求指标收集器（线程安全）

    跟踪：
    - 总请求数、总错误数（4xx/5xx）
    - 响应时间统计（avg / min / max / p50 / p95 / p99）
    - 按路径、按状态码、按方法的请求分布
    """

    def __init__(self, max_response_times: int = 10000):
        self._lock = threading.Lock()
        self._total_requests = 0
        self._total_errors = 0  # status >= 400
        self._total_5xx = 0  # status >= 500
        self._response_times: deque = deque(maxlen=max_response_times)
        self._requests_by_path: dict = defaultdict(int)
        self._requests_by_status: dict = defaultdict(int)
        self._requests_by_method: dict = defaultdict(int)

    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        elapsed_sec: float,
    ) -> None:
        """记录一次请求的指标"""
        with self._lock:
            self._total_requests += 1
            if status_code >= 500:
                self._total_5xx += 1
                self._total_errors += 1
            elif status_code >= 400:
                self._total_errors += 1
            self._response_times.append(elapsed_sec)
            self._requests_by_path[path] += 1
            self._requests_by_status[status_code] += 1
            self._requests_by_method[method] += 1

    def snapshot(self) -> dict:
        """获取当前指标快照"""
        with self._lock:
            times = list(self._response_times)
            n = len(times)

            if n == 0:
                resp_time_stats = {
                    "avg_ms": 0.0,
                    "min_ms": 0.0,
                    "max_ms": 0.0,
                    "p50_ms": 0.0,
                    "p95_ms": 0.0,
                    "p99_ms": 0.0,
                    "samples": 0,
                }
            else:
                avg_time = sum(times) / n
                sorted_times = sorted(times)

                def percentile(p: float) -> float:
                    idx = int(n * p)
                    return sorted_times[min(idx, n - 1)]

                resp_time_stats = {
                    "avg_ms": round(avg_time * 1000, 2),
                    "min_ms": round(sorted_times[0] * 1000, 2),
                    "max_ms": round(sorted_times[-1] * 1000, 2),
                    "p50_ms": round(percentile(0.5) * 1000, 2),
                    "p95_ms": round(percentile(0.95) * 1000, 2),
                    "p99_ms": round(percentile(0.99) * 1000, 2),
                    "samples": n,
                }

            return {
                "total_requests": self._total_requests,
                "total_errors": self._total_errors,
                "total_5xx": self._total_5xx,
                "error_rate": round(self._total_errors / max(self._total_requests, 1) * 100, 2),
                "response_time": resp_time_stats,
                "requests_by_path": dict(self._requests_by_path),
                "requests_by_status": dict(self._requests_by_status),
                "requests_by_method": dict(self._requests_by_method),
            }

    def reset(self) -> None:
        """重置所有指标（调试/测试用）"""
        with self._lock:
            self._total_requests = 0
            self._total_errors = 0
            self._total_5xx = 0
            self._response_times.clear()
            self._requests_by_path.clear()
            self._requests_by_status.clear()
            self._requests_by_method.clear()

    def generate_prometheus_text(self) -> str:
        """生成 Prometheus 文本格式（exposition format）的指标输出"""
        snap = self.snapshot()
        lines = []
        # HELP / TYPE 注释
        lines.append("# HELP http_requests_total 总请求数")
        lines.append("# TYPE http_requests_total counter")
        lines.append(f"http_requests_total {snap['total_requests']}")

        lines.append("# HELP http_errors_total 总错误数 (status >= 400)")
        lines.append("# TYPE http_errors_total counter")
        lines.append(f"http_errors_total {snap['total_errors']}")

        lines.append("# HELP http_5xx_total 服务器错误数 (status >= 500)")
        lines.append("# TYPE http_5xx_total counter")
        lines.append(f"http_5xx_total {snap['total_5xx']}")

        lines.append("# HELP http_error_rate 错误率 (百分比)")
        lines.append("# TYPE http_error_rate gauge")
        lines.append(f"http_error_rate {snap['error_rate']}")

        rt = snap["response_time"]
        lines.append("# HELP http_response_time_ms 响应时间统计 (毫秒)")
        lines.append("# TYPE http_response_time_ms gauge")
        lines.append(f'http_response_time_ms{{quantile="avg"}} {rt["avg_ms"]}')
        lines.append(f'http_response_time_ms{{quantile="min"}} {rt["min_ms"]}')
        lines.append(f'http_response_time_ms{{quantile="max"}} {rt["max_ms"]}')
        lines.append(f'http_response_time_ms{{quantile="p50"}} {rt["p50_ms"]}')
        lines.append(f'http_response_time_ms{{quantile="p95"}} {rt["p95_ms"]}')
        lines.append(f'http_response_time_ms{{quantile="p99"}} {rt["p99_ms"]}')

        lines.append("# HELP http_response_samples 响应时间采样数")
        lines.append("# TYPE http_response_samples gauge")
        lines.append(f"http_response_samples {rt['samples']}")

        lines.append("# HELP http_requests_by_method 按方法的请求数")
        lines.append("# TYPE http_requests_by_method counter")
        for method, count in snap["requests_by_method"].items():
            lines.append(f'http_requests_by_method{{method="{method}"}} {count}')

        lines.append("# HELP http_requests_by_status 按状态码的请求数")
        lines.append("# TYPE http_requests_by_status counter")
        for status, count in snap["requests_by_status"].items():
            lines.append(f'http_requests_by_status{{status="{status}"}} {count}')

        lines.append("# HELP http_requests_by_path 按路径的请求数")
        lines.append("# TYPE http_requests_by_path counter")
        for path, count in snap["requests_by_path"].items():
            escaped_path = path.replace('"', '\\"')
            lines.append(f'http_requests_by_path{{path="{escaped_path}"}} {count}')

        # 运行时长
        lines.append("# HELP app_uptime_seconds 应用运行时长 (秒)")
        lines.append("# TYPE app_uptime_seconds counter")
        lines.append(f"app_uptime_seconds {get_uptime()}")

        return "\n".join(lines) + "\n"


# 全局单例
_metrics_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """获取全局指标收集器实例"""
    return _metrics_collector


# ============================================================
# 系统信息收集（纯 stdlib，零外部依赖）
# ============================================================
def get_system_info() -> dict:
    """
    收集系统状态信息

    跨平台（Linux / macOS / Windows）：
    - CPU 核心数、系统负载（仅 Linux）
    - 内存总量/已用/可用（仅 Linux 读取 /proc/meminfo）
    - 磁盘总量/已用/可用（跨平台 shutil）
    - 应用运行时长、Python 版本、平台名
    """
    info: dict = {
        "uptime_sec": round(get_uptime()),
        "uptime_human": format_uptime(get_uptime()),
        "cpu_count": os.cpu_count() or 0,
        "platform": _get_platform(),
        "python_version": os.sys.version.split()[0],
        "hostname": _get_hostname(),
    }

    # ---- 系统负载（仅 Linux） ----
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().strip().split()
            info["load_avg"] = {
                "1min": float(parts[0]),
                "5min": float(parts[1]),
                "15min": float(parts[2]),
            }
    except (OSError, FileNotFoundError, IndexError):
        pass

    # ---- 内存信息（仅 Linux /proc/meminfo） ----
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                try:
                    k, v_raw = line.split(":", 1)
                    v = v_raw.strip().split()[0]
                    meminfo[k] = int(v) * 1024  # kB -> bytes
                except (ValueError, IndexError):
                    pass

        mem_total = meminfo.get("MemTotal", 0)
        mem_avail = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
        mem_used = mem_total - mem_avail
        info["memory"] = {
            "total_bytes": mem_total,
            "used_bytes": mem_used,
            "available_bytes": mem_avail,
            "used_percent": round((mem_used / mem_total) * 100, 1) if mem_total > 0 else 0,
        }
    except (OSError, FileNotFoundError):
        pass

    # ---- 磁盘信息（跨平台） ----
    try:
        import shutil

        usage = shutil.disk_usage("/")
        info["disk"] = {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "used_percent": round((usage.used / usage.total) * 100, 1) if usage.total > 0 else 0,
        }
    except (ImportError, OSError):
        pass

    return info


def _get_platform() -> str:
    """获取平台名称（兼容 Linux / Windows / macOS）"""
    if hasattr(os, "uname"):
        return os.uname().sysname  # Linux / Darwin
    return os.name  # 'nt' for Windows


def _get_hostname() -> str:
    """获取主机名"""
    try:
        return os.uname().nodename
    except AttributeError:
        try:
            import socket

            return socket.gethostname()
        except Exception:
            return "unknown"


def format_uptime(seconds: float) -> str:
    """将秒转换为人类可读的运行时长"""
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m {secs}s"
    elif hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


# ============================================================
# 数据库健康检查
# ============================================================
def check_db_health() -> dict:
    """
    检查数据库连接是否正常（兼容 SQLAlchemy 2.0+ 使用 text()）

    Returns:
        {"status": "healthy"|"unhealthy", "type": "sqlite"|"mysql"|"postgres", "error": "..."}
    """
    from sqlalchemy import text

    from app.database import DB_TYPE, engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "healthy", "type": DB_TYPE}
    except Exception as e:
        logger.warning("数据库健康检查失败", extra={"error": str(e)})
        return {"status": "unhealthy", "type": DB_TYPE, "error": str(e)}


def check_payment_health() -> dict:
    """
    检查支付通道可达性

    检查支付配置是否已注册（微信支付/支付宝），
    若配置了真实模式则尝试轻量级探活。

    Returns:
        {"status": "healthy"|"unhealthy"|"not_configured",
         "channels": [...],
         "error": "..."}
    """
    result = {"channels": []}
    try:
        from payment.config import (
            PLATFORM_ALIPAY,
            PLATFORM_WXPAY,
            has_config,
            is_real_mode,
            list_platforms,
        )

        platforms = list_platforms()
        if not platforms:
            result["status"] = "not_configured"
            result["channels"] = []
            return result

        for platform in platforms:
            configured = has_config(platform)
            channel_info = {"name": platform, "configured": configured}
            result["channels"].append(channel_info)

        result["status"] = "healthy"
        return result
    except ImportError:
        # 未安装支付模块
        result["status"] = "not_configured"
        result["channels"] = []
        result["note"] = "payment module not installed"
        return result
    except Exception as e:
        logger.warning("支付通道健康检查失败", extra={"error": str(e)})
        result["status"] = "unhealthy"
        result["error"] = str(e)
        return result
