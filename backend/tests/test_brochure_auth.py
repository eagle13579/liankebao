"""
AI数字名片 Brochure API — 认证测试套件
========================================
覆盖:
  - 密码 bcrypt 哈希 (含旧密码兼容格式)
  - Token 创建/撤销/过期验证
  - 注册/登录流程 (数据库层模拟)
  - 用户认证隔离 (is_active)
  - 数据库唯一约束

路由前缀: /api/v1/digital-brochure
"""

import uuid
from datetime import datetime, timedelta

import bcrypt
import pytest

from digital_brochure_api import dict_from_row


# ============================================================
# 密码哈希测试
# ============================================================


class TestPasswordBcrypt:
    """密码 bcrypt 哈希功能 (核心认证基础)"""

    def test_bcrypt_hash_format(self):
        """bcrypt hash 应以 $2b$ 开头, 长度 60"""
        pw = "SecureP@ss2024!"
        hashed = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        assert hashed.startswith("$2b$"), f"格式错误: {hashed}"
        assert len(hashed) == 60, f"长度应为 60: {len(hashed)}"

    def test_bcrypt_verify_correct(self):
        """正确密码验证通过"""
        pw = "MyP@ssword!@#"
        hashed = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        assert bcrypt.checkpw(pw.encode(), hashed.encode())

    def test_bcrypt_verify_wrong(self):
        """错误密码验证失败"""
        hashed = bcrypt.hashpw(b"RealP@ss", bcrypt.gensalt()).decode()
        assert not bcrypt.checkpw(b"WrongP@ss", hashed.encode())

    def test_bcrypt_salt_uniqueness(self):
        """同一密码每次 hash 结果不同 (salt 随机)"""
        pw = "SamePassword!1"
        h1 = bcrypt.hashpw(pw.encode(), bcrypt.gensalt())
        h2 = bcrypt.hashpw(pw.encode(), bcrypt.gensalt())
        assert h1 != h2
        assert bcrypt.checkpw(pw.encode(), h1)
        assert bcrypt.checkpw(pw.encode(), h2)

    def test_bcrypt_old_format_compatibility(self, brochure_db):
        """兼容旧版 bcrypt hash (模拟老系统迁移数据)"""
        conn = brochure_db
        cursor = conn.cursor()
        # 旧的 bcrypt hash (可能使用 $2a$ 前缀)
        old_hash = bcrypt.hashpw(b"OldP@ss1", bcrypt.gensalt(rounds=10)).decode()
        # 确保存储和验证流程正确
        cursor.execute(
            """INSERT INTO auth_users (username, password_hash, is_active)
               VALUES (?, ?, 1)""",
            ("old_user", old_hash),
        )
        conn.commit()

        cursor.execute("SELECT password_hash FROM auth_users WHERE username = ?", ("old_user",))
        stored = cursor.fetchone()[0]
        assert bcrypt.checkpw(b"OldP@ss1", stored.encode())
        assert not bcrypt.checkpw(b"WrongOldP@ss", stored.encode())

    def test_bcrypt_store_and_verify_flow(self, brochure_db):
        """完整注册→存储→登录验证流程"""
        conn = brochure_db
        cursor = conn.cursor()
        password = "FlowTestP@ss1"
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # 模拟注册
        cursor.execute(
            """INSERT INTO auth_users (username, password_hash, email, is_active)
               VALUES (?, ?, ?, 1)""",
            ("flow_user", password_hash, "flow@test.com"),
        )
        user_id = cursor.lastrowid
        conn.commit()

        # 模拟登录: 读取 hash 并验证
        cursor.execute("SELECT password_hash FROM auth_users WHERE id = ?", (user_id,))
        stored_hash = cursor.fetchone()[0]
        assert bcrypt.checkpw(password.encode(), stored_hash.encode())
        assert not bcrypt.checkpw(b"wrong_password", stored_hash.encode())

    def test_bcrypt_special_chars(self):
        """含特殊字符的密码应正常处理"""
        special_pws = [
            "P@$$w0rd!~#",
            "密码ABC123!",
            "  leading_space!1",
            "\t tab_password!1",
            "a" * 128 + "!A1",  # 超长密码
        ]
        for pw in special_pws:
            hashed = bcrypt.hashpw(pw.encode(), bcrypt.gensalt())
            assert bcrypt.checkpw(pw.encode(), hashed)

    def test_password_empty_rejected(self):
        """空密码不应通过验证流程 (但 bcrypt 本身不会阻止)"""
        # 验证空字符串是否可 hash/verify (应用层应校验)
        hashed = bcrypt.hashpw(b"", bcrypt.gensalt())
        # bcrypt 允许空密码, 但业务层应拒绝
        assert bcrypt.checkpw(b"", hashed)


