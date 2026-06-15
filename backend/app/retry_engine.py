"""
支付回调补偿机制 — 重试引擎 + 死信队列

功能:
  1. RetryEngine: 将失败的任务写入 SQLite 队列，周期性轮询并重试
  2. DeadLetterManager: 管理死信（超过重试上限的任务），支持查询/重放/统计
  3. 指数退避: 每次重试间隔递增 (1min → 5min → 30min … 封顶 30min)
  4. 纯 Python 标准库实现，零外部依赖
"""

import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from urllib import request as urllib_request
from urllib.error import URLError

logger = logging.getLogger(__name__)

# ============================================================
# 数据类
# ============================================================


@dataclass
class RetryTask:
    """重试任务"""

    task_id: str = ""
    target_url: str = ""
    payload: str = ""  # JSON 字符串
    max_retries: int = 3
    attempt: int = 0
    next_run_at: float | None = None  # unix timestamp
    status: str = "pending"  # pending / processing / completed / dead / failed
    created_at: float | None = None
    last_error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# SQLite 数据库管理
# ============================================================

_RETRY_DB_PATH: str | None = None


def _get_db_path() -> str:
    """获取重试引擎 SQLite 数据库路径"""
    global _RETRY_DB_PATH
    if _RETRY_DB_PATH:
        return _RETRY_DB_PATH
    # 与主应用数据目录保持一致
    import os

    base_dir = os.environ.get(
        "SQLITE_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
    )
    os.makedirs(base_dir, exist_ok=True)
    _RETRY_DB_PATH = os.path.join(base_dir, "retry_engine.db")
    return _RETRY_DB_PATH


def set_db_path(path: str) -> None:
    """允许外部注入自定义数据库路径（用于测试）"""
    global _RETRY_DB_PATH
    _RETRY_DB_PATH = path


def _get_conn() -> sqlite3.Connection:
    """获取 SQLite 连接"""
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _init_table() -> None:
    """创建 retry_tasks 表（如不存在）"""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS retry_tasks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id         TEXT NOT NULL UNIQUE,
                target_url      TEXT NOT NULL,
                payload         TEXT NOT NULL,
                max_retries     INTEGER NOT NULL DEFAULT 3,
                attempt         INTEGER NOT NULL DEFAULT 0,
                next_run_at     REAL,
                status          TEXT NOT NULL DEFAULT 'pending',
                created_at      REAL NOT NULL,
                last_error      TEXT DEFAULT ''
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ============================================================
# RetryEngine — 重试引擎
# ============================================================


