"""
认证模块测试
============
- 注册成功 / 密码太短
- 登录成功（返回 access_token + refresh_token）
- 登录频率限制（超过 10 次 / 5 分钟被限制）
- 刷新 token
- 退出登录（blacklist）
"""
import pytest
from fastapi.testclient import TestClient


class TestRegister:
    """用户注册测试"""

    REGISTER_URL = "/api/auth/register"

    def test_register_success(self, client: TestClient):
        """注册成功：合法手机号（通过schema校验）+ 密码 >= 8 位"""
        resp = client.post(
            self.REGISTER_URL,
            json={
                "username": "13800138000",  # 手机号：通过schema + router双重校验
                "password": "Pass1234",
                "name": "测试用户",
                "phone": "13800138000",
                "company": "测试公司",
                "position": "测试职位",
                "role": "buyer",
            },
        )
        assert resp.status_code == 200, f"注册应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "注册成功"
        assert data["data"]["username"] == "13800138000"
        assert data["data"]["role"] == "buyer"
        # 密码不应出现在响应中
        assert "password" not in data["data"]
        assert "password_hash" not in data["data"]

    def test_register_duplicate_username(self, client: TestClient):
        """重复手机号注册应返回 400"""
        # 先注册一个新用户
        resp = client.post(
            self.REGISTER_URL,
            json={
                "username": "13900139000",
                "password": "Pass1234",
                "name": "新用户",
                "phone": "13900139000",
            },
        )
        assert resp.status_code == 200, f"首次注册应成功: {resp.text}"

        # 再次用相同用户名注册
        resp = client.post(
            self.REGISTER_URL,
            json={
                "username": "13900139000",
                "password": "Pass1234",
                "name": "重复用户",
            },
        )
        assert resp.status_code == 400, "重复用户名应被拒绝"
        assert "用户名已存在" in resp.text

    def test_register_password_too_short(self, client: TestClient):
        """密码少于 8 位应返回 400"""
        # Pydantic 校验会在请求体层面拦截（min_length=8），
        # 但我们同时也测业务层的校验逻辑
        resp = client.post(
            self.REGISTER_URL,
            json={
                "username": "shortpwd@test.com",
                "password": "123",  # 少于 8 位
                "name": "密码太短",
            },
        )
        # Pydantic 校验未通过返回 422
        assert resp.status_code in (400, 422), f"短密码应被拒绝: {resp.text}"

    def test_register_invalid_username(self, client: TestClient):
        """非邮箱/非手机号的用户名应返回 400"""
        resp = client.post(
            self.REGISTER_URL,
            json={
                "username": "invalid!@#$",  # 非法字符且非邮箱/手机
                "password": "Pass1234",
                "name": "非法用户名",
            },
        )
        assert resp.status_code in (400, 422), f"非法用户名应被拒绝: {resp.text}"


class TestLogin:
    """用户登录测试"""

    LOGIN_URL = "/api/auth/login"

    def test_login_success(self, client: TestClient):
        """登录成功：应返回 access_token 和 refresh_token"""
        resp = client.post(
            self.LOGIN_URL,
            json={"username": "buyer1", "password": "Test1234"},
        )
        assert resp.status_code == 200, f"登录应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "登录成功"

        token_data = data["data"]
        assert "access_token" in token_data, "缺少 access_token"
        assert "refresh_token" in token_data, "缺少 refresh_token"
        assert token_data["token_type"] == "bearer"
        assert token_data["user"]["username"] == "buyer1"
        assert token_data["user"]["role"] == "buyer"

        # 验证 token 格式（JWT 应包含两个点）
        assert token_data["access_token"].count(".") == 2
        assert token_data["refresh_token"].count(".") == 2

    def test_login_wrong_password(self, client: TestClient):
        """错误密码应返回 401"""
        resp = client.post(
            self.LOGIN_URL,
            json={"username": "buyer1", "password": "WrongPass1"},
        )
        assert resp.status_code == 401, f"错误密码应返回 401: {resp.text}"

    def test_login_nonexistent_user(self, client: TestClient):
        """不存在的用户应返回 401"""
        resp = client.post(
            self.LOGIN_URL,
            json={"username": "nobody", "password": "Test1234"},
        )
        assert resp.status_code == 401, f"不存在用户应返回 401: {resp.text}"

    def test_login_rate_limit(self, client: TestClient):
        """
        登录频率限制：超过 10 次 / 5 分钟被限
        _login_attempts 已在 conftest clean_global_state 中清空
        """
        # 在 5 分钟窗口内连续发送 11 次请求
        for i in range(10):
            resp = client.post(
                self.LOGIN_URL,
                json={"username": "wrong_user", "password": "WrongPass1"},
            )
            # 前 10 次应返回 401（密码错误），而不是 429
            assert resp.status_code in (401, 422), f"第 {i+1} 次登录不应被限流: {resp.text}"

        # 第 11 次应被限流
        resp = client.post(
            self.LOGIN_URL,
            json={"username": "buyer1", "password": "Test1234"},
        )
        assert resp.status_code == 429, f"第 11 次应被限流: {resp.text}"
        assert "过于频繁" in resp.text or "429" in resp.text


