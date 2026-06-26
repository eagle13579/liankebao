"""
链客宝 - 冠军挑战者实验框架 单元测试
========================================
覆盖：基础分流、结果记录、聚合查询、显著性检验、胜者判定、模型提升、指标跟踪。
"""

import os
import random
import tempfile
import time

import pytest

from ml.evaluation import ExperimentConfig, ChampionChallenger, MetricsTracker


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_config():
    return ExperimentConfig(
        experiment_id="exp_test_001",
        name="排序模型v2 vs v3",
        description="测试双塔模型与三塔模型的排序效果对比",
        control_model="ranking_v2",
        treatment_model="ranking_v3",
        traffic_split=0.5,
        metrics=["auc", "precision@10", "recall@20", "diversity@10"],
        duration_days=7,
        min_samples=1000,
    )


@pytest.fixture
def temp_db():
    """临时 SQLite 数据库路径。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    for _ in range(3):
        try:
            if os.path.exists(path):
                os.unlink(path)
            break
        except PermissionError:
            time.sleep(0.1)


@pytest.fixture
def champion(temp_db, sample_config):
    """使用临时数据库的 ChampionChallenger 实例。"""
    cc = ChampionChallenger(config=sample_config, db_path=temp_db)
    yield cc
    cc.close()


# ============================================================================
# 1. ExperimentConfig 基础功能
# ============================================================================


class TestExperimentConfig:
    def test_default_metrics(self):
        cfg = ExperimentConfig(
            experiment_id="e1", name="n", description="d",
            control_model="m1", treatment_model="m2",
        )
        assert cfg.metrics == ["auc", "precision@10", "recall@20", "diversity@10"]
        assert cfg.traffic_split == 0.5
        assert cfg.duration_days == 7
        assert cfg.min_samples == 1000

    def test_traffic_split_validation(self):
        with pytest.raises(ValueError, match="traffic_split"):
            ExperimentConfig(
                experiment_id="e1", name="n", description="d",
                control_model="m1", treatment_model="m2",
                traffic_split=0,
            )
        with pytest.raises(ValueError, match="traffic_split"):
            ExperimentConfig(
                experiment_id="e1", name="n", description="d",
                control_model="m1", treatment_model="m2",
                traffic_split=1.0,
            )

    def test_duration_validation(self):
        with pytest.raises(ValueError):
            ExperimentConfig(
                experiment_id="e1", name="n", description="d",
                control_model="m1", treatment_model="m2",
                duration_days=0,
            )


# ============================================================================
# 2. 确定性分流
# ============================================================================


class TestAssignment:
    def test_deterministic_assignment(self, champion):
        """同一个 user_id 在同一实验下必须返回相同分组。"""
        uid = "user_12345"
        g1 = champion.assign_group(uid)
        g2 = champion.assign_group(uid)
        g3 = champion.assign_group(uid)
        assert g1 == g2 == g3
        assert g1 in ("control", "treatment")

    def test_different_users_different_groups(self, champion):
        """不同用户应分散到不同分组（统计意义上）。"""
        groups = {}
        for i in range(1000):
            uid = f"user_{i:05d}"
            groups[uid] = champion.assign_group(uid)
        control_count = sum(1 for g in groups.values() if g == "control")
        treatment_count = sum(1 for g in groups.values() if g == "treatment")
        total = control_count + treatment_count
        ratio = control_count / total
        # 应该在 0.5 附近（允许 10% 波动）
        assert 0.40 <= ratio <= 0.60, f"control ratio = {ratio:.3f}"
        assert treatment_count > 0

    def test_traffic_split_effect(self, temp_db):
        """不同 traffic_split 应影响分流比例。"""
        cfg = ExperimentConfig(
            experiment_id="exp_split",
            name="分流测试",
            description="",
            control_model="m1",
            treatment_model="m2",
            traffic_split=0.2,  # 控制组只占 20%
        )
        cc = ChampionChallenger(config=cfg, db_path=temp_db)
        try:
            groups = {}
            for i in range(5000):
                uid = f"user_{i:06d}"
                groups[uid] = cc.assign_group(uid)
            control_count = sum(1 for g in groups.values() if g == "control")
            ratio = control_count / len(groups)
            assert 0.15 <= ratio <= 0.25, f"expected ~0.2, got {ratio:.3f}"
        finally:
            cc.close()

    def test_different_experiment_different_group(self, temp_db):
        """同一个 user_id 在不同实验下可能分到不同组。"""
        cfg1 = ExperimentConfig(
            experiment_id="exp_a", name="a", description="",
            control_model="m1", treatment_model="m2",
        )
        cfg2 = ExperimentConfig(
            experiment_id="exp_b", name="b", description="",
            control_model="m1", treatment_model="m2",
        )
        cc1 = ChampionChallenger(config=cfg1, db_path=temp_db)
        cc2 = ChampionChallenger(config=cfg2, db_path=temp_db)
        try:
            uid = "same_user"
            g1 = cc1.assign_group(uid)
            g2 = cc2.assign_group(uid)
        finally:
            cc1.close()
            cc2.close()
        # 两个实验使用不同 seed 所以结果不同是可能的，但不强制
        assert g1 in ("control", "treatment")
        assert g2 in ("control", "treatment")


# ============================================================================
# 3. 结果记录与聚合
# ============================================================================


class TestRecording:
    def test_record_and_get_results(self, champion):
        """记录一批结果后，聚合返回值应正确。"""
        for i in range(200):
            uid = f"user_{i:04d}"
            group = champion.assign_group(uid)
            # 模拟指标
            metrics = {
                "auc": 0.75 + random.uniform(-0.05, 0.05),
                "precision@10": 0.70 + random.uniform(-0.05, 0.05),
                "recall@20": 0.60 + random.uniform(-0.05, 0.05),
                "diversity@10": 0.50 + random.uniform(-0.05, 0.05),
            }
            model = champion.config.control_model if group == "control" else champion.config.treatment_model
            champion.record_result(uid, model, metrics)

        results = champion.get_results()
        assert "control" in results
        assert "treatment" in results
        for metric in champion.config.metrics:
            assert metric in results["control"]
            assert metric in results["treatment"]

    def test_empty_results(self, champion):
        """没有任何记录时，聚合返回 0 值。"""
        results = champion.get_results()
        for metric in champion.config.metrics:
            assert results["control"][metric] == 0.0
            assert results["treatment"][metric] == 0.0

    def test_record_multiple_users_same_group(self, champion):
        """同一分组的多个用户应累计正确。"""
        for i in range(50):
            uid = f"batch_{i:04d}"
            champion.record_result(uid, champion.config.control_model, {
                "auc": 0.80, "precision@10": 0.75,
                "recall@20": 0.65, "diversity@10": 0.55,
            })
        results = champion.get_results()
        assert pytest.approx(results["control"]["auc"], 0.01) == 0.80


# ============================================================================
# 4. 显著性检验
# ============================================================================


class TestSignificance:
    def test_significant_difference(self, temp_db):
        """当治疗组显著优于对照组时，is_significant 应返回 True。"""
        cfg = ExperimentConfig(
            experiment_id="exp_sig",
            name="显著测试",
            description="",
            control_model="m_old",
            treatment_model="m_new",
            min_samples=50,
        )
        cc = ChampionChallenger(config=cfg, db_path=temp_db)
        try:
            for i in range(200):
                uid = f"user_sig_{i:04d}"
                group = cc.assign_group(uid)
                # 治疗组 AUC 显著更高
                if group == "treatment":
                    auc = 0.88 + random.uniform(-0.01, 0.01)
                else:
                    auc = 0.82 + random.uniform(-0.01, 0.01)
                model = cfg.control_model if group == "control" else cfg.treatment_model
                cc.record_result(uid, model, {"auc": auc})
            assert cc.is_significant("auc", confidence=0.95)
        finally:
            cc.close()

    def test_no_significant_difference(self, temp_db):
        """两组无显著差异时，is_significant 应返回 False。"""
        cfg = ExperimentConfig(
            experiment_id="exp_no_sig",
            name="无差异测试",
            description="",
            control_model="m_a",
            treatment_model="m_b",
            min_samples=30,
        )
        cc = ChampionChallenger(config=cfg, db_path=temp_db)
        try:
            for i in range(100):
                uid = f"user_nosig_{i:04d}"
                group = cc.assign_group(uid)
                val = 0.75 + random.uniform(-0.03, 0.03)
                cc.record_result(uid, cfg.control_model if group == "control" else cfg.treatment_model,
                                 {"auc": val})
            assert not cc.is_significant("auc", confidence=0.95)
        finally:
            cc.close()

    def test_insufficient_samples(self, champion):
        """样本不足时，is_significant 应返回 False。"""
        assert champion.is_significant("auc") is False


# ============================================================================
# 5. 胜者判定
# ============================================================================


class TestWinner:
    def test_treatment_wins(self, temp_db):
        """挑战者显著胜出时，declare_winner 返回 treatment。"""
        cfg = ExperimentConfig(
            experiment_id="exp_win",
            name="胜者测试",
            description="",
            control_model="m_old",
            treatment_model="m_new",
            min_samples=30,
        )
        cc = ChampionChallenger(config=cfg, db_path=temp_db)
        try:
            for i in range(300):
                uid = f"user_win_{i:04d}"
                group = cc.assign_group(uid)
                metrics = {
                    "auc": 0.90 if group == "treatment" else 0.80,
                    "precision@10": 0.85 if group == "treatment" else 0.75,
                    "recall@20": 0.75 if group == "treatment" else 0.65,
                    "diversity@10": 0.60 if group == "treatment" else 0.55,
                }
                model = cfg.control_model if group == "control" else cfg.treatment_model
                cc.record_result(uid, model, metrics)
            verdict = cc.declare_winner()
            assert verdict["winner"] == "treatment"
            assert "details" in verdict
            for metric in cfg.metrics:
                assert metric in verdict["details"]
        finally:
            cc.close()

    def test_control_retains(self, temp_db):
        """对照组成绩更好时，declared_winner 返回 control。"""
        cfg = ExperimentConfig(
            experiment_id="exp_no_win",
            name="对照组胜出",
            description="",
            control_model="m_old",
            treatment_model="m_new",
            min_samples=30,
        )
        cc = ChampionChallenger(config=cfg, db_path=temp_db)
        try:
            for i in range(300):
                uid = f"user_cwin_{i:04d}"
                group = cc.assign_group(uid)
                # 对照组反而更好
                metrics = {
                    "auc": 0.82 if group == "treatment" else 0.89,
                    "precision@10": 0.78 if group == "treatment" else 0.84,
                    "recall@20": 0.70 if group == "treatment" else 0.76,
                    "diversity@10": 0.60 if group == "treatment" else 0.62,
                }
                model = cfg.control_model if group == "control" else cfg.treatment_model
                cc.record_result(uid, model, metrics)
            verdict = cc.declare_winner()
            assert verdict["winner"] == "control"
        finally:
            cc.close()

    def test_tie_insufficient_samples(self, champion):
        """样本不足时，declare_winner 返回 tie。"""
        # 只记录少量
        champion.record_result("u1", champion.config.control_model, {"auc": 0.8})
        champion.record_result("u2", champion.config.treatment_model, {"auc": 0.9})
        verdict = champion.declare_winner()
        assert verdict["winner"] == "tie"
        assert "样本不足" in verdict["details"].get("_reason", "")


# ============================================================================
# 6. 模型提升
# ============================================================================


class TestPromote:
    def test_promote_treatment(self, temp_db):
        """挑战者胜出时，promote() 应提升治疗模型为冠军。"""
        cfg = ExperimentConfig(
            experiment_id="exp_promote",
            name="提升测试",
            description="",
            control_model="m_old",
            treatment_model="m_new",
            min_samples=30,
        )
        cc = ChampionChallenger(config=cfg, db_path=temp_db)
        try:
            for i in range(300):
                uid = f"user_promote_{i:04d}"
                group = cc.assign_group(uid)
                metrics = {
                    "auc": 0.92 if group == "treatment" else 0.81,
                    "precision@10": 0.88 if group == "treatment" else 0.76,
                    "recall@20": 0.77 if group == "treatment" else 0.66,
                    "diversity@10": 0.62 if group == "treatment" else 0.56,
                }
                model = cfg.control_model if group == "control" else cfg.treatment_model
                cc.record_result(uid, model, metrics)
            new_champion = cc.promote()
            assert new_champion == "m_new"
            # 配置应已更新
            assert cc.config.control_model == "m_new"
        finally:
            cc.close()

    def test_promote_control_returns_none(self, temp_db):
        """对照组胜出时，promote() 返回 None。"""
        cfg = ExperimentConfig(
            experiment_id="exp_no_promote",
            name="对照组胜出",
            description="",
            control_model="m_old",
            treatment_model="m_new",
            min_samples=30,
        )
        cc = ChampionChallenger(config=cfg, db_path=temp_db)
        try:
            for i in range(300):
                uid = f"user_nop_{i:04d}"
                group = cc.assign_group(uid)
                metrics = {
                    "auc": 0.83 if group == "treatment" else 0.88,
                    "precision@10": 0.79 if group == "treatment" else 0.85,
                    "recall@20": 0.71 if group == "treatment" else 0.75,
                    "diversity@10": 0.60 if group == "treatment" else 0.61,
                }
                model = cfg.control_model if group == "control" else cfg.treatment_model
                cc.record_result(uid, model, metrics)
            result = cc.promote()
            assert result is None
        finally:
            cc.close()


# ============================================================================
# 7. MetricsTracker
# ============================================================================


class TestMetricsTracker:
    def test_log_and_get_series(self, temp_db):
        tracker = MetricsTracker(db_path=temp_db)
        try:
            ts = time.time()
            for i in range(5):
                tracker.log_metric("exp_1", "model_a", "auc", 0.80 + i * 0.02, ts + i)
            series = tracker.get_series("exp_1", "model_a", "auc")
            assert len(series) == 5
            for i, (t, v) in enumerate(series):
                assert v == 0.80 + i * 0.02
        finally:
            tracker.close()

    def test_summary(self, temp_db):
        tracker = MetricsTracker(db_path=temp_db)
        try:
            tracker.log_metric("exp_s", "m1", "auc", 0.85, 100.0)
            tracker.log_metric("exp_s", "m1", "auc", 0.87, 101.0)
            tracker.log_metric("exp_s", "m1", "precision@10", 0.72, 100.0)
            tracker.log_metric("exp_s", "m2", "auc", 0.90, 100.0)
            report = tracker.summary("exp_s")
            assert "m1" in report
            assert "m2" in report
            assert report["m1"]["auc"]["mean"] == 0.86
            assert report["m1"]["auc"]["min"] == 0.85
            assert report["m1"]["auc"]["max"] == 0.87
            assert report["m1"]["auc"]["count"] == 2
            assert report["m2"]["auc"]["last"] == 0.90
        finally:
            tracker.close()

    def test_empty_series(self, temp_db):
        tracker = MetricsTracker(db_path=temp_db)
        try:
            series = tracker.get_series("nonexistent", "m1", "auc")
            assert series == []
            report = tracker.summary("nonexistent")
            assert report == {}
        finally:
            tracker.close()
