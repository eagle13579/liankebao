"""数据安全模块 — 顶层模块 import + 结构验证测试"""

import os
import types


class TestTopLevelImports:
    """验证顶层模块 data_security_loader.py 可正常导入"""

    def test_data_security_loader_import(self):
        from data_security.data_security_loader import DataSecurity, create_test_security

        assert isinstance(DataSecurity, type)
        assert isinstance(create_test_security, types.FunctionType)

    def test_data_security_instantiation(self):
        from data_security.data_security_loader import DataSecurity

        security = DataSecurity(contracts_dir=None)
        assert security is not None
        assert hasattr(security, "validate_and_write")
        assert hasattr(security, "contract_manager")

    def test_validate_contracts_import(self):
        import data_security.validate_contracts as validate_contracts

        assert hasattr(validate_contracts, "validate_yaml_file")
        assert isinstance(validate_contracts.validate_yaml_file, types.FunctionType)

    def test_validate_contracts_has_main(self):
        import data_security.validate_contracts as validate_contracts

        assert hasattr(validate_contracts, "main") or hasattr(validate_contracts, "validate_yaml_file")


class TestTopLevelStructure:
    """验证 data_security/ 顶层目录结构"""

    def test_top_level_dir_exists(self):
        _DS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        assert os.path.isdir(_DS)

    def test_top_level_has_expected_files(self):
        _DS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        expected = {
            "data_security_loader.py",
            "validate_contracts.py",
        }
        files = {f for f in os.listdir(_DS) if f.endswith(".py") and os.path.isfile(os.path.join(_DS, f))}
        assert expected.issubset(files), f"Missing: {expected - files}"

    def test_submodules_exist(self):
        _DS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        expected_dirs = {
            "baselines",
            "contracts",
            "core",
            "db",
            "gate3",
            "quarantine",
            "wolf",
            "tests",
        }
        dirs = {f for f in os.listdir(_DS) if os.path.isdir(os.path.join(_DS, f)) and not f.startswith("__")}
        assert expected_dirs.issubset(dirs), f"Missing: {expected_dirs - dirs}"
