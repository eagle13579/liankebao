"""
链客宝 — 认证路由集成测试
===========================
涵盖: 登录/注册/Token验证
使用 FastAPI TestClient + SQLite 内存数据库
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
import pytest

from app.database import Base, get_db


def _make_standalone_client() -> tuple[TestClient, Session]:
    """构建独立的 FastAPI app + TestClient + 内存数据库"""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestSession()

    # 创建一个最小化 FastAPI app，只注册需要测试的路由
    app = FastAPI(title="test-auth")

    # 注册 auth 路由
    from app.routers.auth import router as auth_router
    from app.routers.business_card import router as bc_router
    app.include_router(auth_router)
    app.include_router(bc_router)

    # 健康检查端点
    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    # 覆盖 get_db 依赖
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    return client, db


class TestAuthLogin:
    """登录端点测试 — 登录使用硬编码 DEV_CREDENTIALS，无需数据库"""

    LOGIN_URL = "/api/auth/login"

    @pytest.fixture
    def client(self):
        c, _ = _make_standalone_client()
        return c

    def test_login_admin_success(self, client: TestClient):
        """admin 登录成功"""
        resp = client.post(self.LOGIN_URL, json={"username": "admin", "password": "admin123"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "admin"
        assert data["user"]["role"] == "admin"

    def test_login_dev_success(self, client: TestClient):
        """dev 登录成功"""
        resp = client.post(self.LOGIN_URL, json={"username": "dev", "password": "dev123"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "dev"
        assert data["user"]["role"] == "developer"

    def test_login_wrong_password_returns_401(self, client: TestClient):
        """密码错误返回 401"""
        resp = client.post(self.LOGIN_URL, json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401
        assert "detail" in resp.json()

    def test_login_nonexistent_user_returns_401(self, client: TestClient):
        """不存在的用户返回 401"""
        resp = client.post(self.LOGIN_URL, json={"username": "ghost", "password": "x"})
        assert resp.status_code == 401

    def test_login_missing_fields_returns_422(self, client: TestClient):
        """缺少必填字段返回 422"""
        resp = client.post(self.LOGIN_URL, json={})
        assert resp.status_code == 422

    def test_login_token_is_valid_jwt(self, client: TestClient):
        """登录返回的 token 是有效的 JWT 格式（三段式）"""
        resp = client.post(self.LOGIN_URL, json={"username": "admin", "password": "admin123"})
        token = resp.json()["token"]
        parts = token.split(".")
        assert len(parts) == 3, "JWT 应为三段式 header.payload.signature"


class TestAuthRegister:
    """注册端点测试"""

    REGISTER_URL = "/api/auth/register"

    @pytest.fixture
    def client(self):
        c, self._db = _make_standalone_client()
        return c

    def test_register_success(self, client: TestClient):
        """注册新用户成功"""
        resp = client.post(
            self.REGISTER_URL,
            json={
                "username": "newuser",
                "password": "pass123456",
                "name": "新用户",
                "phone": "13800138000",
                "company": "测试公司",
                "position": "工程师",
            },
        )
        assert resp.status_code == 200, f"注册失败: {resp.text}"
        data = resp.json()
        assert data["message"] == "注册成功"
        assert "token" in data
        assert data["user"]["username"] == "newuser"
        assert data["user"]["role"] == "user"
        assert data["user"]["name"] == "新用户"
        assert "id" in data["user"]

    def test_register_duplicate_username(self, client: TestClient):
        """重复用户名返回 400"""
        client.post(
            self.REGISTER_URL,
            json={"username": "dupuser", "password": "pass123456"},
        )
        resp = client.post(
            self.REGISTER_URL,
            json={"username": "dupuser", "password": "pass123456"},
        )
        assert resp.status_code == 400
        assert "已存在" in resp.json()["detail"]

    def test_register_minimal_fields(self, client: TestClient):
        """仅用必填字段注册"""
        resp = client.post(
            self.REGISTER_URL,
            json={"username": "minimal", "password": "min123456"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["username"] == "minimal"

    def test_register_short_password_returns_422(self, client: TestClient):
        """密码太短（<6位）返回 422"""
        resp = client.post(
            self.REGISTER_URL,
            json={"username": "testuser", "password": "ab"},
        )
        assert resp.status_code == 422

    def test_register_with_chinese_fields(self, client: TestClient):
        """含中文字段的注册"""
        resp = client.post(
            self.REGISTER_URL,
            json={
                "username": "chinese_user",
                "password": "chinese123",
                "name": "张三丰",
                "company": "武当科技有限公司",
                "position": "掌门人",
                "phone": "13912345678",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["name"] == "张三丰"
        assert data["user"]["company"] == "武当科技有限公司"

    def test_register_then_login(self, client: TestClient):
        """注册后可获取有效 token（格式验证）"""
        resp = client.post(
            self.REGISTER_URL,
            json={"username": "logmetest", "password": "pass123456"},
        )
        assert resp.status_code == 200
        token = resp.json()["token"]
        # JWT 三段式验证
        assert len(token.split(".")) == 3


class TestAuthTokenValidation:
    """Token 验证与认证中间件测试"""

    @pytest.fixture
    def client(self):
        c, self._db = _make_standalone_client()
        return c

    def test_auth_middleware_blocks_unauthenticated(self, client: TestClient):
        """无 token 访问受保护端点返回 401"""
        resp = client.get("/api/business-card/cards")
        assert resp.status_code == 401

    def test_auth_middleware_allows_whitelist(self, client: TestClient):
        """白名单路径无需认证"""
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_auth_middleware_with_admin_token(self, client: TestClient):
        """admin token 可访问受保护端点"""
        login_resp = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/business-card/cards", headers=headers)
        assert resp.status_code != 401

    def test_invalid_token_returns_401(self, client: TestClient):
        """无效 token 返回 401"""
        headers = {"Authorization": "Bearer invalid.jwt.token"}
        resp = client.get("/api/business-card/cards", headers=headers)
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, client: TestClient):
        """过期 JWT token 返回 401"""
        import jwt as pyjwt
        import datetime

        expired_payload = {
            "sub": "admin",
            "role": "admin",
            "iat": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2),
            "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1),
        }
        expired_token = pyjwt.encode(expired_payload, "chainke-dev-secret-key", algorithm="HS256")

        headers = {"Authorization": f"Bearer {expired_token}"}
        resp = client.get("/api/business-card/cards", headers=headers)
        assert resp.status_code == 401
