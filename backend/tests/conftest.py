"""
pytest 测试配置
================
- 内存 SQLite 测试数据库（自动创建表 + 种子数据）
- httpx.TestClient（FastAPI 自带）
- 四个测试用户：admin / buyer1 / promoter1 / supplier1（密码均为 "Test1234"）
- 自动清理登录频率限制和 token 黑名单
- 自动替换 app.database.engine / SessionLocal / get_db 为测试专用版本
"""
import sys
import os
import json
from typing import Generator, Dict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from passlib.hash import bcrypt as bcrypt_hasher

# ------------------------------------------------------------
# 将项目根目录加入 sys.path，确保 from app.xxx 可正常导入
# ------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ------------------------------------------------------------
# 必须在任何 app 模块导入前设定测试环境变量
# ------------------------------------------------------------
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")

# ------------------------------------------------------------
# 创建内存 SQLite 引擎（测试专用）
# ------------------------------------------------------------
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    echo=False,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)

# ------------------------------------------------------------
# 导入 app 模块并立即替换数据库为测试专用
# ------------------------------------------------------------
import app.database as db_module
from app.database import Base
from app.models import User, Product, Order, Withdrawal

# 保存原始 get_db 函数引用（route 模块 import 时捕获的就是这个对象）
_original_get_db = db_module.get_db

# 替换 app.database 的全局对象，使任何直接引用 engine/SessionLocal 的代码都走测试库
db_module.engine = TEST_ENGINE
db_module.SessionLocal = TestSessionLocal

from app.main import app

# 移除启动事件处理函数（init_db），因为我们自行管理数据库
app.router.on_startup.clear()


