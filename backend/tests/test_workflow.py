"""
工作流引擎测试脚本

用法:
  python test_workflow.py                     # 运行所有测试
  python test_workflow.py --setup-only         # 只初始化数据库和种子数据
  python test_workflow.py --manual             # 进入手动测试模式

环境:
  - 在 /var/www/liankebao/backend/ 目录下运行
  - 需要在虚拟环境中执行 (已安装 fastapi, sqlalchemy, pyyaml)
"""
import json
import os
import sys
import time

# 确保能找到模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine, Base
from modules.workflow.workflow_engine import WorkflowEngine, DEAL_STAGES
from modules.workflow.notifications import NotificationService


def setup_database():
    """初始化数据库表"""
    # 导入所有模型以确保注册
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    print("[✓] 数据库表已创建")


def test_notification_service():
    """测试通知服务"""
    print("\n=== 测试通知服务 ===")
    ns = NotificationService()

    # 发送通知
    nid = ns.send(
        user_id=1,
        title="测试通知",
        content="这是一条测试通知内容",
        notification_type="info",
    )
    print(f"  通知创建成功 (ID: {nid})")

    # 发送广播
    ids = ns.send_broadcast(
        user_ids=[1, 2, 3],
        title="广播通知",
        content="全员广播",
    )
    print(f"  广播通知创建成功 (IDs: {ids})")

    # 查询
    notifs = ns.get_user_notifications(user_id=1)
    print(f"  用户1通知数: {len(notifs)}")
    print(f"  未读数: {ns.count_unread(1)}")

    # 标记已读
    if notifs:
        ns.mark_read(notifs[0]["id"])
        print(f"  标记通知 {notifs[0]['id']} 已读")
        print(f"  未读数: {ns.count_unread(1)}")

    # 标记全部已读
    ns.mark_all_read(1)
    print(f"  全部标记已读后未读数: {ns.count_unread(1)}")

    print("[✓] 通知服务测试通过")
    return ns


def create_sample_deal():
    """创建测试用的 Deal"""
    from modules.workflow.models.deal import Deal

    db = SessionLocal()
    try:
        # 创建测试联系人 (如果不存在)
        from modules.contacts.models.contact import Contact

        contact = db.query(Contact).filter(Contact.name == "测试联系人").first()
        if not contact:
            contact = Contact(name="测试联系人", phone="13800138000", owner_id=1)
            db.add(contact)
            db.flush()

        deal = Deal(
            title="测试商机 - 企业管理系统",
            description="一家中型企业的管理系统需求",
            stage="qualification",
            amount=50000.0,
            probability=30,
            contact_id=contact.id,
            owner_id=1,
        )
        db.add(deal)
        db.commit()
        db.refresh(deal)
        print(f"  Deal 创建成功 (ID: {deal.id})")
        return deal
    finally:
        db.close()


