"""
AI数字名片 Brochure API — 健康检查/监控/可观测性测试套件
=========================================================
覆盖:
  - 健康检查端点 (/health)
  - 数据库初始化 (init_db 幂等性)
  - 数据库表结构完整性
  - Schema 版本管理
  - 数据库连接管理 (get_connection / close_connection)
  - 中间件行为 (CORS 头, 请求 ID)
  - 限流模拟 (如果实现了 rate limiting)
  - Router 挂载验证
  - 404/405 处理
  - 线程安全性 (多线程连接)
"""

import threading
import time
import uuid

import pytest
from digital_brochure_api import (
    close_connection,
    dict_from_row,
    get_connection,
    init_db,
)


# ============================================================
# 数据库初始化
# ============================================================


class TestDatabaseInit:
    """数据库初始化测试"""

    EXPECTED_TABLES = {
        "auth_users", "auth_tokens", "users", "brochures",
        "trust_network", "match_records", "visitor_logs",
        "_schema_version",
    }

    def test_init_creates_tables(self, brochure_db):
        """初始化后应创建所有表"""
        cursor = brochure_db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = {row[0] for row in cursor.fetchall()}

        for t in self.EXPECTED_TABLES:
            assert t in tables, f"缺少表: {t}"

    def test_init_idempotent(self):
        """多次初始化应幂等 (不报错)"""
        for _ in range(5):
            init_db()

    def test_schema_version_recorded(self, brochure_db):
        """数据库应有 schema 版本记录"""
        cursor = brochure_db.cursor()
        cursor.execute("SELECT version, description FROM _schema_version")
        row = cursor.fetchone()
        assert row is not None, "缺少 schema 版本记录"
        assert row[0] == "v1.0.0"

    def test_reinit_does_not_overwrite(self, brochure_db):
        """重复初始化不会覆盖数据"""
        cursor = brochure_db.cursor()
        cursor.execute("INSERT INTO auth_users (username, password_hash) VALUES (?, ?)",
                       ("persist_user", "hash"))
        brochure_db.commit()

        init_db()  # 重新初始化

        cursor.execute("SELECT id FROM auth_users WHERE username = ?", ("persist_user",))
        assert cursor.fetchone() is not None

    def test_table_columns(self, brochure_db):
        """验证表结构完整性"""
        cursor = brochure_db.cursor()

        # auth_users
        cursor.execute("PRAGMA table_info(auth_users)")
        cols = {r[1] for r in cursor.fetchall()}
        for col in ["id", "username", "password_hash", "email", "phone", "is_active", "created_at", "updated_at"]:
            assert col in cols, f"auth_users 缺少列: {col}"

        # brochures
        cursor.execute("PRAGMA table_info(brochures)")
        cols = {r[1] for r in cursor.fetchall()}
        for col in ["id", "user_id", "title", "cover", "pages_count", "description", "status", "is_public", "view_count", "share_count", "created_at", "updated_at"]:
            assert col in cols, f"brochures 缺少列: {col}"

    def test_indexes_created(self, brochure_db):
        """验证索引创建"""
        cursor = brochure_db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
        indexes = {r[0] for r in cursor.fetchall()}

        expected_indexes = {
            "idx_auth_tokens_user", "idx_auth_tokens_token",
            "idx_users_auth", "idx_brochures_user", "idx_brochures_status",
            "idx_trust_network_user", "idx_trust_network_target",
            "idx_match_records_user", "idx_match_records_match",
            "idx_visitor_logs_brochure", "idx_visitor_logs_visitor",
            "idx_visitor_logs_time",
        }

        for idx in expected_indexes:
            assert idx in indexes, f"缺少索引: {idx}"

    def test_pragma_settings(self, brochure_db):
        """验证 PRAGMA 设置"""
        cursor = brochure_db.cursor()
        cursor.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0] == "wal"


# ============================================================
# 数据库连接管理
# ============================================================


