"""数据安全模块完整测试覆盖 — 6个核心类，每个≥3测试用例

测试目标:
  - DataWriteGateway   (3 测试)
  - AnomalyScorer      (5 测试)
  - DataContract       (5 测试)
  - WolfDataAttack     (4 测试)
  - QuarantineManager  (5 测试)
  - Gate3Validator     (3 测试)
  总计: 25 测试用例
"""

import json
import os
import sys
import tempfile
import time

import pytest

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_contract_yaml_content():
    """提供一个合法的契约 YAML 字符串"""
    return r"""
module: test_module
version: "1.0"
tables:
  - name: users
    allowed_fields:
      - id
      - name
      - email
      - age
      - active
      - role
      - score
      - bio
    required:
      - name
    constraints:
      name:
        max_length: 100
        min_length: 1
      email:
        regex: '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
      age:
        type: integer
        min: 0
        max: 150
      active:
        type: boolean
      role:
        enum: [admin, user, guest]
      score:
        type: float
        min: 0.0
        max: 100.0
    not_allowed: []
"""


@pytest.fixture
def sample_contract_yaml(sample_contract_yaml_content):
    """创建一个 ContractYAML 实例"""
    from data_security.core.data_contract import ContractYAML

    return ContractYAML(content=sample_contract_yaml_content)


@pytest.fixture
def contract_validator(sample_contract_yaml):
    """创建一个 ContractValidator 实例（严格模式）"""
    from data_security.core.data_contract import ContractValidator

    return ContractValidator(sample_contract_yaml, strict_mode=True)


@pytest.fixture
def contract_validator_loose(sample_contract_yaml):
    """创建一个 ContractValidator 实例（宽松模式）"""
    from data_security.core.data_contract import ContractValidator

    return ContractValidator(sample_contract_yaml, strict_mode=False)