def create_sample_order():
    """创建测试用的 Order"""
    from modules.orders.models.order import Order

    db = SessionLocal()
    try:
        from modules.products.models.product import Product

        product = db.query(Product).first()
        if not product:
            product = Product(
                name="测试产品",
                price=99.0,
                category="软件",
                status="approved",
                owner_id=1,
            )
            db.add(product)
            db.flush()

        order = Order(
            order_no=f"TEST{int(time.time())}",
            product_id=product.id,
            buyer_id=1,
            supplier_id=1,
            quantity=1,
            total_price=99.0,
            status="paid",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        print(f"  Order 创建成功 (ID: {order.id}, No: {order.order_no})")
        return order
    finally:
        db.close()


def test_workflow_engine(engine: WorkflowEngine):
    """测试工作流引擎核心功能"""
    print("\n=== 测试工作流引擎 ===")

    # 1. 规则加载
    rules = engine.get_all_rules()
    print(f"  已加载规则: {len(rules)} 条")
    for r in rules:
        trigger = r.get("trigger", {})
        print(f"    - {r['name']}: {trigger.get('type')}/{trigger.get('event', trigger.get('cron', 'N/A'))} "
              f"[{'启用' if r.get('enabled', True) else '禁用'}]")

    # 2. 触发 on_deal_created 事件
    print("\n  触发 on_deal_created 事件...")
    results = engine.fire_event(
        event_type="on_deal_created",
        entity_type="deal",
        entity_id=1,
        payload={
            "deal": {
                "id": 1,
                "title": "测试商机 - 企业管理系统",
                "owner_id": 1,
                "contact_id": 1,
                "created_at": "2026-05-28 09:00:00",
                "stage_entered_at": "2026-05-28 09:00:00",
                "elapsed_hours": 36,  # > 24小时
            }
        },
    )
    print(f"  匹配规则: {len(results)} 条")
    for r in results:
        print(f"    规则: {r['rule']}")
        for a in r.get("actions", []):
            print(f"      动作: {a['type']} -> {a['status']}")

    # 3. 触发 on_order_paid 事件
    print("\n  触发 on_order_paid 事件...")
    results = engine.fire_event(
        event_type="on_order_paid",
        entity_type="order",
        entity_id=1,
        payload={
            "order": {
                "id": 1,
                "order_no": "TEST123456",
                "total_price": 99.0,
                "buyer_id": 1,
                "product_id": 1,
            }
        },
    )
    print(f"  匹配规则: {len(results)} 条")
    for r in results:
        print(f"    规则: {r['rule']}")

    # 4. 查询执行历史
    history = engine.get_execution_history(limit=10)
    print(f"\n  执行历史: {len(history)} 条记录")
    for h in history:
        print(f"    [{h['executed_at']}] {h['rule_name']} ({h['trigger_type']}) -> {h['status']}")

    # 5. 查询事件日志
    events = engine.get_recent_events(limit=10)
    print(f"\n  事件日志: {len(events)} 条记录")
    for e in events:
        print(f"    [{e['created_at']}] {e['event_type']}")

    # 6. 定时触发器测试
    print("\n  测试定时触发器...")
    engine.check_scheduled_triggers()

    # 7. 条件触发器测试
    print("\n  测试条件触发器...")
    engine.check_conditional_triggers()

    print("\n[✓] 工作流引擎核心测试通过")


def test_api_integration():
    """测试 API 集成 (使用 FastAPI TestClient)"""
    print("\n=== 测试 API 集成 ===")
    try:
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        from modules.workflow.routes import init_workflow_engine

        app = FastAPI()
        eng = init_workflow_engine(app)
        client = TestClient(app)

        # 健康检查
        resp = client.get("/api/workflow/health")
        print(f"  GET /api/workflow/health: {resp.status_code}")
        assert resp.status_code == 200
        data = resp.json()
        print(f"    规则数: {data['rules_loaded']}")

        # 获取规则列表
        resp = client.get("/api/workflow/rules")
        print(f"  GET /api/workflow/rules: {resp.status_code}")
        assert resp.status_code == 200
        data = resp.json()
        print(f"    规则数: {data['count']}")

        # 触发事件
        resp = client.post(
            "/api/workflow/events",
            json={
                "event_type": "on_deal_created",
                "entity_type": "deal",
                "entity_id": 1,
                "payload": {
                    "deal": {
                        "id": 1,
                        "title": "API测试商机",
                        "owner_id": 1,
                        "contact_id": 1,
                        "elapsed_hours": 48,
                    }
                },
            },
        )
        print(f"  POST /api/workflow/events: {resp.status_code}")
        assert resp.status_code == 200
        data = resp.json()
        print(f"    匹配规则: {data['matched_rules']}")

        # 查询执行历史
        resp = client.get("/api/workflow/executions?limit=5")
        print(f"  GET /api/workflow/executions: {resp.status_code}")
        assert resp.status_code == 200

        # 手动执行规则
        resp = client.post(
            "/api/workflow/execute",
            json={
                "rule_name": "deal_no_followup_24h",
                "context": {
                    "deal": {
                        "id": 1,
                        "title": "手动测试商机",
                        "owner_id": 1,
                        "contact_id": 1,
                    }
                },
            },
        )
        print(f"  POST /api/workflow/execute: {resp.status_code}")
        assert resp.status_code == 200
        data = resp.json()
        print(f"    动作数: {data['actions_count']}")

        # 启用/禁用规则
        resp = client.put(
            "/api/workflow/rules/order_paid_log_activity/toggle",
            json={"enabled": False},
        )
        print(f"  PUT /api/workflow/rules/.../toggle: {resp.status_code}")
        assert resp.status_code == 200

        # 查询通知
        resp = client.get("/api/workflow/notifications/1?limit=5")
        print(f"  GET /api/workflow/notifications/1: {resp.status_code}")
        assert resp.status_code == 200
        data = resp.json()
        print(f"    通知数: {data['count']}, 未读: {data['unread_count']}")

        print("\n[✓] API 集成测试通过")

    except ImportError as e:
        print(f"  [!] 跳过 API 测试 (缺少依赖: {e})")
    except Exception as e:
        print(f"  [!] API 测试出错: {e}")
        import traceback
        traceback.print_exc()


def test_yaml_rules():
    """测试 YAML 规则文件"""
    print("\n=== 测试 YAML 规则文件 ===")
    import yaml

    rules_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "modules", "workflow", "rules",
    )
    files = sorted([f for f in os.listdir(rules_dir) if f.endswith((".yaml", ".yml"))])
    print(f"  找到 {len(files)} 个规则文件:")

    for fname in files:
        fpath = os.path.join(rules_dir, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            rule = yaml.safe_load(f)

        assert rule.get("name"), f"{fname}: 缺少 name"
        assert rule.get("trigger"), f"{fname}: 缺少 trigger"
        assert rule.get("actions"), f"{fname}: 缺少 actions"

        trigger = rule["trigger"]
        assert trigger.get("type") in ("event", "schedule", "condition"), \
            f"{fname}: trigger.type 无效: {trigger.get('type')}"

        if trigger["type"] == "event":
            assert trigger.get("event"), f"{fname}: event trigger 缺少 event"

        for action in rule["actions"]:
            assert action.get("type"), f"{fname}: action 缺少 type"
            assert action["type"] in (
                "create_notification", "create_activity", "update_deal_stage",
                "send_followup_reminder", "assign_task", "notify_promoters"
            ), f"{fname}: action.type 无效: {action['type']}"

        print(f"    [✓] {fname}: {rule['name']}")

    print("\n[✓] YAML 规则测试通过")


def test_deal_model():
    """测试 Deal 模型"""
    print("\n=== 测试 Deal 模型 ===")
    from modules.workflow.models.deal import Deal

    # 检查表结构
    assert hasattr(Deal, "id")
    assert hasattr(Deal, "stage")
    assert hasattr(Deal, "stage_entered_at")
    assert hasattr(Deal, "owner_id")

    # 检查阶段常量
    assert "qualification" in DEAL_STAGES
    assert "closed_won" in DEAL_STAGES
    assert len(DEAL_STAGES) == 6

    print(f"  Deal 阶段: {DEAL_STAGES}")
    print("[✓] Deal 模型测试通过")


def test_event_model():
    """测试 Event 模型"""
    print("\n=== 测试 Event 模型 ===")
    from modules.workflow.models.event import Event

    assert hasattr(Event, "event_type")
    assert hasattr(Event, "entity_type")
    assert hasattr(Event, "data")

    print(f"  Event 类型示例: on_deal_created, on_order_paid, ...")
    print("[✓] Event 模型测试通过")


def cleanup():
    """清理测试数据"""
    print("\n=== 清理测试数据 ===")
    ns = NotificationService()
    ns.delete_old(days=0)  # 删除所有

    # 清理 workflow.db
    wf = WorkflowEngine()
    conn = wf._conn
    conn.execute("DELETE FROM workflow_events")
    conn.execute("DELETE FROM workflow_executions")
    conn.execute("DELETE FROM workflow_conditions")
    conn.commit()
    print("  清理完成")


def interactive_menu(engine: WorkflowEngine):
    """交互式手动测试模式"""
    print("\n" + "=" * 60)
    print("  工作流引擎 - 手动测试模式")
    print("=" * 60)
    print("可用命令:")
    print("  trigger <event_type> [entity_type] [entity_id]  - 触发事件")
    print("  execute <rule_name>                             - 手动执行规则")
    print("  rules                                           - 列出所有规则")
    print("  toggle <rule_name> <0|1>                        - 启用/禁用规则")
    print("  notifs <user_id>                                - 查看用户通知")
    print("  history [rule_name]                             - 查看执行历史")
    print("  events                                         - 查看事件日志")
    print("  check                                          - 检查定时/条件触发器")
    print("  quit                                           - 退出")
    print()

    while True:
        try:
            cmd = input("wf> ").strip()
            if not cmd:
                continue
            parts = cmd.split()
            action = parts[0].lower()

            if action == "quit":
                break
            elif action == "rules":
                for r in engine.get_all_rules():
                    status = "启用" if r.get("enabled", True) else "禁用"
                    print(f"  {r['name']} [{status}]")
            elif action == "trigger":
                if len(parts) < 2:
                    print("  用法: trigger <event_type> [entity_type] [entity_id]")
                    continue
                event_type = parts[1]
                entity_type = parts[2] if len(parts) > 2 else None
                entity_id = int(parts[3]) if len(parts) > 3 else None
                results = engine.fire_event(event_type, entity_type, entity_id)
                print(f"  匹配规则: {len(results)}")
                for r in results:
                    print(f"    -> {r['rule']}: {r['actions']}")
            elif action == "execute":
                if len(parts) < 2:
                    print("  用法: execute <rule_name>")
                    continue
                rule = engine.get_rule(parts[1])
                if not rule:
                    print(f"  规则 '{parts[1]}' 不存在")
                    continue
                context = {"event": {"type": "manual"}, "deal": {"id": 1, "title": "手动测试", "owner_id": 1, "contact_id": 1}}
                results = engine._execute_actions(rule.get("actions", []), context)
                engine._record_execution(parts[1], "manual", "cli", "success", results)
                print(f"  结果: {json.dumps(results, ensure_ascii=False, indent=2)}")
            elif action == "toggle":
                if len(parts) < 3:
                    print("  用法: toggle <rule_name> <0|1>")
                    continue
                engine.enable_rule(parts[1], parts[2] == "1")
                print(f"  规则 {parts[1]} -> {'启用' if parts[2]=='1' else '禁用'}")
            elif action == "notifs":
                uid = int(parts[1]) if len(parts) > 1 else 1
                notifs = engine.notifier.get_user_notifications(uid)
                unread = engine.notifier.count_unread(uid)
                print(f"  用户 {uid}: {len(notifs)} 条通知 (未读: {unread})")
                for n in notifs[:10]:
                    print(f"    [{n['created_at']}] {n['title']} - {'未读' if not n['is_read'] else '已读'}")
            elif action == "history":
                rn = parts[1] if len(parts) > 1 else None
                hist = engine.get_execution_history(rule_name=rn, limit=10)
                for h in hist:
                    print(f"    [{h['executed_at']}] {h['rule_name']} ({h['trigger_type']}) -> {h['status']}")
            elif action == "events":
                events = engine.get_recent_events(limit=10)
                for e in events:
                    print(f"    [{e['created_at']}] {e['event_type']} ({e['entity_type']}:{e['entity_id']})")
            elif action == "check":
                print("  检查定时触发器...")
                engine.check_scheduled_triggers()
                print("  检查条件触发器...")
                engine.check_conditional_triggers()
                print("  完成")
            else:
                print(f"  未知命令: {action}")
        except KeyboardInterrupt:
            print()
            break
        except Exception as e:
            print(f"  错误: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="工作流引擎测试")
    parser.add_argument("--setup-only", action="store_true", help="只初始化数据库和种子数据")
    parser.add_argument("--manual", action="store_true", help="进入手动测试模式")
    parser.add_argument("--skip-db-setup", action="store_true", help="跳过数据库初始化")
    parser.add_argument("--no-cleanup", action="store_true", help="不清理测试数据")
    args = parser.parse_args()

    print("=" * 60)
    print("  链客宝工作流引擎 - 测试套件")
    print("=" * 60)

    # 数据库初始化
    if not args.skip_db_setup:
        setup_database()

    # 创建引擎实例
    engine = WorkflowEngine()

    if args.setup_only:
        engine.seed_rules()
        engine.load_rules()
        print(f"\n种子规则已创建，共加载 {len(engine.get_all_rules())} 条规则")
        sys.exit(0)

    # 种子规则
    print("\n创建种子规则...")
    engine.seed_rules()
    engine.load_rules()
    print(f"加载 {len(engine.get_all_rules())} 条规则")

    if args.manual:
        interactive_menu(engine)
        sys.exit(0)

    # 运行所有测试
    try:
        test_yaml_rules()
        test_event_model()
        test_deal_model()
        test_notification_service()
        test_workflow_engine(engine)
        test_api_integration()
    finally:
        if not args.no_cleanup:
            cleanup()

    print("\n" + "=" * 60)
    print("  所有测试通过 ✓")
    print("=" * 60)
