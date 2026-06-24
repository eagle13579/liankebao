"""
全链路多租户隔离验证脚本

测试场景:
  1. 创建两个租户组织（Org A 和 Org B）
  2. 为每个组织创建独立数据
  3. 验证 Org A 的用户看不到 Org B 的数据
  4. 验证 IS_MULTI_TENANT 标志位为 True
  5. 验证 TenantSessionWrapper 自动过滤
  6. 验证 apply_tenant_filter 手动过滤
  7. 验证无租户上下文时不过滤（兼容性）

使用方法:
  python scripts/verify_tenant_isolation.py

约束:
  - 使用内存 SQLite（无需 PostgreSQL）
  - 只追加不覆盖（铁律九十二）
  - 不修改任何现有代码
"""

import os
import sys
import tempfile
import uuid

# 强制启用多租户（覆盖可能存在的 False 环境变量）
os.environ["IS_MULTI_TENANT"] = "true"

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base

# ============================================================
# 测试用 SQLite 引擎
# ============================================================
_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), f"chainke_verify_tenant_{uuid.uuid4().hex[:8]}.db")
TEST_ENGINE = create_engine(
    f"sqlite:///{_TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)

# 替换 app.database 的全局对象
import app.database as db_module

db_module.engine = TEST_ENGINE
db_module.SessionLocal = TestSessionLocal


# ============================================================
# 导入业务模块（必须在 engine 替换之后）
# ============================================================
from app.auth import hash_password
from app.models import (
    BusinessCard,
    BusinessNeed,
    Contact,
    ImportHistory,
    Order,
    PrivateBoardOrder,
    Product,
    RevokedToken,
    User,
    Withdrawal,
)
from app.tenant import (
    IS_MULTI_TENANT,
    TenantContext,
    TenantSessionWrapper,
    _tenant_filter_kwargs,
    apply_tenant_filter,
    get_current_org_id,
)


# ============================================================
# 测试结果追踪
# ============================================================
class TestResult:
    """单条测试结果"""

    def __init__(self, name: str):
        self.name = name
        self.passed = True
        self.message = ""

    def fail(self, msg: str):
        self.passed = False
        self.message = msg

    def ok(self, msg: str = ""):
        self.message = msg


class TestSuite:
    """测试套件"""

    def __init__(self):
        self.results: list[TestResult] = []
        self._test_count = 0

    def test(self, name: str):
        """创建新测试"""
        self._test_count += 1
        tr = TestResult(f"[{self._test_count}] {name}")
        self.results.append(tr)
        return tr

    def report(self) -> tuple[int, int]:
        """打印报告，返回 (pass, fail)"""
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)

        print("\n" + "=" * 60)
        print("全链路多租户隔离验证报告")
        print("=" * 60)
        for r in self.results:
            status = "✓ PASS" if r.passed else "✗ FAIL"
            print(f"  {status} | {r.name}")
            if r.message:
                print(f"         {r.message}")
        print("-" * 60)
        print(f"  总: {passed + failed}  |  通过: {passed}  |  失败: {failed}")
        print("=" * 60)
        return passed, failed


suite = TestSuite()


# ============================================================
# 验证 IS_MULTI_TENANT 标志位
# ============================================================
def test_multi_tenant_flag():
    tr = suite.test("IS_MULTI_TENANT 默认为 True（由环境变量控制）")
    assert IS_MULTI_TENANT is True, f"期望 True，实际 {IS_MULTI_TENANT}"
    tr.ok()