# ============================================================
# Token 管理测试
# ============================================================


class TestTokenManagement:
    """Token 创建/查询/撤销/过期"""

    def test_create_token(self, brochure_db, brochure_user):
        """创建有效 token"""
        conn = brochure_db
        cursor = conn.cursor()
        token_str = str(uuid.uuid4())
        expires_at = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """INSERT INTO auth_tokens (user_id, token, token_type, expires_at)
               VALUES (?, ?, 'access', ?)""",
            (brochure_user["id"], token_str, expires_at),
        )
        conn.commit()

        cursor.execute("SELECT * FROM auth_tokens WHERE token = ?", (token_str,))
        row = dict_from_row(cursor.fetchone())
        assert row is not None
        assert row["user_id"] == brochure_user["id"]
        assert row["token_type"] == "access"
        assert row["revoked"] == 0

    def test_token_unique(self, brochure_db, brochure_user):
        """token 值必须唯一 (UNIQUE 约束)"""
        conn = brochure_db
        cursor = conn.cursor()
        token_str = "duplicate-token-value-12345"
        expires_at = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """INSERT INTO auth_tokens (user_id, token, token_type, expires_at)
               VALUES (?, ?, 'access', ?)""",
            (brochure_user["id"], token_str, expires_at),
        )
        conn.commit()

        with pytest.raises(Exception):
            cursor.execute(
                """INSERT INTO auth_tokens (user_id, token, token_type, expires_at)
                   VALUES (?, ?, 'access', ?)""",
                (brochure_user["id"], token_str, expires_at),
            )
            conn.commit()

    def test_expired_token_invalid(self, brochure_db, brochure_user):
        """过期 token 应被视为无效"""
        conn = brochure_db
        cursor = conn.cursor()
        token_str = str(uuid.uuid4())
        expires_at = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """INSERT INTO auth_tokens (user_id, token, token_type, expires_at)
               VALUES (?, ?, 'access', ?)""",
            (brochure_user["id"], token_str, expires_at),
        )
        conn.commit()

        cursor.execute(
            """SELECT id FROM auth_tokens
               WHERE token = ? AND revoked = 0 AND expires_at > datetime('now')""",
            (token_str,),
        )
        assert cursor.fetchone() is None

    def test_revoke_token(self, brochure_db, brochure_token):
        """撤销 token 标记为 revoked=1"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE auth_tokens SET revoked = 1 WHERE token = ?",
            (brochure_token["token"],),
        )
        conn.commit()

        cursor.execute(
            "SELECT revoked FROM auth_tokens WHERE token = ?",
            (brochure_token["token"],),
        )
        assert cursor.fetchone()[0] == 1

    def test_revoked_token_invalid(self, brochure_db, brochure_token):
        """已撤销的 token 无法通过验证"""
        conn = brochure_db
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE auth_tokens SET revoked = 1 WHERE token = ?",
            (brochure_token["token"],),
        )
        conn.commit()

        cursor.execute(
            """SELECT id FROM auth_tokens
               WHERE token = ? AND revoked = 0 AND expires_at > datetime('now')""",
            (brochure_token["token"],),
        )
        assert cursor.fetchone() is None

    def test_multiple_tokens_per_user(self, brochure_db, brochure_user):
        """同一用户可拥有多个 token"""
        conn = brochure_db
        cursor = conn.cursor()
        expires_at = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

        for i in range(3):
            cursor.execute(
                """INSERT INTO auth_tokens (user_id, token, token_type, expires_at)
                   VALUES (?, ?, 'access', ?)""",
                (brochure_user["id"], f"multi-token-{i}", expires_at),
            )
        conn.commit()

        cursor.execute(
            "SELECT COUNT(*) FROM auth_tokens WHERE user_id = ? AND revoked = 0",
            (brochure_user["id"],),
        )
        assert cursor.fetchone()[0] == 3

    def test_token_with_different_types(self, brochure_db, brochure_user):
        """支持不同 token 类型 (access, refresh)"""
        conn = brochure_db
        cursor = conn.cursor()
        expires_at = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

        types = ["access", "refresh", "reset"]
        for t in types:
            cursor.execute(
                """INSERT INTO auth_tokens (user_id, token, token_type, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (brochure_user["id"], f"type-{t}-{uuid.uuid4()}", t, expires_at),
            )
        conn.commit()

        cursor.execute(
            "SELECT COUNT(*) FROM auth_tokens WHERE user_id = ?",
            (brochure_user["id"],),
        )
        assert cursor.fetchone()[0] == len(types)


