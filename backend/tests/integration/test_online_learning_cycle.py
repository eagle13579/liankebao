"""链客宝 — 在线学习全量闭环集成测试
======================================
完整端到端闭环验证：FeedbackService → OnlineWeightOptimizer → ChampionChallenger

测试覆盖 (20 用例):
  1. 用户提交 like 反馈 → feedback_service.submit_feedback
  2. 用户提交 rating 反馈（带评分）
  3. 在线学习读取反馈 → OnlineWeightOptimizer.update(feedback_data)
  4. 权重更新 → optimizer.get_weights() 确认变化
  5. 权重历史 → optimizer.get_history() 确认记录
  6. 正反馈提升权重 / 负反馈降低权重 / 中性反馈微调
  7. 多次正反馈 → 权重收敛到上限 [0, 2]
  8. 多次负反馈 → 权重收敛到下限 [0, 2]
  9. A/B 框架集成: champion_challenger.assign_group + record_result
  10. 全链路: 提交反馈 → 在线学习 → A/B 记录 → 权重变化 → 验证 (正/负/多步)
  11. 大量反馈 (1000+) 后的性能稳定性
  12. 边界与异常: 权重限制 / 无效输入校验
"""

import os
import sys
import time
import json
import math

import pytest

# ── 确保项目根目录在 sys.path ──
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.services.feedback_service import FeedbackService
from app.models.feedback import Feedback

from ml.online_learning import OnlineWeightOptimizer
from ml.evaluation import ExperimentConfig, ChampionChallenger


# ============================================================================
# Fixtures — 每个测试独立数据库
# ============================================================================


@pytest.fixture
def db_session():
    """每个测试函数独立的 SQLite 内存数据库会话"""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def feedback_svc(db_session):
    """已绑定数据库的 FeedbackService 实例"""
    return FeedbackService(db_session)


@pytest.fixture
def optimizer():
    """标准 OnlineWeightOptimizer 实例"""
    return OnlineWeightOptimizer(
        initial_weights={"industry": 1.0, "region": 1.0, "position": 1.0},
        base_lr=0.01,
        l2_lambda=0.001,
        weight_min=0.0,
        weight_max=2.0,
    )


@pytest.fixture
def champion():
    """使用内存数据库的 ChampionChallenger 实例"""
    config = ExperimentConfig(
        experiment_id="exp_integration_001",
        name="在线学习闭环测试",
        description="集成测试：在线学习 × A/B 框架联合验证",
        control_model="ranking_v2",
        treatment_model="ranking_v3",
        traffic_split=0.5,
        metrics=["auc", "precision@10", "recall@20"],
        duration_days=7,
        min_samples=1000,
    )
    cc = ChampionChallenger(config=config, db_path=":memory:")
    yield cc
    cc.close()


# ============================================================================
# TC1 ~ TC2: 反馈提交
# ============================================================================


class TestFeedbackSubmission:
    """验证反馈服务层的正确性"""

    def test_submit_like_feedback(self, feedback_svc):
        """TC1: 用户提交 like 反馈 → feedback_service.submit_feedback"""
        fb = feedback_svc.submit_feedback(
            user_id="u001",
            target_type="enterprise",
            target_id="ent_001",
            feedback_type="like",
        )
        assert fb.id is not None, "反馈记录应获得自增 ID"
        assert fb.user_id == "u001"
        assert fb.target_type == "enterprise"
        assert fb.feedback_type == "like"
        assert fb.score is None  # like 无评分

    def test_submit_rating_feedback(self, feedback_svc):
        """TC2: 用户提交 rating 反馈（带评分）"""
        fb = feedback_svc.submit_feedback(
            user_id="u002",
            target_type="card",
            target_id="card_002",
            feedback_type="rating",
            score=4,
        )
        assert fb.id is not None
        assert fb.score == 4


# ============================================================================
# TC3 ~ TC5: 在线学习更新
# ============================================================================


