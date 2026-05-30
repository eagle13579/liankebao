#!/usr/bin/env python3
"""
检疫区管理器 (Quarantine Manager)
参照数据安全架构v1.0文档第5章

核心职责：
  1. 数据写入检疫区隔离，防止污染真实数据
  2. 严格审批流程：数据须通过二次契约验证+完全消毒才能放行
  3. 超时自动升级机制：4h通知 → 8h升级Owner → 24h自动放行(宽松校验)
  4. 修复致命缺陷#2：删除旧版auto_resolve规则4（消毒通过就放行→自循环逃逸）

依赖：仅使用Python标准库 (sqlite3替代PostgreSQL, 生产环境应切换至psycopg2)
"""

import json
import sqlite3
import sys
import time
import threading
import os
import datetime
import uuid
from typing import Optional, List, Dict, Any

# ============================================================================
# 通知接口 — 可扩展为Webhook/Slack/邮件
# ============================================================================
_NOTIFY_HANDLERS = []


def register_notify_handler(fn):
    """注册外部通知处理器，fn(level, title, message)"""
    _NOTIFY_HANDLERS.append(fn)


def _notify(level: str, title: str, message: str):
    """
    通知核心：先打印到stderr，再调用已注册的处理器。
    level: 'info' | 'warning' | 'critical'
    """
    timestamp = datetime.datetime.now().isoformat()
    line = f"[{timestamp}] [{level.upper()}] {title}: {message}"
    print(line, file=sys.stderr, flush=True)
    for handler in _NOTIFY_HANDLERS:
        try:
            handler(level, title, message)
        except Exception as exc:
            print(
                f"[notify_handler_error] {exc}", file=sys.stderr, flush=True
            )


# ============================================================================
# 数据消毒与契约验证（模拟5步完整校验）
# ============================================================================

def _step1_schema_validation(payload: dict, target_schema: str, target_table: str) -> List[str]:
    """
    步骤1：模式/契约验证 — 检查payload字段是否匹配目标表预期结构。
    生产环境应查询契约注册表获取schema定义。
    返回错误列表（空列表=通过）。
    """
    errors = []
    # 模拟检查：payload必须是dict且包含必要字段
    if not isinstance(payload, dict):
        errors.append(f"payload必须是dict类型，收到{type(payload).__name__}")
        return errors
    # 检查保留字段（生产环境应从目标表schema定义中读取）
    required_fields = {"id", "data"}
    if not required_fields.intersection(payload.keys()):
        errors.append(f"payload缺少必要字段（至少需要id和data之一）")
    # 字段名不能包含危险字符
    for key in payload.keys():
        if not isinstance(key, str) or any(c in key for c in ";\n\r"):
            errors.append(f"字段名包含非法字符: {key!r}")
    return errors


def _step2_data_type_validation(payload: dict) -> List[str]:
    """步骤2：数据类型校验 — 检查可序列化与类型安全。"""
    errors = []
    for key, val in payload.items():
        if isinstance(val, (bytes, bytearray)):
            errors.append(f"字段{key!r}不能为bytes类型")
        if isinstance(val, str) and len(val) > 100000:
            errors.append(f"字段{key!r}字符串超长({len(val)}字符)")
    return errors


def _step3_range_constraint_validation(payload: dict) -> List[str]:
    """步骤3：范围/约束校验 — 检查数值范围与长度限制。"""
    errors = []
    for key, val in payload.items():
        if isinstance(val, (int, float)):
            # 防止极端数值
            if abs(val) > 1e18:
                errors.append(f"字段{key!r}数值超出安全范围({val})")
        if isinstance(val, str) and len(val) > 50000:
            errors.append(f"字段{key!r}字符串超长({len(val)}字符)")
    return errors


