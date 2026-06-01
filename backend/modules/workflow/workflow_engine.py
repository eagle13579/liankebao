"""
链客宝工作流自动化引擎 (workflow_engine.py)

轻量级工作流引擎，零外部依赖，纯 Python + SQLite 实现。

功能:
  1. 触发器系统 (事件/定时/条件)
  2. 动作系统 (通知/活动/Deal阶段/跟进/分配)
  3. Rule 配置 (YAML)
  4. 种子规则

架构:
  - 引擎使用自己的 SQLite 数据库 (workflow.db) 存储规则和执行记录
  - 通过 SQLAlchemy 与现有链客宝数据模型集成 (Activity, Deal, Order, User 等)
  - NotificationService 管理站内通知 (独立 SQLite)
"""
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
#  常量
# ────────────────────────────────────────────────────────────────

TRIGGER_TYPES = {"event", "schedule", "condition"}
EVENT_TRIGGERS = {
    "on_deal_created",
    "on_deal_stage_changed",
    "on_contact_added",
    "on_order_paid",
    "on_activity_logged",
    "on_product_created",
}
ACTION_TYPES = {
    "create_notification",
    "create_activity",
    "update_deal_stage",
    "send_followup_reminder",
    "assign_task",
    "notify_promoters",
}
DEAL_STAGES = [
    "qualification",
    "meeting",
    "proposal",
    "negotiation",
    "closed_won",
    "closed_lost",
]

# ────────────────────────────────────────────────────────────────
#  异常
# ────────────────────────────────────────────────────────────────


class WorkflowError(Exception):
    """工作流引擎异常基类"""


class RuleNotFoundError(WorkflowError):
    """规则未找到"""


class TriggerError(WorkflowError):
    """触发器错误"""


class ActionError(WorkflowError):
    """动作执行错误"""


# ────────────────────────────────────────────────────────────────
#  WorkflowEngine
# ────────────────────────────────────────────────────────────────