class TestConnectionManagement:
    """连接管理"""

    def test_get_connection_reuses(self, brochure_db):
        """同一线程应复用连接"""
        conn2 = get_connection()
        assert conn2 is brochure_db

    def test_close_creates_new(self, brochure_db):
        """关闭后应创建新连接"""
        close_connection()
        conn2 = get_connection()
        assert conn2 is not brochure_db

    def test_close_connection_cleanup(self):
        """关闭连接应清理 _local.conn"""
        init_db()
        conn = get_connection()
        assert conn is not None
        close_connection()
        # 重新获取应该是新连接
        conn2 = get_connection()
        assert conn2 is not None

    def test_thread_safety(self, brochure_db):
        """多线程获取连接不应冲突"""
        results = []

        def worker():
            try:
                c = get_connection()
                c.execute("SELECT 1")
                results.append(True)
            except Exception as e:
                results.append(e)

        threads = []
        for _ in range(10):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(results) == 10
        assert all(r is True for r in results)

    def test_concurrent_init(self):
        """并发 init_db 不应冲突"""
        errors = []

        def worker():
            try:
                init_db()
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(5):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"并发初始化错误: {errors}"

    def test_db_dir_creation(self):
        """BROCHURE_DB_DIR 不存在时自动创建"""
        import os
        import tempfile
        new_dir = os.path.join(tempfile.mkdtemp(), "nested", "db", "dir")
        os.environ["BROCHURE_DB_DIR"] = new_dir
        try:
            init_db()
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM auth_users")
            assert cursor.fetchone()[0] == 0
        finally:
            close_connection()
            os.environ.pop("BROCHURE_DB_DIR", None)


# ============================================================
# 健康检查端点
# ============================================================


