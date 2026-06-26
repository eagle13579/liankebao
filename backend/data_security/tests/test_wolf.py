"""数据安全模块 — wolf 子系统 import + 结构验证测试"""

import os
import types


class TestWolfImports:
    """验证 wolf/ 各模块可正常导入"""

    def test_attack_payloads_import(self):
        from data_security.wolf.attack_payloads import ATTACK_PAYLOADS

        assert isinstance(ATTACK_PAYLOADS, list)
        assert len(ATTACK_PAYLOADS) > 0

    def test_attack_payloads_structure(self):
        from data_security.wolf.attack_payloads import ATTACK_PAYLOADS

        required_keys = {
            "id",
            "name",
            "description",
            "category",
            "payloads",
            "expected_defense",
            "severity",
        }
        for payload in ATTACK_PAYLOADS:
            assert required_keys.issubset(payload.keys()), (
                f"Payload {payload.get('id')} missing keys: {required_keys - payload.keys()}"
            )
            assert isinstance(payload["payloads"], list)
            assert len(payload["payloads"]) > 0

    def test_wolf_data_attack_import(self):
        from data_security.wolf.wolf_data_attack import (
            CoverageGuide,
            DataVerifier,
            PayloadMutator,
            ReportWriter,
            ScoringEngine,
            WolfDataAttack,
        )

        assert isinstance(PayloadMutator, type)
        assert isinstance(WolfDataAttack, type)
        assert isinstance(DataVerifier, type)
        assert isinstance(CoverageGuide, type)
        assert isinstance(ScoringEngine, type)
        assert isinstance(ReportWriter, type)

    def test_payload_mutator_instantiation(self):
        from data_security.wolf.wolf_data_attack import PayloadMutator

        mutator = PayloadMutator(seed=42)
        assert mutator is not None

    def test_payload_mutator_basic(self):
        from data_security.wolf.wolf_data_attack import PayloadMutator

        mutator = PayloadMutator(seed=42)
        payload = {"method": "POST", "endpoint": "/test", "headers": {}, "body": "test"}
        variants = mutator.mutate(payload, variants=2)
        assert len(variants) >= 1
        assert payload in variants

    def test_wolf_attack_engine_instantiation(self):
        from data_security.wolf.wolf_data_attack import WolfDataAttack

        engine = WolfDataAttack(target_base_url="http://localhost:8000")
        assert engine is not None
        assert engine.target_base_url == "http://localhost:8000"


class TestWolfStructure:
    """验证 wolf/ 目录结构完整性"""

    def test_wolf_dir_exists(self):
        _BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _WOLF = os.path.join(_BASE, "wolf")
        assert os.path.isdir(_WOLF)

    def test_wolf_has_expected_files(self):
        _BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _WOLF = os.path.join(_BASE, "wolf")
        expected = {"attack_payloads.py", "wolf_data_attack.py"}
        files = {f for f in os.listdir(_WOLF) if f.endswith(".py")}
        assert expected.issubset(files), f"Missing: {expected - files}"