class TestOnlineLearningUpdate:
    """验证 OnlineWeightOptimizer 的更新行为"""

    def test_update_with_feedback_data(self, optimizer):
        """TC3: 在线学习读取反馈 → OnlineWeightOptimizer.update(feedback_data)"""
        initial = optimizer.get_weights()
        result = optimizer.update({"score": 5, "features": ["industry"]})
        assert result is not None
        assert isinstance(result, dict)
        # 权重应该发生了变化
        self._assert_weight_changed(initial, result, "industry")
        assert all(0.0 <= v <= 2.0 for v in result.values()), "所有权重应在 [0, 2]"

    def test_get_weights_confirms_change(self, optimizer):
        """TC4: 权重更新 → optimizer.get_weights() 确认变化"""
        before = optimizer.get_weights()
        optimizer.update({"score": 5, "features": ["industry"]})
        after = optimizer.get_weights()
        assert after["industry"] != before["industry"], "industry 权重应变化"
        assert after["region"] == before["region"], "region 权重不应变化（未在 features 中）"

    def test_get_history_records(self, optimizer):
        """TC5: 权重历史 → optimizer.get_history() 确认记录"""
        assert len(optimizer.get_history()) == 0
        optimizer.update({"score": 4, "features": ["region"]})
        optimizer.update({"score": 2, "features": ["industry"]})
        history = optimizer.get_history()
        assert len(history) == 2
        assert history[0]["score"] == 4
        assert history[1]["score"] == 2
        # 验证历史快照字段完整性
        for entry in history:
            assert "before" in entry
            assert "after" in entry
            assert "delta" in entry
            assert "grad_direction" in entry

    @staticmethod
    def _assert_weight_changed(before, after, feature):
        assert after.get(feature) != before.get(feature), (
            f"{feature} 权重应从 {before.get(feature)} 变化"
        )


# ============================================================================
# TC6: 正反馈提升 / 负反馈降低
# ============================================================================


class TestFeedbackDirection:
    """验证正负反馈对权重的方向性影响"""

    def test_positive_feedback_increases_weight(self, optimizer):
        """TC6a: 正反馈 (score>=4) 提升权重"""
        before = optimizer.get_weights()["industry"]
        optimizer.update({"score": 5, "features": ["industry"]})
        after = optimizer.get_weights()["industry"]
        assert after > before, (
            f"正反馈应提升权重: {before} → {after}"
        )

    def test_negative_feedback_decreases_weight(self, optimizer):
        """TC6b: 负反馈 (score<=2) 降低权重"""
        before = optimizer.get_weights()["region"]
        optimizer.update({"score": 1, "features": ["region"]})
        after = optimizer.get_weights()["region"]
        assert after < before, (
            f"负反馈应降低权重: {before} → {after}"
        )

    def test_neutral_feedback_slight_increase(self, optimizer):
        """TC6c: 中性反馈 (score=3) 轻微正向微调"""
        # 重置以保证可预测性
        optimizer.reset()
        before = optimizer.get_weights()["position"]
        optimizer.update({"score": 3, "features": ["position"]})
        after = optimizer.get_weights()["position"]
        # neutral 方向是 +0.1，但由于 L2 + AdaGrad，变化量很小但应为正
        delta = after - before
        assert delta > 0, (
            f"中性反馈应轻微提升权重: {before} → {after}, delta={delta}"
        )


# ============================================================================
# TC7 ~ TC8: 权重收敛边界
# ============================================================================


class TestWeightConvergence:
    """验证权重在多次反馈后收敛到边界"""

    def test_converge_to_upper_bound(self, optimizer):
        """TC7: 多次正反馈 → 权重收敛到上限 2.0"""
        for i in range(2000):
            optimizer.update({"score": 5, "features": ["industry"]})
        w = optimizer.get_weights()["industry"]
        assert w <= 2.0 + 1e-6, f"权重不应超过上限 2.0, 当前: {w}"
        # 靠近上限（AdaGrad 自适应学习率衰减，2000 步后应 > 1.8）
        assert w > 1.8, f"多次正反馈后权重应接近上限, 当前: {w}"

    def test_converge_to_lower_bound(self, optimizer):
        """TC8: 多次负反馈 → 权重收敛到下限 0.0"""
        optimizer.reset()
        for i in range(2000):
            optimizer.update({"score": 1, "features": ["region"]})
        w = optimizer.get_weights()["region"]
        assert w >= 0.0 - 1e-6, f"权重不应低于下限 0.0, 当前: {w}"
        # 靠近下限（AdaGrad 自适应学习率衰减，2000 步后应 < 0.2）
        assert w < 0.2, f"多次负反馈后权重应接近下限, 当前: {w}"


# ============================================================================
# TC9: A/B 框架集成
# ============================================================================


class TestABFrameworkIntegration:
    """验证 ChampionChallenger A/B 框架的集成"""

    def test_assign_group_and_record_result(self, champion):
        """TC9a: champion_challenger.assign_group + record_result"""
        # 确定性分组
        group = champion.assign_group("user_intg_001")
        assert group in ("control", "treatment"), f"分组应为 control/treatment, 收到: {group}"

        # 记录结果
        champion.record_result(
            user_id="user_intg_001",
            model_name="ranking_v2",
            metrics_dict={"auc": 0.85, "precision@10": 0.72},
        )

        # 验证结果可查询
        results = champion.get_results()
        assert "control" in results or "treatment" in results

    def test_ab_with_multiple_users(self, champion):
        """TC9b: 多用户 A/B 分组与记录"""
        users = [f"user_ab_{i}" for i in range(20)]
        for uid in users:
            group = champion.assign_group(uid)
            # 模拟不同模型的指标
            model = "ranking_v3" if group == "treatment" else "ranking_v2"
            champion.record_result(
                user_id=uid,
                model_name=model,
                metrics_dict={
                    "auc": 0.82 + (0.05 if group == "treatment" else 0.0),
                    "precision@10": 0.70 + (0.04 if group == "treatment" else 0.0),
                },
            )
        results = champion.get_results()
        assert "control" in results
        assert "treatment" in results


