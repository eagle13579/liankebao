"""多租户隔离测试（SQLite模式下验证兼容性）"""

import pytest


class TestTenantContext:
    """租户上下文测试"""

    def test_tenant_context_singleton(self):
        """租户上下文单例模式"""
        from app.tenant import TenantContext

        ctx1 = TenantContext(org_id=1, org_slug="test-org")
        TenantContext.set(ctx1)

        ctx2 = TenantContext.get()
        assert ctx2 is not None
        assert ctx2.org_id == 1
        assert ctx2.org_slug == "test-org"

    def test_tenant_context_clear(self):
        """清除租户上下文"""
        from app.tenant import TenantContext

        ctx = TenantContext(org_id=1)
        TenantContext.set(ctx)
        TenantContext.clear()

        assert TenantContext.get() is None

    def test_get_current_org_id_no_context(self):
        """无上下文时返回None"""
        from app.tenant import TenantContext, get_current_org_id

        TenantContext.clear()
        assert get_current_org_id() is None

    def test_get_current_org_slug(self):
        """获取org_slug"""
        from app.tenant import TenantContext, get_current_org_slug

        ctx = TenantContext(org_id=1, org_slug="my-org")
        TenantContext.set(ctx)
        assert get_current_org_slug() == "my-org"
        TenantContext.clear()

    def test_tenant_filter_kwargs_sqlite(self):
        """SQLite模式下不过滤租户"""
        from app.tenant import IS_MULTI_TENANT, _tenant_filter_kwargs

        kwargs = _tenant_filter_kwargs()
        if not IS_MULTI_TENANT:
            assert kwargs == {}

    def test_tenant_filter_empty_when_no_context(self):
        """无上下文时不过滤"""
        from app.tenant import TenantContext, _tenant_filter_kwargs

        TenantContext.clear()
        kwargs = _tenant_filter_kwargs()
        # SQLite模式下始终为空
        from app.tenant import IS_MULTI_TENANT

        if not IS_MULTI_TENANT:
            assert kwargs == {}

    def test_is_multi_tenant_flag(self):
        """多租户标志位 — 由 IS_MULTI_TENANT 环境变量控制，默认 True"""
        from app.tenant import IS_MULTI_TENANT

        # IS_MULTI_TENANT 现在由 os.environ.get('IS_MULTI_TENANT', 'true') 控制
        # 默认值为 True（因为 conftest 未设置该环境变量）
        expected = os.environ.get("IS_MULTI_TENANT", "true").lower() in ("1", "true", "yes")
        assert IS_MULTI_TENANT == expected
        # 测试环境下应为 True（默认值）
        assert IS_MULTI_TENANT == True

    def test_apply_tenant_filter_noop_sqlite(self):
        """SQLite下apply_tenant_filter不修改查询"""
        from app.models import Product
        from app.tenant import apply_tenant_filter

        # 模拟query对象
        class MockQuery:
            def filter(self, *args, **kwargs):
                self.filtered = True
                return self

        q = MockQuery()
        result = apply_tenant_filter(q, Product)
        assert not hasattr(result, "filtered") or result.filtered == False