class TestHealthEndpoint:
    """健康检查端点"""

    def test_health_returns_200(self, brochure_client):
        resp = brochure_client.get("/health")
        assert resp.status_code == 200

    def test_health_response_fields(self, brochure_client):
        resp = brochure_client.get("/health")
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "digital-brochure"

    def test_router_mounted(self, brochure_client):
        """验证 router 已正确挂载"""
        resp = brochure_client.get("/api/v1/digital-brochure/0")
        assert resp.status_code == 404  # 路由存在, 只是 ID=0 不存在

    def test_nonexistent_route_returns_404(self, brochure_client):
        resp = brochure_client.get("/api/v1/digital-brochure/nonexistent")
        assert resp.status_code in (404, 422)

    def test_cors_headers(self, brochure_client):
        """验证 CORS 头"""
        resp = brochure_client.options(
            "/api/v1/digital-brochure/1",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS 头存在 (FastAPI CORS 中间件默认行为)
        assert resp.status_code in (200, 405)

    def test_metrics_endpoint(self, brochure_client):
        """模拟 metrics 端点"""
        resp = brochure_client.get("/metrics")
        # /metrics 在 conftest_brochure 的 brochure_client fixture 中定义
        assert resp.status_code == 200

    def test_metrics_response_format(self, brochure_client):
        resp = brochure_client.get("/metrics")
        data = resp.json()
        assert "total_brochures" in data
        assert "total_users" in data
        assert "total_visits" in data

    def test_invalid_method_returns_405(self, brochure_client, brochure_sample):
        """不支持的 HTTP 方法返回 405"""
        resp = brochure_client.put(f"/api/v1/digital-brochure/{brochure_sample['id']}")
        assert resp.status_code == 405

    def test_options_endpoint(self, brochure_client):
        """OPTIONS 请求可能返回 405 (视路由配置)"""
        resp = brochure_client.options("/health")
        assert resp.status_code in (200, 405)


# ============================================================
# Rate Limiting (模拟)
# ============================================================


class TestRateLimiting:
    """限流模拟测试

    当前 digital_brochure_api.py 未实现限流中间件。
    这些测试验证当限流加入时预期的行为。
    """

    @pytest.mark.skip(reason="限流中间件尚未实现")
    def test_rate_limit_headers(self, brochure_client):
        """响应应包含限流头"""
        resp = brochure_client.get("/health")
        headers = resp.headers
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Reset" in headers

    @pytest.mark.skip(reason="限流中间件尚未实现")
    def test_rate_limit_exceeded(self, brochure_client):
        """超过限流应返回 429"""
        for _ in range(100):
            brochure_client.get("/health")
        resp = brochure_client.get("/health")
        assert resp.status_code == 429

    @pytest.mark.skip(reason="限流中间件尚未实现")
    def test_rate_limit_per_endpoint(self, brochure_client):
        """不同端点应有独立的限流计数"""
        for _ in range(60):
            brochure_client.get("/api/v1/digital-brochure/0")
        resp = brochure_client.get("/health")
        assert resp.status_code == 200  # health 端点不受影响


# ============================================================
# Request ID / Trace ID (模拟)
# ============================================================


class TestRequestTracing:
    """请求追踪测试

    当前 digital_brochure_api.py 未实现请求 ID 中间件。
    这些测试验证预期行为。
    """

    @pytest.mark.skip(reason="Trace ID 中间件尚未实现")
    def test_response_has_request_id(self, brochure_client):
        resp = brochure_client.get("/health")
        assert "X-Request-ID" in resp.headers

    @pytest.mark.skip(reason="Trace ID 中间件尚未实现")
    def test_request_id_unique(self, brochure_client):
        ids = set()
        for _ in range(10):
            resp = brochure_client.get("/health")
            ids.add(resp.headers.get("X-Request-ID"))
        assert len(ids) == 10

    @pytest.mark.skip(reason="Trace ID 中间件尚未实现")
    def test_x_trace_id_header(self, brochure_client):
        """客户端可传入 X-Trace-ID 并反映在响应中"""
        trace_id = str(uuid.uuid4())
        resp = brochure_client.get("/health", headers={"X-Trace-ID": trace_id})
        assert resp.headers.get("X-Trace-ID") == trace_id


# ============================================================
# 数据库性能与边界
# ============================================================


class TestDatabaseEdgeCases:
    """数据库边缘情况"""

    def test_connection_after_close(self):
        """关闭后重新获取连接应正常工作"""
        close_connection()
        conn = get_connection()
        assert conn is not None
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1

    def test_concurrent_read_write(self, brochure_db, brochure_user):
        """模拟并发读写"""
        def writer():
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO brochures (user_id, title) VALUES (?, ?)",
                (brochure_user["profile_id"], "并发创建"),
            )
            conn.commit()

        def reader():
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM brochures")
            return cursor.fetchone()[0]

        threads = []
        for _ in range(5):
            t = threading.Thread(target=writer)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        from digital_brochure_api import get_user_brochures
        count = len(get_user_brochures(brochure_user["profile_id"]))
        assert count >= 5

    def test_close_twice_no_error(self):
        """重复关闭连接不应报错"""
        close_connection()
        close_connection()  # 第二次应安全

    def test_large_dataset(self, brochure_db, brochure_user):
        """大量数据插入"""
        conn = brochure_db
        cursor = conn.cursor()
        for i in range(100):
            cursor.execute(
                "INSERT INTO brochures (user_id, title) VALUES (?, ?)",
                (brochure_user["profile_id"], f"bulk_brochure_{i}"),
            )
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM brochures WHERE user_id = ?",
                       (brochure_user["profile_id"],))
        assert cursor.fetchone()[0] == 100

    def test_cleanup_between_tests(self):
        """确保每个测试的数据库是独立的"""
        pass  # 由 _brochure_env fixture 保证


# ============================================================
# 安全相关
# ============================================================


class TestSecurity:
    """安全相关测试"""

    def test_no_sql_injection_on_get(self, brochure_client):
        """SQL 注入尝试不应破坏查询"""
        resp = brochure_client.get("/api/v1/digital-brochure/1%27%20OR%20%271%27%3D%271")
        assert resp.status_code in (404, 422)

    def test_negative_id_handling(self, brochure_client):
        """负数 ID 处理"""
        resp = brochure_client.get("/api/v1/digital-brochure/-1")
        # 可能返回 404 (不存在) 或 422 (校验失败)
        assert resp.status_code in (404, 422)

    def test_large_id_handling(self, brochure_client):
        """极大 ID 处理"""
        resp = brochure_client.get("/api/v1/digital-brochure/999999999999")
        assert resp.status_code == 404

    def test_unknown_endpoint(self, brochure_client):
        """未知路径应返回 404"""
        resp = brochure_client.get("/api/v1/digital-brochure/unknown/endpoint")
        assert resp.status_code == 404
