"""
认证模块测试：登录/令牌
（已适配 chainke-full 认证系统：
  - admin/admin123 → role: admin
  - dev/dev123 → role: developer
  - JWT token 返回在 "token" 字段）
"""

from fastapi.testclient import TestClient


class TestAuth:
    """认证核心流程测试"""

    LOGIN_URL = "/api/auth/login"

    def test_login_admin_success(self, client: TestClient):
        """admin 登录成功返回 token"""
        resp = client.post(
            self.LOGIN_URL,
            json={"username": "admin", "password": "admin123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "admin"
        assert data["user"]["role"] == "admin"

    def test_login_dev_success(self, client: TestClient):
        """dev 登录成功返回 token"""
        resp = client.post(
            self.LOGIN_URL,
            json={"username": "dev", "password": "dev123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "dev"
        assert data["user"]["role"] == "developer"

    def test_login_wrong_password(self, client: TestClient):
        """密码错误返回 401"""
        resp = client.post(
            self.LOGIN_URL,
            json={"username": "admin", "password": "wrongpassword"},
        )
        assert resp.status_code == 401
        data = resp.json()
        assert "detail" in data

    def test_login_nonexistent_user(self, client: TestClient):
        """不存在的用户返回 401"""
        resp = client.post(
            self.LOGIN_URL,
            json={"username": "nonexistent_user", "password": "Test1234"},
        )
        assert resp.status_code == 401

    def test_login_missing_fields(self, client: TestClient):
        """缺少字段返回 422"""
        resp = client.post(self.LOGIN_URL, json={})
        assert resp.status_code == 422

    def test_auth_header_protects_api(self, client: TestClient):
        """未认证访问受保护端点返回 401"""
        resp = client.get("/api/contacts")
        assert resp.status_code == 401

    def test_auth_header_with_valid_token(self, client: TestClient):
        """有效 token 可访问受保护端点"""
        login_resp = client.post(
            self.LOGIN_URL,
            json={"username": "admin", "password": "admin123"},
        )
        token = login_resp.json()["token"]
        resp = client.get(
            "/api/contacts",
            headers={"Authorization": f"Bearer {token}"},
        )
        # 即使没有数据，也应返回 200 而非 401
        assert resp.status_code in (200, 404)