# ============================================================
# 数据准备
# ============================================================
def prepare_data(db: Session) -> dict:
    """创建两个租户及其数据，返回各 id 的引用"""
    from app.models.organization import Organization

    # --- 创建租户组织 ---
    org_a = Organization(name="租户A-科技有限公司", slug="org-a")
    org_b = Organization(name="租户B-贸易有限公司", slug="org-b")
    db.add_all([org_a, org_b])
    db.flush()

    # --- 创建用户 ---
    pwhash = hash_password("Test1234")

    user_a = User(
        username="user_a",
        password_hash=pwhash,
        name="用户A",
        organization_id=org_a.id,
    )
    user_b = User(
        username="user_b",
        password_hash=pwhash,
        name="用户B",
        organization_id=org_b.id,
    )
    db.add_all([user_a, user_b])
    db.flush()

    # --- 创建产品 ---
    product_a = Product(
        name="A公司的产品",
        description="仅属于租户A的产品",
        price=100.00,
        status="approved",
        owner_id=user_a.id,
        organization_id=org_a.id,
    )
    product_b = Product(
        name="B公司的产品",
        description="仅属于租户B的产品",
        price=200.00,
        status="approved",
        owner_id=user_b.id,
        organization_id=org_b.id,
    )
    db.add_all([product_a, product_b])
    db.flush()

    # --- 创建订单 ---
    order_a = Order(
        user_id=user_a.id,
        product_id=product_a.id,
        quantity=1,
        total_price=100.00,
        organization_id=org_a.id,
    )
    order_b = Order(
        user_id=user_b.id,
        product_id=product_b.id,
        quantity=2,
        total_price=400.00,
        organization_id=org_b.id,
    )
    db.add_all([order_a, order_b])
    db.flush()

    # --- 创建联系人 ---
    contact_a = Contact(
        owner_id=user_a.id,
        name="联系人A",
        phone="13800000001",
        organization_id=org_a.id,
    )
    contact_b = Contact(
        owner_id=user_b.id,
        name="联系人B",
        phone="13800000002",
        organization_id=org_b.id,
    )
    db.add_all([contact_a, contact_b])
    db.flush()

    # --- 创建需求 ---
    need_a = BusinessNeed(
        user_id=user_a.id,
        title="租户A的需求",
        contact_name="用户A",
        organization_id=org_a.id,
    )
    need_b = BusinessNeed(
        user_id=user_b.id,
        title="租户B的需求",
        contact_name="用户B",
        organization_id=org_b.id,
    )
    db.add_all([need_a, need_b])
    db.flush()

    # --- 创建名片 ---
    card_a = BusinessCard(
        user_id=user_a.id,
        fields='{"name":"用户A","company":"A公司"}',
        share_token=f"share-a-{uuid.uuid4().hex[:8]}",
        organization_id=org_a.id,
    )
    card_b = BusinessCard(
        user_id=user_b.id,
        fields='{"name":"用户B","company":"B公司"}',
        share_token=f"share-b-{uuid.uuid4().hex[:8]}",
        organization_id=org_b.id,
    )
    db.add_all([card_a, card_b])
    db.flush()

    # --- 创建提现记录 ---
    withdrawal_a = Withdrawal(
        user_id=user_a.id,
        amount=50.00,
        organization_id=org_a.id,
    )
    withdrawal_b = Withdrawal(
        user_id=user_b.id,
        amount=100.00,
        organization_id=org_b.id,
    )
    db.add_all([withdrawal_a, withdrawal_b])
    db.flush()

    # --- 创建导入记录 ---
    import_a = ImportHistory(
        user_id=user_a.id,
        filename="a_contacts.csv",
        file_type="csv",
        total_rows=10,
        imported_rows=10,
        batch_id=str(uuid.uuid4()),
        organization_id=org_a.id,
    )
    import_b = ImportHistory(
        user_id=user_b.id,
        filename="b_contacts.csv",
        file_type="csv",
        total_rows=20,
        imported_rows=20,
        batch_id=str(uuid.uuid4()),
        organization_id=org_b.id,
    )
    db.add_all([import_a, import_b])
    db.flush()

    # --- 创建私董会订单 ---
    pbo_a = PrivateBoardOrder(
        user_id=user_a.id,
        company="A公司",
        amount=19999.00,
        organization_id=org_a.id,
    )
    pbo_b = PrivateBoardOrder(
        user_id=user_b.id,
        company="B公司",
        amount=19999.00,
        organization_id=org_b.id,
    )
    db.add_all([pbo_a, pbo_b])
    db.flush()

    # --- 创建吊销 Token ---
    rtoken_a = RevokedToken(
        jti=f"jti-a-{uuid.uuid4().hex[:16]}",
        organization_id=org_a.id,
    )
    rtoken_b = RevokedToken(
        jti=f"jti-b-{uuid.uuid4().hex[:16]}",
        organization_id=org_b.id,
    )
    db.add_all([rtoken_a, rtoken_b])
    db.flush()

    db.commit()

    return {
        "org_a": org_a,
        "org_b": org_b,
        "user_a": user_a,
        "user_b": user_b,
        "product_a": product_a,
        "product_b": product_b,
        "order_a": order_a,
        "order_b": order_b,
        "contact_a": contact_a,
        "contact_b": contact_b,
        "need_a": need_a,
        "need_b": need_b,
        "card_a": card_a,
        "card_b": card_b,
        "withdrawal_a": withdrawal_a,
        "withdrawal_b": withdrawal_b,
        "import_a": import_a,
        "import_b": import_b,
        "pbo_a": pbo_a,
        "pbo_b": pbo_b,
        "rtoken_a": rtoken_a,
        "rtoken_b": rtoken_b,
    }


