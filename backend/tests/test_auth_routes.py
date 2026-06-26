"""链客宝 — auth.py 路由集成测试（5个测试）
===========================================
测试: 注册新用户、登录成功、登录失败、token验证、重复注册
使用 FastAPI TestClient + SQLite 内存数据库
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest
import jwt as pyjwt

# 必须确保 User 模型在 Base.metadata 上注册
from app.database import Base
from app.models import User  # noqa: F401 — registers User on Base
from app.models.user import hash_password  # noqa: F401
from app.database import get_db


@pytest.fixture
def client_with_db():
    """创建独立的 FastAPI app + SQLite 内存数据库（StaticPool 保证单连接）"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestSession()

    app = FastAPI(title="test-auth-routes")
    from app.routers.auth import router as auth_router

    app.include_router(auth_router)

    # 覆盖 get_db 依赖
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    yield client
    db.close()


class TestAuthRoutes:
    """auth.py 路由的5个核心集成测试"""

    LOGIN_URL = "/api/auth/login"
    REGISTER_URL = "/api/auth/register"

    # ================================================================
    # 测试1: 注册新用户成功
    # ================================================================
    def test_register_new_user(self, client_with_db):
        """注册新用户返回200，包含token和用户信息"""
        resp = client_with_db.post(
            self.REGISTER_URL,
            json={
                "username": "testuser",
                "password": "test123456",
                "name": "测试用户",
                "phone": "13800138000",
            },
        )
        assert resp.status_code == 200, f"注册失败: {resp.text}"
        data = resp.json()
        assert data["message"] == "注册成功"
        assert "token" in data
        assert data["user"]["username"] == "testuser"
        assert data["user"]["name"] == "测试用户"
        assert data["user"]["role"] == "user"
        assert "id" in data["user"]

    # ================================================================
    # 测试2: 登录成功（使用硬编码的dev账号）
    # ================================================================
    def test_login_success(self, client_with_db):
        """admin账号登录成功，返回JWT token"""
        resp = client_with_db.post(
            self.LOGIN_URL,
            json={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 200, f"登录失败: {resp.text}"
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "admin"
        assert data["user"]["role"] == "admin"
        parts = data["token"].split(".")
        assert len(parts) == 3, "JWT 应为三段式 header.payload.signature"

    # ================================================================
    # 测试3: 登录失败（错误密码返回401）
    # ================================================================
    def test_login_wrong_password(self, client_with_db):
        """错误密码登录返回401"""
        resp = client_with_db.post(
            self.LOGIN_URL,
            json={"username": "admin", "password": "wrongpass"},
        )
        assert resp.status_code == 401
        assert "用户名或密码错误" in resp.json()["detail"]

    # ================================================================
    # 测试4: token验证 — 注册返回的token可解码验证
    # ================================================================
    def test_token_validation(self, client_with_db):
        """注册返回的JWT token可解码，包含sub、user_id、role等字段"""
        resp = client_with_db.post(
            self.REGISTER_URL,
            json={"username": "tokenuser", "password": "tokenpass123"},
        )
        assert resp.status_code == 200
        token = resp.json()["token"]

        payload = pyjwt.decode(
            token,
            "chainke-dev-secret-key",
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
        assert payload["sub"] == "tokenuser"
        assert payload["role"] == "user"
        assert "user_id" in payload
        assert "iat" in payload
        assert "exp" in payload

    # ================================================================
    # 测试5: 重复注册返回400
    # ================================================================
    def test_register_duplicate_username(self, client_with_db):
        """重复用户名注册返回400"""
        resp1 = client_with_db.post(
            self.REGISTER_URL,
            json={"username": "dupuser", "password": "pass123456"},
        )
        assert resp1.status_code == 200

        resp2 = client_with_db.post(
            self.REGISTER_URL,
            json={"username": "dupuser", "password": "pass123456"},
        )
        assert resp2.status_code == 400
        assert "已存在" in resp2.json()["detail"]
