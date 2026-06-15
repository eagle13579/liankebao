#!/usr/bin/env python3
"""
链客宝AI 健康看板
====================
零依赖纯Python HTTP 服务 (BaseHTTPRequestHandler)
- 端口: 9100
- /health    → JSON 健康状态
- /metrics   → Prometheus 文本格式指标
- /          → HTML 简易看板

健康检查:
  - 后端 API: curl http://127.0.0.1:8001/api/v1/products
  - 数据库:   ping SQLite 文件 (backend/data/chainke.db)
"""

import json
import os
import platform
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# ============================================================
# 配置
# ============================================================
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "9100"))
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8001/api/v1/products")
SQLITE_PATH = os.environ.get(
    "SQLITE_PATH",
    str(Path(__file__).resolve().parent / "data" / "chainke.db"),
)
VERSION = "0.1.0"

# ============================================================
# 启动时间
# ============================================================
START_TIME = time.time()


def _uptime() -> float:
    """返回秒级运行时长"""
    return round(time.time() - START_TIME, 2)


def _check_db() -> dict:
    """检查 SQLite 数据库是否可读"""
    result = {"ok": False, "error": None}
    if not os.path.isfile(SQLITE_PATH):
        result["error"] = f"数据库文件不存在: {SQLITE_PATH}"
        return result
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        result["ok"] = True
    except Exception as exc:
        result["error"] = str(exc)
    return result


def _check_backend() -> dict:
    """检查后端 API 是否可达"""
    result = {"ok": False, "status_code": None, "error": None}
    try:
        req = urllib.request.Request(
            BACKEND_URL,
            method="GET",
            headers={"User-Agent": "HealthDashboard/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result["ok"] = 200 <= resp.status < 400
            result["status_code"] = resp.status
    except urllib.error.HTTPError as exc:
        # 4xx/5xx 也算服务在运行
        result["ok"] = True
        result["status_code"] = exc.code
    except urllib.error.URLError as exc:
        result["error"] = str(exc.reason)
    except Exception as exc:
        result["error"] = str(exc)
    return result


def _build_health() -> dict:
    """组装完整的健康状态"""
    db = _check_db()
    api = _check_backend()
    overall = db["ok"] and api["ok"]
    return {
        "status": "ok" if overall else "degraded",
        "uptime_seconds": _uptime(),
        "version": VERSION,
        "db": {
            "ok": db["ok"],
            "error": db["error"],
            "path": SQLITE_PATH,
        },
        "api": {
            "ok": api["ok"],
            "url": BACKEND_URL,
            "status_code": api["status_code"],
            "error": api["error"],
        },
        "host": platform.node(),
        "python": platform.python_version(),
        "timestamp": time.time(),
    }


def _prometheus_metrics(health: dict) -> str:
    """将健康状态转换为 Prometheus 文本格式"""
    lines = []
    lines.append("# HELP liankebao_up 链客宝AI整体健康状态 (1=ok, 0=degraded/down)")
    lines.append("# TYPE liankebao_up gauge")
    lines.append(f"liankebao_up{ {'ok': 1, 'degraded': 0}.get(health['status'], 0) }")

    lines.append("# HELP liankebao_db_up 数据库状态 (1=ok, 0=down)")
    lines.append("# TYPE liankebao_db_up gauge")
    lines.append(f"liankebao_db_up{ {True: 1, False: 0}[health['db']['ok']] }")

    lines.append("# HELP liankebao_api_up 后端API状态 (1=ok, 0=down)")
    lines.append("# TYPE liankebao_api_up gauge")
    lines.append(f"liankebao_api_up{ {True: 1, False: 0}[health['api']['ok']] }")

    lines.append("# HELP liankebao_uptime_seconds 运行时长(秒)")
    lines.append("# TYPE liankebao_uptime_seconds gauge")
    lines.append(f"liankebao_uptime_seconds {health['uptime_seconds']}")

    lines.append("# HELP liankebao_build_info 构建信息")
    lines.append("# TYPE liankebao_build_info gauge")
    lines.append(f'liankebao_build_info{{version="{VERSION}",python="{health["python"]}"}} 1')
    return "\n".join(lines) + "\n"


class HealthHandler(BaseHTTPRequestHandler):
    """健康看板 HTTP 处理器"""

    def do_GET(self):
        health = _build_health()

        if self.path == "/metrics":
            body = _prometheus_metrics(health)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body.encode())))
            self.end_headers()
            self.wfile.write(body.encode())

        elif self.path == "/health" or self.path == "/":
            body = json.dumps(health, ensure_ascii=False, indent=2) + "\n"
            status = 200 if health["status"] == "ok" else 503
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body.encode())))
            self.end_headers()
            self.wfile.write(body.encode())

        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            body = json.dumps({"error": "not found", "path": self.path})
            self.send_header("Content-Length", str(len(body.encode())))
            self.end_headers()
            self.wfile.write(body.encode())

    def log_message(self, fmt, *args):
        """输出到 stdout (systemd/journald 友好)"""
        sys.stdout.write(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {self.address_string()} - {args[0]} {args[1]} {args[2]}\n"
        )
        sys.stdout.flush()


def main():
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)
    print(
        f"[链客宝AI健康看板] 启动于 http://0.0.0.0:{HEALTH_PORT}"
        f"  ├─ /health   → JSON 健康状态"
        f"  ├─ /metrics  → Prometheus 指标"
        f"  └─ /         → JSON 健康状态"
        f"  数据库: {SQLITE_PATH}"
        f"  后端:   {BACKEND_URL}"
        f"  版本:   {VERSION}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[链客宝AI健康看板] 关闭服务", flush=True)
        server.server_close()


if __name__ == "__main__":
    main()
