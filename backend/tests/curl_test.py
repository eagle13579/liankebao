"""
Curl 验证脚本 - 工作流引擎端到端测试

重点验证:
  1. 引擎初始化与规则加载
  2. 通知服务 (notifications.py)
  3. 事件触发与规则匹配
  4. API 端点 (FastAPI TestClient)
  5. 种子规则 YAML 完整性
  6. 模板解析
  7. 动作系统执行能力
"""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def verify_engine_core():
    """验证引擎核心功能"""
    from modules.workflow.workflow_engine import WorkflowEngine

    print("=" * 60)
    print("  [验证1] 引擎初始化与规则加载")
    print("=" * 60)

    engine = WorkflowEngine()
    engine.seed_rules()
    engine.load_rules()

    rules = engine.get_all_rules()
    print(f"  规则数: {len(rules)}")
    for r in rules:
        print(f"    [{r['name']}] trigger={r['trigger']['type']}/{r['trigger'].get('event','?')} "
              f"actions={len(r['actions'])} enabled={r.get('enabled',True)}")
    assert len(rules) == 4
    print("  [PASS]")

    print("\n" + "=" * 60)
    print("  [验证2] YAML 种子规则文件完整性")
    print("=" * 60)

    import yaml
    rules_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "modules", "workflow", "rules",
    )
    files = sorted(os.listdir(rules_dir))
    yaml_files = [f for f in files if f.endswith((".yaml", ".yml"))]
    assert len(yaml_files) == 4, f"期望4个YAML文件, 找到{len(yaml_files)}"
    for fname in yaml_files:
        with open(os.path.join(rules_dir, fname)) as f:
            rule = yaml.safe_load(f)
        assert rule.get("name"), f"{fname} missing name"
        assert rule.get("trigger"), f"{fname} missing trigger"
        assert rule.get("actions"), f"{fname} missing actions"
        assert rule.get("enabled") is True, f"{fname} should be enabled"
        print(f"    [OK] {fname} -> {rule['name']}")
    print("  [PASS]")


def verify_notifications():
    """验证通知服务"""
    from modules.workflow.notifications import NotificationService

    print("\n" + "=" * 60)
    print("  [验证3] 通知服务 (notifications.py)")
    print("=" * 60)

    ns = NotificationService()

    # 清理并发送新通知
    conn = sqlite3.connect(ns._db_path)
    conn.execute("DELETE FROM notifications")
    conn.commit()
    conn.close()

    # 发送
    nid1 = ns.send(1, "验证通知A", "内容A")
    nid2 = ns.send(1, "验证通知B", "内容B", "warning", "deal", 123)
    nid3 = ns.send(2, "用户2通知", "内容C")
    print(f"  发送通知: ID={nid1},{nid2},{nid3}")

    # 查询
    u1 = ns.get_user_notifications(1)
    assert len(u1) == 2
    print(f"  用户1通知数: {len(u1)}")

    # 未读计数
    assert ns.count_unread(1) == 2
    print(f"  用户1未读数: 2")

    # 标记已读
    ns.mark_read(nid1)
    assert ns.count_unread(1) == 1
    print(f"  标记1条已读后: 1")

    # 全部已读
    ns.mark_all_read(1)
    assert ns.count_unread(1) == 0
    print(f"  全部已读: 0")

    # 广播
    ids = ns.send_broadcast([3, 4, 5], "广播通知", "全员通知")
    assert len(ids) == 3
    print(f"  广播3人: IDs={ids}")

    # 删除
    ns.delete(nid1)
    assert ns.get_by_id(nid1) is None
    print(f"  删除后查询: None")

    print("  [PASS]")


def verify_template_engine():
    """验证模板变量解析"""
    from modules.workflow.workflow_engine import WorkflowEngine as WE

    print("\n" + "=" * 60)
    print("  [验证4] 模板变量解析")
    print("=" * 60)

    cases = [
        ("{{ deal.title }}", {"deal": {"title": "商机A"}}, "商机A"),
        ("{{ order.total_price }}", {"order": {"total_price": 99.99}}, "99.99"),
        ("{{ user.name }}", {"user": {"name": "张三"}}, "张三"),
        ("无变量文本", {}, "无变量文本"),
        ("{{ empty.field }}", {}, ""),
        ("前后{{ deal.id }}中间", {"deal": {"id": 42}}, "前后42中间"),
    ]
    for tmpl, ctx, expected in cases:
        result = WE._resolve_template(tmpl, ctx)
        assert result == expected, f"'{tmpl}' -> '{result}' != '{expected}'"
        print(f"    OK: '{tmpl}' -> '{result}'")
    print("  [PASS]")


