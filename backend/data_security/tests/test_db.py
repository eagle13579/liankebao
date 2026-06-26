"""数据安全模块 — db 子目录结构验证测试"""

import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_BASE, "db")


class TestDbStructure:
    """验证 db/ 目录下的 SQL 迁移文件"""

    def test_db_dir_exists(self):
        assert os.path.isdir(_DB)

    def test_db_has_sql_files(self):
        files = [f for f in os.listdir(_DB) if f.endswith(".sql")]
        assert len(files) > 0, "db/ 目录应包含 SQL 文件"

    def test_db_sql_readable(self):
        """验证所有 SQL 文件可读取"""
        files = [f for f in os.listdir(_DB) if f.endswith(".sql")]
        for fname in files:
            path = os.path.join(_DB, fname)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert len(content) > 0, f"{fname} 不应为空"

    def test_db_expected_files(self):
        expected = {"migration_rls_check_audit.sql", "migration_roles_permissions.sql"}
        files = {f for f in os.listdir(_DB) if f.endswith(".sql")}
        assert expected.issubset(files), f"Missing: {expected - files}"
