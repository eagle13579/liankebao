"""数据安全模块 — 战狼攻击引擎单元测试 (wolf/wolf_data_attack.py, wolf/attack_payloads.py)"""

import os
import sys
import tempfile

import pytest

# 将 wolf/ 加入 sys.path
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WOLF = os.path.join(_BASE, "data_security", "wolf")
if _WOLF not in sys.path:
    sys.path.insert(0, _WOLF)

from attack_payloads import ATTACK_PAYLOADS
from wolf_data_attack import (
    CoverageGuide,
    DataVerifier,
    PayloadMutator,
    ScoringEngine,
)


class TestAttackPayloads:
    """攻击向量 payload 库测试"""

    def test_all_20_attacks_present(self):
        assert len(ATTACK_PAYLOADS) >= 20

    def test_each_attack_has_required_fields(self):
        for attack in ATTACK_PAYLOADS:
            assert "id" in attack
            assert "name" in attack
            assert "description" in attack
            assert "category" in attack
            assert "payloads" in attack
            assert len(attack["payloads"]) >= 5

    def test_all_ids_unique(self):
        ids = [a["id"] for a in ATTACK_PAYLOADS]
        assert len(ids) == len(set(ids))

    def test_attack_ids_format(self):
        for attack in ATTACK_PAYLOADS:
            assert attack["id"].startswith("D-")

    def test_first_attack_is_sql_injection(self):
        assert ATTACK_PAYLOADS[0]["id"] == "D-001"
        assert ATTACK_PAYLOADS[0]["category"] == "sqli"

    def test_coverage_of_categories(self):
        categories = set(a["category"] for a in ATTACK_PAYLOADS)
        assert "sqli" in categories
        assert "xss" in categories
        assert "ssrf" in categories
        assert "pp" in categories  # prototype pollution


class TestPayloadMutator:
    """Payload 变异引擎测试"""

    def test_mutate_single(self):
        mutator = PayloadMutator(seed=42)
        payload = {"method": "POST", "body": {"name": "test"}}
        variants = mutator.mutate(payload, variants=3)
        assert len(variants) >= 1
        assert payload in variants

    def test_mutate_all(self):
        mutator = PayloadMutator(seed=42)
        payloads = [
            {"method": "POST", "body": {"name": "test1"}},
            {"method": "POST", "body": {"name": "test2"}},
        ]
        results = mutator.mutate_all(payloads, variants_per_payload=2)
        assert len(results) >= 2

    def test_case_mutate_effect(self):
        mutator = PayloadMutator(seed=42)
        payload = {"method": "POST", "body": {"query": "SELECT * FROM users"}}
        variants = mutator.mutate(payload, variants=5)
        # 至少应该有一些变体
        assert len(variants) > 1

    def test_stats(self):
        mutator = PayloadMutator(seed=42)
        assert mutator.stats["total_mutations"] == 0
        mutator.mutate({"a": 1}, variants=3)
        assert mutator.stats["total_mutations"] >= 1