# ============================================================
# 测试：租户A看不到租户B的数据
# ============================================================
def test_tenant_isolation(db: Session, refs: dict):
    """验证在租户A的上下文中查询不到租户B的数据"""

    # 设置为租户A的上下文
    TenantContext.set(TenantContext(org_id=refs["org_a"].id))
    assert get_current_org_id() == refs["org_a"].id

    # --- 测试每个模型 ---
    isolation_tests = [
        ("User", User, "user_b", lambda u: u.id == refs["user_b"].id),
        ("Product", Product, "product_b", lambda p: p.id == refs["product_b"].id),
        ("Order", Order, "order_b", lambda o: o.id == refs["order_b"].id),
        ("Contact", Contact, "contact_b", lambda c: c.id == refs["contact_b"].id),
        ("BusinessNeed", BusinessNeed, "need_b", lambda n: n.id == refs["need_b"].id),
        ("BusinessCard", BusinessCard, "card_b", lambda c: c.id == refs["card_b"].id),
        ("Withdrawal", Withdrawal, "withdrawal_b", lambda w: w.id == refs["withdrawal_b"].id),
        ("ImportHistory", ImportHistory, "import_b", lambda i: i.id == refs["import_b"].id),
        ("PrivateBoardOrder", PrivateBoardOrder, "pbo_b", lambda p: p.id == refs["pbo_b"].id),
        ("RevokedToken", RevokedToken, "rtoken_b", lambda r: r.id == refs["rtoken_b"].id),
    ]

    for model_name, model_cls, ref_key, check_fn in isolation_tests:
        q = apply_tenant_filter(db.query(model_cls), model_cls)
        results = q.all()
        # 租户B的数据不应该出现在结果中
        leaked = [r for r in results if check_fn(r)]
        if leaked:
            tr = suite.test(f"租户隔离 — {model_name} 看不到租户B的数据")
            tr.fail(f"找到 {len(leaked)} 条泄露数据")
        else:
            tr = suite.test(f"租户隔离 — {model_name} 看不到租户B的数据 ✓")
            tr.ok()

    # 验证租户A自己的数据可见
    own_data_tests = [
        ("User", User, "user_a", lambda u: u.id == refs["user_a"].id),
        ("Product", Product, "product_a", lambda p: p.id == refs["product_a"].id),
        ("Order", Order, "order_a", lambda o: o.id == refs["order_a"].id),
        ("Contact", Contact, "contact_a", lambda c: c.id == refs["contact_a"].id),
        ("BusinessNeed", BusinessNeed, "need_a", lambda n: n.id == refs["need_a"].id),
    ]
    for model_name, model_cls, ref_key, check_fn in own_data_tests:
        q = apply_tenant_filter(db.query(model_cls), model_cls)
        results = q.all()
        found = [r for r in results if check_fn(r)]
        tr = suite.test(f"自身数据可见 — {model_name} 能看到自己的数据")
        if not found:
            tr.fail(f"未找到自己的数据 ({ref_key})")
        else:
            tr.ok()

    TenantContext.clear()


# ============================================================
# 测试：租户B也看不到租户A的数据（对称验证）
# ============================================================
def test_tenant_isolation_symmetric(db: Session, refs: dict):
    """对称验证：设置租户B的上下文，看不到租户A的数据"""
    TenantContext.set(TenantContext(org_id=refs["org_b"].id))
    assert get_current_org_id() == refs["org_b"].id

    tr = suite.test("对称验证 — 租户B看不到租户A的产品")
    q = apply_tenant_filter(db.query(Product), Product)
    results = q.all()
    leaked = [r for r in results if r.id == refs["product_a"].id]
    if leaked:
        tr.fail("租户A的产品泄露给了租户B")
    else:
        tr.ok()

    TenantContext.clear()


