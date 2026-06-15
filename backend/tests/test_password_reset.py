"""密码重置流程测试：forgot-password + reset-password"""

import time


class TestPasswordReset:
    """密码重置端到端测试"""

    def _register_test_user(self, client, username):
        """注册一个测试用户并返回用户名"""
        client.post(
            "/api/auth/register",
            json={
                "username": username,
                "password": "TestPass123",
                "name": "密码重置测试",
                "phone": "13900009999",
                "company": "测试",
                "position": "测试",
                "role": "buyer",
            },
        )
        return username

    def test_forgot_password_user_exists(self, client):
        """已存在用户请求密码重置 - 返回200和重置令牌"""
        resp = client.post(
            "/api/auth/forgot-password",
            json={"email": "buyer1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "reset_token" in data["data"]
        assert len(data["data"]["reset_token"]) > 0

    def test_forgot_password_user_not_exists(self, client):
        """不存在的用户请求密码重置 - 返回200（不暴露用户是否存在）"""
        resp = client.post(
            "/api/auth/forgot-password",
            json={"email": "nonexistent_user_99999@test.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        # 不应返回令牌
        assert data["data"] is None

    def test_reset_password_success(self, client):
        """使用有效令牌重置密码"""
        # 注册一个独立测试用户，避免影响其他测试
        username = f"pwdtest_{int(time.time() * 1000000)}"
        self._register_test_user(client, username)

        # 请求重置令牌
        resp = client.post("/api/auth/forgot-password", json={"email": username})
        assert resp.status_code == 200
        token = resp.json()["data"]["reset_token"]

        new_password = "NewPass12345"
        resp = client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": new_password},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "密码重置成功"

        # 验证可以用新密码登录
        login_resp = client.post(
            "/api/auth/login",
            json={"username": username, "password": new_password},
        )
        assert login_resp.status_code == 200
        assert login_resp.json()["code"] == 200

    def test_reset_password_used_token(self, client):
        """一次性令牌被使用后再次使用应失败"""
        # 注册一个独立测试用户
        username = f"pwdtest2_{int(time.time() * 1000000)}"
        self._register_test_user(client, username)

        # 请求令牌
        resp = client.post("/api/auth/forgot-password", json={"email": username})
        assert resp.status_code == 200
        token = resp.json()["data"]["reset_token"]

        # 第一次使用（成功）
        resp1 = client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "NewPass1"},
        )
        assert resp1.status_code == 200

        # 第二次使用同一令牌（应失败）
        resp2 = client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "AnotherPass123"},
        )
        assert resp2.status_code == 400
        assert "无效" in resp2.text

    def test_reset_password_invalid_token(self, client):
        """无效令牌应返回400"""
        resp = client.post(
            "/api/auth/reset-password",
            json={"token": "invalid-token-12345", "password": "NewPass12345"},
        )
        assert resp.status_code == 400
        assert "无效" in resp.text

    def test_reset_password_short_password(self, client):
        """新密码过短应返回422"""
        resp = client.post(
            "/api/auth/reset-password",
            json={"token": "some-token", "password": "1234567"},  # 7位 < 8位
        )
        assert resp.status_code == 422
