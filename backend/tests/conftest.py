"""
pytest 配置: Fixtures 和测试数据库
====================================
为 digital_brochure_api.py 提供测试基础设施:
- 临时 SQLite 数据库 (每个测试函数独立)
- FastAPI TestClient
- 预置测试用户/图册数据
"""
import os
import sys
import tempfile
import pytest
from pathlib import Path

# 确保能导入 backend 包
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# ============================================================
# 测试数据库 Fixture
# ============================================================


@pytest.fixture(autouse=True)
def setup_test_env():
    """在每个测试前设置测试环境变量"""
    # 使用临时目录作为数据库目录
    old_env = os.environ.get("BROCHURE_DB_DIR")
    os.environ["BROCHURE_DB_DIR"] = tempfile.mkdtemp()
    yield
    # 清理
    if old_env is None:
        os.environ.pop("BROCHURE_DB_DIR", None)
    else:
        os.environ["BROCHURE_DB_DIR"] = old_env
    # 关闭并清理数据库连接
    from digital_brochure_api import close_connection
    close_connection()


@pytest.fixture
def test_db():
    """
    提供已初始化的测试数据库连接。

    每个测试函数获得一个独立的临时数据库，
    数据在测试结束后自动清理 (通过 setup_test_env 的 tmpdir 清理)。
    """
    from digital_brochure_api import get_connection, init_db

    # 确保数据库已初始化
    init_db()
    conn = get_connection()

    # 清理所有表（保持测试隔离）
    tables = [
        "visitor_logs", "match_records", "trust_network",
        "brochures", "users", "auth_tokens", "auth_users",
    ]
    for table in tables:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()

    return conn


@pytest.fixture
def client():
    """
    FastAPI TestClient 实例。

    使用 digital_brochure_api 中的 router 挂载到测试 App。
    每个测试获得独立客户端（背后是独立数据库）。
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from digital_brochure_api import router, init_db

    # 确保数据库已初始化
    init_db()

    app = FastAPI(title="觅迹·数字图册 - Test")
    if router is not None:
        app.include_router(router)

    # 添加健康检查端点
    @app.get("/health")
    def health():
        return {"status": "ok", "service": "digital-brochure"}

    with TestClient(app) as c:
        yield c


# ============================================================
# 测试数据工厂
# ============================================================


@pytest.fixture
def sample_user_data(test_db) -> dict:
    """创建一个测试用户并返回用户信息"""
    import bcrypt
    from digital_brochure_api import dict_from_row

    conn = test_db
    cursor = conn.cursor()

    password = "Test123!@#"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    cursor.execute(
        """INSERT INTO auth_users (username, password_hash, email, phone, is_active)
           VALUES (?, ?, ?, ?, 1)""",
        ("testuser", password_hash, "test@example.com", "13800138000"),
    )
    user_id = cursor.lastrowid

    cursor.execute(
        """INSERT INTO users (auth_user_id, name, company, position, phone, email, is_public)
           VALUES (?, ?, ?, ?, ?, ?, 1)""",
        (user_id, "测试用户", "测试公司", "测试工程师", "13800138000", "test@example.com"),
    )
    profile_id = cursor.lastrowid
    conn.commit()

    return {
        "id": user_id,
        "profile_id": profile_id,
        "username": "testuser",
        "password": password,
        "password_hash": password_hash,
        "email": "test@example.com",
        "phone": "13800138000",
    }


@pytest.fixture
def sample_brochure(test_db, sample_user_data) -> dict:
    """创建一个测试图册并返回信息"""
    conn = test_db
    cursor = conn.cursor()

    cursor.execute(
        """INSERT INTO brochures
           (user_id, title, cover, pages_count, description, status, is_public)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            sample_user_data["profile_id"],
            "测试画册",
            "https://example.com/cover.jpg",
            10,
            "这是一本测试画册",
            "published",
            1,
        ),
    )
    brochure_id = cursor.lastrowid
    conn.commit()

    return {
        "id": brochure_id,
        "user_id": sample_user_data["profile_id"],
        "title": "测试画册",
        "cover": "https://example.com/cover.jpg",
        "pages_count": 10,
        "description": "这是一本测试画册",
        "status": "published",
        "is_public": True,
    }


@pytest.fixture
def auth_token(test_db, sample_user_data) -> dict:
    """
    创建一个有效 token 并返回 token 信息。

    包含: token, token_type, expires_at, user_id
    """
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

    return {
        "id": token_id,
        "token": token_str,
        "user_id": sample_user_data["id"],
        "token_type": "access",
        "expires_at": expires_at,
    }


@pytest.fixture
def auth_headers(auth_token) -> dict:
    """提供 Authorization header dict"""
    return {"Authorization": f"Bearer {auth_token['token']}"}


@pytest.fixture
def second_user(test_db) -> dict:
    """创建第二个用户（用于权限隔离测试）"""
    import bcrypt

    conn = test_db
    cursor = conn.cursor()

    password = "OtherPass456!"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    cursor.execute(
        """INSERT INTO auth_users (username, password_hash, email, phone, is_active)
           VALUES (?, ?, ?, ?, 1)""",
        ("otheruser", password_hash, "other@example.com", "13900139000"),
    )
    user_id = cursor.lastrowid

    cursor.execute(
        """INSERT INTO users (auth_user_id, name, company, position, is_public)
           VALUES (?, ?, ?, ?, 1)""",
        (user_id, "其他用户", "其他公司", "其他职位"),
    )
    profile_id = cursor.lastrowid
    conn.commit()

    return {
        "id": user_id,
        "profile_id": profile_id,
        "username": "otheruser",
        "password": password,
    }
