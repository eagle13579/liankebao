#!/usr/bin/env python3
"""
matrix_watchdog.py — 盖娅矩阵母体API 7x24值守看门狗

每2分钟socket巡检 127.0.0.1:5199，离线自动重启。
日志写入 scripts/_logs/matrix_watchdog.log
"""

import os
import sys
import time
import socket
import subprocess
import logging
from datetime import datetime

# ── 路径 ──
HERMES = r"D:\向海容的知识库\wiki\wiki\记忆宫殿"
SCRIPT_DIR = os.path.join(HERMES, "scripts")
API_SCRIPT = os.path.join(SCRIPT_DIR, "matrix_api.py")
LOG_DIR = os.path.join(SCRIPT_DIR, "_logs")
LOG_FILE = os.path.join(LOG_DIR, "matrix_watchdog.log")

CHECK_INTERVAL = 120  # 2分钟
TARGET_HOST = "127.0.0.1"
TARGET_PORT = 5199

os.makedirs(LOG_DIR, exist_ok=True)

# ── 日志 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("watchdog")


def check_port(host, port, timeout=5):
    """Socket 连接检查端口是否在线"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        log.warning(f"Socket检查异常: {e}")
        return False


def kill_by_port():
    """通过 netstat 查找占用端口的进程并杀掉"""
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.split("\n"):
            if f":{TARGET_PORT}" in line and "LISTENING" in line.upper():
                parts = line.strip().split()
                pid = parts[-1]
                if pid.isdigit():
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True, timeout=5)
                    log.info(f"  ✓ 已杀掉占用端口 {TARGET_PORT} 的进程 PID={pid}")
                    time.sleep(2)
                    return True
    except Exception as e:
        log.warning(f"  通过端口杀进程失败: {e}")
    return False


def restart_api():
    """重启 matrix_api.py 服务"""
    log.info("🔄 正在重启盖娅矩阵API...")

    # 通过端口杀掉旧进程（不依赖PID查找）
    if check_port(TARGET_HOST, TARGET_PORT):
        log.info("  端口仍在占用，先释放端口...")
        kill_by_port()
    time.sleep(2)

    # 启动新进程
    try:
        python_exe = sys.executable or "python"
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        proc = subprocess.Popen(
            [python_exe, API_SCRIPT],
            cwd=SCRIPT_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        log.info(f"  ✓ 新进程已启动 PID={proc.pid}")
        return True
    except Exception as e:
        log.error(f"  ❌ 启动失败: {e}")
        return False


def main():
    log.info("=" * 60)
    log.info("🛡️  盖娅矩阵母体API看门狗 启动")
    log.info(f"   巡检目标: {TARGET_HOST}:{TARGET_PORT}")
    log.info(f"   巡检间隔: {CHECK_INTERVAL}s")
    log.info(f"   API脚本: {API_SCRIPT}")
    log.info(f"   日志文件: {LOG_FILE}")
    log.info("=" * 60)

    # 启动时先检查一次
    if not check_port(TARGET_HOST, TARGET_PORT):
        log.warning("⚠️  启动检测: API不在线，执行首次启动")
        restart_api()
    else:
        log.info("✅ 启动检测: API在线，开始值守监控")

    consecutive_failures = 0
    restart_count = 0

    while True:
        time.sleep(CHECK_INTERVAL)

        online = check_port(TARGET_HOST, TARGET_PORT)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if online:
            if consecutive_failures > 0:
                log.info(f"✅ [{now}] API 已恢复在线 (离线了 {consecutive_failures} 次巡检)")
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            restart_count += 1
            log.warning(f"❌ [{now}] API 离线! (连续 {consecutive_failures} 次巡检失败)")
            log.warning(f"   第 {restart_count} 次重启尝试...")

            if restart_api():
                log.info(f"✅ 重启成功 ✓ (累计重启: {restart_count} 次)")
                # 等待几秒确认启动
                time.sleep(5)
                if check_port(TARGET_HOST, TARGET_PORT):
                    log.info(f"✅ 端口确认已恢复")
                else:
                    log.warning(f"⚠️  端口尚未就绪，将在下次巡检中重试")
            else:
                log.error(f"❌ 重启失败! 将在 {CHECK_INTERVAL}s 后重试")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("👋 看门狗已停止")
    except Exception as e:
        log.exception(f"💥 看门狗崩溃: {e}")
        sys.exit(1)