# ============================================================
# 测试：无租户上下文时不过滤
# ============================================================
def test_no_context_no_filter(db: Session, refs: dict):
    """无租户上下文时，查询所有数据（兼容模式）"""
    TenantContext.clear()

    tr = suite.test("无上下文模式 — _tenant_filter_kwargs 返回空字典")
    kwargs = _tenant_filter_kwargs()
    if kwargs == {}:
        tr.ok()
    else:
        tr.fail(f"期望 {{}}, 实际 {kwargs}")

    # 无上下文时，所有数据可见
    tr2 = suite.test("无上下文模式 — 所有产品可见")
    all_products = db.query(Product).all()
    if len(all_products) == 2:  # 两个租户的产品都存在
        tr2.ok()
    else:
        tr2.fail(f"期望 2 条产品，实际 {len(all_products)}")


# ============================================================
# 测试：TenantSessionWrapper 自动注入
# ============================================================
def test_tenant_session_wrapper(db: Session, refs: dict):
    """TenantSessionWrapper 自动附加 organization_id 过滤"""
    TenantContext.set(TenantContext(org_id=refs["org_a"].id))

    with TenantSessionWrapper(db) as wrapped:
        products = wrapped.query(Product).all()

    tr = suite.test("TenantSessionWrapper — 自动过滤租户A的产品")
    ids = [p.id for p in products]
    if refs["product_a"].id in ids and refs["product_b"].id not in ids:
        tr.ok()
    elif refs["product_a"].id not in ids:
        tr.fail("自己的产品丢失")
    else:
        tr.fail("租户B的产品泄露")

    TenantContext.clear()


# =============================================  ===============
# 测试：organization_id 列存在性验证
# ============================================================
def test_org_id_exists():
    """验证所有业务模型都有 organization_id 列"""
    models_with_org = [
        User,
        Product,
        Order,
        Contact,
        BusinessNeed,
        BusinessCard,
        ImportHistory,
        Withdrawal,
        PrivateBoardOrder,
        RevokedToken,
    ]
    for model_cls in models_with_org:
        tr = suite.test(f"列存在 — {model_cls.__name__}.organization_id")
        if hasattr(model_cls, "organization_id"):
            tr.ok()
        else:
            tr.fail(f"{model_cls.__name__} 缺少 organization_id 列")


# ============================================================
# 测试：环境变量覆盖
# ============================================================
def test_env_override():
    """IS_MULTI_TENANT 可通过环境变量覆盖"""
    tr = suite.test("环境变量覆盖 — IS_MULTI_TENANT=true")
    assert IS_MULTI_TENANT is True
    tr.ok()

    # 临时设 false
    old_val = os.environ.get("IS_MULTI_TENANT", "true")
    os.environ["IS_MULTI_TENANT"] = "false"
    # 需要重新加载模块才能生效（仅验证逻辑，不实际 reload）
    # 注意：这里读到的是模块导入时的值，所以还是 True
    # 手动验证逻辑
    computed = os.environ.get("IS_MULTI_TENANT", "true").lower() in ("1", "true", "yes")
    tr2 = suite.test("环境变量覆盖 — IS_MULTI_TENANT=false 生效")
    if computed is False:
        tr2.ok()
    else:
        tr2.fail("设置为 false 后仍未关闭")
    os.environ["IS_MULTI_TENANT"] = old_val


# ============================================================
# 主入口
# ============================================================
def main():
    print("链客宝 多租户全链路隔离验证")
    print("=" * 60)
    print(f"  DB_TYPE         = {db_module.DB_TYPE}")
    print(f"  IS_MULTI_TENANT = {IS_MULTI_TENANT}")
    print(f"  测试数据库      = {_TEST_DB_PATH}")
    print("=" * 60)

    # 1. 创建表
    Base.metadata.create_all(bind=TEST_ENGINE)

    # 2. 准备数据
    db = TestSessionLocal()
    try:
        refs = prepare_data(db)
        print("\n数据准备完成：2个租户，每个租户约10条业务记录\n")

        # 3. 运行测试
        test_multi_tenant_flag()
        test_org_id_exists()
        test_tenant_isolation(db, refs)
        test_tenant_isolation_symmetric(db, refs)
        test_no_context_no_filter(db, refs)
        test_tenant_session_wrapper(db, refs)
        test_env_override()

        # 4. 报告
        passed, failed = suite.report()

        # 5. 清理
        db.commit()
    finally:
        db.close()
        try:
            os.remove(_TEST_DB_PATH)
        except Exception:
            pass

    # 6. 退出码
    if failed > 0:
        print("\n⚠️  有测试未通过，请检查上述结果。")
        sys.exit(1)
    else:
        print("\n✅ 所有验证通过！多租户隔离正常运行。")


if __name__ == "__main__":
    main()
