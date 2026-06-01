"""
pytest 配置: Fixtures 和测试数据库
====================================
为 digital_brochure_api.py 提供测试基础设施:
- 临时 SQLite 数据库 (每个测试函数独立)
- FastAPI TestClient
- 预置测试用户/图册数据
- 信任网络/匹配记录工厂

所有 fixture 使用独立的临时数据库, 不影响生产数据.
"""

import os
import sys
import tempfile
import uuid as uuid_mod
from datetime import datetime, timedelta
from pathlib import Path

import bcrypt
import pytest

# 确保能导入 backend 包
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from digital_brochure_api import close_connection, dict_from_row, get_connection, init_db


# ============================================================
# 测试数据库 Fixture
# ============================================================


@pytest.fixture(autouse=True)
def setup_test_env():
    """在每个测试前设置测试环境变量"""
    old_env = os.environ.get("BROCHURE_DB_DIR")
    os.environ["BROCHURE_DB_DIR"] = tempfile.mkdtemp()
    yield
    if old_env is None:
        os.environ.pop("BROCHURE_DB_DIR", None)
    else:
        os.environ["BROCHURE_DB_DIR"] = old_env
    close_connection()


@pytest.fixture
def test_db():
    """
    提供已初始化的测试数据库连接。
    每个测试函数获得一个独立的临时数据库。
    """
    init_db()
    conn = get_connection()

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
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from digital_brochure_api import router, init_db as _init_db

    _init_db()

    app = FastAPI(title="觅迹·数字图册 - Test")
    if router is not None:
        app.include_router(router)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "digital-brochure"}

    @app.get("/metrics")
    def metrics():
        return {"total_brochures": 0, "total_users": 0, "total_visits": 0}

    with TestClient(app) as c:
        yield c


# ============================================================
# 测试数据工厂 (原有)
# ============================================================


@pytest.fixture
def sample_user_data(test_db) -> dict:
    """创建一个测试用户并返回用户信息"""
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
    """创建一个有效 token 并返回 token 信息"""
    conn = test_db
    cursor = conn.cursor()

    token_str = str(uuid_mod.uuid4())
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


# ============================================================
# 额外测试数据工厂 (Brochure 专用)
# ============================================================


@pytest.fixture
def brochure_db(test_db):
    """test_db 别名 (兼容 brochure 测试文件)"""
    return test_db


@pytest.fixture
def brochure_client(client):
    """client 别名 (兼容 brochure 测试文件)"""
    return client


@pytest.fixture
def brochure_user(sample_user_data):
    """sample_user_data 别名 (兼容 brochure 测试文件)"""
    return sample_user_data


@pytest.fixture
def brochure_user2(second_user):
    """second_user 别名 (兼容 brochure 测试文件)"""
    return second_user


@pytest.fixture
def brochure_token(auth_token):
    """auth_token 别名 (兼容 brochure 测试文件)"""
    return auth_token


@pytest.fixture
def brochure_headers(auth_headers):
    """auth_headers 别名 (兼容 brochure 测试文件)"""
    return auth_headers


@pytest.fixture
def brochure_sample(sample_brochure):
    """sample_brochure 别名 (兼容 brochure 测试文件)"""
    return sample_brochure


@pytest.fixture
def brochure_sample_draft(test_db, sample_user_data):
    """创建一本草稿状态的测试图册"""
    conn = test_db
    cursor = conn.cursor()

    cursor.execute(
        """INSERT INTO brochures
           (user_id, title, cover, pages_count, description, status, is_public)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            sample_user_data["profile_id"],
            "草稿画册",
            None,
            0,
            "这是一本草稿画册",
            "draft",
            0,
        ),
    )
    brochure_id = cursor.lastrowid
    conn.commit()

    return {
        "id": brochure_id,
        "user_id": sample_user_data["profile_id"],
        "title": "草稿画册",
        "status": "draft",
        "is_public": False,
    }


@pytest.fixture
def brochure_other_sample(test_db, second_user):
    """创建属于 second_user 的图册 (用于权限测试)"""
    conn = test_db
    cursor = conn.cursor()

    cursor.execute(
        """INSERT INTO brochures
           (user_id, title, cover, pages_count, description, status, is_public)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            second_user["profile_id"],
            "其他用户的画册",
            "https://example.com/other.jpg",
            8,
            "这是其他用户的画册",
            "published",
            1,
        ),
    )
    brochure_id = cursor.lastrowid
    conn.commit()

    return {
        "id": brochure_id,
        "user_id": second_user["profile_id"],
        "title": "其他用户的画册",
    }


@pytest.fixture
def brochure_trust(test_db, sample_user_data, second_user):
    """创建一条 trust_network 关系"""
    conn = test_db
    cursor = conn.cursor()

    cursor.execute(
        """INSERT INTO trust_network
           (user_id, target_user_id, trust_level, tags, notes, is_mutual, source)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            sample_user_data["profile_id"],
            second_user["profile_id"],
            2,
            '["合作", "推荐"]',
            "通过项目合作建立信任",
            0,
            "manual",
        ),
    )
    trust_id = cursor.lastrowid
    conn.commit()

    return {
        "id": trust_id,
        "user_id": sample_user_data["profile_id"],
        "target_user_id": second_user["profile_id"],
        "trust_level": 2,
    }


@pytest.fixture
def brochure_match_record(test_db, sample_user_data, second_user):
    """创建一条匹配记录"""
    conn = test_db
    cursor = conn.cursor()

    cursor.execute(
        """INSERT INTO match_records
           (user_id, matched_user_id, match_type, match_score, match_reason, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            sample_user_data["profile_id"],
            second_user["profile_id"],
            "supply_demand",
            0.85,
            "供应与需求高度匹配",
            "pending",
        ),
    )
    record_id = cursor.lastrowid
    conn.commit()

    return {
        "id": record_id,
        "user_id": sample_user_data["profile_id"],
        "matched_user_id": second_user["profile_id"],
        "match_type": "supply_demand",
        "match_score": 0.85,
    }
