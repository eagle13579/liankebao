#!/usr/bin/env python3
"""
链客宝自动恢复脚本 — Auto Recovery
====================================
自动检测服务异常并执行恢复操作。

检测规则:
  - 端口不通 → 自动重启uvicorn
  - 内存>80% → 重启服务
  - 磁盘>90% → 清理日志/临时文件

最大重试3次, 3次失败 → 发CRITICAL告警

启动: python scripts/auto_recover.py --daemon
"""

import argparse
import atexit
import logging
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

# 尝试导入 psutil（可选 — 内存/磁盘检测）
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# ============================================================
# 路径配置
# ============================================================
_BASE_DIR = Path(__file__).resolve().parent.parent
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

LOG_DIR = _BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "auto_recover.log"

RUN_DIR = _BASE_DIR / "run"
RUN_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = RUN_DIR / "auto_recover.pid"

# ============================================================
# 日志
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("auto_recover")

# ============================================================
# 配置
# ============================================================
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8001"))
BACKEND_HOST = os.environ.get("BACKEND_HOST", "127.0.0.1")
DOCKER_SERVICE_NAME = os.environ.get("DOCKER_SERVICE_NAME", "chainke-backend")
UVICORN_CMD = os.environ.get(
    "UVICORN_CMD",
    "uvicorn app.main:app --host 0.0.0.0 --port {} --workers 2 --log-level info".format(
        BACKEND_PORT
    ),
)

MEMORY_THRESHOLD = int(os.environ.get("MEMORY_THRESHOLD", "80"))  # %
DISK_THRESHOLD = int(os.environ.get("DISK_THRESHOLD", "90"))  # %
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "30"))  # 秒
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))

# Docker compose 项目路径
DOCKER_COMPOSE_DIR = _BASE_DIR / "deploy"


# ============================================================
# 恢复操作状态跟踪
# ============================================================
class RecoveryState:
    """跟踪每次异常的恢复状态"""

    def __init__(self):
        self._lock = Lock()
        self._port_retries: dict[int, int] = {}  # port -> retry_count
        self._memory_retries = 0
        self._disk_retries = 0
        self._last_port_fail_time: float | None = None
        self._last_memory_fail_time: float | None = None
        self._last_disk_fail_time: float | None = None

    def increment_port(self, port: int) -> int:
        with self._lock:
            self._port_retries[port] = self._port_retries.get(port, 0) + 1
            self._last_port_fail_time = time.time()
            return self._port_retries[port]

    def increment_memory(self) -> int:
        with self._lock:
            self._memory_retries += 1
            self._last_memory_fail_time = time.time()
            return self._memory_retries

    def increment_disk(self) -> int:
        with self._lock:
            self._disk_retries += 1
            self._last_disk_fail_time = time.time()
            return self._disk_retries

    def reset_port(self, port: int):
        with self._lock:
            self._port_retries.pop(port, None)

    def reset_all(self):
        with self._lock:
            self._port_retries.clear()
            self._memory_retries = 0
            self._disk_retries = 0

    def get_port_retries(self, port: int) -> int:
        with self._lock:
            return self._port_retries.get(port, 0)


state = RecoveryState()


# ============================================================
# 工具函数：发送告警（直接调用 alert_manager 模块）
# ============================================================
def send_alert(title: str, message: str, level: str = "ERROR"):
    """发送告警 — 尝试导入alert_manager模块"""
    try:
        sys.path.insert(0, str(_BASE_DIR))
        from deploy.alert_manager import _dispatcher

        _dispatcher.dispatch(title, message, level)
    except ImportError:
        logger.error(
            f"无法导入alert_manager，告警未发送: [{level}] {title} - {message}"
        )
        # 降级：写入日志文件
        alert_log = LOG_DIR / "recovery_alerts.log"
        with open(alert_log, "a", encoding="utf-8") as f:
            f.write(
                f"[{level}] {datetime.now().isoformat()} - {title}\n  {message}\n\n"
            )


