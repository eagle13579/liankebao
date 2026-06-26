"""链客宝 — 在线学习权重自动调优单元测试
===========================================

测试 OnlineWeightOptimizer (AdaGrad 风格):

  1.  test_initial_weights        — 初始权重正确返回
  2.  test_positive_feedback      — 正反馈提升权重
  3.  test_negative_feedback      — 负反馈降低权重
  4.  test_neutral_feedback       — 中性反馈轻微正向
  5.  test_lr_decay               — 同一特征反复更新后 lr 衰减
  6.  test_weight_bounds          — 权重被约束在 [0, 2]
  7.  test_l2_regularization      — L2 正则化防止发散
  8.  test_partial_feature_update — 只更新指定特征
  9.  test_no_features_global     — 无 features 时全局更新
  10. test_reset                  — reset() 回到初始态
  11. test_history_recording      — 历史记录完整
  12. test_invalid_score          — 非法 score 抛出异常
  13. test_empty_initial_weights  — 空初始权重抛出异常
"""

import math
import sys
import os

# ── 确保能找到 ml 模块 ──
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ml.online_learning import OnlineWeightOptimizer


# ===================================================================
# 1. 初始权重
# ===================================================================
def test_initial_weights():
    """初始权重应返回传入的字典"""
    init = {"industry": 1.0, "region": 0.8, "scale": 0.5}
    opt = OnlineWeightOptimizer(init)
    w = opt.get_weights()
    assert w == init, f"预期 {init}, 收到 {w}"
    print("  ✓ test_initial_weights")


# ===================================================================
# 2. 正反馈提升权重
# ===================================================================
def test_positive_feedback():
    """rating >= 4 应提升相关特征权重"""
    init = {"industry": 1.0, "region": 1.0}
    opt = OnlineWeightOptimizer(init, base_lr=0.1)
    before = opt.get_weights()["industry"]
    opt.update({"score": 5, "features": ["industry"]})
    after = opt.get_weights()["industry"]
    assert after > before, f"正反馈后权重应上升: {before} -> {after}"
    print("  ✓ test_positive_feedback")


# ===================================================================
# 3. 负反馈降低权重
# ===================================================================
def test_negative_feedback():
    """rating <= 2 应降低相关特征权重"""
    init = {"industry": 1.0, "region": 1.0}
    opt = OnlineWeightOptimizer(init, base_lr=0.1)
    before = opt.get_weights()["industry"]
    opt.update({"score": 1, "features": ["industry"]})
    after = opt.get_weights()["industry"]
    assert after < before, f"负反馈后权重应下降: {before} -> {after}"
    print("  ✓ test_negative_feedback")


# ===================================================================
# 4. 中性反馈轻微正向
# ===================================================================
def test_neutral_feedback():
    """score == 3 应产生轻微正向 (探索)"""
    init = {"industry": 1.0}
    opt = OnlineWeightOptimizer(init, base_lr=0.1, neutral_lr=0.05)
    before = opt.get_weights()["industry"]
    opt.update({"score": 3, "features": ["industry"]})
    after = opt.get_weights()["industry"]
    assert after > before, f"中性反馈后权重应微升: {before} -> {after}"
    print("  ✓ test_neutral_feedback")


# ===================================================================
# 5. 学习率衰减 (AdaGrad)
# ===================================================================
def test_lr_decay():
    """同一特征反复更新后, 每次增量应递减"""
    init = {"industry": 1.0}
    opt = OnlineWeightOptimizer(init, base_lr=0.5, epsilon=1e-12)

    deltas = []
    for _ in range(5):
        before = opt.get_weights()["industry"]
        opt.update({"score": 5, "features": ["industry"]})
        after = opt.get_weights()["industry"]
        deltas.append(abs(after - before))

    # 每次更新幅度应递减 (AdaGrad 特性)
    for i in range(1, len(deltas)):
        assert deltas[i] <= deltas[i - 1] + 1e-9, (
            f"第 {i+1} 次更新增量 ({deltas[i]:.8f}) "
            f"不应大于第 {i} 次 ({deltas[i-1]:.8f})"
        )
    print(f"  ✓ test_lr_decay  (deltas: {[f'{d:.6f}' for d in deltas]})")


# ===================================================================
# 6. 边界约束
# ===================================================================
def test_weight_bounds():
    """权重应始终保持在 [0, 2] 范围内"""
    init = {"industry": 1.0, "region": 0.5}
    opt = OnlineWeightOptimizer(init, base_lr=10.0, weight_min=0.0, weight_max=2.0)

    # 反复正反馈 → 不应超过 2.0
    for _ in range(100):
        opt.update({"score": 5, "features": ["industry"]})
    assert opt.get_weights()["industry"] <= 2.0 + 1e-9, (
        f"上界违规: {opt.get_weights()['industry']}"
    )

    # 反复负反馈 → 不应低于 0.0
    for _ in range(100):
        opt.update({"score": 1, "features": ["region"]})
    assert opt.get_weights()["region"] >= 0.0 - 1e-9, (
        f"下界违规: {opt.get_weights()['region']}"
    )

    print("  ✓ test_weight_bounds")


