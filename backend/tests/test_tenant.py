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
        """多租户标志位"""
        from app.database import DB_TYPE
        from app.tenant import IS_MULTI_TENANT

        assert IS_MULTI_TENANT == (DB_TYPE == "postgres")
        # 测试环境下应该是False（SQLite）
        assert IS_MULTI_TENANT == False

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
        """SQLite模式下不是多租户"""
        from app.database import is_multi_tenant

        assert is_multi_tenant() == False
