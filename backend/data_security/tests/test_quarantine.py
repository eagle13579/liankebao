"""数据安全模块 — quarantine 子系统 import + 结构验证测试"""

import os
import tempfile
import types


class TestQuarantineImports:
    """验证 quarantine/ 模块可正常导入"""

    def test_quarantine_manager_import(self):
        from data_security.quarantine.quarantine_manager import (
            QuarantineManager,
            register_notify_handler,
        )

        assert isinstance(QuarantineManager, type)
        assert isinstance(register_notify_handler, types.FunctionType)

    def test_quarantine_manager_instantiation(self):
        from data_security.quarantine.quarantine_manager import QuarantineManager

        qm = QuarantineManager(db_url=tempfile.mktemp(suffix=".db"), start_escalator=False)
        assert qm is not None

    def test_quarantine_crud(self):
        from data_security.quarantine.quarantine_manager import QuarantineManager

        qm = QuarantineManager(db_url=tempfile.mktemp(suffix=".db"), start_escalator=False)
        entry_id = qm.add(
            module="test_mod",
            target_schema="core",
            target_table="users",
            operation="INSERT",
            payload={"name": "test"},
            score=50.0,
            reasons=["test validation"],
        )
        assert entry_id > 0
        items = qm.get_pending()
        assert len(items) > 0
        first = items[0]
        assert first["module"] == "test_mod"
        qm.close()


class TestQuarantineStructure:
    """验证 quarantine/ 目录结构完整性"""

    def test_quarantine_dir_exists(self):
        _BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _QUAR = os.path.join(_BASE, "quarantine")
        assert os.path.isdir(_QUAR)

    def test_quarantine_has_expected_files(self):
        _BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _QUAR = os.path.join(_BASE, "quarantine")
        expected = {"quarantine_manager.py"}
        files = {f for f in os.listdir(_QUAR) if f.endswith(".py")}
        assert expected.issubset(files), f"Missing: {expected - files}"