@pytest.fixture
def quarantine_db_path():
    """创建临时 SQLite 数据库路径用于检疫区测试"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def quarantine_manager(quarantine_db_path):
    """创建一个 QuarantineManager 实例（不启动后台线程）"""
    from data_security.quarantine.quarantine_manager import QuarantineManager

    qm = QuarantineManager(quarantine_db_path, start_escalator=False)
    yield qm
    qm.close()


# ============================================================================
# 1. DataWriteGateway (3 个测试)
# ============================================================================


class TestDataWriteGateway:
    """DataWriteGateway — 正常路径 + 边界 + 异常"""

    def test_dwg_initialization_defaults(self):
        """正常路径: 使用默认参数初始化 DWG"""
        from data_security.core.data_write_gateway import DataWriteGateway

        dwg = DataWriteGateway()
        assert dwg is not None
        assert dwg._strict_mode is True
        assert dwg._degrade_mode == "normal"
        assert dwg._circuit_breaker is not None
        assert dwg._sanitizer is not None
        assert dwg._scorer is not None
        assert dwg._writer is not None
        assert dwg._audit_logger is not None
        assert dwg._stats["total_requests"] == 0

    def test_dwg_circuit_breaker_basic(self):
        """正常路径: 熔断器状态机 — 关闭→失败达到阈值→打开→时间恢复→半开"""
        from data_security.core.data_write_gateway import CircuitBreaker

        # 快速熔断: 阈值=2, 恢复=1秒
        cb = CircuitBreaker(threshold=2, recovery_timeout=1, half_open_max=2)
        assert cb.state == "closed"
        assert cb.can_attempt is True
        assert cb.before_request() is True

        # 触发两次失败 → 打开
        cb.on_failure()
        assert cb.state == "closed"  # 1次失败未达阈值
        cb.on_failure()
        assert cb.state == "open"  # 2次失败达到阈值
        assert cb.can_attempt is False
        assert cb.before_request() is False
        assert cb.stats["total_rejected"] == 1

        # 等待恢复超时 → HALF_OPEN
        time.sleep(1.1)
        assert cb.can_attempt is True
        assert cb.before_request() is True
        assert cb.state == "half_open"

        # 半开状态成功 → 关闭
        cb.on_success()
        assert cb.state == "closed"
        assert cb.failure_count == 0

    def test_dwg_circuit_breaker_reset_and_edge(self):
        """边界+异常: 熔断器手动重置 + 半开失败回到打开"""
        from data_security.core.data_write_gateway import CircuitBreaker

        cb = CircuitBreaker(threshold=1, recovery_timeout=3600)
        cb.on_failure()
        assert cb.state == "open"

        # 手动重置
        cb.reset()
        assert cb.state == "closed"
        assert cb.failure_count == 0

        # 半开失败 → 回到打开
        cb.on_failure()  # open
        cb._state = "half_open"  # 强制设为半开
        cb._half_open_attempts = 0
        cb.on_failure()  # 半开失败 → open
        assert cb.state == "open"

    def test_dwg_step5_route_decision(self):
        """正常路径: step5_route 的四种决策场景"""
        from data_security.core.data_write_gateway import _StepEngine

        passed_data = {"name": "test"}
        # 场景1: 全部通过
        result = _StepEngine.step5_route(
            {"passed": True, "cleaned": passed_data},
            {"passed": True, "coerced": {}},
            {"passed": True, "cleaned": passed_data, "warnings": []},
            {"score": 10.0, "reasons": []},
        )
        assert result["decision"] == "passed"

        # 场景2: step1 拒绝
        result = _StepEngine.step5_route(
            {"passed": False, "errors": [{"message": "bad field"}]},
            {"passed": True, "coerced": {}},
            {"passed": True, "cleaned": passed_data, "warnings": []},
            {"score": 0.0, "reasons": []},
        )
        assert result["decision"] == "rejected"

        # 场景3: 异常评分 >= 60 → 隔离
        result = _StepEngine.step5_route(
            {"passed": True, "cleaned": passed_data},
            {"passed": True, "coerced": {}},
            {"passed": True, "cleaned": passed_data, "warnings": []},
            {"score": 65.0, "reasons": ["high_anomaly"]},
        )
        assert result["decision"] == "quarantined"

        # 场景4: 异常评分 >= 30 + warnings → 隔离
        result = _StepEngine.step5_route(
            {"passed": True, "cleaned": passed_data},
            {"passed": True, "coerced": {}},
            {"passed": True, "cleaned": passed_data, "warnings": ["suspicious"]},
            {"score": 35.0, "reasons": []},
        )
        assert result["decision"] == "quarantined"


# ============================================================================
# 2. AnomalyScorer (5 个测试)
# ============================================================================


class TestAnomalyScorer:
    """AnomalyScorer — 多维异常评分引擎"""

    def test_anomaly_scorer_cold_start(self):
        """正常路径: 冷启动状态应返回全零评分"""
        from data_security.core.anomaly_scorer import AnomalyScorer

        scorer = AnomalyScorer()
        # 使用唯一模块/表名以避免基线文件污染
        import uuid
        uid = uuid.uuid4().hex[:8]
        result = scorer.score(
            module=f"cold_mod_{uid}",
            table=f"cold_tbl_{uid}",
            data={"name": "alice", "email": "alice@example.com"},
        )
        assert result["cold_start"] is True
        assert result["score"] == 0.0
        assert len(result["details"]) == 5
        for d in result["details"]:
            assert d["score"] == 0.0

    def test_anomaly_scorer_baseline_update_and_warm(self):
        """正常路径: 多次写入后应建立基线，离开冷启动"""
        from data_security.core.anomaly_scorer import AnomalyScorer

        scorer = AnomalyScorer()
        # 写入 101 次以离开冷启动 (COLD_START_THRESHOLD = 100)
        for i in range(101):
            scorer.score(
                module="test_mod",
                table="test_tbl",
                data={"name": f"user_{i}", "email": "user@example.com", "age": 25},
            )
        # 验证冷启动状态已解除
        summary = scorer.get_baseline_summary("test_mod", "test_tbl")
        assert summary["total_writes"] >= 100

    def test_anomaly_scorer_set_sensitivity(self):
        """正常路径: 灵敏度配置应正确合并"""
        from data_security.core.anomaly_scorer import AnomalyScorer

        scorer = AnomalyScorer()
        scorer.set_sensitivity("mod", "tbl", {"d1_frequency": 2.0, "d3_type_shift": 0.5})
        sens = scorer._get_sensitivity("mod", "tbl")
        assert sens["d1_frequency"] == 2.0
        assert sens["d3_type_shift"] == 0.5
        # 未设置的部分保留默认值
        assert sens["d2_distribution"] == 1.0

        # 重置灵敏度
        scorer.set_sensitivity("mod", "tbl", None)
        sens = scorer._get_sensitivity("mod", "tbl")
        assert sens == {
            "d1_frequency": 1.0,
            "d2_distribution": 1.0,
            "d3_type_shift": 1.0,
            "d4_violation": 1.0,
            "d5_consistency": 1.0,
        }

    def test_anomaly_scorer_clear_baselines(self):
        """正常路径: 清除基线数据"""
        from data_security.core.anomaly_scorer import AnomalyScorer

        scorer = AnomalyScorer()
        # 写入一些数据
        scorer.score("mod_a", "tbl_x", {"val": 1})
        scorer.score("mod_b", "tbl_y", {"val": 2})

        # 清除单个
        cleared = scorer.clear_baselines(module="mod_a", table="tbl_x")
        assert cleared == 1
        summary = scorer.get_baseline_summary("mod_a", "tbl_x")
        assert summary["total_writes"] == 0

    def test_anomaly_scorer_score_with_violations(self):
        """正常路径: 带违反数据的评分"""
        from data_security.core.anomaly_scorer import AnomalyScorer

        scorer = AnomalyScorer()
        result = scorer.score(
            module="mod_1",
            table="tbl_1",
            data={"field_a": "value_a", "field_b": "value_b"},
            violations={"field_a": 2, "field_b": 1},
        )
        # 冷启动阶段，评分应为 0
        assert result["cold_start"] is True
        assert result["score"] == 0.0


# ============================================================================
# 3. DataContract (5 个测试)
# ============================================================================


class TestDataContract:
    """DataContract — ContractYAML + ContractValidator + ContractManager"""

    def test_contract_yaml_load_and_query(self, sample_contract_yaml_content):
        """正常路径: 加载契约 YAML 并查询表结构"""
        from data_security.core.data_contract import ContractYAML

        cy = ContractYAML(content=sample_contract_yaml_content)
        assert cy.get_module_name() == "test_module"
        assert cy.get_version() == "1.0"
        assert cy.get_all_table_names() == ["users"]

        allowed = cy.get_allowed_fields("users")
        assert "name" in allowed
        assert "email" in allowed
        assert "age" in allowed

        assert cy.get_required_fields("users") == ["name"]
        constraints = cy.get_constraints("users")
        assert "email" in constraints
        assert constraints["email"]["regex"] is not None
        assert cy.get_checksum() is not None

    def test_contract_yaml_validation_errors(self):
        """异常路径: 无效的契约结构应抛出 ContractSchemaError"""
        from data_security.core.data_contract import ContractSchemaError, ContractYAML

        # 缺少顶层字段
        with pytest.raises(ContractSchemaError, match="缺失顶层字段"):
            ContractYAML(content="tables: []")

        # module 为空字符串
        with pytest.raises(ContractSchemaError, match="module 字段必须为非空字符串"):
            ContractYAML(content="module: ''\nversion: '1.0'\ntables: []")

        # tables 必须是列表或字典
        with pytest.raises(ContractSchemaError, match="tables 字段必须为列表或字典"):
            ContractYAML(content="module: test\nversion: '1.0'\ntables: 'invalid'")

        # 表缺少 name
        with pytest.raises(ContractSchemaError, match="缺少 'name' 字段"):
            ContractYAML(
                content="module: test\nversion: '1.0'\ntables:\n  - allowed_fields: [id]\n"
            )

    def test_contract_validator_validate_normal(self, contract_validator):
        """正常路径: ContractValidator 校验合法数据"""
        cleaned = contract_validator.validate(
            "users",
            {
                "name": "Alice",
                "email": "alice@example.com",
                "age": 30,
                "active": True,
                "role": "admin",
                "score": 85.5,
            },
        )
        assert cleaned["name"] == "Alice"
        assert cleaned["email"] == "alice@example.com"
        assert cleaned["age"] == 30
        # 宽松模式下 extra fields 会被清洗掉

    def test_contract_validator_validation_failures(self, contract_validator):
        """异常路径: ContractValidator 拒绝非法数据"""
        from data_security.core.data_contract import ContractValidationError

        # 缺少必需字段
        with pytest.raises(ContractValidationError) as exc_info:
            contract_validator.validate("users", {"email": "a@b.com"})
        errors = exc_info.value.errors
        assert any(e["rule"] == "required" and "name" in e["message"] for e in errors)

        # 枚举值非法
        with pytest.raises(ContractValidationError) as exc_info:
            contract_validator.validate(
                "users", {"name": "Bob", "role": "superadmin"}
            )
        errors = exc_info.value.errors
        assert any("枚举值" in e["message"] for e in errors)

        # email 格式非法
        with pytest.raises(ContractValidationError) as exc_info:
            contract_validator.validate(
                "users", {"name": "Bob", "email": "not-an-email"}
            )
        errors = exc_info.value.errors
        assert any("不匹配正则" in e["message"] for e in errors)

    def test_contract_validator_batch_validate(self, contract_validator):
        """正常路径: 批量校验"""
        records = [
            {"name": "Alice", "email": "alice@test.com"},
            {"name": "Bob", "email": "bob@test.com"},
            {"name": "Charlie", "email": "bad-email"},  # 非法
        ]
        passed, failed = contract_validator.validate_batch("users", records)
        assert len(passed) == 2
        assert len(failed) == 1
        assert "_errors" in failed[0]

    def test_contract_validator_loose_mode(self, contract_validator_loose):
        """边界: 宽松模式下额外字段不报错"""
        cleaned = contract_validator_loose.validate(
            "users",
            {
                "name": "Alice",
                "extra_field": "should_pass_in_loose",
                "email": "alice@test.com",
            },
        )
        assert cleaned["name"] == "Alice"
        assert "extra_field" in cleaned  # 宽松模式保留额外字段


# ============================================================================
# 4. WolfDataAttack (4 个测试)
# ============================================================================


class TestWolfDataAttack:
    """WolfDataAttack — PayloadMutator + ScoringEngine + CoverageGuide + DataVerifier"""

    def test_payload_mutator_basic(self):
        """正常路径: PayloadMutator 应生成变体"""
        from data_security.wolf.wolf_data_attack import PayloadMutator

        mutator = PayloadMutator(seed=42)
        base = {
            "method": "POST",
            "endpoint": "/api/v1/login",
            "headers": {"Content-Type": "application/json"},
            "body": {"username": "admin", "password": "test"},
        }
        variants = mutator.mutate(base, variants=3)
        # 结果应包含原始 + 至少1个变体
        assert len(variants) >= 2
        assert variants[0] == base  # 第一个是原始
        assert mutator.stats["total_mutations"] > 0

    def test_payload_mutator_mutate_all(self):
        """正常路径: mutate_all 批量变异"""
        from data_security.wolf.wolf_data_attack import PayloadMutator

        mutator = PayloadMutator(seed=42)
        payloads = [
            {
                "method": "POST",
                "endpoint": "/api/test",
                "headers": {},
                "body": {"x": 1},
            },
            {
                "method": "GET",
                "endpoint": "/api/test2",
                "headers": {},
                "body": None,
            },
        ]
        results = mutator.mutate_all(payloads, variants_per_payload=2)
        assert len(results) >= 2

    def test_scoring_engine_basic(self):
        """正常路径: ScoringEngine 评分计算"""
        from data_security.wolf.wolf_data_attack import ScoringEngine

        se = ScoringEngine()
        assert se.calculate() == 100  # 基础分

        se.register_result("D-001", "bypassed", "WAF")
        se.register_result("D-002", "blocked", "WAF")
        assert se.calculate() == 90  # 100 - 10(bypass)

        se.register_false_positive("D-003", "误报")
        assert se.calculate() == 85  # 90 - 5(fp)

        se.register_data_verification()
        assert se.calculate() == 90  # 85 + 5(data_verify)

        # 覆盖率加成
        assert se.calculate(coverage_pct=80) == 98  # 90 + 8(coverage_bonus)
        report = se.detailed_report(coverage_pct=80)
        assert report["final_score"] == 98
        assert report["grade"] == "S"

    def test_coverage_guide(self):
        """正常路径: CoverageGuide 覆盖率跟踪"""
        from data_security.wolf.wolf_data_attack import CoverageGuide

        cg = CoverageGuide()
        payload_map = {
            "D-001": [{"p1": 1}, {"p2": 2}],
            "D-002": [{"p3": 3}],
        }

        # 初始覆盖率 0
        assert cg.overall_coverage(payload_map) == 0.0

        # 标记测试
        cg.mark_tested("D-001", {"p1": 1})
        assert cg.coverage_pct("D-001", 2) == 50.0

        cg.mark_tested("D-001", {"p2": 2})
        assert cg.coverage_pct("D-001", 2) == 100.0

        cg.mark_tested("D-002", {"p3": 3})
        assert cg.overall_coverage(payload_map) == 100.0

        summary = cg.summary(payload_map)
        assert "100.0%" in summary


# ============================================================================
# 5. QuarantineManager (5 个测试)
# ============================================================================


class TestQuarantineManager:
    """QuarantineManager — 检疫区管理器"""

    def test_add_and_get_pending(self, quarantine_manager):
        """正常路径: 添加检疫区条目并查询待处理"""
        qm = quarantine_manager
        qid = qm.add(
            module="test_mod",
            target_schema="public",
            target_table="users",
            operation="INSERT",
            payload={"name": "test", "email": "test@test.com"},
            score=0.5,
            reasons=["测试"],
        )
        assert qid > 0

        pending = qm.get_pending()
        assert len(pending) == 1
        assert pending[0]["id"] == qid
        assert pending[0]["module"] == "test_mod"
        assert pending[0]["status"] == "pending"
        assert pending[0]["payload"]["name"] == "test"

    def test_resolve_approve(self, quarantine_manager):
        """正常路径: 审批通过检疫区条目（通过5步校验）"""
        qm = quarantine_manager
        qid = qm.add(
            module="test_mod",
            target_schema="public",
            target_table="users",
            operation="INSERT",
            payload={"id": 1, "data": "safe_data"},
            score=0.3,
            reasons=["low risk"],
        )
        result = qm.resolve(qid, action="approve", reviewer="admin")
        assert result["success"] is True
        assert result["status"] == "approved"
        # 验证状态已更新
        item = qm._fetchone("SELECT * FROM quarantine_items WHERE id=?", (qid,))
        assert item["status"] == "approved"

    def test_resolve_reject(self, quarantine_manager):
        """正常路径: 拒绝检疫区条目"""
        qm = quarantine_manager
        qid = qm.add(
            module="test_mod",
            target_schema="public",
            target_table="users",
            operation="DELETE",
            payload={"id": 42},
            score=0.9,
            reasons=["high risk"],
        )
        result = qm.resolve(qid, action="reject", reviewer="admin")
        assert result["success"] is True
        assert result["status"] == "rejected"

    def test_resolve_not_found(self, quarantine_manager):
        """异常路径: 解析不存在的条目"""
        qm = quarantine_manager
        result = qm.resolve(99999, action="approve")
        assert result["success"] is False
        assert result["status"] == "not_found"

    def test_auto_resolve_rules(self, quarantine_manager):
        """正常路径: auto_resolve 规则检查"""
        qm = quarantine_manager

        # 高评分首次出现应返回 pending（规则1）
        qid1 = qm.add(
            module="new_module",
            target_schema="public",
            target_table="users",
            operation="INSERT",
            payload={"id": 1, "data": "test"},
            score=0.9,
            reasons=["high"],
        )
        item1 = qm._fetchone("SELECT * FROM quarantine_items WHERE id=?", (qid1,))
        decision = qm.auto_resolve(item1)
        assert decision == "pending"  # 首次高评分 → 须人工

        # 低评分的合法数据应 approve
        qid2 = qm.add(
            module="new_module",
            target_schema="public",
            target_table="users",
            operation="INSERT",
            payload={"id": 2, "data": "normal"},
            score=0.3,
            reasons=["normal"],
        )
        item2 = qm._fetchone("SELECT * FROM quarantine_items WHERE id=?", (qid2,))
        decision = qm.auto_resolve(item2)
        assert decision == "approve"

        # 无效 payload（带危险内容导致5步校验拒绝）
        qid3 = qm.add(
            module="new_module",
            target_schema="public",
            target_table="users",
            operation="INSERT",
            payload={"id": 3, "data": "<script>alert('xss')</script>", "password": "secret123"},
            score=0.5,
            reasons=["包含XSS和敏感字段"],
        )
        item3 = qm._fetchone("SELECT * FROM quarantine_items WHERE id=?", (qid3,))
        decision = qm.auto_resolve(item3)
        # password 字段会触发安全策略检查（步骤5），导致 reject
        assert decision == "reject"

    def test_get_pending_filtered(self, quarantine_manager):
        """正常路径: 带过滤条件的待处理查询"""
        qm = quarantine_manager
        qm.add(
            module="mod_a",
            target_schema="public",
            target_table="t1",
            operation="INSERT",
            payload={"id": 1},
            score=0.3,
            reasons=[],
        )
        qm.add(
            module="mod_b",
            target_schema="public",
            target_table="t2",
            operation="UPDATE",
            payload={"id": 2},
            score=0.4,
            reasons=[],
        )

        filtered = qm.get_pending(module="mod_a")
        assert len(filtered) == 1
        assert filtered[0]["module"] == "mod_a"

        all_pending = qm.get_pending()
        assert len(all_pending) == 2


# ============================================================================
# 6. Gate3Validator (3 个测试)
# ============================================================================


class TestGate3Validator:
    """Gate3Validator — 量化评分检查工具函数"""

    def test_ok_and_fail_helpers(self):
        """正常路径: ok() 和 fail() 辅助函数返回正确结构"""
        from data_security.gate3.gate3_validator import fail, ok

        r1 = ok(10, 10, "详情")
        assert r1 == {"score": 10, "max": 10, "detail": "详情"}

        r2 = ok(5, 10, "部分通过")
        assert r2 == {"score": 5, "max": 10, "detail": "部分通过"}

        r3 = fail(10, "失败原因")
        assert r3 == {"score": 0, "max": 10, "detail": "失败原因"}

        r4 = fail(20)
        assert r4 == {"score": 0, "max": 20, "detail": ""}

    def test_check_functions_return_correct_structure(self, monkeypatch):
        """正常路径: 各 check_* 函数应返回 dict 结构 (即使 HTTP 不可达)"""
        from data_security.gate3.gate3_validator import (
            CHECKS,
        )

        # 模拟 urllib.request.urlopen 使其快速返回空 JSON 以避免超时
        import urllib.request

        class MockResponse:
            def __init__(self, *args, **kwargs):
                pass

            def read(self):
                return b'{"status": "ok"}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: MockResponse())

        module = "test_mod"
        url = "http://localhost:1"

        for name, fn, max_score in CHECKS:
            result = fn(module, url, verbose=False)
            assert isinstance(result, dict), f"{name} 返回非 dict: {type(result)}"
            assert "score" in result, f"{name} 缺少 score"
            assert "max" in result, f"{name} 缺少 max"
            assert isinstance(result["score"], int), f"{name} score 非 int"
            assert isinstance(result["max"], int), f"{name} max 非 int"
            assert 0 <= result["score"] <= result["max"], (
                f"{name} score({result['score']}) 超出范围 [0,{result['max']}]"
            )

    def test_run_module_aggregates_scores(self, monkeypatch):
        """正常路径: run_module 应聚合所有检查的分数"""
        from data_security.gate3.gate3_validator import (
            CHECKS,
            TOTAL_MAX,
            run_module,
        )

        # 模拟 HTTP 请求
        import urllib.request

        class MockResponse:
            def __init__(self, *args, **kwargs):
                pass

            def read(self):
                return b'{"status": "ok", "blocked": true, "sanitized": true, "valid": true, "quarantined": true, "isolated": true, "approvable": true}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: MockResponse())

        results, total, bonus = run_module("test_mod", "http://localhost:1", verbose=False)
        assert len(results) == len(CHECKS)
        assert 0 <= total <= TOTAL_MAX
        assert 0 <= bonus <= 10
        # 每个结果应是 (name, dict, is_bonus) 格式
        for name, r, is_bonus in results:
            assert isinstance(name, str)
            assert isinstance(r, dict)
            assert "score" in r
            assert "max" in r
            assert isinstance(is_bonus, bool)


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
