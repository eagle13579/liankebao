"""链客宝 — OnlineWeightOptimizer 单元测试 (8 用例)
=============================================

覆盖:
  - 正常路径: 正反馈 / 负反馈 / 中性反馈的权重方向
  - 边界:     空 features 列表 / 未知特征 (零样本) / 权重裁剪
  - 异常:     缺少 score / 无效 score / 空 initial_weights
"""

import pytest
import math

from ml.online_learning import OnlineWeightOptimizer


# ============================================================================
# Fixture — 标准优化器实例
# ============================================================================

@pytest.fixture
def opt():
    """三特征的 OnlineWeightOptimizer 标准实例"""
    return OnlineWeightOptimizer(
        initial_weights={"industry": 1.0, "region": 1.0, "position": 1.0},
        base_lr=0.01,
        l2_lambda=0.001,
        weight_min=0.0,
        weight_max=2.0,
    )


# ============================================================================
# 正常路径
# ============================================================================

class TestPositiveFeedback:
    """正反馈 (score >= 4) 应提升权重"""

    def test_score_5_increases_weight(self, opt):
        """score=5 → 梯度方向 +1.0, industry 权重上升"""
        before = opt.get_weights()["industry"]
        opt.update({"score": 5, "features": ["industry"]})
        after = opt.get_weights()["industry"]
        assert after > before, (
            f"score=5 正反馈应提升权重: {before} → {after}"
        )

    def test_score_4_increases_weight(self, opt):
        """score=4 → 梯度方向 +1.0, region 权重上升"""
        before = opt.get_weights()["region"]
        opt.update({"score": 4, "features": ["region"]})
        after = opt.get_weights()["region"]
        assert after > before, (
            f"score=4 正反馈应提升权重: {before} → {after}"
        )


class TestNegativeFeedback:
    """负反馈 (score <= 2) 应降低权重"""

    def test_score_1_decreases_weight(self, opt):
        """score=1 → 梯度方向 -1.0, position 权重下降"""
        before = opt.get_weights()["position"]
        opt.update({"score": 1, "features": ["position"]})
        after = opt.get_weights()["position"]
        assert after < before, (
            f"score=1 负反馈应降低权重: {before} → {after}"
        )

    def test_score_2_decreases_weight(self, opt):
        """score=2 → 梯度方向 -1.0, industry 权重下降"""
        before = opt.get_weights()["industry"]
        opt.update({"score": 2, "features": ["industry"]})
        after = opt.get_weights()["industry"]
        assert after < before, (
            f"score=2 负反馈应降低权重: {before} → {after}"
        )


class TestNeutralFeedback:
    """中性反馈 (score == 3) 应轻微正向微调"""

    def test_score_3_mild_increase(self, opt):
        """score=3 → 梯度方向 +0.1 (neutral_lr), 权重轻微上升"""
        opt.reset()
        before = opt.get_weights()["region"]
        opt.update({"score": 3, "features": ["region"]})
        after = opt.get_weights()["region"]
        delta = after - before
        assert delta > 0, (
            f"score=3 中性反馈应轻微提升: {before} → {after}, delta={delta}"
        )
        # 验证历史记录的梯度方向为 neutral_lr (0.1)
        history = opt.get_history()
        assert history[0]["grad_direction"] == opt._neutral_lr, (
            "中性反馈的 grad_direction 应为 neutral_lr"
        )


# ============================================================================
# 边界: 空数据 / 零样本 / 权重裁剪
# ============================================================================

class TestBoundary:
    """边界条件测试"""

    def test_empty_features_list_updates_all(self, opt):
        """features=[] → 降级为全局更新, 所有权重都应变化"""
        before = opt.get_weights()
        opt.update({"score": 5, "features": []})
        after = opt.get_weights()
        for feat in before:
            assert after[feat] != before[feat], (
                f"空 features 列表应更新所有特征, 但 {feat} 未变化"
            )

    def test_unknown_features_downgrades_to_global(self, opt):
        """features=['unknown_feat'] → 该特征不在权重组中, 降级为全局更新
        即零样本 / 未见过的特征名场景"""
        before = opt.get_weights()
        opt.update({"score": 5, "features": ["unknown_feat_xyz"]})
        after = opt.get_weights()
        for feat in before:
            assert after[feat] != before[feat], (
                f"未知特征应降级为全局更新, 但 {feat} 未变化"
            )
        # 验证历史记录中的 target_features 为所有已知特征
        history = opt.get_history()
        assert len(history) == 1
        assert sorted(history[0]["target_features"]) == sorted(before.keys()), (
            "降级全局更新时 target_features 应包含所有已知特征"
        )

    def test_weight_clipping_at_bounds(self, opt):
        """多次正/负反馈后权重应始终在 [weight_min, weight_max] 区间内

        使用自定义窄区间 [0.5, 1.5] 验证边界裁剪生效
        """
        narrow = OnlineWeightOptimizer(
            initial_weights={"industry": 1.0},
            base_lr=0.1,        # 大学习率加速收敛到边界
            l2_lambda=0.0,      # 关闭正则化以便更快触边
            weight_min=0.5,
            weight_max=1.5,
        )
        # 多次正反馈 → 应被裁剪到 1.5
        for _ in range(500):
            narrow.update({"score": 5, "features": ["industry"]})
        w_up = narrow.get_weights()["industry"]
        assert w_up == 1.5, f"正反馈后权重应裁剪到 1.5, 实际: {w_up}"

        # 重置后多次负反馈 → 应被裁剪到 0.5
        narrow.reset()
        for _ in range(500):
            narrow.update({"score": 1, "features": ["industry"]})
        w_down = narrow.get_weights()["industry"]
        assert w_down == 0.5, f"负反馈后权重应裁剪到 0.5, 实际: {w_down}"


# ============================================================================
# 异常
# ============================================================================

class TestException:
    """异常输入校验"""

    def test_missing_score_raises(self, opt):
        """feedback_data 缺少 score 字段 → ValueError"""
        with pytest.raises(ValueError, match="必须包含.*score"):
            opt.update({"features": ["industry"]})

    def test_invalid_score_raises(self, opt):
        """score 越界 (0 或 6) 或类型错误 → ValueError"""
        with pytest.raises(ValueError, match="score 必须是 1-5"):
            opt.update({"score": 0, "features": ["industry"]})
        with pytest.raises(ValueError, match="score 必须是 1-5"):
            opt.update({"score": 6, "features": ["industry"]})
        with pytest.raises(ValueError, match="score 必须是 1-5"):
            opt.update({"score": "3", "features": ["industry"]})

    def test_empty_initial_weights_raises(self):
        """initial_weights 为空字典 → ValueError"""
        with pytest.raises(ValueError, match="不能为空"):
            OnlineWeightOptimizer(initial_weights={})

    def test_features_not_list_raises(self, opt):
        """features 类型错误 (非 list/None) → ValueError"""
        with pytest.raises(ValueError, match="features 必须是 list"):
            opt.update({"score": 4, "features": "industry"})

    def test_invalid_l2_lambda_raises(self):
        """l2_lambda 为负 → ValueError"""
        with pytest.raises(ValueError, match="l2_lambda 不能为负"):
            OnlineWeightOptimizer(
                initial_weights={"a": 1.0}, l2_lambda=-0.1
            )

    def test_weight_min_ge_max_raises(self):
        """weight_min >= weight_max → ValueError"""
        with pytest.raises(ValueError, match="weight_min.*必须.*weight_max"):
            OnlineWeightOptimizer(
                initial_weights={"a": 1.0}, weight_min=2.0, weight_max=1.0
            )