class RetryEngine:
    """
    重试引擎

    用法:
        engine = RetryEngine()
        engine.add_task(RetryTask(target_url="...", payload="..."))
        engine.start()  # 在后台线程启动处理循环
        engine.stop()   # 优雅关闭
    """

    def __init__(self, poll_interval: float = 10.0):
        """
        Args:
            poll_interval: 轮询间隔（秒），每次轮询拉取到期 pending 任务
        """
        self._poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        _init_table()

    # ----- 公开方法 -----

    def add_task(self, task: RetryTask) -> str:
        """
        将任务加入重试队列

        Args:
            task: 重试任务（至少需设置 target_url 和 payload）

        Returns:
            task_id: 生成的唯一任务 ID
        """
        if not task.task_id:
            task.task_id = str(uuid.uuid4())
        if not task.created_at:
            task.created_at = time.time()
        if task.next_run_at is None:
            task.next_run_at = task.created_at  # 立即执行

        conn = _get_conn()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO retry_tasks
                    (task_id, target_url, payload, max_retries, attempt,
                     next_run_at, status, created_at, last_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.target_url,
                    task.payload,
                    task.max_retries,
                    task.attempt,
                    task.next_run_at,
                    task.status,
                    task.created_at,
                    task.last_error,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # 已存在，更新
            conn.execute(
                """
                UPDATE retry_tasks SET
                    target_url=?, payload=?, max_retries=?, attempt=?,
                    next_run_at=?, status=?, last_error=?
                WHERE task_id=?
                """,
                (
                    task.target_url,
                    task.payload,
                    task.max_retries,
                    task.attempt,
                    task.next_run_at,
                    task.status,
                    task.last_error,
                    task.task_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        logger.info(f"重试任务已加入队列: task_id={task.task_id}, target_url={task.target_url}")
        return task.task_id

    def start(self) -> None:
        """在后台线程启动处理循环"""
        if self._thread and self._thread.is_alive():
            logger.warning("重试引擎已在运行")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="retry-engine")
        self._thread.start()
        logger.info("重试引擎已启动")

    def stop(self, timeout: float = 5.0) -> None:
        """停止处理循环"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            logger.info("重试引擎已停止")

    def process_loop(self) -> int:
        """
        手动触发一次处理循环（单次轮询）
        返回本次处理的任务数
        """
        return self._process_due_tasks()

    # ----- 内部方法 -----

    def _run_loop(self) -> None:
        """后台线程主循环"""
        while not self._stop_event.is_set():
            try:
                processed = self._process_due_tasks()
                if processed:
                    logger.debug(f"重试引擎本轮处理了 {processed} 个任务")
            except Exception:
                logger.exception("重试引擎处理循环异常")
            # 等待下一次轮询
            self._stop_event.wait(self._poll_interval)

    def _process_due_tasks(self) -> int:
        """
        查找所有到期的 pending 任务，依次处理
        返回处理的任务数
        """
        now = time.time()
        tasks = self._fetch_pending(now)
        count = 0
        for row in tasks:
            try:
                self._execute_task(dict(row))
                count += 1
            except Exception:
                logger.exception(f"处理重试任务异常: task_id={row.get('task_id', '')}")
        return count

    def _fetch_pending(self, now: float) -> list:
        """查询已到期的 pending 任务"""
        conn = _get_conn()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM retry_tasks
                WHERE status = 'pending' AND next_run_at <= ?
                ORDER BY next_run_at ASC
                LIMIT 50
                """,
                (now,),
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def _execute_task(self, task: dict) -> None:
        """执行单个重试任务：标记为 processing → 发送请求 → 更新状态"""
        task_id = task["task_id"]
        target_url = task["target_url"]
        payload_raw = task["payload"]
        attempt = task["attempt"]
        max_retries = task["max_retries"]

        # 标记 processing
        self._update_status(task_id, "processing")

        success = False
        error_msg = ""

        try:
            data = payload_raw.encode("utf-8") if isinstance(payload_raw, str) else payload_raw
            req = urllib_request.Request(
                target_url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "liankebao-retry-engine/1.0",
                },
                method="POST",
            )
            resp = urllib_request.urlopen(req, timeout=30)
            status_code = resp.getcode()

            if 200 <= status_code < 300:
                success = True
                logger.info(f"重试成功: task_id={task_id}, status={status_code}")
            else:
                error_msg = f"HTTP {status_code}"
                logger.warning(f"重试返回非2xx: task_id={task_id}, status={status_code}")
        except URLError as e:
            error_msg = f"网络错误: {e.reason}"
            logger.warning(f"重试网络错误: task_id={task_id}, error={error_msg}")
        except Exception as e:
            error_msg = str(e)[:500]
            logger.warning(f"重试异常: task_id={task_id}, error={error_msg}")

        if success:
            self._update_status(task_id, "completed")
            return

        # 失败：更新尝试次数
        new_attempt = attempt + 1
        last_error = error_msg

        if new_attempt >= max_retries:
            # 超过上限 → 死信
            self._update_status(task_id, "dead", attempt=new_attempt, last_error=last_error)
            logger.warning(f"任务超过重试上限，进入死信: task_id={task_id}, attempts={new_attempt}")
        else:
            # 计算退避时间
            next_run = self._backoff(new_attempt)
            self._update_status(
                task_id,
                "pending",
                attempt=new_attempt,
                next_run_at=next_run,
                last_error=last_error,
            )
            logger.info(
                f"任务将在下次重试: task_id={task_id}, attempt={new_attempt}/{max_retries}, next_run_at={next_run}"
            )

    def _backoff(self, attempt: int) -> float:
        """
        指数退避计算
        公式: 2^(attempt-1) * 60 秒
        封顶: 30 分钟 (1800 秒)
        """
        delay = (2 ** (attempt - 1)) * 60
        delay = min(delay, 1800)  # 封顶 30 分钟
        return time.time() + delay

    def _update_status(
        self,
        task_id: str,
        status: str,
        attempt: int | None = None,
        next_run_at: float | None = None,
        last_error: str = "",
    ) -> None:
        """更新任务状态"""
        conn = _get_conn()
        try:
            fields = ["status = ?"]
            values: list = [status]
            if attempt is not None:
                fields.append("attempt = ?")
                values.append(attempt)
            if next_run_at is not None:
                fields.append("next_run_at = ?")
                values.append(next_run_at)
            if last_error:
                fields.append("last_error = ?")
                values.append(last_error)

            values.append(task_id)
            sql = f"UPDATE retry_tasks SET {', '.join(fields)} WHERE task_id = ?"
            conn.execute(sql, values)
            conn.commit()
        finally:
            conn.close()


# ============================================================
# DeadLetterManager — 死信管理器
# ============================================================


class DeadLetterManager:
    """
    死信队列管理

    用法:
        dlm = DeadLetterManager()
        letters = dlm.get_dead_letters()
        dlm.replay(task_id="xxx")
        stats = dlm.stats()
    """

    def __init__(self):
        _init_table()

    def get_dead_letters(self, limit: int = 100, offset: int = 0) -> list:
        """
        查询死信队列

        Returns:
            list[dict]: 死信任务列表
        """
        conn = _get_conn()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM retry_tasks
                WHERE status = 'dead'
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def replay(self, task_id: str) -> str:
        """
        人工重放死信任务
        将指定死信任务状态重置为 pending，清空尝试次数

        Args:
            task_id: 任务 ID

        Returns:
            task_id: 任务 ID

        Raises:
            ValueError: 任务不存在或不是死信状态
        """
        conn = _get_conn()
        try:
            cursor = conn.execute(
                "SELECT * FROM retry_tasks WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"任务不存在: {task_id}")
            task = dict(row)
            if task["status"] != "dead":
                raise ValueError(f"任务状态不是 dead (当前: {task['status']}): {task_id}")

            conn.execute(
                """
                UPDATE retry_tasks
                SET status = 'pending', attempt = 0, next_run_at = ?, last_error = ''
                WHERE task_id = ?
                """,
                (time.time(), task_id),
            )
            conn.commit()
            logger.info(f"死信任务已重放: task_id={task_id}")
            return task_id
        finally:
            conn.close()

    def stats(self) -> dict:
        """
        返回统计信息

        Returns:
            dict: {total, pending, processing, completed, dead}
        """
        conn = _get_conn()
        try:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) AS processing,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN status = 'dead' THEN 1 ELSE 0 END) AS dead,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
                FROM retry_tasks
                """
            )
            row = cursor.fetchone()
            result = dict(row)
            # 将 None 转 0
            return {k: (v if v is not None else 0) for k, v in result.items()}
        finally:
            conn.close()

    def replay_all(self) -> int:
        """
        重放所有死信任务

        Returns:
            int: 重放的任务数
        """
        conn = _get_conn()
        try:
            now = time.time()
            cursor = conn.execute(
                """
                UPDATE retry_tasks
                SET status = 'pending', attempt = 0, next_run_at = ?, last_error = ''
                WHERE status = 'dead'
                """,
                (now,),
            )
            conn.commit()
            count = cursor.rowcount
            logger.info(f"死信任务批量重放: {count} 个")
            return count
        finally:
            conn.close()


# ============================================================
# 便捷函数：创建全局单例
# ============================================================

_engine_instance: RetryEngine | None = None
_dlm_instance: DeadLetterManager | None = None


def get_retry_engine() -> RetryEngine:
    """获取全局 RetryEngine 单例"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = RetryEngine()
    return _engine_instance


def get_dead_letter_manager() -> DeadLetterManager:
    """获取全局 DeadLetterManager 单例"""
    global _dlm_instance
    if _dlm_instance is None:
        _dlm_instance = DeadLetterManager()
    return _dlm_instance
