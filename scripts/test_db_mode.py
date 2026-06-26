"""
微任务3: 双数据库模式验证测试脚本
=======================================
测试 config/database.py 的三种核心行为:
  ① 无 PG_URL 时 fallback 到 SQLite (返回 sqlite:///...)
  ② 有 PG_URL 时构建 PG 连接串 (postgresql://...)
  ③ 两模式切换正确无异常
"""

import os
import sys
import unittest
from pathlib import Path

# ── Ensure project root is on sys.path ──────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.database import get_database_url, is_postgres, is_dev, create_engine

# ── Test suite ──────────────────────────────────────────────────────────────

class TestDualDatabaseMode(unittest.TestCase):
    """验证双数据库模式（SQLite ↔ PostgreSQL）自动切换的正确性。"""

    # ── Helpers ──────────────────────────────────────────────────────────

    def setUp(self):
        """Save original env so each test starts clean."""
        self._saved_pg = os.environ.pop("PG_URL", None)

    def tearDown(self):
        """Restore original env."""
        if self._saved_pg is not None:
            os.environ["PG_URL"] = self._saved_pg
        else:
            os.environ.pop("PG_URL", None)

    # ── ① SQLite fallback ───────────────────────────────────────────────

    def test_sqlite_fallback_no_pg_url(self):
        """① 无 PG_URL → 返回 sqlite:///..."""
        os.environ.pop("PG_URL", None)      # ensure NOT set
        url = get_database_url()
        self.assertTrue(
            url.startswith("sqlite:///"),
            f"Expected sqlite:///... but got: {url}",
        )
        # Should contain the data/chainkefull.db path
        self.assertIn(
            "chainkefull.db", url,
            f"Expected chainkefull.db in SQLite path, got: {url}",
        )
        # Should have check_same_thread=False for web safety
        self.assertIn(
            "check_same_thread=False", url,
            f"Expected check_same_thread=False in SQLite URL, got: {url}",
        )

    def test_sqlite_fallback_helpers(self):
        """① 无 PG_URL → is_postgres()=False, is_dev()=True"""
        os.environ.pop("PG_URL", None)
        self.assertFalse(is_postgres())
        self.assertTrue(is_dev())

    # ── ② PostgreSQL mode ───────────────────────────────────────────────

    def test_postgres_full_uri(self):
        """② PG_URL 已包含 postgresql:// → 保持原样"""
        os.environ["PG_URL"] = "postgresql://user:pass@localhost:5432/chainke"
        url = get_database_url()
        self.assertEqual(url, "postgresql://user:pass@localhost:5432/chainke")

    def test_postgres_bare_string(self):
        """② PG_URL 不含 postgresql:// → 自动补充前缀"""
        os.environ["PG_URL"] = "user:pass@localhost:5432/chainke"
        url = get_database_url()
        self.assertEqual(
            url,
            "postgresql://user:pass@localhost:5432/chainke",
        )

    def test_postgres_with_query_params(self):
        """② PG_URL 带查询参数 → 保持完整"""
        os.environ["PG_URL"] = (
            "postgresql://user:pass@localhost:5432/chainke?sslmode=require"
        )
        url = get_database_url()
        self.assertEqual(
            url,
            "postgresql://user:pass@localhost:5432/chainke?sslmode=require",
        )

    def test_postgres_helpers(self):
        """② PG_URL 已设 → is_postgres()=True, is_dev()=False"""
        os.environ["PG_URL"] = "postgresql://u:p@h/db"
        self.assertTrue(is_postgres())
        self.assertFalse(is_dev())

    # ── ③ Mode switching ────────────────────────────────────────────────

    def test_switch_sqlite_to_pg(self):
        """③ SQLite → PostgreSQL 切换: 无异常"""
        os.environ.pop("PG_URL", None)
        url1 = get_database_url()
        self.assertTrue(url1.startswith("sqlite:///"))

        os.environ["PG_URL"] = "postgresql://u:p@h/db"
        url2 = get_database_url()
        self.assertTrue(url2.startswith("postgresql://"))

    def test_switch_pg_to_sqlite(self):
        """③ PostgreSQL → SQLite 切换: 无异常"""
        os.environ["PG_URL"] = "postgresql://u:p@h/db"
        url1 = get_database_url()
        self.assertTrue(url1.startswith("postgresql://"))

        os.environ.pop("PG_URL", None)
        url2 = get_database_url()
        self.assertTrue(url2.startswith("sqlite:///"))

    def test_switch_round_trip(self):
        """③ 来回切换三次: 每次结果正确，无异常"""
        for i in range(3):
            # ── SQLite ──
            os.environ.pop("PG_URL", None)
            self.assertTrue(
                get_database_url().startswith("sqlite:///"),
                f"Round {i}: expected SQLite",
            )
            self.assertFalse(is_postgres())
            self.assertTrue(is_dev())

            # ── PostgreSQL ──
            os.environ["PG_URL"] = f"postgresql://u:p@h/db{i}"
            self.assertEqual(
                get_database_url(),
                f"postgresql://u:p@h/db{i}",
                f"Round {i}: expected PG URL",
            )
            self.assertTrue(is_postgres())
            self.assertFalse(is_dev())

    # ── SQLAlchemy engine (optional — requires sqlalchemy installed) ────

    def test_create_engine_sqlite(self):
        """① create_engine() with SQLite → engine created (no connect)"""
        os.environ.pop("PG_URL", None)
        engine = create_engine()
        self.assertIsNotNone(engine)
        self.assertEqual(engine.url.drivername, "sqlite")

    def test_create_engine_postgres_not_connect(self):
        """② create_engine() with PG_URL → engine object ok (won't connect)"""
        os.environ["PG_URL"] = "postgresql://u:p@localhost:5432/chainke"
        engine = create_engine()
        self.assertIsNotNone(engine)
        self.assertEqual(engine.url.drivername, "postgresql")


# ── Entry point ─────────────────────────────────────────────────────────────

def run_tests() -> dict:
    """Run all tests and return structured results."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestDualDatabaseMode)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "was_successful": result.wasSuccessful(),
    }


if __name__ == "__main__":
    print("=" * 72)
    print("  双数据库模式验证 — config.database")
    print("=" * 72)
    stats = run_tests()
    print("=" * 72)
    if stats["was_successful"]:
        print(f"  ✓ 全部 {stats['tests_run']} 项测试通过")
        sys.exit(0)
    else:
        print(
            f"  ✗ 失败 {stats['failures']} / 错误 {stats['errors']}"
            f" (共 {stats['tests_run']} 项)"
        )
        sys.exit(1)
