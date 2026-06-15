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
        user = data["data"]["user"]
        assert user["username"] == username
        assert user["role"] == "buyer"
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


class TestAuthExtended:
    """认证模块扩展测试：logout / forgot-password / reset-password"""

    def test_logout_success(self, client, buyer_token):
        """正常退出登录"""
        headers = {"Authorization": f"Bearer {buyer_token}"}
        resp = client.post("/api/auth/logout", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200

    def test_logout_twice(self, client, buyer_token):
        """重复退出：第一次成功，第二次 token 已失效返回 401"""
        headers = {"Authorization": f"Bearer {buyer_token}"}
        resp1 = client.post("/api/auth/logout", headers=headers)
        assert resp1.status_code == 200
        # 使用同一个 token 再次退出（已加入黑名单，token 失效）
        resp2 = client.post("/api/auth/logout", headers=headers)
        assert resp2.status_code in (400, 401, 403)

    def test_logout_unauthenticated(self, client):
        """未登录退出返回 401"""
        resp = client.post("/api/auth/logout")
        assert resp.status_code in (401, 403)

    def test_logout_no_header(self, client):
        """无认证头退出返回 400 或 401"""
        resp = client.post("/api/auth/logout", headers={"Authorization": "Bearer "})
        assert resp.status_code in (400, 401, 403)

    def test_forgot_password_existing_user(self, client):
        """已存在用户请求密码重置"""
        resp = client.post(
            "/api/auth/forgot-password",
            json={"email": "buyer1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        # 开发阶段直接返回 reset_token
        assert "reset_token" in data["data"]

    def test_forgot_password_nonexistent_user(self, client):
        """不存在的用户请求密码重置（安全起见仍返回 200）"""
        resp = client.post(
            "/api/auth/forgot-password",
            json={"email": "nonexistent_user_99999"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200

    def test_forgot_password_invalid_email(self, client):
        """空邮箱请求密码重置"""
        resp = client.post(
            "/api/auth/forgot-password",
            json={"email": ""},
        )
        # 空字符串可能通过验证也可能被拒绝
        assert resp.status_code in (200, 422)

    def test_reset_password_success(self, client):
        """正常重置密码流程：先 forgot 获取 token，再用 token 重置"""
        # Step 1: forgot-password 获取 reset_token
        forgot_resp = client.post(
            "/api/auth/forgot-password",
            json={"email": "buyer1"},
        )
        assert forgot_resp.status_code == 200
        reset_token = forgot_resp.json()["data"]["reset_token"]

        # Step 2: 用 token 重置密码
        resp = client.post(
            "/api/auth/reset-password",
            json={"token": reset_token, "password": "NewPass12345"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "密码重置成功"

        # Step 3: 用新密码登录
        login_resp = client.post(
            "/api/auth/login",
            json={"username": "buyer1", "password": "NewPass12345"},
        )
        assert login_resp.status_code == 200

    def test_reset_password_invalid_token(self, client):
        """无效的重置令牌返回 400"""
        resp = client.post(
            "/api/auth/reset-password",
            json={"token": "invalid-token-12345", "password": "NewPass12345"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "无效" in data.get("detail", "")

    def test_reset_password_short_password(self, client):
        """密码太短返回 400"""
        resp = client.post(
            "/api/auth/reset-password",
            json={"token": "some-token", "password": "short"},
        )
        assert resp.status_code in (400, 422)
