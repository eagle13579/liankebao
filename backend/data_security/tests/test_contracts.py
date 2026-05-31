"""数据安全模块 — contracts 子目录结构验证测试"""

import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONTRACTS = os.path.join(_BASE, "contracts")


class TestContractsStructure:
    """验证 contracts/ 目录下的契约 YAML 文件"""

    def test_contracts_dir_exists(self):
        assert os.path.isdir(_CONTRACTS)

    def test_contracts_has_yaml_files(self):
        files = [f for f in os.listdir(_CONTRACTS) if f.endswith(".yaml") or f.endswith(".yml")]
        assert len(files) > 0, "contracts/ 目录应包含 YAML 文件"

    def test_contracts_readable(self):
        """验证所有 YAML 文件可读取"""
        files = [f for f in os.listdir(_CONTRACTS) if f.endswith(".yaml") or f.endswith(".yml")]
        for fname in files:
            path = os.path.join(_CONTRACTS, fname)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert len(content) > 0, f"{fname} 不应为空"

    def test_contracts_expected_files(self):
        expected = {"ai_card.yaml", "chainke.yaml", "digital_port.yaml", "enterprise.yaml"}
        files = {f for f in os.listdir(_CONTRACTS) if f.endswith(".yaml")}
        assert expected.issubset(files), f"Missing: {expected - files}"
