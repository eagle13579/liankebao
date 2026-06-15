"""数据安全模块 — core 子系统 import + 结构验证测试"""

import os
import sys
import types

# 将 core/ 加入 sys.path
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CORE = os.path.join(_BASE, "core")
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)


class TestCoreImports:
    """验证 core/ 下各模块可正常导入"""

    def test_anomaly_scorer_import(self):
        from anomaly_scorer import (
            AnomalyScorer,
            BaselineManager,
            D1FrequencyScorer,
            D2DistributionScorer,
            D3TypeShiftScorer,
            D4ViolationScorer,
            D5ConsistencyScorer,
        )

        assert isinstance(AnomalyScorer, type)
        assert isinstance(BaselineManager, type)
        assert isinstance(D1FrequencyScorer, type)
        assert isinstance(D2DistributionScorer, type)
        assert isinstance(D3TypeShiftScorer, type)
        assert isinstance(D4ViolationScorer, type)
        assert isinstance(D5ConsistencyScorer, type)

    def test_anomaly_scorer_instantiation(self):
        from anomaly_scorer import AnomalyScorer

        scorer = AnomalyScorer()
        assert hasattr(scorer, "score")

    def test_data_contract_import(self):
        from data_contract import (
            ContractManager,
            ContractNotFoundError,
            ContractValidationError,
            ContractValidator,
            ContractYAML,
            DataContractError,
            validate_yaml_file,
        )

        assert isinstance(ContractManager, type)
        assert isinstance(ContractValidator, type)
        assert isinstance(ContractYAML, type)
        assert issubclass(ContractNotFoundError, Exception)
        assert issubclass(ContractValidationError, Exception)
        assert issubclass(DataContractError, Exception)
        assert isinstance(validate_yaml_file, types.FunctionType)

    def test_data_write_gateway_import(self):
        from data_write_gateway import (
            DataWriteGateway,
            DataWriteGatewayError,
        )

        assert isinstance(DataWriteGateway, type)
        assert issubclass(DataWriteGatewayError, Exception)

    def test_sanitizer_import(self):
        from sanitizer import InjectionDetectedError, Sanitizer, SanitizerError

        assert isinstance(Sanitizer, type)
        assert issubclass(SanitizerError, Exception)
        assert issubclass(InjectionDetectedError, Exception)

    def test_sanitizer_basic_sanitize(self):
        from sanitizer import sanitize

        result = sanitize("<script>alert(1)</script>")
        # sanitize() returns {'cleaned': ..., 'warnings': [...]}
        assert isinstance(result, dict)
        assert "cleaned" in result
        assert isinstance(result["warnings"], list)


class TestCoreStructure:
    """验证 core/ 目录结构完整性"""

    def test_core_dir_exists(self):
        assert os.path.isdir(_CORE)

    def test_core_has_expected_files(self):
        expected = {
            "anomaly_scorer.py",
            "data_contract.py",
            "data_write_gateway.py",
            "sanitizer.py",
        }
        files = {f for f in os.listdir(_CORE) if f.endswith(".py")}
        assert expected.issubset(files), f"Missing: {expected - files}"
