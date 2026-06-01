"""
健康检查 / 数据库初始化测试
============================
验证:
- 数据库初始化
- FastAPI 端点可访问
- 基本响应格式
"""
import pytest


class TestHealth:
    """健康检查测试"""

    def test_health_endpoint(self, client):
        """健康检查端点应返回 200"""
        resp = client.get("/health")
        assert resp.status_code == 200, f"健康检查失败: {resp.text}"
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "digital-brochure"

    def test_database_init(self, test_db):
        """数据库应正确初始化所有表"""
        cursor = test_db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")

        tables = [row[0] for row in cursor.fetchall()]
        expected_tables = {
            "auth_users", "auth_tokens", "users", "brochures",
            "trust_network", "match_records", "visitor_logs",
            "_schema_version",
        }

        for t in expected_tables:
            assert t in tables, f"缺少表: {t}"

    def test_schema_version(self, test_db):
        """数据库应有 schema 版本记录"""
        cursor = test_db.cursor()
        cursor.execute("SELECT version, description FROM _schema_version")
        row = cursor.fetchone()
        assert row is not None, "缺少 schema 版本记录"
        assert row[0] == "v1.0.0", f"Schema 版本不匹配: {row[0]}"

    def test_database_reinit_idempotent(self, test_db):
        """重复初始化不应报错（幂等性）"""
        from digital_brochure_api import init_db

        # 多次初始化不应抛出异常
        for _ in range(3):
            init_db()

    def test_brochure_router_exists(self, client):
        """FastAPI router 应正确挂载"""
        resp = client.get("/api/digital-brochure/0")
        # 图册 ID=0 不存在，应返回 404 而非 500 或 405
        assert resp.status_code in (404,), f"意外响应: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "code" in data
        assert data["code"] == 404


class TestConnectionManagement:
    """数据库连接管理测试"""

    def test_get_connection_reuses(self, test_db):
        """同一线程应复用连接"""
        from digital_brochure_api import get_connection

        conn2 = get_connection()
        assert conn2 is test_db, "同一线程应返回同一连接"

    def test_close_connection(self, test_db):
        """关闭连接后应创建新连接"""
        from digital_brochure_api import close_connection, get_connection

        close_connection()
        conn2 = get_connection()
        assert conn2 is not test_db, "关闭后应创建新连接"