class TestDataVerifier:
    """数据落盘验证引擎测试"""

    def test_connect_no_url(self):
        verifier = DataVerifier(db_url=None)
        assert verifier.connect() is False

    def test_connect_sqlite(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            verifier = DataVerifier(db_url=f"sqlite://{path}")
            assert verifier.connect() is True
        finally:
            try:
                os.unlink(path)
            except (PermissionError, FileNotFoundError):
                pass

    def test_verify_injection(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            verifier = DataVerifier(db_url=f"sqlite://{path}")
            verifier.connect()
            # 先记录
            verifier.record_find("attack_1", "test_payload", "users", "name")
            assert verifier.verify_injection("attack_1", "test_payload") is True
            assert verifier.verify_injection("attack_1", "nonexistent") is False
        finally:
            try:
                os.unlink(path)
            except (PermissionError, FileNotFoundError):
                pass

    def test_record_and_check_persists(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            verifier = DataVerifier(db_url=f"sqlite://{path}")
            verifier.connect()
            verifier.record_find("attack_2", "malicious_data", "orders", "amount")
            assert verifier.check_data_persists("attack_2") is True
            assert verifier.check_data_persists("nonexistent") is False
        finally:
            try:
                os.unlink(path)
            except (PermissionError, FileNotFoundError):
                pass

    def test_clear_audit(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            verifier = DataVerifier(db_url=f"sqlite://{path}")
            verifier.connect()
            verifier.record_find("attack_3", "data", "tbl", "col")
            verifier.clear_audit()
            assert verifier.check_data_persists("attack_3") is False
        finally:
            try:
                os.unlink(path)
            except (PermissionError, FileNotFoundError):
                pass


class TestCoverageGuide:
    """覆盖率引导测试"""

    def test_mark_and_check_tested(self):
        cg = CoverageGuide()
        payload = {"method": "GET", "endpoint": "/test"}
        cg.mark_tested("A-001", payload)
        assert cg.is_tested("A-001", payload) is True
        assert cg.is_tested("A-001", {"other": "payload"}) is False

    def test_untested_payloads(self):
        cg = CoverageGuide()
        all_payloads = [{"a": 1}, {"a": 2}, {"a": 3}]
        cg.mark_tested("X", all_payloads[0])
        untested = cg.get_untested_payloads("X", all_payloads)
        assert len(untested) == 2
        assert all_payloads[0] not in untested

    def test_coverage_percentage(self):
        cg = CoverageGuide()
        all_payloads = [{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}]
        for p in all_payloads[:2]:
            cg.mark_tested("Y", p)
        cov = cg.coverage_pct("Y", len(all_payloads))
        assert cov == 50.0

    def test_overall_coverage(self):
        cg = CoverageGuide()
        attack_map = {
            "A": [{"a": 1}, {"a": 2}],
            "B": [{"b": 1}],
        }
        cg.mark_tested("A", attack_map["A"][0])
        overall = cg.overall_coverage(attack_map)
        assert overall == pytest.approx(33.33, abs=0.1)

    def test_summary(self):
        cg = CoverageGuide()
        attack_map = {"A": [{"a": 1}]}
        cg.mark_tested("A", attack_map["A"][0])
        summary = cg.summary(attack_map)
        assert "覆盖率" in summary
        assert "100.0%" in summary


class TestScoringEngine:
    """量化评分系统测试"""

    def test_initial_score(self):
        se = ScoringEngine()
        assert se.calculate() == 100

    def test_bypass_penalty(self):
        se = ScoringEngine()
        se.register_result("A-001", "bypassed")
        assert se.calculate() == 90

    def test_false_positive_penalty(self):
        se = ScoringEngine()
        se.register_false_positive("A-001", "误报")
        assert se.calculate() == 95

    def test_data_verification_bonus(self):
        se = ScoringEngine()
        se.register_data_verification()
        se.register_data_verification()
        assert se.calculate() == 110

    def test_coverage_bonus(self):
        se = ScoringEngine()
        score = se.calculate(coverage_pct=100.0)
        assert score == 110

    def test_score_clamped(self):
        se = ScoringEngine()
        for _ in range(20):
            se.register_result("X", "bypassed")
        score = se.calculate()
        assert score >= 0
        assert score <= 100

    def test_grade_s(self):
        se = ScoringEngine()
        assert se.grade(100) == "S"
        assert se.grade(95) == "S"

    def test_grade_a(self):
        se = ScoringEngine()
        assert se.grade(90) == "A"
        assert se.grade(85) == "A"

    def test_grade_fail(self):
        se = ScoringEngine()
        assert se.grade(49) == "D"

    def test_detailed_report(self):
        se = ScoringEngine()
        se.register_result("A", "bypassed")
        report = se.detailed_report()
        assert "final_score" in report
        assert "grade" in report
        assert report["bypass_count"] == 1