def _step4_disinfection(payload: dict) -> tuple:
    """
    步骤4：消毒/净化 — 去除XSS、SQL注入等危险载荷。
    返回 (cleaned_payload, issues) 元组。
    """
    cleaned = {}
    issues = []
    dangerous_patterns = [
        ("<script", "XSS脚本标签"),
        ("javascript:", "XSS伪协议"),
        ("onerror=", "事件处理器"),
        ("onload=", "事件处理器"),
        ("--", "SQL注释"),
        ("';", "SQL注入"),
        ("/*", "SQL注释开始"),
        ("*/", "SQL注释结束"),
        ("DROP TABLE", "SQL风险关键词"),
        ("DELETE FROM", "SQL风险关键词"),
        ("xp_cmdshell", "危险存储过程"),
        ("../", "路径遍历"),
    ]
    for key, val in payload.items():
        if isinstance(val, str):
            cleaned_val = val
            for pattern, desc in dangerous_patterns:
                if pattern.lower() in cleaned_val.lower():
                    # 替换危险模式
                    cleaned_val = cleaned_val.replace(pattern, "")
                    issues.append(
                        f"字段{key!r}已清除{desc}, 原始包含{pattern!r}"
                    )
            cleaned[key] = cleaned_val
        elif isinstance(val, dict):
            sub_val, sub_issues = _step4_disinfection(val)
            cleaned[key] = sub_val
            issues.extend(sub_issues)
        elif isinstance(val, list):
            cleaned_list = []
            for idx, item in enumerate(val):
                if isinstance(item, dict):
                    sub_val, sub_issues = _step4_disinfection(item)
                    cleaned_list.append(sub_val)
                    issues.extend(
                        [f"[{idx}] {si}" for si in sub_issues]
                    )
                else:
                    cleaned_list.append(item)
            cleaned[key] = cleaned_list
        else:
            cleaned[key] = val
    return cleaned, issues


def _step5_security_policy_check(payload: dict) -> List[str]:
    """步骤5：安全策略检查 — 敏感数据泄露、不合规内容等。"""
    errors = []
    payload_str = json.dumps(payload, default=str).lower()
    sensitive_patterns = [
        ("password", "密码字段"),
        ("secret", "密钥字段"),
        ("token", "令牌字段"),
        ("ssn", "社保号"),
        ("credit_card", "信用卡号"),
        ("phone", "电话号码"),
        ("id_card", "身份证号"),
    ]
    for pattern, desc in sensitive_patterns:
        if pattern in payload_str:
            errors.append(f"检测到疑似{desc}({pattern})，需确认脱敏策略")
    return errors


def full_validation_5step(
    payload: dict, target_schema: str, target_table: str
) -> dict:
    """
    完整5步重新校验（不是只做消毒 — 修复缺陷#2的关键）：
      1. Schema/契约验证
      2. 数据类型验证
      3. 范围/约束验证
      4. 消毒净化
      5. 安全策略检查
    返回 {'passed': bool, 'errors': [], 'disinfection_warnings': [], 'cleaned_payload': dict}
    """
    result = {
        "passed": True,
        "errors": [],
        "disinfection_warnings": [],
        "cleaned_payload": payload,
    }

    # Step 1
    errs = _step1_schema_validation(payload, target_schema, target_table)
    if errs:
        result["errors"].extend(errs)
        result["passed"] = False

    # Step 2
    errs = _step2_data_type_validation(payload)
    if errs:
        result["errors"].extend(errs)
        result["passed"] = False

    # Step 3
    errs = _step3_range_constraint_validation(payload)
    if errs:
        result["errors"].extend(errs)
        result["passed"] = False

    # Step 4 — 消毒（即使有警告也不阻断，但必须记录）
    cleaned, issues = _step4_disinfection(payload)
    result["cleaned_payload"] = cleaned
    if issues:
        result["disinfection_warnings"] = issues
        # 注意：消毒警告≠阻断，但留痕

    # Step 5
    errs = _step5_security_policy_check(cleaned)
    if errs:
        result["errors"].extend(errs)
        result["passed"] = False

    return result


# ============================================================================
# 宽松校验（超24小时自动放行时使用）
# ============================================================================