# ============================================================
# Docker 操作
# ============================================================
def _run_docker_compose(args: list[str]) -> tuple[bool, str]:
    """运行 docker compose 命令"""
    try:
        result = subprocess.run(
            ["docker", "compose"] + args,
            cwd=str(DOCKER_COMPOSE_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )
        success = result.returncode == 0
        output = result.stdout + result.stderr
        return success, output.strip()
    except FileNotFoundError:
        return False, "docker 命令未找到"
    except subprocess.TimeoutExpired:
        return False, "docker compose 命令超时"
    except Exception as e:
        return False, str(e)


# ============================================================
# 检测与恢复
# ============================================================


# ---- 1. 端口检测 ----
def check_port(host: str, port: int) -> bool:
    """检查端口是否可达"""
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.error(f"端口检测异常 {host}:{port}: {e}")
        return False


def recover_port(host: str, port: int) -> bool:
    """端口不通 → 重启uvicorn"""
    retries = state.increment_port(port)
    logger.warning(f"端口 {host}:{port} 不可达 (第{retries}/{MAX_RETRIES}次重试)")

    if retries > MAX_RETRIES:
        send_alert(
            title="端口恢复失败（超过最大重试次数）",
            message=(
                f"后端服务 {host}:{port} 端口无法连接\n"
                f"已尝试重启 {MAX_RETRIES} 次均失败\n"
                f"最后一次检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"建议: 人工介入检查服务状态"
            ),
            level="CRITICAL",
        )
        state.reset_port(port)
        return False

    logger.info(f"尝试重启后端服务: docker compose restart {DOCKER_SERVICE_NAME}")
    success, output = _run_docker_compose(["restart", DOCKER_SERVICE_NAME])

    if success:
        logger.info("docker compose restart 成功")
        # 等待服务启动
        time.sleep(10)
        if check_port(host, port):
            logger.info(f"服务已恢复: {host}:{port}")
            state.reset_port(port)
            send_alert(
                title="服务自动恢复成功",
                message=(
                    f"后端服务 {host}:{port} 已通过 docker compose restart 自动恢复\n"
                    f"恢复时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                ),
                level="WARNING",
            )
            return True
        else:
            logger.warning("服务重启后端口仍未恢复，将进行下一次重试")
    else:
        logger.error(f"docker compose restart 失败: {output}")
        send_alert(
            title="Docker重启失败",
            message=f"docker compose restart {DOCKER_SERVICE_NAME} 失败: {output}",
            level="ERROR",
        )

    return False


# ---- 2. 内存检测 ----
def check_memory() -> tuple[bool, float]:
    """检查内存使用率"""
    if not PSUTIL_AVAILABLE:
        logger.warning("psutil 未安装，跳过内存检测")
        return True, 0.0

    try:
        mem = psutil.virtual_memory()
        usage_pct = mem.percent
        logger.debug(f"内存使用率: {usage_pct:.1f}%")
        return usage_pct < MEMORY_THRESHOLD, usage_pct
    except Exception as e:
        logger.error(f"内存检测失败: {e}")
        return True, 0.0


def recover_memory() -> bool:
    """内存>80% → 重启服务"""
    retries = state.increment_memory()
    logger.warning(
        f"内存使用率超过 {MEMORY_THRESHOLD}% (第{retries}/{MAX_RETRIES}次重试)"
    )

    if retries > MAX_RETRIES:
        send_alert(
            title="内存恢复失败（超过最大重试次数）",
            message=(
                f"内存使用率持续超过 {MEMORY_THRESHOLD}%\n"
                f"已尝试重启 {MAX_RETRIES} 次均失败\n"
                f"建议: 人工介入检查内存泄漏或扩容"
            ),
            level="CRITICAL",
        )
        state._memory_retries = 0
        return False

    logger.info(f"内存过高，重启后端服务: docker compose restart {DOCKER_SERVICE_NAME}")
    success, output = _run_docker_compose(["restart", DOCKER_SERVICE_NAME])

    if success:
        logger.info("docker compose restart 成功 (内存恢复)")
        state._memory_retries = 0
        send_alert(
            title="内存告警恢复",
            message=(
                f"内存使用率超过 {MEMORY_THRESHOLD}%，已自动重启服务\n"
                f"恢复时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            ),
            level="WARNING",
        )
        return True
    else:
        logger.error(f"docker compose restart 失败: {output}")
        send_alert(
            title="Docker重启失败（内存）",
            message=f"docker compose restart {DOCKER_SERVICE_NAME} 失败: {output}",
            level="ERROR",
        )

    return False


# ---- 3. 磁盘检测 ----
def check_disk() -> tuple[bool, float]:
    """检查磁盘使用率"""
    if not PSUTIL_AVAILABLE:
        logger.warning("psutil 未安装，跳过磁盘检测")
        return True, 0.0

    try:
        # 检查项目所在磁盘
        disk_path = str(_BASE_DIR)
        usage = psutil.disk_usage(disk_path)
        usage_pct = usage.percent
        logger.debug(f"磁盘使用率 ({disk_path}): {usage_pct:.1f}%")
        return usage_pct < DISK_THRESHOLD, usage_pct
    except Exception as e:
        logger.error(f"磁盘检测失败: {e}")
        return True, 0.0


def clean_disk() -> bool:
    """磁盘>90% → 清理日志/临时文件"""
    retries = state.increment_disk()
    logger.warning(
        f"磁盘使用率超过 {DISK_THRESHOLD}% (第{retries}/{MAX_RETRIES}次重试)"
    )

    if retries > MAX_RETRIES:
        send_alert(
            title="磁盘清理失败（超过最大重试次数）",
            message=(
                f"磁盘使用率持续超过 {DISK_THRESHOLD}%\n"
                f"已尝试清理 {MAX_RETRIES} 次均未降至阈值以下\n"
                f"建议: 人工介入检查磁盘扩容"
            ),
            level="CRITICAL",
        )
        state._disk_retries = 0
        return False

    cleaned = 0
    try:
        # 清理日志文件（保留最近3天的日志）
        log_files = list(LOG_DIR.glob("*.log*"))
        cutoff = time.time() - 3 * 86400  # 3天前
        for log_file in log_files:
            if log_file.stat().st_mtime < cutoff:
                size = log_file.stat().st_size
                log_file.unlink()
                cleaned += size
                logger.info(f"清理过期日志: {log_file.name} ({size / 1024:.1f}KB)")

        # 清理 __pycache__ 目录
        for pycache_dir in _BASE_DIR.rglob("__pycache__"):
            if pycache_dir.is_dir():
                for f in pycache_dir.glob("*"):
                    if f.is_file():
                        cleaned += f.stat().st_size
                        f.unlink()
                try:
                    pycache_dir.rmdir()
                except OSError:
                    pass

        # 清理临时文件
        tmp_dir = _BASE_DIR / "tmp"
        if tmp_dir.exists():
            for f in tmp_dir.glob("*"):
                if f.is_file():
                    cleaned += f.stat().st_size
                    f.unlink()
                elif f.is_dir():
                    import shutil

                    shutil.rmtree(str(f), ignore_errors=True)

        # 清理 Docker 系统（可选）
        try:
            subprocess.run(
                ["docker", "system", "prune", "-f", "--volumes"],
                capture_output=True,
                timeout=30,
            )
        except Exception:
            pass

        logger.info(f"磁盘清理完成: 释放 {cleaned / 1024 / 1024:.2f}MB")

        if cleaned > 0:
            send_alert(
                title="磁盘自动清理完成",
                message=(
                    f"磁盘使用率超过 {DISK_THRESHOLD}%，已自动清理\n"
                    f"释放空间: {cleaned / 1024 / 1024:.2f}MB\n"
                    f"清理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                ),
                level="INFO",
            )

        state._disk_retries = 0
        return True

    except Exception as e:
        logger.error(f"磁盘清理失败: {e}")
        send_alert(
            title="磁盘清理异常",
            message=f"磁盘清理过程中发生错误: {e}",
            level="ERROR",
        )
        return False


# ============================================================
# 主检测循环
# ============================================================
def detection_loop():
    """定期检测循环"""
    logger.info(f"自动恢复监控启动，检测间隔: {CHECK_INTERVAL}s")
    logger.info(f"端口检测: {BACKEND_HOST}:{BACKEND_PORT}")
    logger.info(f"内存阈值: {MEMORY_THRESHOLD}%")
    logger.info(f"磁盘阈值: {DISK_THRESHOLD}%")
    logger.info(f"最大重试: {MAX_RETRIES}次")

    if not PSUTIL_AVAILABLE:
        logger.warning("psutil 未安装，内存/磁盘检测功能受限")
        logger.warning("请执行: pip install psutil")

    while True:
        try:
            now = datetime.now(UTC)

            # ---- 检测1: 端口检测 ----
            port_ok = check_port(BACKEND_HOST, BACKEND_PORT)
            if not port_ok:
                recover_port(BACKEND_HOST, BACKEND_PORT)
            else:
                # 端口恢复后重置
                state.reset_port(BACKEND_PORT)

            # ---- 检测2: 内存检测 ----
            mem_ok, mem_pct = check_memory()
            if not mem_ok:
                logger.warning(f"内存使用率过高: {mem_pct:.1f}%")
                recover_memory()

            # ---- 检测3: 磁盘检测 ----
            disk_ok, disk_pct = check_disk()
            if not disk_ok:
                logger.warning(f"磁盘使用率过高: {disk_pct:.1f}%")
                clean_disk()

            logger.debug(
                f"状态: 端口={'OK' if port_ok else 'FAIL'} "
                f"内存={'OK' if mem_ok else f'{mem_pct:.1f}%'} "
                f"磁盘={'OK' if disk_ok else f'{disk_pct:.1f}%'}"
            )

        except Exception as e:
            logger.error(f"检测循环异常: {e}", exc_info=True)

        time.sleep(CHECK_INTERVAL)


# ============================================================
# Daemon 管理
# ============================================================
def write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    logger.info(f"PID文件已写入: {PID_FILE} (PID: {os.getpid()})")


def remove_pid():
    if PID_FILE.exists():
        PID_FILE.unlink()
        logger.info("PID文件已删除")


def is_running() -> bool:
    if PID_FILE.exists():
        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            if sys.platform == "win32":
                import ctypes

                handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                os.kill(pid, 0)
                return True
        except (OSError, ValueError, ProcessLookupError):
            return False
    return False


def daemonize():
    if sys.platform == "win32":
        logger.info("Windows环境: 跳过daemonize")
        return
    pid = os.fork()
    if pid > 0:
        sys.exit(0)
    os.setsid()
    os.umask(0)
    pid = os.fork()
    if pid > 0:
        sys.exit(0)
    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "r") as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open(os.devnull, "w") as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())


# ============================================================
# Main
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="链客宝自动恢复脚本")
    parser.add_argument("--daemon", action="store_true", help="以守护进程模式运行")
    parser.add_argument("--stop", action="store_true", help="停止运行中的自动恢复")
    parser.add_argument("--status", action="store_true", help="查看运行状态")
    args = parser.parse_args()

    if args.status:
        if is_running():
            with open(PID_FILE) as f:
                pid = f.read().strip()
            print(f"✅ 自动恢复正在运行 (PID: {pid})")
            sys.exit(0)
        else:
            print("❌ 自动恢复未运行")
            sys.exit(1)

    if args.stop:
        if PID_FILE.exists():
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            try:
                if sys.platform == "win32":
                    import ctypes

                    handle = ctypes.windll.kernel32.OpenProcess(0x0001, False, pid)
                    if handle:
                        ctypes.windll.kernel32.TerminateProcess(handle, 0)
                        ctypes.windll.kernel32.CloseHandle(handle)
                else:
                    os.kill(pid, 15)
                print(f"✅ 自动恢复已停止 (PID: {pid})")
                remove_pid()
            except ProcessLookupError:
                print("⚠️ 进程不存在，清理PID文件")
                remove_pid()
            except Exception as e:
                print(f"❌ 停止失败: {e}")
                sys.exit(1)
        else:
            print("❌ PID文件不存在，自动恢复未运行")
        sys.exit(0)

    if args.daemon:
        if is_running():
            with open(PID_FILE) as f:
                pid = f.read().strip()
            print(f"❌ 自动恢复已在运行 (PID: {pid})")
            sys.exit(1)
        daemonize()
        write_pid()
        atexit.register(remove_pid)

    logger.info("=" * 50)
    logger.info("链客宝自动恢复监控启动")
    logger.info(f"检测目标: {BACKEND_HOST}:{BACKEND_PORT}")
    logger.info(f"Docker服务: {DOCKER_SERVICE_NAME}")
    logger.info(f"内存阈值: {MEMORY_THRESHOLD}%")
    logger.info(f"磁盘阈值: {DISK_THRESHOLD}%")
    logger.info(f"检测间隔: {CHECK_INTERVAL}s")
    logger.info(f"最大重试: {MAX_RETRIES}次")
    logger.info("=" * 50)

    try:
        detection_loop()
    except KeyboardInterrupt:
        logger.info("收到中断信号，自动恢复退出")
    finally:
        remove_pid()


if __name__ == "__main__":
    main()
