"""数据安全模块 — 检疫区管理器单元测试 (quarantine/quarantine_manager.py)"""

import os
import sys
import tempfile

import pytest

# 将 quarantine/ 加入 sys.path
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_QUAR = os.path.join(_BASE, "data_security", "quarantine")
if _QUAR not in sys.path:
    sys.path.insert(0, _QUAR)

# 还需要 core/ 因为一些内部导入
_CORE = os.path.join(_BASE, "data_security", "core")
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from quarantine_manager import (
    QuarantineManager,
    _step1_schema_validation,
    _step2_data_type_validation,
    _step3_range_constraint_validation,
    _step4_disinfection,
    _step5_security_policy_check,
    full_validation_5step,
    register_notify_handler,
    relaxed_validation_5step,
)


class TestValidationSteps:
    """5步校验独立函数测试"""

    def test_step1_schema_valid(self):
        errors = _step1_schema_validation({"id": 1, "data": "test"}, "public", "users")
        assert errors == []

    def test_step1_schema_not_dict(self):
        errors = _step1_schema_validation("not a dict", "public", "users")
        assert len(errors) > 0

    def test_step1_schema_missing_fields(self):
        errors = _step1_schema_validation({"other": "value"}, "public", "users")
        assert len(errors) > 0

    def test_step2_data_type_valid(self):
        errors = _step2_data_type_validation({"name": "张三", "age": 25})
        assert errors == []

    def test_step2_data_type_bytes(self):
        errors = _step2_data_type_validation({"data": b"binary"})
        assert len(errors) > 0

    def test_step3_range_valid(self):
        errors = _step3_range_constraint_validation({"amount": 100, "name": "test"})
        assert errors == []

    def test_step3_range_extreme_value(self):
        errors = _step3_range_constraint_validation({"amount": 1e20})
        assert len(errors) > 0

    def test_step4_disinfection_clean(self):
        cleaned, issues = _step4_disinfection({"name": "张三", "bio": "你好世界"})
        assert issues == []
        assert cleaned["name"] == "张三"

    def test_step4_disinfection_xss(self):
        cleaned, issues = _step4_disinfection({"comment": "<script>alert(1)</script>"})
        assert len(issues) > 0
        assert "<script>" not in cleaned["comment"]

    def test_step4_disinfection_sql(self):
        cleaned, issues = _step4_disinfection({"query": "'; DROP TABLE users--"})
        assert len(issues) > 0

    def test_step4_disinfection_nested(self):
        cleaned, issues = _step4_disinfection({"nested": {"xss": "<script>evil</script>"}})
        assert len(issues) > 0

    def test_step5_security_check_clean(self):
        errors = _step5_security_policy_check({"name": "张三"})
        assert errors == []

    def test_step5_security_check_sensitive(self):
        errors = _step5_security_policy_check({"password": "secret123"})
        assert len(errors) > 0


class TestFullValidation5Step:
    """完整5步校验测试"""

    def test_full_validation_pass(self):
        result = full_validation_5step({"id": 1, "data": "test"}, "public", "users")
        assert result["passed"] is True
        assert result["errors"] == []

    def test_full_validation_fail_schema(self):
        result = full_validation_5step("bad", "public", "users")
        assert result["passed"] is False
        assert len(result["errors"]) > 0

    def test_full_validation_disinfection_warnings(self):
        result = full_validation_5step({"id": 1, "comment": "<script>xss</script>"}, "public", "users")
        assert len(result["disinfection_warnings"]) > 0

    def test_relaxed_validation_pass(self):
        result = relaxed_validation_5step({"id": 1, "data": "test"}, "public", "users")
        assert result["passed"] is True

    def test_relaxed_validation_fail(self):
        result = relaxed_validation_5step("bad", "public", "users")
        assert result["passed"] is False