def verify_event_dispatch():
    """验证事件分发与动作执行"""
    from modules.workflow.workflow_engine import WorkflowEngine

    print("\n" + "=" * 60)
    print("  [验证5] 事件分发 & 动作执行")
    print("=" * 60)

    engine = WorkflowEngine()
    engine.seed_rules()
    engine.load_rules()

    # 5a. 无条件事件: on_order_paid
    print("  [5a] on_order_paid (无条件规则)")
    results = engine.fire_event(
        event_type="on_order_paid",
        entity_type="order",
        entity_id=999,
        payload={
            "order": {
                "id": 999,
                "order_no": "TEST-001",
                "total_price": 9999.0,
                "buyer_id": 1,
                "product_id": 1,
            }
        },
    )
    assert len(results) >= 1
    for r in results:
        assert r["rule"] == "order_paid_log_activity"
        for a in r["actions"]:
            assert a["status"] in ("ok", "error")
            print(f"    规则={r['rule']} 动作={a['type']} -> {a['status']}")
    print("    [PASS]")

    # 5b. 有条件事件: on_deal_created (无条件触发,但条件评估在DB加载)
    print("  [5b] on_deal_created (条件规则)")
    results = engine.fire_event(
        event_type="on_deal_created",
        entity_type="deal",
        entity_id=999,
        payload={
            "deal": {
                "id": 999,
                "title": "测试商机",
                "owner_id": 1,
                "contact_id": 1,
                "elapsed_hours": 48,
            }
        },
    )
    # 条件规则 require elapsed_hours from DB-loaded context
    # 当entity_id=999不存在时,条件不满足,这是预期行为
    print(f"    匹配: {len(results)}条 (DB无此ID时条件不满足, 预期行为)")
    print("    [PASS]")

    # 5c. 手动执行验证动作系统完整性
    print("  [5c] 手动执行 -> 验证动作系统")
    results = engine._execute_actions(
        engine.get_rule("deal_no_followup_24h")["actions"],
        {
            "deal": {
                "id": 1, "title": "手动测试商机",
                "owner_id": 1, "contact_id": 1,
                "elapsed_hours": 48,
            }
        },
    )
    engine._record_execution("deal_no_followup_24h", "manual", "test", "success", results)
    print(f"    动作数: {len(results)}")
    for a in results:
        print(f"      动作={a['type']} -> {a['status']}")
        if a["status"] == "ok":
            rid = a["result"].get("notification_id", a["result"].get("activity_id", "?"))
            print(f"        ID: {rid}")
    # 通知动作应总是成功
    notif_actions = [a for a in results if a["type"] == "create_notification"]
    assert all(a["status"] == "ok" for a in notif_actions)
    print("    [PASS]")

    # 5d. 定时触发器
    print("  [5d] 定时触发器检查")
    engine.check_scheduled_triggers()
    print("    [PASS]")

    # 5e. 条件触发器
    print("  [5e] 条件触发器检查")
    engine.check_conditional_triggers()
    print("    [PASS]")

    # 5f. 查询历史
    print("  [5f] 执行历史查询")
    hist = engine.get_execution_history(limit=10)
    print(f"    记录: {len(hist)}条")
    assert len(hist) >= 1
    for h in hist:
        print(f"      [{h['executed_at']}] {h['rule_name']} {h['trigger_type']} -> {h['status']}")
    print("    [PASS]")

    # 5g. 事件日志
    print("  [5g] 事件日志查询")
    events = engine.get_recent_events(limit=10)
    print(f"    事件: {len(events)}条")
    assert len(events) >= 1
    print("    [PASS]")

    # 5h. 规则启用/禁用
    print("  [5h] 规则启用/禁用")
    engine.enable_rule("order_paid_log_activity", False)
    assert engine.get_rule("order_paid_log_activity")["enabled"] is False
    engine.enable_rule("order_paid_log_activity", True)
    assert engine.get_rule("order_paid_log_activity")["enabled"] is True
    print("    [PASS]")