def relaxed_validation_5step(
    payload: dict, target_schema: str, target_table: str
) -> dict:
    """
    宽松校验：仅做步骤1(schema)+步骤4(消毒)。
    用于超24小时自动放行场景，平衡安全与数据不阻塞。
    """
    result = {
        "passed": True,
        "errors": [],
        "disinfection_warnings": [],
        "cleaned_payload": payload,
    }

    # Step 1 — 仅检查基本契约
    errs = _step1_schema_validation(payload, target_schema, target_table)
    if errs:
        result["errors"].extend(errs)
        result["passed"] = False

    # Step 4 — 消毒必须做
    cleaned, issues = _step4_disinfection(payload)
    result["cleaned_payload"] = cleaned
    if issues:
        result["disinfection_warnings"] = issues

    return result


# ============================================================================
# 检疫区管理器主类
# ============================================================================

class QuarantineManager:
    """
    检疫区管理器 (Quarantine Manager)
    对接数据库，管理数据隔离、审批流转、超时升级。

    使用sqlite3作为后端（Python标准库兼容），生产环境应切换至psycopg2。
    PostgreSQL DDL见类末尾的SQL常量。
    """

    # ---- SQL 常量 ----
    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS quarantine_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        module TEXT NOT NULL,
        target_schema TEXT NOT NULL,
        target_table TEXT NOT NULL,
        operation TEXT NOT NULL CHECK(operation IN ('INSERT','UPDATE','DELETE')),
        payload TEXT NOT NULL,
        score REAL NOT NULL DEFAULT 0.0,
        reasons TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','approved','rejected','auto-approved')),
        reviewer TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        escalation_level INTEGER NOT NULL DEFAULT 0,
        last_notified_at TEXT,
        owner_escalated_at TEXT,
        rescan_count INTEGER NOT NULL DEFAULT 0
    );
    """

    # 生产环境PostgreSQL版本（供参考）
    PG_CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS quarantine_items (
        id SERIAL PRIMARY KEY,
        module VARCHAR(255) NOT NULL,
        target_schema VARCHAR(255) NOT NULL,
        target_table VARCHAR(255) NOT NULL,
        operation VARCHAR(10) NOT NULL CHECK(operation IN ('INSERT','UPDATE','DELETE')),
        payload JSONB NOT NULL,
        score REAL NOT NULL DEFAULT 0.0,
        reasons JSONB NOT NULL DEFAULT '[]',
        status VARCHAR(20) NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','approved','rejected','auto-approved')),
        reviewer VARCHAR(255),
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        resolved_at TIMESTAMP,
        escalation_level INTEGER NOT NULL DEFAULT 0,
        last_notified_at TIMESTAMP,
        owner_escalated_at TIMESTAMP,
        rescan_count INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_quarantine_status ON quarantine_items(status);
    CREATE INDEX IF NOT EXISTS idx_quarantine_module ON quarantine_items(module);
    CREATE INDEX IF NOT EXISTS idx_quarantine_created ON quarantine_items(created_at);
    """

    def __init__(self, db_url: str, start_escalator: bool = True):
        """
        初始化检疫区管理器。
        db_url: sqlite数据库文件路径（例: '/data/quarantine.db'）
                生产环境应传入PostgreSQL连接URL并使用psycopg2。
        start_escalator: 是否启动后台升级检查守护线程（测试时设为False）
        """
        self._db_url = db_url
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_url, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._init_db()
        # 启动后台升级检查线程（守护线程）
        self._escalate_thread_running = start_escalator
        if start_escalator:
            self._escalate_thread = threading.Thread(
                target=self._background_escalation_loop,
                daemon=True,
                name="quarantine-escalator",
            )
            self._escalate_thread.start()
        else:
            self._escalate_thread = None
        _notify("info", "QuarantineManager初始化", f"数据库: {db_url}")

    def _init_db(self):
        """初始化数据库表结构"""
        with self._lock:
            self._conn.execute(self.CREATE_TABLE_SQL)
            self._conn.commit()

    def close(self):
        """关闭数据库连接并停止后台线程"""
        self._escalate_thread_running = False
        self._conn.close()

    # ---- 内部工具方法 ----

    def _now(self) -> str:
        """返回ISO格式当前时间"""
        return datetime.datetime.now().isoformat()

    def _hours_since(self, iso_time: str) -> float:
        """计算从iso_time到现在的时差（小时）"""
        if not iso_time:
            return 0.0
        try:
            dt = datetime.datetime.fromisoformat(iso_time)
            delta = datetime.datetime.now() - dt
            return delta.total_seconds() / 3600.0
        except (ValueError, TypeError):
            return 0.0

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """将sqlite3.Row转为dict，并解析JSON字段（若存在）"""
        d = dict(row)
        if "payload" in d:
            try:
                d["payload"] = json.loads(d["payload"])
            except (json.JSONDecodeError, TypeError):
                pass
        if "reasons" in d:
            try:
                d["reasons"] = json.loads(d["reasons"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    def _fetchone(self, sql: str, params: tuple = ()) -> Optional[dict]:
        """查询单行并转为dict"""
        with self._lock:
            cur = self._conn.execute(sql, params)
            row = cur.fetchone()
            return self._row_to_dict(row) if row else None

    def _fetchall(self, sql: str, params: tuple = ()) -> List[dict]:
        """查询多行并转为dict列表"""
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [self._row_to_dict(row) for row in cur.fetchall()]

    def _execute(self, sql: str, params: tuple = ()) -> int:
        """执行写操作，返回受影响行数"""
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.rowcount

    # ---- 核心接口 ----

    def add(
        self,
        module: str,
        target_schema: str,
        target_table: str,
        operation: str,
        payload: dict,
        score: float,
        reasons: List[str],
    ) -> int:
        """
        写入检疫区，返回quarantine_id。

        参数:
            module: 来源模块名（如 'etl-user-import'）
            target_schema: 目标schema（如 'public'）
            target_table: 目标表名（如 'users'）
            operation: 操作类型 ('INSERT'|'UPDATE'|'DELETE')
            payload: 数据载荷（dict，存入时JSON序列化）
            score: 风险评分 0.0~1.0
            reasons: 风险原因列表

        返回:
            int: 新记录的quarantine_id
        """
        now = self._now()
        payload_json = json.dumps(payload, ensure_ascii=False)
        reasons_json = json.dumps(reasons, ensure_ascii=False)
        sql = """
        INSERT INTO quarantine_items
            (module, target_schema, target_table, operation,
             payload, score, reasons, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """
        params = (
            module, target_schema, target_table, operation,
            payload_json, score, reasons_json, now,
        )
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            qid = cur.lastrowid
        _notify(
            "info",
            f"检疫区新条目 [#{qid}]",
            f"module={module} table={target_schema}.{target_table} "
            f"op={operation} score={score}",
        )
        return qid

    def resolve(self, qid: int, action: str, reviewer: str = None) -> dict:
        """
        处理检疫区条目。

        参数:
            qid: 检疫区ID
            action: 'approve' | 'reject' | 'rescan'
            reviewer: 审批人标识

        返回:
            dict: {
                'success': bool,
                'status': str,
                'message': str,
                'qitem': dict or None
            }
        """
        qitem = self._fetchone(
            "SELECT * FROM quarantine_items WHERE id = ?", (qid,)
        )
        if not qitem:
            return {
                "success": False,
                "status": "not_found",
                "message": f"检疫区条目 #{qid} 不存在",
                "qitem": None,
            }

        if qitem["status"] != "pending":
            return {
                "success": False,
                "status": qitem["status"],
                "message": f"检疫区条目 #{qid} 已处理，当前状态: {qitem['status']}",
                "qitem": qitem,
            }

        now = self._now()

        if action == "approve":
            # ---- 审批通过：数据必须通过完整5步校验 ----
            validation = full_validation_5step(
                qitem["payload"],
                qitem["target_schema"],
                qitem["target_table"],
            )
            if not validation["passed"]:
                reason = "; ".join(validation["errors"])
                old_reasons = list(qitem.get("reasons", []))
                old_reasons.append(
                    f"审批驳回: 5步校验未通过 - {reason}"
                )
                self._execute(
                    "UPDATE quarantine_items SET status='rejected', "
                    "reviewer=?, resolved_at=?, reasons=? WHERE id=?",
                    (reviewer, now, json.dumps(old_reasons), qid),
                )
                _notify(
                    "warning",
                    f"检疫区审批驳回 [#{qid}]",
                    f"5步校验未通过: {reason}",
                )
                return {
                    "success": False,
                    "status": "rejected",
                    "message": f"5步校验未通过: {reason}",
                    "qitem": self._fetchone(
                        "SELECT * FROM quarantine_items WHERE id = ?",
                        (qid,),
                    ),
                }

            # 通过校验 → 写入真实表（此处模拟记录，生产环境应执行真实INSERT/UPDATE）
            # 修复缺陷#2：使用消毒后的数据写入
            cleaned = validation["cleaned_payload"]
            self._execute(
                "UPDATE quarantine_items SET status='approved', "
                "reviewer=?, resolved_at=?, payload=? WHERE id=?",
                (reviewer, now, json.dumps(cleaned), qid),
            )
            _notify(
                "info",
                f"检疫区审批通过 [#{qid}]",
                f"审批人={reviewer} 消毒警告={len(validation['disinfection_warnings'])}",
            )
            return {
                "success": True,
                "status": "approved",
                "message": "审批通过，数据已放行（使用消毒后payload写入真实表）",
                "qitem": self._fetchone(
                    "SELECT * FROM quarantine_items WHERE id = ?", (qid,)
                ),
            }

        elif action == "reject":
            # ---- 拒绝：记录并通知 ----
            old_reasons = qitem.get("reasons", [])
            if isinstance(old_reasons, list):
                old_reasons = old_reasons + [f"人工拒绝 (by {reviewer})"]
            else:
                old_reasons = [f"人工拒绝 (by {reviewer})"]
            self._execute(
                "UPDATE quarantine_items SET status='rejected', "
                "reviewer=?, resolved_at=?, reasons=? WHERE id=?",
                (reviewer, now, json.dumps(old_reasons), qid),
            )
            _notify(
                "warning",
                f"检疫区拒绝 [#{qid}]",
                f"审批人={reviewer}",
            )
            return {
                "success": True,
                "status": "rejected",
                "message": "已拒绝",
                "qitem": self._fetchone(
                    "SELECT * FROM quarantine_items WHERE id = ?", (qid,)
                ),
            }

        elif action == "rescan":
            # ---- 重新扫描：重置状态并增加重扫计数 ----
            rescan_count = (qitem.get("rescan_count") or 0) + 1
            self._execute(
                "UPDATE quarantine_items SET rescan_count=?, "
                "created_at=? WHERE id=?",
                (rescan_count, now, qid),
            )
            _notify(
                "info",
                f"检疫区重新扫描 [#{qid}]",
                f"第{rescan_count}次重扫",
            )
            return {
                "success": True,
                "status": "pending",
                "message": f"已重置为待处理（第{rescan_count}次重扫）",
                "qitem": self._fetchone(
                    "SELECT * FROM quarantine_items WHERE id = ?", (qid,)
                ),
            }

        else:
            return {
                "success": False,
                "status": "invalid_action",
                "message": f"未知操作: {action}，可选: approve|reject|rescan",
                "qitem": qitem,
            }

    def auto_resolve(self, qitem: dict) -> str:
        """
        新增的严格版自动规则（修复缺陷#2的核心）。

        规则概览：
          - 规则1：首次出现的高评分(>0.8) → 需人工审批，返回'pending'
          - 规则2：新模块(<7天)但评分>0.5 → 需人工审批，返回'pending'
          - 规则3：**已删除** 旧版规则4（消毒通过就放行 → 自循环逃逸）
          - 规则4：数据必须通过二次契约验证+完全消毒才能放行 → 返回'approve'
          - 不再有「消毒通过就自动放行」的路径

        参数:
            qitem: 检疫区条目的dict表示

        返回:
            str: 'approve' | 'pending' | 'reject'
        """
        score = qitem.get("score", 0.0)
        module = qitem.get("module", "unknown")
        reasons = qitem.get("reasons", [])
        payload = qitem.get("payload", {})
        target_schema = qitem.get("target_schema", "")
        target_table = qitem.get("target_table", "")

        # ================================================================
        # 规则1：首次出现的高评分(>0.8) → 需人工审批
        # ================================================================
        if score > 0.8:
            # 检查该模块是否有历史审批记录
            history = self._fetchall(
                "SELECT id FROM quarantine_items WHERE module=? "
                "AND status IN ('approved','rejected') LIMIT 5",
                (module,),
            )
            if not history:
                # 首次出现且高评分 — 必须人工
                _notify(
                    "warning",
                    f"auto_resolve [规则1] 需人工审批",
                    f"module={module} score={score} 首次出现高评分",
                )
                return "pending"

        # ================================================================
        # 规则2：新模块(<7天)但评分>0.5 → 需人工审批
        # ================================================================
        if score > 0.5:
            # 检查模块首次出现时间
            first_seen = self._fetchone(
                "SELECT MIN(created_at) as first_seen "
                "FROM quarantine_items WHERE module=?",
                (module,),
            )
            if first_seen and first_seen["first_seen"]:
                hours = self._hours_since(first_seen["first_seen"])
                days = hours / 24.0
                if days < 7.0:
                    _notify(
                        "warning",
                        f"auto_resolve [规则2] 需人工审批",
                        f"module={module} score={score} "
                        f"模块上线{days:.1f}天(<7天)",
                    )
                    return "pending"

        # ================================================================
        # 规则3：[已删除] 旧版规则4 — 不再存在「消毒通过就自动放行」
        # ================================================================

        # ================================================================
        # 规则4：数据必须通过二次契约验证+完全消毒才能放行
        # ================================================================
        validation = full_validation_5step(
            payload, target_schema, target_table
        )

        if not validation["passed"]:
            reason = "; ".join(validation["errors"])
            reasons.append(f"auto_resolve规则4未通过: {reason}")
            self._execute(
                "UPDATE quarantine_items SET reasons=? WHERE id=?",
                (json.dumps(reasons), qitem["id"]),
            )
            _notify(
                "warning",
                f"auto_resolve [规则4] 拒绝",
                f"id={qitem['id']} 二次契约验证未通过: {reason}",
            )
            return "reject"

        # 通过 — 在approve之前更新payload为消毒后数据
        cleaned = validation["cleaned_payload"]
        disinfection_warnings = validation["disinfection_warnings"]
        if disinfection_warnings:
            reasons.append(
                f"auto_resolve规则4: 消毒警告({len(disinfection_warnings)}条)"
            )
            for w in disinfection_warnings[:5]:  # 只记录前5条
                reasons.append(f"  消毒: {w}")

        self._execute(
            "UPDATE quarantine_items SET payload=?, reasons=? WHERE id=?",
            (json.dumps(cleaned), json.dumps(reasons), qitem["id"]),
        )

        return "approve"

    def get_pending(
        self,
        module: Optional[str] = None,
        older_than_hours: Optional[int] = None,
    ) -> List[dict]:
        """
        查询待处理队列。

        参数:
            module: 按模块名过滤（可选）
            older_than_hours: 只返回超过指定小时数的待处理条目（可选）

        返回:
            list[dict]: 检疫区条目列表
        """
        sql = "SELECT * FROM quarantine_items WHERE status='pending'"
        params = []

        if module:
            sql += " AND module=?"
            params.append(module)

        if older_than_hours is not None:
            # 筛选 created_at 超过 older_than_hours 的记录
            # 计算截止时间
            cutoff = (
                datetime.datetime.now()
                - datetime.timedelta(hours=older_than_hours)
            ).isoformat()
            sql += " AND created_at <= ?"
            params.append(cutoff)

        sql += " ORDER BY created_at ASC"
        return self._fetchall(sql, tuple(params))

    def get_stats(self) -> dict:
        """检疫区统计"""
        with self._lock:
            total = self._fetchone(
                "SELECT COUNT(*) as cnt FROM quarantine_items"
            )["cnt"]
            by_status = self._fetchall(
                "SELECT status, COUNT(*) as cnt "
                "FROM quarantine_items GROUP BY status"
            )
            pending_count = 0
            approved_count = 0
            rejected_count = 0
            auto_approved_count = 0
            for row in by_status:
                if row["status"] == "pending":
                    pending_count = row["cnt"]
                elif row["status"] == "approved":
                    approved_count = row["cnt"]
                elif row["status"] == "rejected":
                    rejected_count = row["cnt"]
                elif row["status"] == "auto-approved":
                    auto_approved_count = row["cnt"]

            # 按模块统计
            by_module = self._fetchall(
                "SELECT module, COUNT(*) as cnt "
                "FROM quarantine_items GROUP BY module ORDER BY cnt DESC"
            )

            # 平均等待时间（pending）
            avg_wait = self._fetchone(
                "SELECT AVG("
                "  CAST(julianday('now') AS REAL) - "
                "  CAST(julianday(created_at) AS REAL)"
                ") as avg_days FROM quarantine_items WHERE status='pending'"
            )
            avg_wait_hours = (
                (avg_wait["avg_days"] * 24.0)
                if avg_wait and avg_wait["avg_days"]
                else 0.0
            )

            # 升级中的条目
            escalated = self._fetchall(
                "SELECT id, module, escalation_level, "
                "created_at FROM quarantine_items "
                "WHERE status='pending' AND escalation_level > 0 "
                "ORDER BY escalation_level DESC"
            )

            return {
                "total": total,
                "pending": pending_count,
                "approved": approved_count,
                "rejected": rejected_count,
                "auto_approved": auto_approved_count,
                "by_module": {
                    row["module"]: row["cnt"] for row in by_module
                },
                "avg_wait_hours": round(avg_wait_hours, 2),
                "escalated_items": len(escalated),
                "escalation_details": [
                    {
                        "id": e["id"],
                        "module": e["module"],
                        "level": e["escalation_level"],
                        "created_at": e["created_at"],
                    }
                    for e in escalated
                ],
            }

    def auto_escalate(self):
        """
        超时自动升级与自动放行。

        规则：
          - 超过4小时未处理 → 自动通知值班人 (level 1)
          - 超过8小时未处理 → 升级到模块Owner (level 2)
          - 超过24小时未处理 → 自动放行（宽松校验）(level 3)
        """
        now = self._now()
        pending = self._fetchall(
            "SELECT * FROM quarantine_items WHERE status='pending'"
        )

        for item in pending:
            item_id = item["id"]
            module = item.get("module", "unknown")
            hours = self._hours_since(item["created_at"])
            current_level = item.get("escalation_level", 0)

            if hours >= 24.0 and current_level < 3:
                # ---- 超过24小时：自动放行（宽松校验） ----
                validation = relaxed_validation_5step(
                    item["payload"],
                    item["target_schema"],
                    item["target_table"],
                )
                if validation["passed"]:
                    cleaned = validation["cleaned_payload"]
                    self._execute(
                        "UPDATE quarantine_items SET "
                        "status='auto-approved', escalation_level=3, "
                        "resolved_at=?, reviewer='[system:auto_escalate]', "
                        "payload=? WHERE id=?",
                        (now, json.dumps(cleaned), item_id),
                    )
                    _notify(
                        "critical",
                        f"检疫区自动放行 [#{item_id}]",
                        f"超过24小时未处理, module={module}, "
                        f"消毒警告={len(validation['disinfection_warnings'])}",
                    )
                else:
                    # 宽松校验也未通过 — 不能放行，标记为拒绝
                    reason = "; ".join(validation["errors"])
                    self._execute(
                        "UPDATE quarantine_items SET "
                        "status='rejected', escalation_level=3, "
                        "resolved_at=?, reviewer='[system:auto_escalate:fail]', "
                        "reasons=? WHERE id=?",
                        (now, json.dumps(
                            item.get("reasons", [])
                            + [f"超24h自动放行失败: {reason}"]
                        ), item_id),
                    )
                    _notify(
                        "critical",
                        f"检疫区自动放行失败 [#{item_id}]",
                        f"超过24小时但宽松校验未通过: {reason}",
                    )

            elif hours >= 8.0 and current_level < 2:
                # ---- 超过8小时：升级到模块Owner ----
                self._execute(
                    "UPDATE quarantine_items SET "
                    "escalation_level=2, owner_escalated_at=? WHERE id=?",
                    (now, item_id),
                )
                _notify(
                    "critical",
                    f"检疫区升级到Owner [#{item_id}]",
                    f"超过8小时未处理, module={module}, "
                    f"请模块Owner立即处理",
                )

            elif hours >= 4.0 and current_level < 1:
                # ---- 超过4小时：通知值班人 ----
                self._execute(
                    "UPDATE quarantine_items SET "
                    "escalation_level=1, last_notified_at=? WHERE id=?",
                    (now, item_id),
                )
                _notify(
                    "warning",
                    f"检疫区超4h通知 [#{item_id}]",
                    f"超过4小时未处理, module={module}, "
                    f"请值班人处理",
                )

    def _background_escalation_loop(self, interval_seconds: int = 300):
        """
        后台线程：每5分钟运行一次auto_escalate。
        通过self._escalate_thread_running控制启停。
        """
        while self._escalate_thread_running:
            try:
                self.auto_escalate()
            except Exception as exc:
                _notify(
                    "warning",
                    "检疫区后台升级异常",
                    f"auto_escalate失败: {exc}",
                )
            for _ in range(interval_seconds):
                if not self._escalate_thread_running:
                    return
                time.sleep(1)


# ============================================================================
# 使用示例 / 入口
# ============================================================================

def demo():
    """
    快速演示检疫区管理器的核心功能。
    运行: python quarantine_manager.py
    """
    import tempfile

    db_path = os.path.join(tempfile.gettempdir(), "quarantine_demo.db")
    qm = QuarantineManager(db_path)

    # 1. 添加测试条目
    print("=== 添加检疫区条目 ===")
    qid1 = qm.add(
        module="etl-user-import",
        target_schema="public",
        target_table="users",
        operation="INSERT",
        payload={
            "id": 1001,
            "name": "张三",
            "email": "zhangsan@example.com",
            "bio": "<script>alert('xss')</script>Hello!",
        },
        score=0.85,
        reasons=["首次导入", "包含XSS关键词"],
    )
    print(f"条目1 ID: {qid1}")

    qid2 = qm.add(
        module="etl-order-sync",
        target_schema="public",
        target_table="orders",
        operation="UPDATE",
        payload={
            "id": 5001,
            "amount": 999.99,
            "note": "正常数据",
        },
        score=0.3,
        reasons=["低风险更新"],
    )
    print(f"条目2 ID: {qid2}")

    # 2. 测试auto_resolve
    print("\n=== 测试 auto_resolve ===")
    for qid in (qid1, qid2):
        item = qm._fetchone(
            "SELECT * FROM quarantine_items WHERE id=?", (qid,)
        )
        if item:
            result = qm.auto_resolve(item)
            print(f"条目#{qid} auto_resolve -> {result}")

    # 3. 查询待处理
    print("\n=== 待处理队列 ===")
    pending = qm.get_pending()
    print(f"待处理: {len(pending)} 条")
    for p in pending:
        print(f"  #{p['id']} module={p['module']} score={p['score']}")

    # 4. 测试resolve
    print("\n=== 测试 resolve ===")
    # 找到仍为pending的条目
    for p in pending:
        r = qm.resolve(p["id"], action="approve", reviewer="admin")
        print(f"  resolve #{p['id']} -> success={r['success']} status={r['status']}")

    # 5. 统计
    print("\n=== 检疫区统计 ===")
    stats = qm.get_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # 清理
    qm.close()
    os.unlink(db_path)
    print("\n演示完成。")


if __name__ == "__main__":
    demo()