class WorkflowEngine:
    """工作流自动化引擎

    管理规则的加载、评估和执行。
    使用独立的 SQLite 数据库存储引擎状态。
    """

    def __init__(
        self,
        rules_dir: str | None = None,
        db_path: str | None = None,
        notification_service=None,
    ):
        # 规则目录
        if rules_dir is None:
            rules_dir = os.path.join(os.path.dirname(__file__), "rules")
        self.rules_dir = rules_dir

        # 引擎数据库
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "workflow.db")
        self._db_path = db_path

        # 通知服务
        self._notifier = notification_service
        self._local = threading.local()

        # 已加载的规则 (name -> rule dict)
        self._rules: dict[str, dict] = {}

        # 动作注册表: action_type -> callable
        self._action_handlers: dict[str, Callable] = {}
        self._register_default_actions()

        # 数据库初始化
        self._init_db()

    # ── 数据库管理 ───────────────────────────────────────────

    @property
    def _conn(self) -> sqlite3.Connection:
        """线程本地连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            -- 规则定义表（同步 YAML 规则）
            CREATE TABLE IF NOT EXISTS workflow_rules (
                name TEXT PRIMARY KEY,
                description TEXT,
                config TEXT NOT NULL,        -- JSON: 完整规则配置
                enabled INTEGER DEFAULT 1,
                source TEXT DEFAULT 'yaml',   -- yaml / api
                loaded_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            -- 执行记录表
            CREATE TABLE IF NOT EXISTS workflow_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_name TEXT NOT NULL,
                trigger_type TEXT NOT NULL,
                trigger_source TEXT,
                status TEXT DEFAULT 'pending',  -- pending/success/failed
                result TEXT,                     -- JSON 执行结果
                error TEXT,
                executed_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_exec_rule
                ON workflow_executions(rule_name, executed_at DESC);

            -- 定时触发器状态
            CREATE TABLE IF NOT EXISTS workflow_schedules (
                rule_name TEXT PRIMARY KEY,
                cron_expr TEXT NOT NULL,
                last_run TEXT,
                next_run TEXT,
                FOREIGN KEY (rule_name) REFERENCES workflow_rules(name)
            );

            -- 条件触发器状态（用于追踪"在阶段停留时间"等）
            CREATE TABLE IF NOT EXISTS workflow_conditions (
                rule_name TEXT,
                entity_type TEXT,
                entity_id INTEGER,
                condition_key TEXT,
                condition_value TEXT,
                entered_at TEXT,
                last_checked TEXT,
                PRIMARY KEY (rule_name, entity_type, entity_id, condition_key)
            );

            -- 事件表（记录引擎处理过的事件）
            CREATE TABLE IF NOT EXISTS workflow_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                entity_type TEXT,
                entity_id INTEGER,
                payload TEXT,
                processed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_wevent_type
                ON workflow_events(event_type, processed, created_at DESC);
        """)
        conn.commit()
        conn.close()

    # ── 通知服务 ──────────────────────────────────────────────

    @property
    def notifier(self):
        if self._notifier is None:
            from modules.workflow.notifications import NotificationService

            self._notifier = NotificationService()
        return self._notifier

    # ── 规则加载 ──────────────────────────────────────────────

    def load_rules(self, reload: bool = False):
        """从 rules/ 目录加载所有 YAML 规则

        Args:
            reload: 是否重新加载已禁用的规则
        """
        import yaml

        if not os.path.isdir(self.rules_dir):
            os.makedirs(self.rules_dir, exist_ok=True)
            logger.info("规则目录已创建: %s", self.rules_dir)
            return

        loaded = 0
        for fname in sorted(os.listdir(self.rules_dir)):
            if not fname.endswith((".yaml", ".yml")):
                continue
            fpath = os.path.join(self.rules_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    rule = yaml.safe_load(f)
                if not rule or not isinstance(rule, dict):
                    logger.warning("跳过无效规则文件: %s", fname)
                    continue
                name = rule.get("name")
                if not name:
                    logger.warning("规则文件缺少 name: %s", fname)
                    continue
                self._rules[name] = rule
                self._sync_rule_to_db(name, rule)
                logger.info("规则加载: %s (%s)", name, fname)
                loaded += 1
            except Exception as e:
                logger.error("规则文件解析失败 %s: %s", fname, e)

        logger.info("规则加载完成: 共 %d 条", loaded)

    def _sync_rule_to_db(self, name: str, rule: dict):
        """将规则同步到数据库"""
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self._conn.execute(
            """
            INSERT INTO workflow_rules (name, description, config, enabled, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                config=excluded.config,
                enabled=excluded.enabled,
                description=excluded.description,
                updated_at=excluded.updated_at
            """,
            (
                name,
                rule.get("description", ""),
                json.dumps(rule, ensure_ascii=False),
                1 if rule.get("enabled", True) else 0,
                now,
            ),
        )
        self._conn.commit()

    def get_rule(self, name: str) -> dict | None:
        """获取规则"""
        return self._rules.get(name)

    def get_all_rules(self) -> list[dict]:
        """获取所有已加载规则"""
        return list(self._rules.values())

    def enable_rule(self, name: str, enabled: bool = True) -> bool:
        """启用/禁用规则"""
        if name not in self._rules:
            raise RuleNotFoundError(f"规则 '{name}' 不存在")
        self._rules[name]["enabled"] = enabled
        self._conn.execute(
            "UPDATE workflow_rules SET enabled = ?, updated_at = datetime('now', 'localtime') WHERE name = ?",
            (1 if enabled else 0, name),
        )
        self._conn.commit()
        return True

    # ── 动作注册 ──────────────────────────────────────────────

    def register_action(self, action_type: str, handler: Callable):
        """注册自定义动作处理器"""
        self._action_handlers[action_type] = handler

    def _register_default_actions(self):
        """注册默认动作处理器"""
        self._action_handlers = {
            "create_notification": self._action_create_notification,
            "create_activity": self._action_create_activity,
            "update_deal_stage": self._action_update_deal_stage,
            "send_followup_reminder": self._action_send_followup_reminder,
            "assign_task": self._action_assign_task,
            "notify_promoters": self._action_notify_promoters,
        }

    # ── 默认动作实现 ─────────────────────────────────────────

    def _action_create_notification(self, params: dict, context: dict) -> dict:
        """创建站内通知"""
        user_id = self._resolve_template(params.get("user_id", ""), context)
        title = self._resolve_template(params.get("title", ""), context)
        content = self._resolve_template(params.get("content", ""), context)
        ntype = params.get("notification_type", "info")
        ref_type = params.get("reference_type")
        ref_id = self._resolve_template(str(params.get("reference_id", "")), context) if params.get("reference_id") else None

        if not user_id:
            return {"status": "error", "message": "缺少 user_id"}
        if not title:
            return {"status": "error", "message": "缺少 title"}

        try:
            nid = self.notifier.send(
                user_id=int(user_id),
                title=title,
                content=content,
                notification_type=ntype,
                reference_type=ref_type,
                reference_id=int(ref_id) if ref_id and ref_id.isdigit() else None,
            )
            return {"status": "ok", "notification_id": nid}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _action_create_activity(self, params: dict, context: dict) -> dict:
        """创建活动日志 (使用原始SQL, 避免SQLAlchemy模型加载问题)"""
        action_type = params.get("action_type", "note")
        summary = self._resolve_template(params.get("summary", ""), context)
        detail = self._resolve_template(params.get("detail", ""), context)
        owner_id = self._resolve_template(str(params.get("owner_id", "")), context)
        contact_id = self._resolve_template(str(params.get("contact_id", "")), context)

        if not owner_id:
            return {"status": "error", "message": "缺少 owner_id"}

        # 使用原始 SQLite 写入 activities 表
        # 这样可以避免 SQLAlchemy mapper 初始化问题
        db_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data",
        )
        db_path = os.path.join(db_dir, "chainke.db")

        if not os.path.exists(db_path):
            return {"status": "error", "message": f"数据库不存在: {db_path}"}

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                """
                INSERT INTO activities (contact_id, action_type, summary, detail, owner_id, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    int(contact_id) if contact_id and contact_id.isdigit() else 0,
                    action_type,
                    summary or "",
                    detail or "",
                    int(owner_id),
                ),
            )
            conn.commit()
            activity_id = cursor.lastrowid
            conn.close()
            return {"status": "ok", "activity_id": activity_id}
        except sqlite3.OperationalError as e:
            # 表可能不存在, 使用 SQLAlchemy 作为后备
            try:
                from app.database import SessionLocal
                db = SessionLocal()
                try:
                    # 使用无关系版插入
                    stmt = """
                        INSERT INTO activities (contact_id, action_type, summary, detail, owner_id, created_at)
                        VALUES (?, ?, ?, ?, ?, datetime('now'))
                    """
                    db.execute(stmt, (
                        int(contact_id) if contact_id and contact_id.isdigit() else 0,
                        action_type,
                        summary or "",
                        detail or "",
                        int(owner_id),
                    ))
                    db.commit()
                    return {"status": "ok", "activity_id": 0}
                finally:
                    db.close()
            except Exception as e2:
                return {"status": "error", "message": f"创建活动失败: {e2}"}

    def _action_update_deal_stage(self, params: dict, context: dict) -> dict:
        """更新Deal阶段 (使用原始SQL)"""
        deal_id = self._resolve_template(str(params.get("deal_id", "")), context)
        new_stage = self._resolve_template(params.get("stage", ""), context)

        if not deal_id or not new_stage:
            return {"status": "error", "message": "缺少 deal_id 或 stage"}
        if new_stage not in DEAL_STAGES:
            return {"status": "error", "message": f"无效阶段: {new_stage}"}

        try:
            db_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "data",
            )
            db_path = os.path.join(db_dir, "chainke.db")

            if not os.path.exists(db_path):
                return {"status": "error", "message": f"数据库不存在: {db_path}"}

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            # 查询当前阶段
            row = conn.execute("SELECT stage FROM deals WHERE id=?", (deal_id,)).fetchone()
            if not row:
                conn.close()
                return {"status": "error", "message": f"Deal {deal_id} 不存在"}
            old_stage = row["stage"]

            # 更新阶段
            conn.execute(
                "UPDATE deals SET stage=?, stage_entered_at=datetime('now','localtime') WHERE id=?",
                (new_stage, deal_id),
            )
            conn.commit()
            conn.close()

            # 触发 stage_changed 事件
            self._fire_event(
                "on_deal_stage_changed",
                "deal",
                int(deal_id),
                {"deal_id": int(deal_id), "old_stage": old_stage, "new_stage": new_stage},
            )

            return {"status": "ok", "deal_id": int(deal_id), "old_stage": old_stage, "new_stage": new_stage}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _action_send_followup_reminder(self, params: dict, context: dict) -> dict:
        """发送跟进提醒 (创建通知 + 活动)"""
        deal_title = self._resolve_template(params.get("deal_title", ""), context) or context.get("deal", {}).get("title", "未知")
        owner_id = self._resolve_template(str(params.get("owner_id", "")), context) or str(context.get("deal", {}).get("owner_id", ""))
        contact_id = self._resolve_template(str(params.get("contact_id", "")), context) or str(context.get("deal", {}).get("contact_id", ""))

        if not owner_id:
            return {"status": "error", "message": "缺少 owner_id"}

        # 1. 创建通知
        notif_result = self._action_create_notification(
            {
                "user_id": owner_id,
                "title": "跟进提醒",
                "content": f"请及时跟进商机「{deal_title}」",
                "notification_type": "warning",
            },
            context,
        )

        # 2. 创建活动
        act_result = self._action_create_activity(
            {
                "action_type": "task",
                "summary": f"跟进提醒: {deal_title}",
                "detail": f"系统自动提醒: 商机「{deal_title}」需要跟进",
                "owner_id": owner_id,
                "contact_id": contact_id or "0",
            },
            context,
        )

        return {"status": "ok", "notification": notif_result, "activity": act_result}

    def _action_assign_task(self, params: dict, context: dict) -> dict:
        """自动分配任务给指定用户 (创建活动日志标记为任务)"""
        assignee_id = self._resolve_template(str(params.get("assignee_id", "")), context)
        task_title = self._resolve_template(params.get("title", ""), context)
        task_detail = self._resolve_template(params.get("detail", ""), context)
        contact_id = self._resolve_template(str(params.get("contact_id", "")), context) or "0"

        if not assignee_id:
            return {"status": "error", "message": "缺少 assignee_id"}
        if not task_title:
            return {"status": "error", "message": "缺少 title"}

        return self._action_create_activity(
            {
                "action_type": "task",
                "summary": task_title,
                "detail": task_detail,
                "owner_id": assignee_id,
                "contact_id": contact_id or "0",
            },
            context,
        )

    def _action_notify_promoters(self, params: dict, context: dict) -> dict:
        """通知所有推广员 (使用原始SQL)"""
        title = self._resolve_template(params.get("title", ""), context)
        content = self._resolve_template(params.get("content", ""), context)
        ref_type = params.get("reference_type")
        ref_id = self._resolve_template(str(params.get("reference_id", "")), context) if params.get("reference_id") else None

        if not title:
            return {"status": "error", "message": "缺少 title"}

        try:
            # 使用原始SQL查询推广员
            db_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "data",
            )
            db_path = os.path.join(db_dir, "chainke.db")

            if not os.path.exists(db_path):
                return {"status": "error", "message": f"数据库不存在: {db_path}"}

            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT id FROM users WHERE role='promoter' AND is_active=1"
            ).fetchall()
            conn.close()

            promoter_ids = [r[0] for r in rows]

            if not promoter_ids:
                return {"status": "ok", "message": "没有活跃的推广员", "notified_count": 0}

            ids = self.notifier.send_broadcast(
                promoter_ids,
                title=title,
                content=content,
                reference_type=ref_type,
                reference_id=int(ref_id) if ref_id and ref_id.isdigit() else None,
            )
            return {"status": "ok", "notified_count": len(ids), "notification_ids": ids}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ── 模板解析 ──────────────────────────────────────────────

    @staticmethod
    def _resolve_template(template: str, context: dict) -> str:
        """解析 Jinja-like 模板变量 {{ var }}

        支持嵌套属性如 {{ deal.title }}, {{ order.product.name }}
        """
        import re

        def _resolve(path: str) -> str:
            parts = path.split(".")
            obj = context
            for part in parts:
                if isinstance(obj, dict):
                    obj = obj.get(part, "")
                else:
                    try:
                        obj = getattr(obj, part, "")
                    except Exception:
                        return ""
                if obj is None:
                    return ""
            return str(obj) if not isinstance(obj, (dict, list)) else json.dumps(obj, ensure_ascii=False)

        def replacer(m):
            var_path = m.group(1).strip()
            return _resolve(var_path)

        return re.sub(r"\{\{\s*([^}]+)\s*\}\}", replacer, template)

    # ── 事件触发 ──────────────────────────────────────────────

    def fire_event(
        self,
        event_type: str,
        entity_type: str | None = None,
        entity_id: int | None = None,
        payload: dict | None = None,
    ) -> list[dict]:
        """外部调用的触发入口：触发一个事件并评估规则

        Args:
            event_type:  事件类型 (on_deal_created, on_order_paid 等)
            entity_type: 关联实体类型
            entity_id:   关联实体ID
            payload:     事件载荷数据

        Returns:
            匹配规则执行结果列表
        """
        # 记录事件
        self._log_event(event_type, entity_type, entity_id, payload)

        # 构建上下文
        context = self._build_context(entity_type, entity_id, payload)

        # 评估匹配的规则
        results = self._evaluate_rules(event_type, context)

        return results

    def _fire_event(self, event_type: str, entity_type: str, entity_id: int, payload: dict | None = None):
        """内部触发事件（链式触发）"""
        self.fire_event(event_type, entity_type, entity_id, payload)

    def _log_event(self, event_type: str, entity_type: str | None, entity_id: int | None, payload: dict | None):
        """记录事件到数据库"""
        self._conn.execute(
            """
            INSERT INTO workflow_events (event_type, entity_type, entity_id, payload)
            VALUES (?, ?, ?, ?)
            """,
            (event_type, entity_type, entity_id, json.dumps(payload, ensure_ascii=False) if payload else None),
        )
        self._conn.commit()

    def _build_context(self, entity_type: str | None, entity_id: int | None, payload: dict | None) -> dict:
        """构建规则评估上下文

        从数据库加载实体对象(使用原始SQL)并合并到上下文中。
        """
        context = {
            "event": {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "payload": payload or {},
            },
        }

        if payload:
            context.update(payload)

        # 尝试从数据库加载完整实体(使用原始SQL避免SQLAlchemy mapper问题)
        if entity_type and entity_id:
            try:
                db_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    "data",
                )
                db_path = os.path.join(db_dir, "chainke.db")
                if not os.path.exists(db_path):
                    return context

                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row

                if entity_type == "deal":
                    row = conn.execute("SELECT * FROM deals WHERE id=?", (entity_id,)).fetchone()
                    if row:
                        context["deal"] = dict(row)
                        # 计算阶段停留天数
                        if row["stage_entered_at"]:
                            try:
                                entered = datetime.strptime(row["stage_entered_at"], "%Y-%m-%d %H:%M:%S.%f")
                            except ValueError:
                                try:
                                    entered = datetime.strptime(row["stage_entered_at"], "%Y-%m-%d %H:%M:%S")
                                except ValueError:
                                    entered = datetime.utcnow()
                            delta = datetime.utcnow() - entered
                            context["deal"]["stage_duration_days"] = delta.days
                            context["deal"]["elapsed_hours"] = delta.total_seconds() / 3600

                elif entity_type == "order":
                    row = conn.execute("SELECT * FROM orders WHERE id=?", (entity_id,)).fetchone()
                    if row:
                        context["order"] = dict(row)

                elif entity_type == "contact":
                    row = conn.execute("SELECT * FROM contacts WHERE id=?", (entity_id,)).fetchone()
                    if row:
                        context["contact"] = dict(row)

                elif entity_type == "product":
                    row = conn.execute("SELECT * FROM products WHERE id=?", (entity_id,)).fetchone()
                    if row:
                        context["product"] = dict(row)

                conn.close()
            except Exception as e:
                logger.debug("构建上下文时加载实体 %s/%s 失败: %s", entity_type, entity_id, e)

        return context

    # ── 规则评估 ──────────────────────────────────────────────

    def _evaluate_rules(self, event_type: str, context: dict) -> list[dict]:
        """评估所有与事件匹配的规则并执行动作

        Args:
            event_type: 触发的事件类型
            context:    评估上下文

        Returns:
            执行结果列表
        """
        results = []
        for rule_name, rule in self._rules.items():
            if not rule.get("enabled", True):
                continue

            trigger = rule.get("trigger", {})
            trigger_type = trigger.get("type")

            # 1. 事件触发器匹配
            if trigger_type == "event":
                trigger_event = trigger.get("event")
                if trigger_event != event_type:
                    continue
            else:
                continue  # 定时/条件触发器由其他调度机制处理

            # 2. 条件评估
            conditions = rule.get("conditions", [])
            if conditions and not self._evaluate_conditions(conditions, context):
                logger.debug("规则 '%s' 条件未通过", rule_name)
                continue

            # 3. 执行动作
            action_results = self._execute_actions(rule.get("actions", []), context)

            # 4. 记录执行
            self._record_execution(
                rule_name=rule_name,
                trigger_type=trigger_type,
                trigger_source=trigger_event,
                status="success",
                result=action_results,
            )

            results.append({
                "rule": rule_name,
                "trigger": event_type,
                "actions": action_results,
            })

        return results

    def _evaluate_conditions(self, conditions: list[dict], context: dict) -> bool:
        """评估条件列表 (AND 逻辑)

        支持的操作符: ==, !=, >, >=, <, <=, in, contains
        """
        for cond in conditions:
            field = cond.get("field", "")
            operator = cond.get("operator", "==")
            value = cond.get("value")

            # 从上下文中获取字段值
            actual = self._resolve_template(f"{{{{ {field} }}}}", context)

            try:
                passed = self._compare(actual, operator, value)
            except Exception as e:
                logger.warning("条件评估失败: %s %s %s (%s)", field, operator, value, e)
                passed = False

            if not passed:
                return False

        return True

    @staticmethod
    def _compare(actual: Any, operator: str, expected: Any) -> bool:
        """比较两个值"""
        if actual is None:
            return False

        # 数值化比较
        try:
            a_num = float(actual)
            e_num = float(expected)
            use_numeric = True
        except (ValueError, TypeError):
            use_numeric = False

        if use_numeric:
            if operator == "==":
                return a_num == e_num
            elif operator == "!=":
                return a_num != e_num
            elif operator == ">":
                return a_num > e_num
            elif operator == ">=":
                return a_num >= e_num
            elif operator == "<":
                return a_num < e_num
            elif operator == "<=":
                return a_num <= e_num
        else:
            actual_str = str(actual)
            expected_str = str(expected)
            if operator == "==":
                return actual_str == expected_str
            elif operator == "!=":
                return actual_str != expected_str
            elif operator == "in":
                return expected_str in actual_str
            elif operator == "contains":
                return actual_str in expected_str

        return False

    # ── 动作执行 ──────────────────────────────────────────────

    def _execute_actions(self, actions: list[dict], context: dict) -> list[dict]:
        """执行动作列表

        Args:
            actions: 动作定义列表
            context: 执行上下文

        Returns:
            每个动作的执行结果
        """
        results = []
        for action in actions:
            action_type = action.get("type")
            params = action.get("params", {})

            handler = self._action_handlers.get(action_type)
            if not handler:
                results.append({
                    "type": action_type,
                    "status": "error",
                    "message": f"未知动作类型: {action_type}",
                })
                continue

            try:
                result = handler(params, context)
                results.append({
                    "type": action_type,
                    "status": result.get("status", "ok"),
                    "result": result,
                })
            except Exception as e:
                logger.exception("动作执行失败: %s", action_type)
                results.append({
                    "type": action_type,
                    "status": "error",
                    "message": str(e),
                })

        return results

    # ── 执行记录 ──────────────────────────────────────────────

    def _record_execution(
        self,
        rule_name: str,
        trigger_type: str,
        trigger_source: str | None,
        status: str,
        result: list[dict] | None = None,
        error: str | None = None,
    ):
        self._conn.execute(
            """
            INSERT INTO workflow_executions
                (rule_name, trigger_type, trigger_source, status, result, error)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                rule_name,
                trigger_type,
                trigger_source,
                status,
                json.dumps(result, ensure_ascii=False) if result else None,
                error,
            ),
        )
        self._conn.commit()

    # ── 查询接口 ──────────────────────────────────────────────

    def get_execution_history(
        self, rule_name: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        """查询执行历史"""
        query = "SELECT * FROM workflow_executions"
        params: list[Any] = []
        if rule_name:
            query += " WHERE rule_name = ?"
            params.append(rule_name)
        query += " ORDER BY executed_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_recent_events(self, limit: int = 50) -> list[dict]:
        """查询最近事件"""
        rows = self._conn.execute(
            "SELECT * FROM workflow_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── 定时触发器检查 ────────────────────────────────────────

    def check_scheduled_triggers(self):
        """检查并触发定时规则

        应在外部调度器中定期调用（例如每分钟/每小时）。
        """
        now = datetime.utcnow()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        for rule_name, rule in self._rules.items():
            if not rule.get("enabled", True):
                continue

            trigger = rule.get("trigger", {})
            if trigger.get("type") != "schedule":
                continue

            cron_expr = trigger.get("cron", "")
            if not cron_expr:
                continue

            parts = cron_expr.split()
            if len(parts) < 5:
                logger.warning("规则 '%s' cron表达式无效: %s", rule_name, cron_expr)
                continue

            # 简单的cron匹配 (minute hour day_of_month month day_of_week)
            match = self._match_cron(parts, now)
            if match:
                logger.info("触发定时规则: %s (cron: %s)", rule_name, cron_expr)
                context = {"event": {"type": "schedule", "cron": cron_expr, "time": now_str}}
                action_results = self._execute_actions(rule.get("actions", []), context)
                self._record_execution(
                    rule_name=rule_name,
                    trigger_type="schedule",
                    trigger_source=cron_expr,
                    status="success",
                    result=action_results,
                )

    @staticmethod
    def _match_cron(parts: list[str], dt: datetime) -> bool:
        """简单的cron表达式匹配

        parts: [minute, hour, day_of_month, month, day_of_week]
        """
        fields = [dt.minute, dt.hour, dt.day, dt.month, dt.weekday()]
        for i, (part, val) in enumerate(zip(parts, fields)):
            if part == "*":
                continue
            if "/" in part:
                base, step = part.split("/")
                step = int(step)
                if base == "*":
                    base_val = 0
                else:
                    base_val = int(base)
                if (val - base_val) % step != 0:
                    return False
            elif "," in part:
                if str(val) not in part.split(","):
                    return False
            elif "-" in part:
                low, high = part.split("-")
                if not (int(low) <= val <= int(high)):
                    return False
            else:
                if val != int(part):
                    return False
        return True

    # ── 条件触发器检查 ────────────────────────────────────────

    def check_conditional_triggers(self):
        """检查条件触发规则

        如 Deal 在 stage 停留 >7 天等。
        应在外部调度器中定期调用。
        """
        from app.database import SessionLocal
        from modules.workflow.models.deal import Deal

        for rule_name, rule in self._rules.items():
            if not rule.get("enabled", True):
                continue

            trigger = rule.get("trigger", {})
            if trigger.get("type") != "condition":
                continue

            # 构建上下文
            context = {"event": {"type": "condition", "rule": rule_name}}

            conditions = rule.get("conditions", [])
            if not conditions:
                continue

            # 检查是否为"Deal在stage停留>7天"类条件
            for cond in conditions:
                if cond.get("field") == "stage_duration_days" and cond.get("operator") in (">=", ">"):
                    threshold = int(cond.get("value", 0))
                    target_stage = None
                    # 查找 stage 条件
                    for c in conditions:
                        if c.get("field") == "stage" and c.get("operator") == "==":
                            target_stage = str(c.get("value", ""))

                    try:
                        db = SessionLocal()
                        try:
                            query = db.query(Deal)
                            if target_stage:
                                query = query.filter(Deal.stage == target_stage)
                            deals = query.all()

                            for deal in deals:
                                if deal.stage_entered_at:
                                    delta = datetime.utcnow() - deal.stage_entered_at
                                    if delta.days >= threshold:
                                        # 检查是否已处理过
                                        key = f"stage_duration_{deal.id}_{deal.stage}"
                                        row = self._conn.execute(
                                            "SELECT 1 FROM workflow_conditions WHERE rule_name=? AND entity_type='deal' "
                                            "AND entity_id=? AND condition_key=?",
                                            (rule_name, deal.id, key),
                                        ).fetchone()
                                        if row:
                                            continue  # 已处理

                                        # 构建deal上下文
                                        deal_ctx = {
                                            "deal": {
                                                "id": deal.id,
                                                "title": deal.title,
                                                "stage": deal.stage,
                                                "owner_id": deal.owner_id,
                                                "contact_id": deal.contact_id,
                                                "stage_duration_days": delta.days,
                                            }
                                        }
                                        context.update(deal_ctx)

                                        action_results = self._execute_actions(
                                            rule.get("actions", []), context
                                        )
                                        self._record_execution(
                                            rule_name=rule_name,
                                            trigger_type="condition",
                                            trigger_source=f"stage_duration>={threshold}d",
                                            status="success",
                                            result=action_results,
                                        )

                                        # 标记已处理
                                        self._conn.execute(
                                            """
                                            INSERT OR IGNORE INTO workflow_conditions
                                            (rule_name, entity_type, entity_id, condition_key, entered_at, last_checked)
                                            VALUES (?, 'deal', ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
                                            """,
                                            (rule_name, deal.id, key),
                                        )
                                        self._conn.commit()
                        finally:
                            db.close()
                    except Exception as e:
                        logger.exception("条件触发器检查失败: %s", rule_name)

    # ── 种子数据 ──────────────────────────────────────────────

    def seed_rules(self):
        """确保种子规则存在于 rules/ 目录"""
        seeds = {
            "seed_01_no_followup.yaml": {
                "name": "deal_no_followup_24h",
                "description": "新Deal创建后24小时未跟进 → 创建跟进提醒",
                "trigger": {"type": "event", "event": "on_deal_created"},
                "conditions": [{"field": "elapsed_hours", "operator": ">=", "value": 24}],
                "actions": [
                    {
                        "type": "create_activity",
                        "params": {
                            "action_type": "task",
                            "summary": "跟进提醒: Deal {{ deal.title }} 已创建24小时未跟进",
                            "detail": "商机 {{ deal.title }} (ID: {{ deal.id }}) 已创建超过24小时，请及时跟进。",
                            "owner_id": "{{ deal.owner_id }}",
                            "contact_id": "{{ deal.contact_id }}",
                        },
                    },
                    {
                        "type": "create_notification",
                        "params": {
                            "user_id": "{{ deal.owner_id }}",
                            "title": "跟进提醒",
                            "content": "商机「{{ deal.title }}」已创建24小时，请及时跟进。",
                            "notification_type": "warning",
                        },
                    },
                ],
                "enabled": True,
            },
            "seed_02_stale_deal.yaml": {
                "name": "deal_stale_qualification",
                "description": "Deal在qualification阶段>7天 → 提醒负责人",
                "trigger": {"type": "event", "event": "on_deal_stage_changed"},
                "conditions": [
                    {"field": "stage", "operator": "==", "value": "qualification"},
                    {"field": "stage_duration_days", "operator": ">=", "value": 7},
                ],
                "actions": [
                    {
                        "type": "create_notification",
                        "params": {
                            "user_id": "{{ deal.owner_id }}",
                            "title": "商机停滞提醒",
                            "content": "商机「{{ deal.title }}」在 qualification 阶段已超过7天，请尽快推进。",
                            "notification_type": "warning",
                            "reference_type": "deal",
                            "reference_id": "{{ deal.id }}",
                        },
                    }
                ],
                "enabled": True,
            },
            "seed_03_order_paid.yaml": {
                "name": "order_paid_log_activity",
                "description": "订单支付成功 → 创建活动日志",
                "trigger": {"type": "event", "event": "on_order_paid"},
                "conditions": [],
                "actions": [
                    {
                        "type": "create_activity",
                        "params": {
                            "action_type": "order",
                            "summary": "订单已支付: {{ order.order_no }}",
                            "detail": "订单 {{ order.order_no }} 已支付 ¥{{ order.total_price }}",
                            "owner_id": "{{ order.buyer_id }}",
                        },
                    },
                    {
                        "type": "create_notification",
                        "params": {
                            "user_id": "{{ order.buyer_id }}",
                            "title": "支付成功",
                            "content": "订单 {{ order.order_no }} 支付成功，金额 ¥{{ order.total_price }}",
                            "notification_type": "success",
                            "reference_type": "order",
                            "reference_id": "{{ order.id }}",
                        },
                    },
                ],
                "enabled": True,
            },
            "seed_04_new_product.yaml": {
                "name": "new_product_notify_promoters",
                "description": "新产品上架 → 通知相关推广员",
                "trigger": {"type": "event", "event": "on_product_created"},
                "conditions": [{"field": "product.status", "operator": "==", "value": "approved"}],
                "actions": [
                    {
                        "type": "notify_promoters",
                        "params": {
                            "title": "新产品上架",
                            "content": "新产品「{{ product.name }}」已上架，¥{{ product.price }}/件，欢迎推广！",
                            "category": "{{ product.category }}",
                            "reference_type": "product",
                            "reference_id": "{{ product.id }}",
                        },
                    },
                    {
                        "type": "create_activity",
                        "params": {
                            "action_type": "note",
                            "summary": "新产品上架通知已发送",
                            "detail": "产品 {{ product.name }} (ID: {{ product.id }}) 上架通知已推送给所有推广员",
                            "owner_id": "{{ product.owner_id }}",
                        },
                    },
                ],
                "enabled": True,
            },
        }

        os.makedirs(self.rules_dir, exist_ok=True)
        for fname, rule_data in seeds.items():
            fpath = os.path.join(self.rules_dir, fname)
            if not os.path.exists(fpath):
                import yaml
                with open(fpath, "w", encoding="utf-8") as f:
                    yaml.dump(rule_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
                logger.info("种子规则已创建: %s", fname)

    def __repr__(self) -> str:
        return f"<WorkflowEngine(rules_dir='{self.rules_dir}', rules_count={len(self._rules)})>"
