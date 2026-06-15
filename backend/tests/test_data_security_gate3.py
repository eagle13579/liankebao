"""数据安全模块 — Gate3 校验器单元测试 (gate3/gate3_validator.py)"""

import os
import sys

import pytest

# 将 gate3/ 加入 sys.path
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GATE3 = os.path.join(_BASE, "data_security", "gate3")
if _GATE3 not in sys.path:
    sys.path.insert(0, _GATE3)

from gate3_validator import (
    CHECKS,
    PASS_THRESHOLD,
    TOTAL_MAX,
    check_anomaly,
    check_audit,
    check_contract,
    check_dwg,
    check_expediency,
    check_quarantine,
    check_rls,
    check_sql,
    check_ssrf,
    check_typeconf,
    check_unicode,
    check_xss,
    check_zhanlang,
    fail,
    ok,
    run_module,
)


class TestHelperFunctions:
    """辅助函数测试"""

    def test_ok_with_detail(self):
        result = ok(8, 10, "测试详情")
        assert result["score"] == 8
        assert result["max"] == 10
        assert result["detail"] == "测试详情"

    def test_ok_without_detail(self):
        result = ok(5, 5)
        assert result["score"] == 5
        assert result["max"] == 5
        assert result["detail"] == ""

    def test_fail(self):
        result = fail(10, "失败了")
        assert result["score"] == 0
        assert result["max"] == 10
        assert result["detail"] == "失败了"

    def test_fail_shorthand_description(self):
        """fail 只接受两个参数: max, detail"""
        result = fail(10, "超时无响应")
        assert result["score"] == 0
        assert result["max"] == 10


class TestCheckFunctions:
    """各项检查函数测试 (不依赖外部 API, 使用无效 URL 验证函数不会崩溃)"""

    INACCESSIBLE = "http://192.0.2.1:12345"  # 保留地址，快速失败

    def test_check_contract_graceful_degradation(self):
        result = check_contract("test_mod", self.INACCESSIBLE, verbose=False)
        assert result["score"] == 0
        assert result["max"] == 10

    def test_check_sql_graceful_degradation(self):
        result = check_sql("test_mod", self.INACCESSIBLE, verbose=False)
        assert result["score"] >= 0
        assert result["max"] == 20

    def test_check_xss_graceful_degradation(self):
        result = check_xss("test_mod", self.INACCESSIBLE, verbose=False)
        assert result["score"] >= 0
        assert result["max"] == 20

    def test_check_typeconf_graceful_degradation(self):
        result = check_typeconf("test_mod", self.INACCESSIBLE, verbose=False)
        assert result["score"] >= 0
        assert result["max"] == 10

    def test_check_unicode_graceful_degradation(self):
        result = check_unicode("test_mod", self.INACCESSIBLE, verbose=False)
        assert result["score"] >= 0
        assert result["max"] == 10

    def test_check_ssrf_graceful_degradation(self):
        result = check_ssrf("test_mod", self.INACCESSIBLE, verbose=False)
        assert result["score"] >= 0
        assert result["max"] == 15

    def test_check_quarantine_graceful_degradation(self):
        result = check_quarantine("test_mod", self.INACCESSIBLE, verbose=False)
        assert result["score"] >= 0
        assert result["max"] == 20

    def test_check_audit_graceful_degradation(self):
        result = check_audit("test_mod", self.INACCESSIBLE, verbose=False)
        assert result["score"] >= 0
        assert result["max"] == 15

    def test_check_rls_graceful_degradation(self):
        result = check_rls("test_mod", self.INACCESSIBLE, verbose=False)
        assert result["score"] >= 0
        assert result["max"] == 15

    def test_check_dwg_graceful_degradation(self):
        result = check_dwg("test_mod", self.INACCESSIBLE, verbose=False)
        assert result["score"] >= 0
        assert result["max"] == 15

    def test_check_anomaly_graceful_degradation(self):
        result = check_anomaly("test_mod", self.INACCESSIBLE, verbose=False)
        assert result["score"] >= 0
        assert result["max"] == 10

    def test_check_zhanlang_graceful_degradation(self):
        result = check_zhanlang("test_mod", self.INACCESSIBLE, verbose=False)
        assert result["score"] == 0
        assert result["max"] == 10

    def test_check_expediency_graceful_degradation(self):
        result = check_expediency("test_mod", self.INACCESSIBLE, verbose=False)
        assert result["score"] >= 0
        assert result["max"] == 10

    def test_run_module_graceful_degradation(self):
        """run_module 应处理所有函数异常"""
        rs, total, bonus = run_module("test_mod", self.INACCESSIBLE, verbose=False)
        assert isinstance(rs, list)
        assert len(rs) == len(CHECKS)
        assert total >= 0
        assert bonus >= 0

    def test_all_check_names_in_changes(self):
        """CHECKS 列表应包含所有检查项"""
        names = [name.strip() for name, _, _ in CHECKS]
        assert "数据契约完整性" in "".join(names)
        assert "SQL注入防护" in "".join(names)
        assert len(CHECKS) == 13


class TestConstants:
    """Gate3 常量测试"""

    def test_pass_threshold(self):
        assert PASS_THRESHOLD == 144
        assert TOTAL_MAX == 180

    def test_threshold_ratio(self):
        """通过率至少80%"""
        assert PASS_THRESHOLD / TOTAL_MAX >= 0.8

    def test_threshold_ratio_exact(self):
        assert PASS_THRESHOLD / TOTAL_MAX == pytest.approx(0.8)
