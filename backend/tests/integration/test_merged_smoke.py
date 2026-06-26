"""
链客宝代码库合并 — 集成冒烟测试
验证所有已迁移模块的导入链和核心功能
"""
import os
import sys

# Add backend to path
backend_dir = os.path.abspath(r"D:\chainke-full\backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

print("=" * 60)
print("  链客宝代码库合并 — 集成冒烟测试")
print("=" * 60)

passed = 0
failed = 0
errors = []

def test(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"  ✅ {name}")
    except Exception as e:
        failed += 1
        errors.append((name, str(e)))
        print(f"  ❌ {name}: {e}")

# ===== Phase 1: 数据安全模块 =====
def test_data_security():
    from data_security.core.sanitizer import Sanitizer
    from data_security.core.data_contract import ContractValidator as DataContract
    from data_security.core.data_write_gateway import DataWriteGateway
    from data_security.core.anomaly_scorer import AnomalyScorer
    assert Sanitizer is not None
    assert DataContract is not None

def test_data_security_gate3():
    from data_security.gate3.gate3_validator import validate_score
    assert validate_score is not None

def test_data_security_quarantine():
    from data_security.quarantine.quarantine_manager import QuarantineManager
    assert QuarantineManager is not None

def test_data_security_wolf():
    from data_security.wolf.wolf_data_attack import WolfDataAttack
    from data_security.wolf.attack_payloads import get_attack_payloads
    assert WolfDataAttack is not None

# ===== Phase 1: 支付模块 =====
def test_payment_alipay():
    from payment.providers.alipay import AliPayProvider
    assert AliPayProvider is not None

def test_payment_wxpay():
    from payment.providers.wxpay import WxPayProvider
    assert WxPayProvider is not None

def test_payment_sdk():
    from payment.sdk.sign import SignTool
    from payment.sdk.config import PaymentConfig
    from payment.sdk.http_delegate import HttpDelegate
    assert SignTool is not None

# ===== Phase 1: 信任引擎 =====
def test_trust_engine():
    from features.trust_engine.scoring import TrustScorer
    from features.trust_engine.tier import TrustTier, get_trust_tier
    from features.trust_engine.matching import TrustEnhancedMatcher
    assert TrustScorer is not None
    assert get_trust_tier(750) == "platinum"

# ===== Phase 2: 业务模块 =====
def test_design_review():
    from features.design_review.engine import DesignReviewEngine
    assert DesignReviewEngine is not None

def test_innovation_engine():
    from features.innovation_engine.engine import InnovationEngine
    assert InnovationEngine is not None

def test_orders():
    from features.orders.models.order import Order
    from features.orders.services.order_service import OrderService
    assert Order is not None

def test_products():
    from features.products.models.product import Product
    from features.products.services.product_service import ProductService
    assert Product is not None

def test_promoter():
    from features.promoter.models.withdrawal import Withdrawal
    from features.promoter.services.withdrawal_service import WithdrawalService
    assert Withdrawal is not None

def test_workflow():
    from features.workflow.workflow_engine import WorkflowEngine
    assert WorkflowEngine is not None

def test_contacts():
    from features.contacts.models.contact import Contact
    from features.contacts.services.contact_service import ContactService
    assert Contact is not None

def test_needs():
    from features.needs.models.need import BusinessNeed
    from features.needs.services.need_service import NeedService
    assert BusinessNeed is not None

def test_external():
    from features.external.models.external_module import ExternalModule
    from features.external.services.adapter import AdapterBase
    from features.external.services.webhook import WebhookReceiver
    assert ExternalModule is not None

def test_activities():
    from features.activities.models.activity import Activity
    from features.activities.services.activity_service import ActivityService
    assert Activity is not None

# ===== Phase 3: 信任服务集成 =====
def test_trust_service():
    from app.services.trust_score_service import TrustScoreService
    assert TrustScoreService is not None

# Run all tests
print("\n--- Phase 1: 基础架构 ---")
test("数据安全核心模块导入", test_data_security)
test("数据安全Gate3导入", test_data_security_gate3)
test("数据安全Quarantine导入", test_data_security_quarantine)
test("数据安全Wolf导入", test_data_security_wolf)
test("支付宝支付模块导入", test_payment_alipay)
test("微信支付模块导入", test_payment_wxpay)
test("支付SDK模块导入", test_payment_sdk)
test("信任引擎模块导入", test_trust_engine)

print("\n--- Phase 2: 业务模块 ---")
test("设计审查模块导入", test_design_review)
test("创新引擎模块导入", test_innovation_engine)
test("订单模块导入", test_orders)
test("产品模块导入", test_products)
test("推广模块导入", test_promoter)
test("工作流模块导入", test_workflow)
test("联系人模块导入", test_contacts)
test("需求模块导入", test_needs)
test("外部集成模块导入", test_external)
test("活动模块导入", test_activities)

print("\n--- Phase 3: 服务层 ---")
test("信任服务模块导入", test_trust_service)

# Summary
print("\n" + "=" * 60)
total = passed + failed
print(f"  测试结果: {passed}/{total} 通过", "🎉" if failed == 0 else f" ❌ {failed} 失败")
if errors:
    print("\n失败详情:")
    for name, err in errors:
        print(f"  {name}: {err}")
print("=" * 60)