class TestRefreshToken:
    """刷新 token 测试"""

    REFRESH_URL = "/api/auth/refresh"

    def test_refresh_token_success(self, client: TestClient):
        """使用 refresh_token 获取新的 access_token + refresh_token（轮换）"""
        # 先登录获取 refresh_token
        login_resp = client.post(
            "/api/auth/login",
            json={"username": "buyer1", "password": "Test1234"},
        )
        assert login_resp.status_code == 200
        old_refresh = login_resp.json()["data"]["refresh_token"]

        # 刷新 token
        resp = client.post(
            self.REFRESH_URL,
            json={"refresh_token": old_refresh},
        )
        assert resp.status_code == 200, f"刷新应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "token刷新成功"

        new_tokens = data["data"]
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens
        assert new_tokens["token_type"] == "bearer"

        # 新的 token 应与旧的不同（轮换机制）
        assert new_tokens["refresh_token"] != old_refresh, "refresh_token 应轮换"

        # 旧 refresh_token 应已失效
        resp2 = client.post(
            self.REFRESH_URL,
            json={"refresh_token": old_refresh},
        )
        assert resp2.status_code == 401, f"旧 refresh_token 应已失效: {resp2.text}"

    def test_refresh_invalid_token(self, client: TestClient):
        """无效的 refresh_token 应返回 401"""
        resp = client.post(
            self.REFRESH_URL,
            json={"refresh_token": "invalid.jwt.token"},
        )
        assert resp.status_code == 401, f"无效 token 应返回 401: {resp.text}"

    def test_refresh_with_access_token(self, client: TestClient):
        """用 access_token 刷新应失败（type 不匹配）"""
        login_resp = client.post(
            "/api/auth/login",
            json={"username": "buyer1", "password": "Test1234"},
        )
        access_token = login_resp.json()["data"]["access_token"]

        resp = client.post(
            self.REFRESH_URL,
            json={"refresh_token": access_token},
        )
        assert resp.status_code == 401, "access_token 不应能刷新"


class TestLogout:
    """退出登录测试"""

    LOGOUT_URL = "/api/auth/logout"

    def test_logout_success(self, client: TestClient, buyer_headers):
        """退出登录：将 token 加入黑名单，再次使用应失效"""
        # 正常请求（带 token 的 /api/auth/me）
        me_resp = client.get("/api/auth/me", headers=buyer_headers)
        assert me_resp.status_code == 200, "token 应有效"

        # 退出登录
        resp = client.post(self.LOGOUT_URL, headers=buyer_headers)
        assert resp.status_code == 200, f"退出应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] in ("退出登录成功", "token 已失效")

        # 再次使用同一 token 应被拒绝
        me_resp2 = client.get("/api/auth/me", headers=buyer_headers)
        assert me_resp2.status_code == 401, "退出后 token 应失效"

    def test_logout_without_token(self, client: TestClient):
        """未携带 token 调用退出应返回 401"""
        resp = client.post(self.LOGOUT_URL)
        assert resp.status_code == 401, "未登录不应能退出"
