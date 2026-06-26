"""
链客宝工作流自动化引擎 — 单元测试
====================================
覆盖 WorkflowEngine 的核心功能: 规则加载、事件触发、条件评估、动作执行、
模板解析、cron 匹配、执行记录查询。

使用 SQLite 内存数据库作为引擎数据库，避免操作真实文件。

运行:
    pytest tests/test_workflow_engine.py -v
"""

import json
import os
import sys
import tempfile

import pytest

# 添加项目根目录到 path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from features.workflow.workflow_engine import (
    WorkflowEngine,
    WorkflowError,
    RuleNotFoundError,
    TriggerError,
    ActionError,
    TRIGGER_TYPES,
    EVENT_TRIGGERS,
    ACTION_TYPES,
    DEAL_STAGES,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def engine():
    """创建一个使用临时文件 SQLite 的 WorkflowEngine 实例"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        tmp_db_path = tmp_db.name
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as notif_db:
        notif_db_path = notif_db.name
    try:
        e = WorkflowEngine(
            rules_dir=tempfile.mkdtemp(),
            db_path=tmp_db_path,
        )
        # 重置通知服务也为临时文件db
        from features.workflow.notifications import NotificationService
        e._notifier = NotificationService(db_path=notif_db_path)
        yield e
    finally:
        try:
            os.unlink(tmp_db_path)
        except OSError:
            pass
        try:
            os.unlink(notif_db_path)
        except OSError:
            pass


# =========================================================================
# 测试: 初始化与数据库
# =========================================================================


class TestInitAndDb:
    """验证引擎初始化和数据库创建"""

    def test_engine_initialization(self, engine):
        """引擎初始化应成功创建所有表"""
        # 验证数据库连接
        conn = engine._conn
        assert conn is not None

        # 检查所有表是否存在
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [r[0] for r in tables]
        assert "workflow_rules" in table_names
        assert "workflow_executions" in table_names
        assert "workflow_schedules" in table_names
        assert "workflow_conditions" in table_names
        assert "workflow_events" in table_names

    def test_default_action_handlers(self, engine):
        """默认动作处理器应全部注册"""
        expected_actions = {
            "create_notification",
            "create_activity",
            "update_deal_stage",
            "send_followup_reminder",
            "assign_task",
            "notify_promoters",
        }
        assert set(engine._action_handlers.keys()) == expected_actions

    def test_constants_defined(self):
        """验证模块级常量定义正确"""
        assert "event" in TRIGGER_TYPES
        assert "schedule" in TRIGGER_TYPES
        assert "condition" in TRIGGER_TYPES
        assert "on_deal_created" in EVENT_TRIGGERS
        assert "on_deal_stage_changed" in EVENT_TRIGGERS
        assert "create_notification" in ACTION_TYPES
        assert "create_activity" in ACTION_TYPES
        assert "update_deal_stage" in ACTION_TYPES
        assert "qualification" in DEAL_STAGES
        assert "closed_won" in DEAL_STAGES
        assert "closed_lost" in DEAL_STAGES

    def test_repr(self, engine):
        """__repr__ 应包含引擎信息"""
        rep = repr(engine)
        assert "WorkflowEngine" in rep
        assert "rules_count" in rep


# =========================================================================
# 测试: 规则管理
# =========================================================================


class TestRuleManagement:
    """验证规则的加载、查询、启用/禁用"""

    def test_get_rule_nonexistent(self, engine):
        """查询不存在的规则应返回 None"""
        assert engine.get_rule("nonexistent_rule") is None

    def test_get_all_rules_empty(self, engine):
        """初始时已加载的规则应为空"""
        assert engine.get_all_rules() == []

    def test_enable_rule_not_found(self, engine):
        """启用不存在的规则应抛出 RuleNotFoundError"""
        with pytest.raises(RuleNotFoundError, match="nonexistent"):
            engine.enable_rule("nonexistent", enabled=True)

    def test_rule_lifecycle(self, engine):
        """规则的加载、查询、禁用、启用完整生命周期"""
        # 手动添加一条规则
        rule = {
            "name": "test_rule",
            "description": "测试规则",
            "trigger": {"type": "event", "event": "on_deal_created"},
            "conditions": [],
            "actions": [],
            "enabled": True,
        }
        engine._rules["test_rule"] = rule
        engine._sync_rule_to_db("test_rule", rule)

        # 查询
        assert engine.get_rule("test_rule") == rule
        assert "test_rule" in [r["name"] for r in engine.get_all_rules()]

        # 禁用
        engine.enable_rule("test_rule", enabled=False)
        assert engine._rules["test_rule"]["enabled"] is False
        db_row = engine._conn.execute(
            "SELECT enabled FROM workflow_rules WHERE name=?", ("test_rule",)
        ).fetchone()
        assert db_row["enabled"] == 0

        # 再次启用
        engine.enable_rule("test_rule", enabled=True)
        assert engine._rules["test_rule"]["enabled"] is True
        db_row = engine._conn.execute(
            "SELECT enabled FROM workflow_rules WHERE name=?", ("test_rule",)
        ).fetchone()
        assert db_row["enabled"] == 1

    def test_sync_rule_to_db_updates_existing(self, engine):
        """同步已存在的规则应更新而非重复插入"""
        rule = {
            "name": "update_test",
            "description": "初始描述",
            "trigger": {"type": "event", "event": "on_deal_created"},
            "actions": [],
            "enabled": True,
        }
        engine._sync_rule_to_db("update_test", rule)

        # 更新描述
        rule["description"] = "更新后的描述"
        engine._sync_rule_to_db("update_test", rule)

        rows = engine._conn.execute(
            "SELECT description FROM workflow_rules WHERE name=?", ("update_test",)
        ).fetchall()
        assert len(rows) == 1  # 不应有重复行
        assert rows[0]["description"] == "更新后的描述"


# =========================================================================
# 测试: 模板解析
# =========================================================================


class TestTemplateResolution:
    """验证 _resolve_template 的变量替换功能"""

    def test_simple_variable(self, engine):
        """简单变量替换"""
        result = engine._resolve_template("Hello {{ name }}", {"name": "World"})
        assert result == "Hello World"

    def test_nested_variable(self, engine):
        """嵌套属性访问"""
        result = engine._resolve_template(
            "{{ deal.title }} - {{ deal.owner_id }}",
            {"deal": {"title": "测试商机", "owner_id": 42}},
        )
        assert result == "测试商机 - 42"

    def test_missing_variable(self, engine):
        """不存在的变量应替换为空字符串"""
        result = engine._resolve_template("{{ missing }}", {})
        assert result == ""

    def test_no_template(self, engine):
        """不含模板变量的字符串应原样返回"""
        result = engine._resolve_template("纯文本字符串", {})
        assert result == "纯文本字符串"

    def test_multiple_variables(self, engine):
        """多个变量同时替换"""
        result = engine._resolve_template(
            "{{ a }}-{{ b }}-{{ c }}", {"a": "x", "b": "y", "c": "z"}
        )
        assert result == "x-y-z"

    def test_none_value(self, engine):
        """None 值应替换为空字符串"""
        result = engine._resolve_template("{{ val }}", {"val": None})
        assert result == ""

    def test_deep_nested(self, engine):
        """深层嵌套属性"""
        result = engine._resolve_template(
            "{{ order.product.name }}",
            {"order": {"product": {"name": "智能音箱"}}},
        )
        assert result == "智能音箱"


# =========================================================================
# 测试: 条件评估和比较
# =========================================================================


class TestConditionEvaluation:
    """验证条件评估和比较功能"""

    def test_compare_equal(self, engine):
        """== 比较"""
        assert engine._compare("5", "==", "5") is True
        assert engine._compare("5", "==", "6") is False

    def test_compare_not_equal(self, engine):
        """!= 比较"""
        assert engine._compare("5", "!=", "6") is True
        assert engine._compare("5", "!=", "5") is False

    def test_compare_greater_than(self, engine):
        """> 比较"""
        assert engine._compare("10", ">", "5") is True
        assert engine._compare("5", ">", "10") is False

    def test_compare_less_than(self, engine):
        """< 比较"""
        assert engine._compare("3", "<", "5") is True
        assert engine._compare("5", "<", "3") is False

    def test_compare_in(self, engine):
        """in 操作符：期望值是否在字符串值中"""
        assert engine._compare("hello world", "in", "world") is True
        assert engine._compare("hello", "in", "xyz") is False

    def test_compare_contains(self, engine):
        """contains 操作符：实际值是否包含期望值中"""
        assert engine._compare("world", "contains", "hello world") is True
        assert engine._compare("xyz", "contains", "hello") is False

    def test_evaluate_conditions_all_pass(self, engine):
        """所有条件都通过时应返回 True (AND 逻辑)"""
        conditions = [
            {"field": "deal.stage", "operator": "==", "value": "qualification"},
            {"field": "deal.owner_id", "operator": ">", "value": "0"},
        ]
        context = {"deal": {"stage": "qualification", "owner_id": 42}}
        assert engine._evaluate_conditions(conditions, context) is True

    def test_evaluate_conditions_one_fails(self, engine):
        """任一条件不通过时应返回 False"""
        conditions = [
            {"field": "deal.stage", "operator": "==", "value": "qualification"},
            {"field": "deal.owner_id", "operator": "==", "value": "999"},
        ]
        context = {"deal": {"stage": "qualification", "owner_id": 42}}
        assert engine._evaluate_conditions(conditions, context) is False

    def test_evaluate_conditions_empty(self, engine):
        """空条件列表应返回 True"""
        assert engine._evaluate_conditions([], {"deal": {}}) is True

    def test_compare_none_actual(self, engine):
        """actual 为 None 时应返回 False"""
        assert engine._compare(None, "==", "value") is False
        assert engine._compare(None, "!=", "value") is False


# =========================================================================
# 测试: 事件触发与规则评估
# =========================================================================


class TestEventTriggering:
    """验证事件触发和规则评估流程"""

    def test_fire_event_no_matching_rules(self, engine):
        """触发事件当没有匹配规则时应返回空列表"""
        results = engine.fire_event("on_deal_created", "deal", 1, {"title": "测试"})
        assert results == []

    def test_fire_event_matching_rule(self, engine):
        """触发事件应执行匹配的规则动作"""
        # 注册一个简单的动作处理器
        action_results = []

        def mock_action(params, context):
            action_results.append({"params": params, "context_keys": list(context.keys())})
            return {"status": "ok", "result": "done"}

        engine.register_action("mock_action", mock_action)

        # 添加匹配规则
        rule = {
            "name": "test_event_rule",
            "description": "测试事件规则",
            "trigger": {"type": "event", "event": "on_deal_created"},
            "conditions": [],
            "actions": [{"type": "mock_action", "params": {"msg": "hello"}}],
            "enabled": True,
        }
        engine._rules["test_event_rule"] = rule
        engine._sync_rule_to_db("test_event_rule", rule)

        results = engine.fire_event("on_deal_created", "deal", 42, {"title": "测试商机"})

        assert len(results) == 1
        assert results[0]["rule"] == "test_event_rule"
        assert results[0]["trigger"] == "on_deal_created"
        assert action_results[0]["params"]["msg"] == "hello"

    def test_fire_event_disabled_rule(self, engine):
        """禁用的规则不应被触发"""
        rule = {
            "name": "disabled_rule",
            "trigger": {"type": "event", "event": "on_deal_created"},
            "conditions": [],
            "actions": [],
            "enabled": False,
        }
        engine._rules["disabled_rule"] = rule
        engine._sync_rule_to_db("disabled_rule", rule)

        results = engine.fire_event("on_deal_created")
        assert len(results) == 0

    def test_fire_event_wrong_event_type(self, engine):
        """事件类型不匹配的规则不应被触发"""
        rule = {
            "name": "order_rule",
            "trigger": {"type": "event", "event": "on_order_paid"},
            "conditions": [],
            "actions": [],
            "enabled": True,
        }
        engine._rules["order_rule"] = rule
        engine._sync_rule_to_db("order_rule", rule)

        results = engine.fire_event("on_deal_created")
        assert len(results) == 0

    def test_event_logging(self, engine):
        """触发事件后应记录到 workflow_events 表"""
        engine.fire_event("on_deal_created", "deal", 1, {"key": "val"})
        events = engine.get_recent_events(limit=5)
        assert len(events) >= 1
        assert events[0]["event_type"] == "on_deal_created"
        assert events[0]["entity_type"] == "deal"
        assert events[0]["entity_id"] == 1

    def test_execution_recorded(self, engine):
        """规则执行后应有执行记录"""
        rule = {
            "name": "track_exec",
            "trigger": {"type": "event", "event": "on_contact_added"},
            "conditions": [],
            "actions": [],
            "enabled": True,
        }
        engine._rules["track_exec"] = rule
        engine._sync_rule_to_db("track_exec", rule)

        engine.fire_event("on_contact_added")
        history = engine.get_execution_history()
        assert len(history) >= 1
        assert history[0]["rule_name"] == "track_exec"
        assert history[0]["status"] == "success"


# =========================================================================
# 测试: 动作执行
# =========================================================================


class TestActionExecution:
    """验证动作的执行流程"""

    def test_unknown_action_type(self, engine):
        """未知动作类型应返回错误"""
        results = engine._execute_actions(
            [{"type": "unknown_action", "params": {}}],
            {},
        )
        assert len(results) == 1
        assert results[0]["status"] == "error"
        assert "未知动作类型" in results[0]["message"]

    def test_custom_action_handler(self, engine):
        """注册的自定义动作处理器应可正常调用"""

        def my_handler(params, context):
            return {"status": "ok", "value": params.get("x", 0) * 2}

        engine.register_action("double", my_handler)
        results = engine._execute_actions(
            [{"type": "double", "params": {"x": 21}}],
            {},
        )
        assert results[0]["status"] == "ok"
        assert results[0]["result"]["value"] == 42

    def test_action_handler_exception(self, engine):
        """动作处理器抛出异常时应被捕获并返回错误"""

        def broken_handler(params, context):
            raise ValueError("模拟失败")

        engine.register_action("broken", broken_handler)
        results = engine._execute_actions(
            [{"type": "broken", "params": {}}],
            {},
        )
        assert results[0]["status"] == "error"
        assert "模拟失败" in results[0]["message"]

    def test_create_notification_missing_user_id(self, engine):
        """创建通知缺少 user_id 应返回错误"""
        result = engine._action_create_notification(
            {"title": "测试", "content": "内容"},
            {},
        )
        assert result["status"] == "error"
        assert "缺少 user_id" in result["message"]

    def test_create_notification_missing_title(self, engine):
        """创建通知缺少 title 应返回错误"""
        result = engine._action_create_notification(
            {"user_id": "1", "content": "内容"},
            {},
        )
        assert result["status"] == "error"
        assert "缺少 title" in result["message"]

    def test_create_notification_success(self, engine):
        """创建通知成功应返回 notification_id"""
        result = engine._action_create_notification(
            {"user_id": "1", "title": "测试通知", "content": "你好"},
            {},
        )
        assert result["status"] == "ok"
        assert "notification_id" in result

    def test_execute_multiple_actions(self, engine):
        """多个动作应全部被执行"""
        calls = []

        def act_a(params, context):
            calls.append("a")
            return {"status": "ok"}

        def act_b(params, context):
            calls.append("b")
            return {"status": "ok"}

        engine.register_action("act_a", act_a)
        engine.register_action("act_b", act_b)

        results = engine._execute_actions(
            [{"type": "act_a", "params": {}}, {"type": "act_b", "params": {}}],
            {},
        )
        assert len(results) == 2
        assert calls == ["a", "b"]


# =========================================================================
# 测试: Cron 表达式匹配
# =========================================================================


class TestCronMatching:
    """验证 cron 表达式匹配功能"""

    def test_cron_match_all(self, engine):
        """* * * * * 始终匹配"""
        from datetime import datetime
        assert engine._match_cron(["*", "*", "*", "*", "*"], datetime(2025, 1, 1, 0, 0)) is True
        assert engine._match_cron(["*", "*", "*", "*", "*"], datetime(2025, 6, 15, 12, 30)) is True

    def test_cron_exact_minute(self, engine):
        """精确匹配分钟"""
        from datetime import datetime
        assert engine._match_cron(["30", "*", "*", "*", "*"], datetime(2025, 1, 1, 10, 30)) is True
        assert engine._match_cron(["30", "*", "*", "*", "*"], datetime(2025, 1, 1, 10, 31)) is False

    def test_cron_range(self, engine):
        """范围匹配"""
        from datetime import datetime
        # 分钟字段范围 9-17
        assert engine._match_cron(["9-17", "*", "*", "*", "*"], datetime(2025, 1, 1, 10, 12)) is True
        assert engine._match_cron(["9-17", "*", "*", "*", "*"], datetime(2025, 1, 1, 10, 9)) is True
        assert engine._match_cron(["9-17", "*", "*", "*", "*"], datetime(2025, 1, 1, 10, 8)) is False
        assert engine._match_cron(["9-17", "*", "*", "*", "*"], datetime(2025, 1, 1, 10, 18)) is False

    def test_cron_step(self, engine):
        """步进匹配 (/ 语法)"""
        from datetime import datetime
        # 每5分钟
        assert engine._match_cron(["*/5", "*", "*", "*", "*"], datetime(2025, 1, 1, 10, 0)) is True
        assert engine._match_cron(["*/5", "*", "*", "*", "*"], datetime(2025, 1, 1, 10, 5)) is True
        assert engine._match_cron(["*/5", "*", "*", "*", "*"], datetime(2025, 1, 1, 10, 7)) is False

    def test_cron_list(self, engine):
        """列表匹配 (, 语法)"""
        from datetime import datetime
        assert engine._match_cron(["0,15,30,45", "*", "*", "*", "*"], datetime(2025, 1, 1, 10, 15)) is True
        assert engine._match_cron(["0,15,30,45", "*", "*", "*", "*"], datetime(2025, 1, 1, 10, 20)) is False

    def test_cron_all_fields(self, engine):
        """多字段匹配"""
        from datetime import datetime
        # 每天 9:00 在周一
        assert engine._match_cron(["0", "9", "*", "*", "0"], datetime(2025, 1, 6, 9, 0)) is True  # 周一=0
        assert engine._match_cron(["0", "9", "*", "*", "0"], datetime(2025, 1, 6, 10, 0)) is False


# =========================================================================
# 测试: 执行历史查询
# =========================================================================


class TestExecutionHistory:
    """验证执行历史记录的查询功能"""

    def test_get_execution_history_empty(self, engine):
        """初始时执行历史应为空"""
        history = engine.get_execution_history()
        assert history == []

    def test_get_execution_history_filter_by_rule(self, engine):
        """按规则名称过滤执行历史"""
        # 直接插入执行记录
        engine._conn.execute(
            "INSERT INTO workflow_executions (rule_name, trigger_type, status) VALUES (?, ?, ?)",
            ("rule_a", "event", "success"),
        )
        engine._conn.execute(
            "INSERT INTO workflow_executions (rule_name, trigger_type, status) VALUES (?, ?, ?)",
            ("rule_b", "event", "success"),
        )
        engine._conn.commit()

        history_a = engine.get_execution_history(rule_name="rule_a")
        assert len(history_a) == 1
        assert history_a[0]["rule_name"] == "rule_a"

        history_all = engine.get_execution_history()
        assert len(history_all) == 2

    def test_get_execution_history_limit_offset(self, engine):
        """分页查询执行历史"""
        for i in range(5):
            engine._conn.execute(
                "INSERT INTO workflow_executions (rule_name, trigger_type, status) VALUES (?, ?, ?)",
                (f"rule_{i}", "event", "success"),
            )
        engine._conn.commit()

        page1 = engine.get_execution_history(limit=2, offset=0)
        assert len(page1) == 2

        page2 = engine.get_execution_history(limit=2, offset=2)
        assert len(page2) == 2
        # 确保分页不重叠
        ids_page1 = {r["id"] for r in page1}
        ids_page2 = {r["id"] for r in page2}
        assert ids_page1 & ids_page2 == set()

    def test_get_recent_events(self, engine):
        """查询最近事件"""
        engine.fire_event("test_event_1")
        engine.fire_event("test_event_2")
        events = engine.get_recent_events(limit=5)
        assert len(events) >= 2
        event_types = {e["event_type"] for e in events}
        assert "test_event_1" in event_types
        assert "test_event_2" in event_types


# =========================================================================
# 测试: 错误处理与边界情况
# =========================================================================


class TestErrorHandling:
    """验证错误处理和边界条件"""

    def test_workflow_error_base(self):
        """WorkflowError 应可被捕获为基类异常"""
        with pytest.raises(WorkflowError):
            raise RuleNotFoundError("测试")
        with pytest.raises(WorkflowError):
            raise TriggerError("测试")
        with pytest.raises(WorkflowError):
            raise ActionError("测试")

    def test_trigger_error(self):
        """TriggerError 应包含消息"""
        err = TriggerError("触发器失败")
        assert str(err) == "触发器失败"

    def test_action_error(self):
        """ActionError 应包含消息"""
        err = ActionError("动作失败")
        assert str(err) == "动作失败"

    def test_rule_not_found_error_message(self, engine):
        """RuleNotFoundError 应包含规则名"""
        try:
            engine.enable_rule("missing_rule")
        except RuleNotFoundError as e:
            assert "missing_rule" in str(e)

    def test_fire_event_with_invalid_type(self, engine):
        """触发无效事件类型不应崩溃"""
        results = engine.fire_event("non_existent_event_type")
        assert results == []
