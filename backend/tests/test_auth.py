"""
用户认证测试 (digital_brochure_api)
=====================================
测试用户注册、登录、Token 验证、密码 bcrypt 哈希。

注意: digital_brochure_api.py 的认证功能尚在实现中。
      本文件包含完整测试结构，标记为 skip 的用例代表
      待实现功能，实现后移除 skip 即可。
"""
import pytest

# ============================================================
# Token 验证辅助函数 (直接测试数据库层)
# ============================================================


class TestPasswordHashing:
    """密码 bcrypt 哈希验证 (功能已可用)"""

    def test_bcrypt_hash_and_verify(self):
        """bcrypt 应能正确哈希和验证密码"""
        import bcrypt

        password = "MySecureP@ss123"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # 验证格式 (bcrypt hash 以 $2b$ 开头)
        assert hashed.startswith("$2b$"), f"bcrypt hash 格式错误: {hashed}"
        assert len(hashed) == 60, f"bcrypt hash 长度应为 60: {len(hashed)}"

        # 正确密码应验证通过
        assert bcrypt.checkpw(password.encode(), hashed.encode())

        # 错误密码应验证失败
        assert not bcrypt.checkpw(b"WrongPassword", hashed.encode())

    def test_bcrypt_hash_unique(self):
        """同一密码每次哈希结果应不同（salt 随机性）"""
        import bcrypt

        password = "SamePassword123"
        h1 = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
        h2 = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

        assert h1 != h2, "bcrypt salt 应使每次 hash 不同"
        assert bcrypt.checkpw(password.encode(), h1)
        assert bcrypt.checkpw(password.encode(), h2)

    def test_store_and_verify_password(self, test_db):
        """模拟注册时的密码存储和登录时的验证流程"""
        import bcrypt

        conn = test_db
        cursor = conn.cursor()

        # 模拟注册: 哈希密码并存储
        password = "RegisterP@ss456"
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        cursor.execute(
            """INSERT INTO auth_users (username, password_hash, email, is_active)
               VALUES (?, ?, ?, 1)""",
            ("pass_test_user", password_hash, "pass@test.com"),
        )
        user_id = cursor.lastrowid
        conn.commit()

        # 模拟登录: 从数据库读取 hash 并验证
        cursor.execute("SELECT password_hash FROM auth_users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        stored_hash = row[0]

        assert bcrypt.checkpw(password.encode(), stored_hash.encode()), "密码验证应通过"
        assert not bcrypt.checkpw(b"wrong_password", stored_hash.encode()), "错误密码应拒绝"


class TestAuthTokenManagement:
    """Token 管理测试 (数据库层)"""

    def test_create_token(self, test_db, sample_user_data):
        """应能创建并存储 token"""
        import uuid
        from datetime import datetime, timedelta

        conn = test_db
        cursor = conn.cursor()

        token_str = str(uuid.uuid4())
        expires_at = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """INSERT INTO auth_tokens (user_id, token, token_type, expires_at)
               VALUES (?, ?, 'access', ?)""",
            (sample_user_data["id"], token_str, expires_at),
        )
        token_id = cursor.lastrowid
        conn.commit()

        assert token_id > 0, "Token 创建失败"

        # 验证可查询
        cursor.execute("SELECT * FROM auth_tokens WHERE id = ?", (token_id,))
        token = dict(zip([d[0] for d in cursor.description], cursor.fetchone()))
        assert token["token"] == token_str
        assert token["user_id"] == sample_user_data["id"]
        assert token["revoked"] == 0

    def test_revoke_token(self, test_db, auth_token):
        """应能撤销 token"""
        conn = test_db
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE auth_tokens SET revoked = 1 WHERE id = ?",
            (auth_token["id"],),
        )
        conn.commit()

        cursor.execute("SELECT revoked FROM auth_tokens WHERE id = ?", (auth_token["id"],))
        assert cursor.fetchone()[0] == 1, "Token 应被标记为已撤销"

    def test_expired_token(self, test_db, sample_user_data):
        """过期 token 应被识别"""
        import uuid
        from datetime import datetime, timedelta

        conn = test_db
        cursor = conn.cursor()

        # 创建已过期 token
        token_str = str(uuid.uuid4())
        expires_at = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """INSERT INTO auth_tokens (user_id, token, token_type, expires_at)
               VALUES (?, ?, 'access', ?)""",
            (sample_user_data["id"], token_str, expires_at),
        )
        conn.commit()

        # 验证过期
        cursor.execute(
            """SELECT id FROM auth_tokens
               WHERE token = ? AND revoked = 0 AND expires_at > datetime('now')""",
            (token_str,),
        )
        assert cursor.fetchone() is None, "过期 token 不应被视为有效"


# ============================================================
# API 端点测试 (待实现功能, 用 skip 标记)
# ============================================================