# ============================================================
# 测试数据库 session 生成器（替代 app.database.get_db）
# ============================================================
def override_get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖覆盖：使用内存 SQLite 的 session"""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# 在 FastAPI 依赖注入系统中注册 override
# 注意：key 必须是 route 模块 import 时捕获的那个原始 get_db 函数对象
app.dependency_overrides[_original_get_db] = override_get_db

# 同时替换 module-level 引用以兜底
db_module.get_db = override_get_db


# ============================================================
# 种子数据密码哈希（预先算好提升性能）
# ============================================================
_TEST_PWHASH = bcrypt_hasher.hash("Test1234")

_TEST_USERS = [
    User(
        username="admin",
        password_hash=_TEST_PWHASH,
        name="管理员",
        phone="13800000000",
        company="链客宝科技",
        position="系统管理员",
        role="admin",
        avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=admin",
    ),
    User(
        username="buyer1",
        password_hash=_TEST_PWHASH,
        name="张三",
        phone="13800000001",
        company="创新科技有限公司",
        position="CEO",
        role="buyer",
        avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=buyer1",
    ),
    User(
        username="promoter1",
        password_hash=_TEST_PWHASH,
        name="李四",
        phone="13800000002",
        company="推广联盟",
        position="高级推广员",
        role="promoter",
        avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=promoter1",
    ),
    User(
        username="supplier1",
        password_hash=_TEST_PWHASH,
        name="王五",
        phone="13800000003",
        company="供应链集团",
        position="销售总监",
        role="supplier",
        avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=supplier1",
    ),
]


def _seed_data(db: Session) -> Dict[str, User]:
    """填充种子数据，返回 {username: user_obj} 字典"""
    db.add_all(_TEST_USERS)
    db.flush()

    users = {u.username: u for u in db.query(User).all()}

    supplier = users["supplier1"]
    products = [
        Product(
            name="测试产品 A",
            description="这是一个测试产品 A 的描述",
            price=100.00,
            earn_per_share=20.00,
            category="电子产品",
            brand="测试品牌",
            stock=100,
            images=json.dumps(["https://example.com/img1.jpg"]),
            specs=json.dumps({"规格": "标准版"}),
            tags="测试,电子",
            is_featured=1,
            sort_order=1,
            status="approved",
            owner_id=supplier.id,
        ),
        Product(
            name="测试产品 B（待审核）",
            description="待审核产品描述",
            price=200.00,
            earn_per_share=40.00,
            category="食品",
            stock=50,
            status="pending",
            owner_id=supplier.id,
        ),
        Product(
            name="测试产品 C",
            description="另一个已上架产品",
            price=50.00,
            earn_per_share=10.00,
            category="日用品",
            stock=200,
            status="approved",
            owner_id=supplier.id,
        ),
    ]
    db.add_all(products)
    db.flush()
    products_in_db = db.query(Product).all()

    buyer = users["buyer1"]
    promoter = users["promoter1"]
    orders = [
        Order(
            user_id=buyer.id,
            product_id=products_in_db[0].id,
            quantity=2,
            total_price=200.00,
            status="received",
            promoter_id=promoter.id,
            commission=20.00,
        ),
        Order(
            user_id=buyer.id,
            product_id=products_in_db[2].id,
            quantity=1,
            total_price=50.00,
            status="paid",
            promoter_id=promoter.id,
            commission=5.00,
        ),
    ]
    db.add_all(orders)
    db.flush()

    withdrawals = [
        Withdrawal(
            user_id=promoter.id,
            amount=10.00,
            status="approved",
            bank_info=json.dumps({"bank_name": "中国银行", "card_number": "6222****1234", "holder_name": "李四"}),
        ),
        Withdrawal(
            user_id=promoter.id,
            amount=5.00,
            status="pending",
            bank_info=json.dumps({"bank_name": "中国银行", "card_number": "6222****1234", "holder_name": "李四"}),
        ),
    ]
    db.add_all(withdrawals)

    db.commit()
    return users


# ============================================================
# session 级别 fixture：一次性初始化数据库 + 种子数据
# ============================================================
@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """创建所有表并填充种子数据（仅一次 / session）"""
    # 在 TestClient 启动前创建表和种子数据
    Base.metadata.create_all(bind=TEST_ENGINE)
    db = TestSessionLocal()
    try:
        _seed_data(db)
    finally:
        db.close()
    yield


# ============================================================
# function 级别 fixture：清理 rate-limit + blacklist
# ============================================================
@pytest.fixture(autouse=True)
def clean_global_state():
    """每次测试前清理登录频率限制和 token 黑名单（均为内存级状态）"""
    from app.routers.auth import _login_attempts
    _login_attempts.clear()
    from app.auth import _token_blacklist
    _token_blacklist.clear()
    yield


# ============================================================
# TestClient fixture
# ============================================================
@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """
    返回 override 了中间件和依赖的 TestClient。
    数据库依赖已在模块加载时通过 app.dependency_overrides 全局注册。
    """
    # 移除不兼容的旧式中间件（RequestLogMiddleware 使用旧式 (request, call_next) 签名）
    app.user_middleware = [
        m for m in app.user_middleware
        if m.cls.__name__ != "RequestLogMiddleware"
    ]
    app.middleware_stack = None

    with TestClient(app) as c:
        yield c


# ============================================================
# 辅助 fixture：各角色登录后的 headers（含 Authorization）
# ============================================================
@pytest.fixture
def buyer_token(client: TestClient) -> str:
    resp = client.post("/api/auth/login", json={"username": "buyer1", "password": "Test1234"})
    assert resp.status_code == 200, f"buyer1 登录失败: {resp.text}"
    return resp.json()["data"]["access_token"]


@pytest.fixture
def promoter_token(client: TestClient) -> str:
    resp = client.post("/api/auth/login", json={"username": "promoter1", "password": "Test1234"})
    assert resp.status_code == 200, f"promoter1 登录失败: {resp.text}"
    return resp.json()["data"]["access_token"]


@pytest.fixture
def admin_token(client: TestClient) -> str:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "Test1234"})
    assert resp.status_code == 200, f"admin 登录失败: {resp.text}"
    return resp.json()["data"]["access_token"]


@pytest.fixture
def supplier_token(client: TestClient) -> str:
    resp = client.post("/api/auth/login", json={"username": "supplier1", "password": "Test1234"})
    assert resp.status_code == 200, f"supplier1 登录失败: {resp.text}"
    return resp.json()["data"]["access_token"]


@pytest.fixture
def buyer_headers(buyer_token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {buyer_token}"}


@pytest.fixture
def promoter_headers(promoter_token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {promoter_token}"}


@pytest.fixture
def admin_headers(admin_token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def supplier_headers(supplier_token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {supplier_token}"}