# ============================================================================
# TC10: 全链路闭环
# ============================================================================


class TestFullCycle:
    """完整端到端闭环：提交反馈 → Online Learning → A/B 记录 → 验证"""

    def data(self):
        """测试数据准备"""
        return {
            "user_id": "u_full_cycle",
            "target_type": "match",
            "target_id": "match_001",
            "feedback_type": "rating",
            "score": 5,
        }

    def test_full_cycle(
        self, feedback_svc, optimizer, champion
    ):
        """TC10a: 全链路闭环 V1 — 单次正反馈"""
        # 1. 提交反馈
        fb = feedback_svc.submit_feedback(
            user_id="u_full_001",
            target_type="enterprise",
            target_id="ent_full_001",
            feedback_type="rating",
            score=5,
            context={"features": ["industry", "region"]},
        )
        assert fb.id is not None

        # 2. Online Learning: 从反馈构造 feedback_data
        feedback_data = {
            "score": fb.score,
            "features": fb.context.get("features", []),
        }
        before = optimizer.get_weights()
        optimizer.update(feedback_data)
        after = optimizer.get_weights()

        # 3. 验证权重变化
        assert after["industry"] > before["industry"], (
            f"industry 应提升: {before['industry']} → {after['industry']}"
        )
        assert after["region"] > before["region"], (
            f"region 应提升: {before['region']} → {after['region']}"
        )

        # 4. A/B 记录
        group = champion.assign_group(fb.user_id)
        model = "ranking_v3" if group == "treatment" else "ranking_v2"
        champion.record_result(
            user_id=fb.user_id,
            model_name=model,
            metrics_dict={"auc": 0.88},
        )

        # 5. 验证历史完整
        history = optimizer.get_history()
        assert len(history) == 1
        assert history[0]["score"] == 5
        assert history[0]["grad_direction"] == 1.0

    def test_full_cycle_negative(self, feedback_svc, optimizer, champion):
        """TC10b: 全链路闭环 V2 — 负反馈"""
        # 1. 提交负反馈
        fb = feedback_svc.submit_feedback(
            user_id="u_full_002",
            target_type="card",
            target_id="card_full_002",
            feedback_type="rating",
            score=1,
            context={"features": ["position"]},
        )
        before = optimizer.get_weights()
        optimizer.update({"score": fb.score, "features": fb.context.get("features", [])})
        after = optimizer.get_weights()
        assert after["position"] < before["position"], (
            f"负反馈应降低 position: {before['position']} → {after['position']}"
        )

        # A/B 记录
        champion.record_result(
            user_id=fb.user_id,
            model_name="ranking_v2",
            metrics_dict={"auc": 0.75},
        )

    def test_full_cycle_multi_step(self, feedback_svc, optimizer, champion):
        """TC10c: 全链路闭环 V3 — 多步混合反馈"""
        feedbacks = [
            ("u_multi_001", "enterprise", "ent_m_001", 5, ["industry"]),
            ("u_multi_002", "card", "card_m_002", 1, ["region"]),
            ("u_multi_003", "match", "match_m_003", 4, ["industry", "position"]),
            ("u_multi_004", "enterprise", "ent_m_004", 2, ["region", "position"]),
            ("u_multi_005", "card", "card_m_005", 3, ["industry"]),
        ]
        weight_snapshots = []
        for uid, ttype, tid, score, features in feedbacks:
            # 提交反馈
            feedback_svc.submit_feedback(
                user_id=uid,
                target_type=ttype,
                target_id=tid,
                feedback_type="rating",
                score=score,
                context={"features": features},
            )
            # 在线学习
            before = optimizer.get_weights()
            optimizer.update({"score": score, "features": features})
            after = optimizer.get_weights()
            weight_snapshots.append(after.copy())

            # A/B 记录
            group = champion.assign_group(uid)
            model = "ranking_v3" if group == "treatment" else "ranking_v2"
            champion.record_result(
                user_id=uid, model_name=model,
                metrics_dict={"auc": 0.80 + score * 0.02},
            )

        # 验证历史长度
        assert len(optimizer.get_history()) == 5

        # 验证权重变化方向: 正反馈应提升, 负反馈应降低
        w0 = weight_snapshots[0]  # score=5, industry up
        w1 = weight_snapshots[1]  # score=1, region down
        assert w0["industry"] > optimizer._initial_weights["industry"]
        assert w1["region"] < optimizer._initial_weights["region"]

        # 验证 A/B 结果
        results = champion.get_results()
        assert "control" in results
        assert "treatment" in results


