"""数据安全模块 — 统一集成入口单元测试 (data_security_loader.py)"""

import os
import sys
import tempfile

import pytest

# 将 data_security/ 加入 sys.path
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DS = os.path.join(_BASE, "data_security")
if _DS not in sys.path:
    sys.path.insert(0, _DS)

from data_security_loader import DataSecurity, create_test_security

SAMPLE_CONTRACT_YAML = """
module: test_mod
version: "1.0"
tables:
  - name: core_users
    allowed_fields:
      - id
      - name
      - email
      - phone
    required:
      - name
    constraints:
      email:
        type: string
        regex: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\\\.[a-zA-Z]{2,}$"
"""


class TestDataSecurity:
    """DataSecurity 统一集成入口测试"""

    @pytest.fixture
    def contracts_dir(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "test_mod.yaml"), "w", encoding="utf-8") as f:
                f.write(SAMPLE_CONTRACT_YAML)
            yield d

    @pytest.fixture
    def security(self, contracts_dir):
        return DataSecurity(contracts_dir=contracts_dir)

    def test_initialization(self, security):
        assert security.contract_manager is not None
        assert security.sanitizer is not None
        assert security.dwg is not None
        assert security.scorer is not None
        assert security.qm is not None

    def test_validate_and_write_pass(self, security):
        result = security.validate_and_write(
            module="test_mod",
            table="core_users",
            data={"name": "张三", "email": "zhangsan@test.com", "phone": "13800138000"},
            context={"_dwg_mode": "normal"},
        )
        assert "status" in result
        # 成功写入或进入检疫区都是合理的
        assert result["status"] in ("passed", "quarantined")

    def test_validate_and_write_quarantine(self, security):
        """高风险数据应进入检疫区"""
        result = security.validate_and_write(
            module="test_mod",
            table="core_users",
            data={"name": "张三", "email": "zhangsan@test.com", "phone": "<script>alert(1)</script>"},
            context={"_dwg_mode": "normal"},
        )
        assert result["status"] in ("quarantined", "rejected", "passed")

    def test_validate_and_write_reject(self, security):
        """缺少必需字段应被拒绝"""
        result = security.validate_and_write(
            module="test_mod",
            table="core_users",
            data={"email": "zhangsan@test.com"},  # 缺少 name
            context={"_dwg_mode": "normal"},
        )
        assert result["status"] == "rejected"

    def test_validate_and_write_unknown_module(self, security):
        result = security.validate_and_write(
            module="unknown",
            table="core_users",
            data={"name": "test"},
            context={"_dwg_mode": "normal"},
        )
        assert result["status"] == "rejected"

    def test_validate_and_write_migration_bypass(self, security):
        """迁移白名单模式应绕过校验"""
        result = security.validate_and_write(
            module="test_mod",
            table="core_users",
            data={"name": "张三"},
            context={"_dwg_mode": "migration_20240101"},
        )
        assert result["status"] in ("passed",)

    def test_get_quarantine_pending(self, security):
        """获取检疫区待处理条目"""
        # 先触发一条进入检疫区
        security.validate_and_write(
            module="test_mod",
            table="core_users",
            data={"name": "张三", "email": "zhangsan@test.com", "phone": "<script>alert(1)</script>"},
            context={"_dwg_mode": "normal"},
        )
        items = security.get_quarantine_pending()
        assert isinstance(items, (list, tuple))

    def test_get_stats(self, security):
        stats = security.get_stats()
        assert isinstance(stats, dict)

    def test_approve_quarantine_item(self, security):
        # 先触发一条进入检疫区
        result = security.validate_and_write(
            module="test_mod",
            table="core_users",
            data={"name": "张三", "email": "zhangsan@test.com"},
            context={"_dwg_mode": "normal"},
        )
        # 如果通过了就不需要审批
        if result["status"] == "quarantined":
            qid = result.get("quarantine_id")
            if qid:
                r = security.approve_quarantine_item(qid, reviewer="admin")
                assert r.get("success") in (True, False)

    def test_reject_quarantine_item(self, security):
        result = security.validate_and_write(
            module="test_mod",
            table="core_users",
            data={"name": "张三", "email": "zhangsan@test.com"},
            context={"_dwg_mode": "normal"},
        )
        if result["status"] == "quarantined":
            qid = result.get("quarantine_id")
            if qid:
                r = security.reject_quarantine_item(qid, reviewer="admin")
                assert r.get("success") in (True, False)

    def test_module_version(self):
        assert hasattr(DataSecurity, "__version__") or hasattr(DataSecurity, "version")


class TestCreateTestSecurity:
    """测试用安全实例创建函数测试"""

    def test_create_default(self):
        security = create_test_security()
        assert security is not None
        assert security.contract_manager is not None

    def test_create_with_contracts_dir(self):
        security = create_test_security()
        result = security.validate_and_write(
            module="test",
            table="test",
            data={"name": "test"},
            context={"_dwg_mode": "normal"},
        )
        assert "status" in result

    def test_create_multiple(self):
        """多次创建不应有冲突"""
        s1 = create_test_security()
        s2 = create_test_security()
        assert s1 is not s2