class TestAuthAPI:
    """认证 API 端点测试

    这些测试用例覆盖注册/登录 API 的预期行为。
    当前 digital_brochure_api.py 尚未实现这些端点，
    实现后移除 mark.skip 即可运行。
    """

    @pytest.mark.skip(reason="注册端点尚未实现")
    def test_register_success(self, client):
        """POST /api/v1/digital-brochure/auth/register 应成功注册新用户

        期望:
        - 状态码 201
        - 返回 user_id, username, token
        - 密码已 bcrypt 哈希存储
        """
        resp = client.post("/api/v1/digital-brochure/auth/register", json={
            "username": "newuser",
            "password": "SecureP@ss1",
            "email": "new@example.com",
            "phone": "13700137000",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == 201
        assert "user_id" in data["data"]
        assert "token" in data["data"]

    @pytest.mark.skip(reason="注册端点尚未实现")
    def test_register_duplicate_username(self, client, sample_user_data):
        """重复用户名应返回 409"""
        resp = client.post("/api/v1/digital-brochure/auth/register", json={
            "username": sample_user_data["username"],
            "password": "SecureP@ss1",
        })
        assert resp.status_code == 409

    @pytest.mark.skip(reason="注册端点尚未实现")
    def test_register_invalid_password(self, client):
        """弱密码应返回 422"""
        resp = client.post("/api/v1/digital-brochure/auth/register", json={
            "username": "weakuser",
            "password": "123",
        })
        assert resp.status_code == 422

    @pytest.mark.skip(reason="登录端点尚未实现")
    def test_login_success(self, client, sample_user_data):
        """POST /api/v1/digital-brochure/auth/login 应返回 token"""
        resp = client.post("/api/v1/digital-brochure/auth/login", json={
            "username": sample_user_data["username"],
            "password": sample_user_data["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "token" in data["data"]
        assert data["data"]["token_type"] == "bearer"

    @pytest.mark.skip(reason="登录端点尚未实现")
    def test_login_wrong_password(self, client, sample_user_data):
        """错误密码应返回 401"""
        resp = client.post("/api/v1/digital-brochure/auth/login", json={
            "username": sample_user_data["username"],
            "password": "WrongPassword!",
        })
        assert resp.status_code == 401

    @pytest.mark.skip(reason="登录端点尚未实现")
    def test_login_inactive_user(self, client, test_db, sample_user_data):
        """停用用户应返回 403"""
        conn = test_db
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE auth_users SET is_active = 0 WHERE id = ?",
            (sample_user_data["id"],),
        )
        conn.commit()

        resp = client.post("/api/v1/digital-brochure/auth/login", json={
            "username": sample_user_data["username"],
            "password": sample_user_data["password"],
        })
        assert resp.status_code == 403

    @pytest.mark.skip(reason="Token 验证端点尚未实现")
    def test_verify_token_valid(self, client, auth_token):
        """有效 token 应验证通过"""
        headers = {"Authorization": f"Bearer {auth_token['token']}"}
        resp = client.get("/api/v1/digital-brochure/auth/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["user_id"] == auth_token["user_id"]

    @pytest.mark.skip(reason="Token 验证端点尚未实现")
    def test_verify_token_missing(self, client):
        """无 token 应返回 401"""
        resp = client.get("/api/v1/digital-brochure/auth/me")
        assert resp.status_code == 401

    @pytest.mark.skip(reason="Token 验证端点尚未实现")
    def test_verify_token_invalid(self, client):
        """无效 token 应返回 401"""
        headers = {"Authorization": "Bearer invalid-token-12345"}
        resp = client.get("/api/v1/digital-brochure/auth/me", headers=headers)
        assert resp.status_code == 401

    @pytest.mark.skip(reason="Token 验证端点尚未实现")
    def test_verify_token_revoked(self, client, test_db, auth_token):
        """已撤销 token 应返回 401"""
        conn = test_db
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE auth_tokens SET revoked = 1 WHERE id = ?",
            (auth_token["id"],),
        )
        conn.commit()

        headers = {"Authorization": f"Bearer {auth_token['token']}"}
        resp = client.get("/api/v1/digital-brochure/auth/me", headers=headers)
        assert resp.status_code == 401

    @pytest.mark.skip(reason="Token 验证端点尚未实现")
    def test_verify_token_expired(self, client, test_db, sample_user_data):
        """过期 token 应返回 401"""
        import uuid
        from datetime import datetime, timedelta

        conn = test_db
        cursor = conn.cursor()
        token_str = str(uuid.uuid4())
        expires_at = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """INSERT INTO auth_tokens (user_id, token, token_type, expires_at)
               VALUES (?, ?, 'access', ?)""",
            (sample_user_data["id"], token_str, expires_at),
        )
        conn.commit()

        headers = {"Authorization": f"Bearer {token_str}"}
        resp = client.get("/api/v1/digital-brochure/auth/me", headers=headers)
        assert resp.status_code == 401
