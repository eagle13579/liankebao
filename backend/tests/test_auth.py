"""认证模块测试：注册/登录/令牌刷新/权限边界"""

import time

from fastapi.testclient import TestClient


class TestAuth:
    """认证核心流程测试"""

    def test_register_success(self, client: TestClient):
        """正常注册新用户"""
        username = f"newuser_{int(time.time() * 1000000)}"
        resp = client.post(
            "/api/auth/register",
            json={
                "username": username,
                "password": "TestPass123",
                "name": "新用户",
                "phone": "13900009999",
                "company": "新公司",
                "position": "经理",
                "role": "buyer",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["username"] == username
        assert data["data"]["role"] == "buyer"
        assert "password" not in str(data["data"])

    def test_login_success(self, client: TestClient):
        """正常登录返回 access_token 和 refresh_token"""
        resp = client.post(
            "/api/auth/login",
            json={
                "username": "buyer1",
                "password": "Test1234",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"
        assert data["data"]["user"]["username"] == "buyer1"

    def test_refresh_token(self, client: TestClient):
        """使用 refresh_token 获取新的 access_token"""
        # 先登录获取 refresh_token
        login_resp = client.post(
            "/api/auth/login",
            json={
                "username": "buyer1",
                "password": "Test1234",
            },
        )
        refresh_token = login_resp.json()["data"]["refresh_token"]

        # 刷新令牌
        resp = client.post(
            "/api/auth/refresh",
            json={
                "refresh_token": refresh_token,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        # 新的 refresh_token 应与旧的不同（轮换机制）
        assert data["data"]["refresh_token"] != refresh_token

    def test_login_wrong_password(self, client: TestClient):
        """密码错误时登录返回 401"""
        resp = client.post(
            "/api/auth/login",
            json={
                "username": "buyer1",
                "password": "WrongPassword999",
            },
        )
        assert resp.status_code == 401
        data = resp.json()
        assert "密码错误" in data.get("detail", "") or "错误" in str(data)

    def test_register_duplicate_username(self, client: TestClient):
        """重复用户名注册返回 400"""
        resp = client.post(
            "/api/auth/register",
            json={
                "username": "buyer1",  # 种子数据中已存在
                "password": "AnotherPass123",
                "name": "重复用户",
                "phone": "13900009998",
                "company": "测试公司",
                "position": "经理",
                "role": "buyer",
            },
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "已存在" in data.get("detail", "") or "已存在" in str(data)

    def test_expired_token_denied(self, client: TestClient):
        """使用过期或伪造的 token 访问受保护接口应返回 401"""
        fake_token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJidXllcjEiLCJyb2xlIjoiYnV5ZXIiLCJleHAiOjE1MTYyMzkwMjJ9.abc123"
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {fake_token}"})
        assert resp.status_code in (401, 403)
        body = resp.json()
        assert "无效" in str(body) or "认证" in str(body)

    def test_login_nonexistent_user(self, client: TestClient):
        """不存在的用户名登录返回 401"""
        resp = client.post(
            "/api/auth/login",
            json={
                "username": "nonexistent_user_99999",
                "password": "Test1234",
            },
        )
        assert resp.status_code == 401
        assert "错误" in resp.text