# ============================================================================
# TC11: 大量反馈性能稳定性
# ============================================================================


class TestHighVolumeStability:
    """验证大量反馈后的性能稳定性"""

    def test_100_positive_feedbacks(self, optimizer):
        """TC11a: 大量正反馈后的权重稳定性"""
        start = time.time()
        for i in range(1000):
            optimizer.update({
                "score": 5,
                "features": ["industry", "region", "position"],
            })
        elapsed = time.time() - start
        # 应在合理时间内完成
        assert elapsed < 5.0, f"1000 次更新耗时过长: {elapsed:.3f}s"
        w = optimizer.get_weights()
        # 所有权重应在上限附近（AdaGrad 收敛）
        for feat, val in w.items():
            assert val > 1.5, f"{feat} 应在上限附近, 当前: {val}"
            assert val <= 2.0 + 1e-6
        assert len(optimizer.get_history()) == 1000

    def test_high_volume_mixed(self, feedback_svc, optimizer, champion):
        """TC11b: 100+ 次混合反馈后的全链路稳定性"""
        import random
        random.seed(42)
        scores = [1, 2, 3, 4, 5]
        features_list = [["industry"], ["region"], ["position"],
                         ["industry", "region"], ["region", "position"],
                         ["industry", "position"], ["industry", "region", "position"]]

        start = time.time()
        for i in range(120):
            score = random.choice(scores)
            features = random.choice(features_list)
            uid = f"u_highvol_{i}"

            feedback_svc.submit_feedback(
                user_id=uid,
                target_type="enterprise" if i % 3 == 0 else ("card" if i % 3 == 1 else "match"),
                target_id=f"target_{i}",
                feedback_type="rating",
                score=score,
                context={"features": features},
            )
            optimizer.update({"score": score, "features": features})

            group = champion.assign_group(uid)
            model = "ranking_v3" if group == "treatment" else "ranking_v2"
            champion.record_result(
                user_id=uid, model_name=model,
                metrics_dict={"auc": random.uniform(0.7, 0.95)},
            )

        elapsed = time.time() - start
        assert elapsed < 10.0, f"120 次全链路更新耗时过长: {elapsed:.3f}s"

        # 验证: 所有权重在 [0, 2] 范围内
        w = optimizer.get_weights()
        for feat, val in w.items():
            assert 0.0 <= val <= 2.0, (
                f"{feat} 权重越界: {val}"
            )

        # 历史记录完整
        assert len(optimizer.get_history()) == 120

        # A/B 结果可查询
        results = champion.get_results()
        assert "control" in results
        assert "treatment" in results


# ============================================================================
# TC12: 边界与异常
# ============================================================================


class TestEdgeCases:
    """验证边界条件和异常处理"""

    def test_weight_bounds_never_exceeded(self, optimizer):
        """TC12a: 极端反馈后权重仍被限制在 [0, 2]"""
        # 1000 次正反馈
        for _ in range(1000):
            optimizer.update({"score": 5, "features": ["industry"]})
        w = optimizer.get_weights()
        assert w["industry"] <= 2.0
        # 1000 次负反馈
        optimizer.reset()
        for _ in range(1000):
            optimizer.update({"score": 1, "features": ["region"]})
        w = optimizer.get_weights()
        assert w["region"] >= 0.0

    def test_feedback_service_rejects_invalid(self, feedback_svc):
        """TC12b: 反馈服务校验无效输入"""
        import pytest
        with pytest.raises(ValueError):
            feedback_svc.submit_feedback(
                user_id="", target_type="enterprise",
                target_id="t1", feedback_type="like",
            )
        with pytest.raises(ValueError):
            feedback_svc.submit_feedback(
                user_id="u1", target_type="bad_type",
                target_id="t1", feedback_type="like",
            )
        with pytest.raises(ValueError):
            feedback_svc.submit_feedback(
                user_id="u1", target_type="enterprise",
                target_id="t1", feedback_type="rating",
                # score missing for rating type
            )

    def test_optimizer_rejects_invalid(self, optimizer):
        """TC12c: 优化器校验无效反馈数据"""
        import pytest
        with pytest.raises(ValueError, match="必须包含 'score'"):
            optimizer.update({"features": ["industry"]})
        with pytest.raises(ValueError, match="score 必须是 1-5"):
            optimizer.update({"score": 0, "features": ["industry"]})
        with pytest.raises(ValueError, match="score 必须是 1-5"):
            optimizer.update({"score": 6, "features": ["industry"]})