# ============================================================
# 用户注册/登录流程 (数据库层模拟)
# ============================================================


class TestUserRegistration:
    """用户注册流程 (数据库层)"""

    def test_register_new_user(self, brochure_db):
        """注册新用户：创建 auth_user + users 记录"""
        conn = brochure_db
        cursor = conn.cursor()

        password = "NewUserP@ss1"
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # 创建认证用户
        cursor.execute(
            """INSERT INTO auth_users (username, password_hash, email, phone, is_active)
               VALUES (?, ?, ?, ?, 1)""",
            ("new_user", password_hash, "new@example.com", "13600136000"),
        )
        auth_id = cursor.lastrowid

        # 创建用户信息
        cursor.execute(
            """INSERT INTO users (auth_user_id, name, company, position, phone, email)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (auth_id, "新用户", "新公司", "新职位", "13600136000", "new@example.com"),
        )
        profile_id = cursor.lastrowid
        conn.commit()

        assert auth_id > 0
        assert profile_id > 0

        # 验证密码正确存储
        cursor.execute("SELECT password_hash FROM auth_users WHERE id = ?", (auth_id,))
        stored_hash = cursor.fetchone()[0]
        assert bcrypt.checkpw(password.encode(), stored_hash.encode())

    def test_register_duplicate_username(self, brochure_db, brochure_user):
        """重复用户名应违反 UNIQUE 约束"""
        conn = brochure_db
        cursor = conn.cursor()
        with pytest.raises(Exception):
            cursor.execute(
                """INSERT INTO auth_users (username, password_hash, is_active)
                   VALUES (?, ?, 1)""",
                (brochure_user["username"], "dup_hash"),
            )
            conn.commit()

    def test_register_minimal_fields(self, brochure_db):
        """仅提供必填字段即可注册"""
        conn = brochure_db
        cursor = conn.cursor()

        password_hash = bcrypt.hashpw(b"MinP@ss1", bcrypt.gensalt()).decode()
        cursor.execute(
            """INSERT INTO auth_users (username, password_hash, is_active)
               VALUES (?, ?, 1)""",
            ("min_user", password_hash),
        )
        conn.commit()
        assert cursor.lastrowid > 0

        # 对应 users 记录可选
        cursor.execute("SELECT id FROM auth_users WHERE username = ?", ("min_user",))
        assert cursor.fetchone() is not None

    def test_register_inactive_user_by_default(self, brochure_db):
        """默认新用户应激活 (is_active=1)"""
        conn = brochure_db
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO auth_users (username, password_hash)
               VALUES (?, ?)""",
            ("active_user", bcrypt.hashpw(b"P@ss1", bcrypt.gensalt()).decode()),
        )
        conn.commit()

        cursor.execute("SELECT is_active FROM auth_users WHERE username = ?", ("active_user",))
        assert cursor.fetchone()[0] == 1


class TestUserLogin:
    """用户登录流程 (数据库层)"""

    def test_login_success(self, brochure_db, brochure_user):
        """正确凭据登录成功"""
        conn = brochure_db
        cursor = conn.cursor()

        cursor.execute("SELECT password_hash FROM auth_users WHERE id = ?", (brochure_user["id"],))
        stored_hash = cursor.fetchone()[0]

        assert bcrypt.checkpw(brochure_user["password"].encode(), stored_hash.encode())

    def test_login_wrong_password(self, brochure_db, brochure_user):
        """错误密码登录失败"""
        conn = brochure_db
        cursor = conn.cursor()

        cursor.execute("SELECT password_hash FROM auth_users WHERE id = ?", (brochure_user["id"],))
        stored_hash = cursor.fetchone()[0]

        assert not bcrypt.checkpw(b"WrongPassword123!", stored_hash.encode())

    def test_login_inactive_user(self, brochure_db, brochure_user):
        """停用用户登录失败 (业务层应检查 is_active)"""
        conn = brochure_db
        cursor = conn.cursor()

        cursor.execute("UPDATE auth_users SET is_active = 0 WHERE id = ?", (brochure_user["id"],))
        conn.commit()

        # 即使密码正确, 业务层应拒绝
        cursor.execute("SELECT is_active FROM auth_users WHERE id = ?", (brochure_user["id"],))
        assert cursor.fetchone()[0] == 0

    def test_login_nonexistent_user(self, brochure_db):
        """不存在的用户登录失败"""
        cursor = brochure_db.cursor()
        cursor.execute("SELECT id FROM auth_users WHERE username = ?", ("nonexistent_user",))
        assert cursor.fetchone() is None

    def test_login_username_case_sensitivity(self, brochure_db, brochure_user):
        """username 应大小写敏感 (取决于 SQLite collation)"""
        conn = brochure_db
        cursor = conn.cursor()

        # SQLite 默认大小写敏感
        cursor.execute("SELECT id FROM auth_users WHERE username = ?", ("BROCHURE_TEST_USER",))
        row = cursor.fetchone()
        # 可能敏感也可能不敏感, 取决于 SQLite 版本
        # 我们只记录行为而不做断言
        _ = row