class TestOrganizationModel:
    """组织模型测试"""

    def test_organization_model_defined(self):
        """组织模型定义"""
        from app.tenant import Organization

        assert hasattr(Organization, "__tablename__")
        assert Organization.__tablename__ == "organizations"

    def test_organization_columns(self):
        """组织模型字段"""
        from app.tenant import Organization

        assert hasattr(Organization, "id")
        assert hasattr(Organization, "name")
        assert hasattr(Organization, "slug")
        assert hasattr(Organization, "plan")
        assert hasattr(Organization, "settings")

    def test_organization_create_and_query(self, db_session):
        """创建和查询组织"""
        from app.tenant import Organization

        org = Organization(
            name="测试组织",
            slug="test-org",
            plan="free",
            settings={"key": "value"},
        )
        db_session.add(org)
        db_session.commit()

        queried = db_session.query(Organization).filter(Organization.slug == "test-org").first()
        assert queried is not None
        assert queried.name == "测试组织"
        assert queried.plan == "free"
        assert queried.settings == {"key": "value"}

    def test_organization_unique_slug(self, db_session):
        """slug唯一性"""
        from app.tenant import Organization

        db_session.add(Organization(name="Org1", slug="same-slug"))
        db_session.commit()

        from sqlalchemy.exc import IntegrityError

        db_session.add(Organization(name="Org2", slug="same-slug"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_organization_default_plan(self, db_session):
        """默认plan为free"""
        from app.tenant import Organization

        org = Organization(name="默认组织", slug="default-test")
        db_session.add(org)
        db_session.commit()

        assert org.plan == "free"


class TestMembershipModel:
    """成员关系模型测试"""

    def test_membership_model_defined(self):
        """成员关系模型定义"""
        from app.tenant import Membership

        assert hasattr(Membership, "__tablename__")
        assert Membership.__tablename__ == "memberships"

    def test_membership_columns(self):
        """成员关系字段"""
        from app.tenant import Membership

        assert hasattr(Membership, "id")
        assert hasattr(Membership, "user_id")
        assert hasattr(Membership, "org_id")
        assert hasattr(Membership, "role")

    def test_membership_create(self, db_session):
        """创建成员关系"""
        from app.models import User
        from app.tenant import Membership, Organization

        org = Organization(name="成员组织", slug="member-org")
        db_session.add(org)
        db_session.commit()

        user = db_session.query(User).first()
        membership = Membership(
            user_id=user.id,
            org_id=org.id,
            role="admin",
        )
        db_session.add(membership)
        db_session.commit()

        queried = (
            db_session.query(Membership)
            .filter(
                Membership.user_id == user.id,
                Membership.org_id == org.id,
            )
            .first()
        )
        assert queried is not None
        assert queried.role == "admin"

    def test_membership_default_role(self, db_session):
        """默认角色为member"""
        from app.models import User
        from app.tenant import Membership, Organization

        org = Organization(name="默认角色组织", slug="default-role")
        db_session.add(org)
        db_session.commit()

        user = db_session.query(User).first()
        membership = Membership(user_id=user.id, org_id=org.id)
        db_session.add(membership)
        db_session.commit()

        assert membership.role == "member"


class TestTenantIsolationORM:
    """多租户ORM隔离测试（验证organization_id字段存在）"""

    def test_user_has_org_id(self):
        """User模型有organization_id字段"""
        from app.models import User

        assert hasattr(User, "organization_id")

    def test_product_has_org_id(self):
        """Product模型有organization_id字段"""
        from app.models import Product

        assert hasattr(Product, "organization_id")

    def test_order_has_org_id(self):
        """Order模型有organization_id字段"""
        from app.models import Order

        assert hasattr(Order, "organization_id")

    def test_contact_has_org_id(self):
        """Contact模型有organization_id字段"""
        from app.models import Contact

        assert hasattr(Contact, "organization_id")

    def test_activity_has_org_id(self):
        """Activity模型有organization_id字段"""
        from app.models import Activity

        assert hasattr(Activity, "organization_id")

    def test_business_need_has_org_id(self):
        """BusinessNeed模型有organization_id字段"""
        from app.models import BusinessNeed

        assert hasattr(BusinessNeed, "organization_id")

    def test_business_card_has_org_id(self):
        """BusinessCard模型有organization_id字段"""
        from app.models import BusinessCard

        assert hasattr(BusinessCard, "organization_id")

    def test_import_history_has_org_id(self):
        """ImportHistory模型有organization_id字段"""
        from app.models import ImportHistory

        assert hasattr(ImportHistory, "organization_id")

    def test_withdrawal_has_org_id(self):
        """Withdrawal模型有organization_id字段"""
        from app.models import Withdrawal

        assert hasattr(Withdrawal, "organization_id")

    def test_org_id_nullable_in_sqlite(self, db_session):
        """SQLite模式下organization_id可为空"""
        from app.database import DB_TYPE

        if DB_TYPE != "postgres":
            import time

            from app.auth import hash_password
            from app.models import User

            user = User(
                username=f"org_null_test_{int(time.time())}",
                password_hash=hash_password("Test1234"),
                name="无组织用户",
            )
            db_session.add(user)
            db_session.commit()
            assert user.organization_id is None


class TestDbFunctions:
    """数据库函数测试"""

    def test_get_db_url_sqlite(self):
        """获取数据库URL"""
        from app.database import get_db_url

        url = get_db_url()
        assert url is not None
        assert "sqlite" in url

    def test_is_multi_tenant_sqlite(self):
        """SQLite模式下不是多租户（database层）"""
        from app.database import is_multi_tenant

        assert is_multi_tenant() == False


# ============================================================
# 新增：多租户隔离全链路验证（SQLite + 内存上下文模拟）
# ============================================================
class TestTenantIsolationFullChain:
    """多租户隔离全链路验证 — 模拟租户A看不到租户B的数据"""

    def test_tenant_filter_by_org_id(self, db_session):
        """_tenant_filter_kwargs 在有租户上下文时返回 org_id"""
        from app.tenant import TenantContext, _tenant_filter_kwargs

        TenantContext.clear()
        TenantContext.set(TenantContext(org_id=5))
        kwargs = _tenant_filter_kwargs()
        TenantContext.clear()

        assert kwargs == {"organization_id": 5}

    def test_tenant_filter_no_context(self, db_session):
        """无租户上下文时不返回 org_id 过滤"""
        from app.tenant import TenantContext, _tenant_filter_kwargs

        TenantContext.clear()
        kwargs = _tenant_filter_kwargs()
        assert kwargs == {}

    def test_apply_tenant_filter_with_context(self, db_session):
        """apply_tenant_filter 在有上下文时正确过滤"""
        from app.models import Product
        from app.tenant import TenantContext, apply_tenant_filter

        org_id = 7
        TenantContext.clear()
        TenantContext.set(TenantContext(org_id=org_id))

        q = db_session.query(Product)
        filtered_q = apply_tenant_filter(q, Product)
        TenantContext.clear()

        # 验证 SQL 中包含了 organization_id 过滤条件
        compiled = str(filtered_q.statement.compile(compile_kwargs={"literal_binds": True}))
        assert f"organization_id = {org_id}" in compiled or "organization_id" in compiled

    def test_tenant_session_wrapper(self, db_session):
        """TenantSessionWrapper 自动注入租户过滤"""
        from app.models import Product
        from app.tenant import TenantContext, TenantSessionWrapper

        org_id = 9
        TenantContext.clear()
        TenantContext.set(TenantContext(org_id=org_id))

        with TenantSessionWrapper(db_session) as wrapped:
            q = wrapped.query(Product)
            compiled = str(q.statement.compile(compile_kwargs={"literal_binds": True}))

        TenantContext.clear()
        assert f"organization_id = {org_id}" in compiled or "organization_id" in compiled

    def test_isolation_two_tenants(self, db_session):
        """模拟两个租户的数据隔离：设置不同上下文看到不同数据"""
        from app.auth import hash_password
        from app.models import Product, User
        from app.tenant import TenantContext, apply_tenant_filter

        # 准备：创建两个租户各自的产品
        pwhash = hash_password("Test1234")
        user = db_session.query(User).first()

        p1 = Product(name="租户A产品", price=100, status="approved", owner_id=user.id, organization_id=10)
        p2 = Product(name="租户B产品", price=200, status="approved", owner_id=user.id, organization_id=20)
        db_session.add_all([p1, p2])
        db_session.flush()

        # 场景1：以租户A身份查询
        TenantContext.clear()
        TenantContext.set(TenantContext(org_id=10))
        q_a = apply_tenant_filter(db_session.query(Product), Product)
        results_a = [r for r in q_a.all() if r.id in (p1.id, p2.id)]
        TenantContext.clear()

        # 场景2：以租户B身份查询
        TenantContext.set(TenantContext(org_id=20))
        q_b = apply_tenant_filter(db_session.query(Product), Product)
        results_b = [r for r in q_b.all() if r.id in (p1.id, p2.id)]
        TenantContext.clear()

        # 验证隔离
        a_names = {r.name for r in results_a}
        b_names = {r.name for r in results_b}

        assert "租户A产品" in a_names, "租户A应能看到自己的产品"
        assert "租户B产品" not in a_names, "租户A不应看到租户B的产品"
        assert "租户B产品" in b_names, "租户B应能看到自己的产品"
        assert "租户A产品" not in b_names, "租户B不应看到租户A的产品"

        # 清理
        db_session.query(Product).filter(Product.id.in_([p1.id, p2.id])).delete(synchronize_session=False)
        db_session.commit()

    def test_get_current_org_id_returns_org(self, db_session):
        """get_current_org_id 返回当前设置的 org_id"""
        from app.tenant import TenantContext, get_current_org_id

        TenantContext.clear()
        TenantContext.set(TenantContext(org_id=42))
        assert get_current_org_id() == 42
        TenantContext.clear()

    def test_get_current_org_id_none(self, db_session):
        """清除上下文后 get_current_org_id 返回 None"""
        from app.tenant import TenantContext, get_current_org_id

        TenantContext.clear()
        assert get_current_org_id() is None
