#!/usr/bin/env python
"""
链客宝 — Docker 容器健康检查
=============================
检查后端服务、Redis、Nginx 是否在线，输出 JSON 状态报告。

Usage:
    python backend/scripts/health_check_docker.py
    python backend/scripts/health_check_docker.py --json

Options:
    --json         仅输出 JSON（适合被 Docker 或监控系统调用）
    --timeout N    每个检查的超时秒数（默认 5）
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ── 配置 ──────────────────────────────────────────────────────────────────────
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001")
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
NGINX_URL = os.getenv("NGINX_URL", "http://127.0.0.1:80")


def check_backend(timeout: int = 5) -> dict:
    """检查后端 FastAPI 服务是否在线"""
    endpoints = [
        ("主健康检查", f"{BACKEND_URL}/health"),
        ("API 健康检查", f"{BACKEND_URL}/api/health"),
    ]

    results = []
    overall = False

    for name, url in endpoints:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")
                ok = status == 200
                if ok:
                    overall = True
                results.append({
                    "endpoint": name,
                    "url": url,
                    "status": status,
                    "ok": ok,
                    "detail": body[:200] if not ok else "",
                })
        except urllib.error.HTTPError as e:
            results.append({
                "endpoint": name,
                "url": url,
                "status": e.code,
                "ok": False,
                "detail": str(e.reason),
            })
        except urllib.error.URLError as e:
            results.append({
                "endpoint": name,
                "url": url,
                "status": 0,
                "ok": False,
                "detail": f"连接失败: {e.reason}",
            })
        except Exception as e:
            results.append({
                "endpoint": name,
                "url": url,
                "status": 0,
                "ok": False,
                "detail": f"异常: {e}",
            })

    return {
        "service": "backend",
        "online": overall,
        "checks": results,
    }


def check_redis(timeout: int = 5) -> dict:
    """检查 Redis 是否在线（通过 redis-cli ping）"""
    import subprocess

    try:
        result = subprocess.run(
            ["redis-cli", "-h", REDIS_HOST, "-p", str(REDIS_PORT), "ping"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        ok = result.stdout.strip() == "PONG"
        return {
            "service": "redis",
            "online": ok,
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip() if result.stderr else "",
        }
    except FileNotFoundError:
        return {
            "service": "redis",
            "online": False,
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "error": "redis-cli 未安装",
        }
    except subprocess.TimeoutExpired:
        return {
            "service": "redis",
            "online": False,
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "error": f"连接超时（{timeout}s）",
        }
    except Exception as e:
        return {
            "service": "redis",
            "online": False,
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "error": str(e),
        }


def check_nginx(timeout: int = 5) -> dict:
    """检查 Nginx 是否在线"""
    try:
        req = urllib.request.Request(f"{NGINX_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
            ok = status in (200, 404)  # 404 说明 Nginx 在工作但路径未匹配
            return {
                "service": "nginx",
                "online": ok,
                "url": f"{NGINX_URL}/health",
                "status": status,
                "detail": body[:200],
            }
    except urllib.error.HTTPError as e:
        # 4xx/5xx 但 Nginx 响应了 => 在线
        return {
            "service": "nginx",
            "online": True,
            "url": f"{NGINX_URL}/health",
            "status": e.code,
            "detail": str(e.reason),
        }
    except urllib.error.URLError as e:
        return {
            "service": "nginx",
            "online": False,
            "url": f"{NGINX_URL}/health",
            "status": 0,
            "detail": f"连接失败: {e.reason}",
        }
    except Exception as e:
        return {
            "service": "nginx",
            "online": False,
            "url": f"{NGINX_URL}/health",
            "status": 0,
            "detail": f"异常: {e}",
        }


def main():
    parser = argparse.ArgumentParser(
        description="链客宝 — Docker 容器健康检查",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="仅输出 JSON（适合被监控系统调用）",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="每个检查的超时秒数（默认 5）",
    )
    args = parser.parse_args()

    # 执行所有健康检查
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": os.uname().nodename if hasattr(os, "uname") else os.environ.get("HOSTNAME", "unknown"),
    }

    results["backend"] = check_backend(timeout=args.timeout)
    results["redis"] = check_redis(timeout=args.timeout)
    results["nginx"] = check_nginx(timeout=args.timeout)

    # 整体状态
    all_online = all(
        results[s]["online"] for s in ("backend", "redis", "nginx")
    )
    results["overall"] = {
        "status": "healthy" if all_online else "degraded",
        "all_online": all_online,
        "online_count": sum(1 for s in ("backend", "redis", "nginx") if results[s]["online"]),
        "total_count": 3,
    }

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        sys.exit(0 if all_online else 1)

    # ── 可读格式输出 ──────────────────────────────────────────────────────
    print("=" * 60)
    print(f"  链客宝 — Docker 容器健康检查")
    print(f"  时间: {results['timestamp']}")
    print(f"  主机: {results['hostname']}")
    print("=" * 60)

    for svc in ("backend", "redis", "nginx"):
        info = results[svc]
        emoji = "✅" if info["online"] else "❌"
        print(f"\n  {emoji} {svc.upper()} {'在线' if info['online'] else '离线'}")
        for k, v in info.items():
            if k == "service" or k == "online":
                continue
            if isinstance(v, list):
                for item in v:
                    for ik, iv in item.items():
                        print(f"      {ik}: {iv}")
            elif isinstance(v, dict):
                for ik, iv in v.items():
                    print(f"      {ik}: {iv}")
            else:
                print(f"      {k}: {v}")

    overall = results["overall"]
    emoji_all = "✅" if overall["all_online"] else "⚠️"
    print(f"\n{emoji_all} 整体状态: {overall['status']}")
    print(f"   在线: {overall['online_count']}/{overall['total_count']}")
    print()

    sys.exit(0 if overall["all_online"] else 1)


if __name__ == "__main__":
    main()