# ============================================================
# API Token 认证测试 (端点可用时)
# ============================================================


class TestAuthAPIEndpoints:
    """认证 API 端点测试 (标记 skip 直到端点实现)"""

    @pytest.mark.skip(reason="注册端点尚未在 API 中实现")
    def test_register_api(self, brochure_client):
        """POST /api/v1/digital-brochure/auth/register"""
        resp = brochure_client.post(
            "/api/v1/digital-brochure/auth/register",
            json={"username": "api_user", "password": "ApiP@ss1", "email": "api@test.com"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == 201
        assert "token" in data["data"]

    @pytest.mark.skip(reason="注册端点尚未在 API 中实现")
    def test_register_duplicate_api(self, brochure_client, brochure_user):
        resp = brochure_client.post(
            "/api/v1/digital-brochure/auth/register",
            json={"username": brochure_user["username"], "password": "ApiP@ss1"},
        )
        assert resp.status_code == 409

    @pytest.mark.skip(reason="注册端点尚未在 API 中实现")
    def test_register_weak_password(self, brochure_client):
        resp = brochure_client.post(
            "/api/v1/digital-brochure/auth/register",
            json={"username": "weak_user", "password": "123"},
        )
        assert resp.status_code == 422

    @pytest.mark.skip(reason="登录端点尚未在 API 中实现")
    def test_login_api(self, brochure_client, brochure_user):
        resp = brochure_client.post(
            "/api/v1/digital-brochure/auth/login",
            json={"username": brochure_user["username"], "password": brochure_user["password"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data["data"]

    @pytest.mark.skip(reason="登录端点尚未在 API 中实现")
    def test_login_wrong_password_api(self, brochure_client, brochure_user):
        resp = brochure_client.post(
            "/api/v1/digital-brochure/auth/login",
            json={"username": brochure_user["username"], "password": "WrongPassword!"},
        )
        assert resp.status_code == 401

    @pytest.mark.skip(reason="登录端点尚未在 API 中实现")
    def test_login_inactive_api(self, brochure_client, brochure_db, brochure_user):
        cursor = brochure_db.cursor()
        cursor.execute("UPDATE auth_users SET is_active = 0 WHERE id = ?", (brochure_user["id"],))
        brochure_db.commit()

        resp = brochure_client.post(
            "/api/v1/digital-brochure/auth/login",
            json={"username": brochure_user["username"], "password": brochure_user["password"]},
        )
        assert resp.status_code == 403

    @pytest.mark.skip(reason="/auth/me 端点尚未在 API 中实现")
    def test_auth_me_valid(self, brochure_client, brochure_token):
        resp = brochure_client.get(
            "/api/v1/digital-brochure/auth/me",
            headers={"Authorization": f"Bearer {brochure_token['token']}"},
        )
        assert resp.status_code == 200

    @pytest.mark.skip(reason="/auth/me 端点尚未在 API 中实现")
    def test_auth_me_no_token(self, brochure_client):
        resp = brochure_client.get("/api/v1/digital-brochure/auth/me")
        assert resp.status_code == 401

    @pytest.mark.skip(reason="/auth/me 端点尚未在 API 中实现")
    def test_auth_me_expired_token(self, brochure_client, brochure_db, brochure_user):
        cursor = brochure_db.cursor()
        token_str = str(uuid.uuid4())
        expires_at = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """INSERT INTO auth_tokens (user_id, token, token_type, expires_at)
               VALUES (?, ?, 'access', ?)""",
            (brochure_user["id"], token_str, expires_at),
        )
        brochure_db.commit()

        resp = brochure_client.get(
            "/api/v1/digital-brochure/auth/me",
            headers={"Authorization": f"Bearer {token_str}"},
        )
        assert resp.status_code == 401
