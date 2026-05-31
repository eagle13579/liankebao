"""数据安全模块 — gate3 子系统 import + 结构验证测试"""

import os
import sys
import types

# 将 gate3/ 加入 sys.path
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GATE3 = os.path.join(_BASE, "gate3")
if _GATE3 not in sys.path:
    sys.path.insert(0, _GATE3)


class TestGate3Imports:
    """验证 gate3/ 模块可正常导入"""

    def test_gate3_validator_import(self):
        import gate3_validator

        assert hasattr(gate3_validator, "ok")
        assert hasattr(gate3_validator, "fail")
        assert hasattr(gate3_validator, "check_contract")
        assert hasattr(gate3_validator, "check_sql")
        assert hasattr(gate3_validator, "check_xss")
        assert hasattr(gate3_validator, "PASS_THRESHOLD")
        assert hasattr(gate3_validator, "TOTAL_MAX")

    def test_gate3_constants(self):
        import gate3_validator

        assert gate3_validator.PASS_THRESHOLD == 144
        assert gate3_validator.TOTAL_MAX == 180

    def test_gate3_functions_exist(self):
        import gate3_validator

        assert isinstance(gate3_validator.ok, types.FunctionType)
        assert isinstance(gate3_validator.fail, types.FunctionType)

    def test_ok_function(self):
        import gate3_validator

        result = gate3_validator.ok(10, 10, "all good")
        assert result == {"score": 10, "max": 10, "detail": "all good"}

    def test_fail_function(self):
        import gate3_validator

        result = gate3_validator.fail(10, "failed")
        assert result == {"score": 0, "max": 10, "detail": "failed"}


class TestGate3Structure:
    """验证 gate3/ 目录结构完整性"""

    def test_gate3_dir_exists(self):
        assert os.path.isdir(_GATE3)

    def test_gate3_has_expected_files(self):
        expected = {"gate3_validator.py"}
        files = {f for f in os.listdir(_GATE3) if f.endswith(".py")}
        assert expected.issubset(files), f"Missing: {expected - files}"