class TestQuarantineManager:
    """检疫区管理器核心功能测试"""

    @pytest.fixture
    def db_path(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        yield path
        try:
            os.unlink(path)
        except PermissionError:
            pass

    @pytest.fixture
    def manager(self, db_path):
        mgr = QuarantineManager(db_url=db_path, start_escalator=False)
        yield mgr
        mgr.close()

    def test_init_creates_table(self, manager, db_path):
        assert os.path.isfile(db_path)

    def test_add_quarantine_item(self, manager):
        qid = manager.add(
            module="test_module",
            target_schema="public",
            target_table="users",
            operation="INSERT",
            payload={"name": "张三", "email": "hacker@evil.com"},
            score=0.85,
            reasons=["XSS检测", "SQL注入检测"],
        )
        assert isinstance(qid, int)
        assert qid > 0

    def test_get_pending_items(self, manager):
        manager.add("mod", "public", "tbl", "INSERT", {"data": "test"}, 0.5, ["risk"])
        items = manager.get_pending_items()
        assert len(items) >= 1

    def test_resolve_approve(self, manager):
        qid = manager.add("mod", "public", "tbl", "INSERT", {"id": 1, "data": "test"}, 0.3, ["low_risk"])
        result = manager.resolve(qid, "approve", reviewer="admin")
        assert result["success"] is True
        assert result["status"] == "approved"

    def test_resolve_reject(self, manager):
        qid = manager.add("mod", "public", "tbl", "INSERT", {"id": 1, "data": "test"}, 0.9, ["high_risk"])
        result = manager.resolve(qid, "reject", reviewer="admin")
        assert result["success"] is True
        assert result["status"] == "rejected"

    def test_resolve_nonexistent(self, manager):
        result = manager.resolve(99999, "approve")
        assert result["success"] is False
        assert result["status"] == "not_found"

    def test_resolve_already_resolved(self, manager):
        qid = manager.add("mod", "public", "tbl", "INSERT", {"data": "test"}, 0.3, ["low"])
        manager.resolve(qid, "approve", reviewer="admin")
        # 再次尝试审批应失败
        result = manager.resolve(qid, "approve", reviewer="admin")
        assert result["success"] is False

    def test_get_stats(self, manager):
        manager.add("mod", "public", "tbl", "INSERT", {"data": "1"}, 0.3, ["a"])
        manager.add("mod", "public", "tbl", "INSERT", {"data": "2"}, 0.7, ["b"])
        stats = manager.get_stats()
        assert stats["total"] >= 2
        assert stats["pending"] >= 2

    def test_notification_handler(self, manager):
        received = []

        def handler(level, title, message):
            received.append((level, title, message))

        register_notify_handler(handler)
        manager.add("mod", "public", "tbl", "INSERT", {"data": "test"}, 0.5, ["risk"])
        assert len(received) >= 1

    def test_rescan_item(self, manager):
        qid = manager.add("mod", "public", "tbl", "INSERT", {"id": 1, "data": "clean"}, 0.5, ["risk"])
        result = manager.resolve(qid, "rescan")
        assert result["success"] is True
        assert result["status"] == "pending"
        assert result["qitem"]["rescan_count"] >= 1

    def test_escalation_check(self, manager):
        """手动触发升级检查"""
        manager.add("mod", "public", "tbl", "INSERT", {"data": "old"}, 0.5, ["risk"])
        manager._check_escalation()
        # 不应崩溃
        assert True


class TestQuarantineEdgeCases:
    """检疫区边界条件测试"""

    @pytest.fixture
    def manager(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        mgr = QuarantineManager(db_url=path, start_escalator=False)
        yield mgr
        mgr.close()
        try:
            os.unlink(path)
        except PermissionError:
            pass

    def test_add_with_empty_payload(self, manager):
        qid = manager.add("mod", "public", "tbl", "INSERT", {}, 0.0, [])
        assert qid > 0

    def test_add_with_unicode_payload(self, manager):
        qid = manager.add("mod", "public", "tbl", "INSERT", {"name": "张\u200b三\u200d"}, 0.5, ["unicode"])
        assert qid > 0

    def test_add_with_large_payload(self, manager):
        large_payload = {"key": "x" * 50000}
        qid = manager.add("mod", "public", "tbl", "INSERT", large_payload, 0.1, [])
        assert qid > 0

    def test_delete_operation(self, manager):
        qid = manager.add("mod", "public", "tbl", "DELETE", {"id": 1}, 0.4, ["destructive"])
        assert qid > 0