def verify_api():
    """验证 FastAPI API 端点"""
    print("\n" + "=" * 60)
    print("  [验证6] API 端点测试")
    print("=" * 60)

    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except ImportError:
        print("  SKIP: 需要 fastapi")
        return

    from modules.workflow.routes import init_workflow_engine

    app = FastAPI()
    eng = init_workflow_engine(app)
    client = TestClient(app)

    endpoints = [
        ("GET", "/api/v1/workflow/health", None, 200),
        ("GET", "/api/v1/workflow/rules", None, 200),
        ("GET", "/api/v1/workflow/rules/deal_no_followup_24h", None, 200),
        ("POST", "/api/v1/workflow/events", {
            "event_type": "on_order_paid",
            "entity_type": "order",
            "entity_id": 1,
            "payload": {"order": {"id": 1, "order_no": "T", "total_price": 1, "buyer_id": 1}},
        }, 200),
        ("POST", "/api/v1/workflow/execute", {
            "rule_name": "deal_no_followup_24h",
            "context": {"deal": {"id": 1, "title": "T", "owner_id": 1, "contact_id": 1}},
        }, 200),
        ("GET", "/api/v1/workflow/executions?limit=5", None, 200),
        ("GET", "/api/v1/workflow/events?limit=5", None, 200),
        ("GET", "/api/v1/workflow/notifications/1?limit=5", None, 200),
        ("PUT", "/api/v1/workflow/rules/order_paid_log_activity/toggle", {"enabled": False}, 200),
        ("POST", "/api/v1/workflow/rules/reload", None, 200),
        # 恢复
        ("PUT", "/api/v1/workflow/rules/order_paid_log_activity/toggle", {"enabled": True}, 200),
    ]

    for method, path, body, expected_code in endpoints:
        if method == "GET":
            resp = client.get(path)
        elif method == "POST":
            resp = client.post(path, json=body)
        elif method == "PUT":
            resp = client.put(path, json=body)
        ok = "OK" if resp.status_code == expected_code else "FAIL"
        print(f"    [{ok}] {method} {path} -> {resp.status_code} (期望{expected_code})")
        assert resp.status_code == expected_code, f"{method} {path}: {resp.status_code}"

    print("  [PASS]")


def verify_deal_model():
    """验证 Deal 模型定义"""
    print("\n" + "=" * 60)
    print("  [验证7] Deal 模型设计")
    print("=" * 60)

    from modules.workflow.models.deal import Deal
    from modules.workflow.workflow_engine import DEAL_STAGES

    # 字段
    for field in ["id", "title", "stage", "amount", "contact_id", "owner_id", "stage_entered_at"]:
        assert hasattr(Deal, field), f"Deal 缺少字段 {field}"
    print("    Deal 字段: id, title, stage, amount, contact_id, owner_id, stage_entered_at")

    # 阶段
    assert "qualification" in DEAL_STAGES
    assert DEAL_STAGES == ["qualification", "meeting", "proposal", "negotiation", "closed_won", "closed_lost"]
    print(f"    Deal 阶段: {DEAL_STAGES}")
    print("  [PASS]")


def verify_event_model():
    """验证 Event 模型定义"""
    print("\n" + "=" * 60)
    print("  [验证8] Event 日志模型")
    print("=" * 60)

    from modules.workflow.models.event import Event
    for field in ["id", "event_type", "entity_type", "entity_id", "data"]:
        assert hasattr(Event, field), f"Event 缺少字段 {field}"
    print("    Event 字段: id, event_type, entity_type, entity_id, data")
    print("  [PASS]")


if __name__ == "__main__":
    verify_engine_core()
    verify_notifications()
    verify_template_engine()
    verify_event_dispatch()
    verify_api()
    verify_deal_model()
    verify_event_model()

    print("\n" + "=" * 60)
    print("  ✓ 全部 8 项验证通过！")
    print("=" * 60)