# ===================================================================
# 7. L2 正则化
# ===================================================================
def test_l2_regularization():
    """L2 正则化应抑制权重发散"""
    init = {"industry": 1.0}
    opt_no_reg = OnlineWeightOptimizer(init, base_lr=1.0, l2_lambda=0.0)
    opt_reg = OnlineWeightOptimizer(init, base_lr=1.0, l2_lambda=0.5)

    for _ in range(20):
        opt_no_reg.update({"score": 5, "features": ["industry"]})
        opt_reg.update({"score": 5, "features": ["industry"]})

    w_no_reg = opt_no_reg.get_weights()["industry"]
    w_reg = opt_reg.get_weights()["industry"]

    # 有正则化的权重应更小 (或相等)
    assert w_reg <= w_no_reg + 1e-9, (
        f"正则化应抑制权重: 无={w_no_reg:.4f}, 有={w_reg:.4f}"
    )
    print(f"  ✓ test_l2_regularization (no_reg={w_no_reg:.4f}, reg={w_reg:.4f})")


# ===================================================================
# 8. 部分特征更新
# ===================================================================
def test_partial_feature_update():
    """只更新 features 中指定的特征, 其他特征不变"""
    init = {"industry": 1.0, "region": 1.0, "scale": 1.0}
    opt = OnlineWeightOptimizer(init, base_lr=0.1)

    before_all = opt.get_weights()
    opt.update({"score": 5, "features": ["industry", "region"]})
    after_all = opt.get_weights()

    # industry 和 region 应变化
    assert after_all["industry"] != before_all["industry"], "industry 应变化"
    assert after_all["region"] != before_all["region"], "region 应变化"
    # scale 应保持不变
    assert after_all["scale"] == before_all["scale"], "scale 应保持不变"

    print("  ✓ test_partial_feature_update")


# ===================================================================
# 9. 无 features → 全局更新
# ===================================================================
def test_no_features_global():
    """不提供 features 时, 所有特征都应更新"""
    init = {"industry": 1.0, "region": 1.0}
    opt = OnlineWeightOptimizer(init, base_lr=0.1)

    before = opt.get_weights()
    opt.update({"score": 5})  # 无 features
    after = opt.get_weights()

    for feat in init:
        assert after[feat] != before[feat], (
            f"全局更新时 {feat} 应变化"
        )

    print("  ✓ test_no_features_global")


# ===================================================================
# 10. Reset
# ===================================================================
def test_reset():
    """reset() 应恢复初始权重并清空历史"""
    init = {"industry": 1.0, "region": 0.5}
    opt = OnlineWeightOptimizer(init)

    opt.update({"score": 5, "features": ["industry"]})
    opt.update({"score": 2, "features": ["region"]})
    assert len(opt.get_history()) == 2

    opt.reset()
    assert opt.get_weights() == init, "reset 后应恢复初始权重"
    assert len(opt.get_history()) == 0, "reset 后历史应为空"
    assert len(opt.get_weights()) == len(init)

    print("  ✓ test_reset")


# ===================================================================
# 11. 历史记录
# ===================================================================
def test_history_recording():
    """每次 update 应记录完整的历史条目"""
    init = {"industry": 1.0, "region": 0.8}
    opt = OnlineWeightOptimizer(init, base_lr=0.1)

    opt.update({"score": 4, "features": ["industry"]})
    h = opt.get_history()
    assert len(h) == 1

    entry = h[0]
    assert entry["score"] == 4
    assert entry["features"] == ["industry"]
    assert "grad_direction" in entry
    assert "target_features" in entry
    assert "before" in entry
    assert "after" in entry
    assert "delta" in entry
    assert entry["grad_direction"] == 1.0  # score >= 4

    print("  ✓ test_history_recording")


# ===================================================================
# 12. 非法 score
# ===================================================================
def test_invalid_score():
    """非法 score 应抛出 ValueError"""
    init = {"industry": 1.0}
    opt = OnlineWeightOptimizer(init)

    for bad in [None, 0, 6, -1, "5"]:
        try:
            opt.update({"score": bad, "features": ["industry"]})
            assert False, f"应抛出 ValueError: score={bad}"
        except ValueError:
            pass
        except TypeError:
            pass  # 某些类型比较也会抛异常

    print("  ✓ test_invalid_score")


# ===================================================================
# 13. 空初始权重
# ===================================================================
def test_empty_initial_weights():
    """空 initial_weights 应抛出 ValueError"""
    try:
        OnlineWeightOptimizer({})
        assert False, "应抛出 ValueError"
    except ValueError:
        pass
    print("  ✓ test_empty_initial_weights")


# ===================================================================
# 主入口
# ===================================================================
if __name__ == "__main__":
    print("=" * 56)
    print("  在线学习权重自动调优 — 单元测试")
    print("=" * 56)
    print()

    tests = [
        test_initial_weights,
        test_positive_feedback,
        test_negative_feedback,
        test_neutral_feedback,
        test_lr_decay,
        test_weight_bounds,
        test_l2_regularization,
        test_partial_feature_update,
        test_no_features_global,
        test_reset,
        test_history_recording,
        test_invalid_score,
        test_empty_initial_weights,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1

    print()
    print("-" * 56)
    print(f"  结果: {passed} 通过, {failed} 失败, {len(tests)} 总计")
    if failed == 0:
        print("  ✓ 全部通过!")
    else:
        print("  ✗ 存在失败的测试!")
    print("=" * 56)
