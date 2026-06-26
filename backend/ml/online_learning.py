"""链客宝 — 在线学习权重自动调优 (AdaGrad 风格)
===============================================

在线学习管道核心模块。根据用户反馈信号，以 AdaGrad 自适应学习率
实时调整推荐特征权重。

算法:
  1. 每个特征维护独立累积梯度平方和，实现自适应学习率
     lr_i = base_lr / sqrt(grad_sq_sum_i + epsilon)
  2. 反馈方向:
     - positive (score >= 4): 梯度方向 +1 (提升权重)
     - negative (score <= 2): 梯度方向 -1 (降低权重)
     - neutral  (score == 3): 梯度方向 +0.1 (轻微正向, 保持探索)
  3. L2 weight decay 正则化防过拟合
  4. 权重裁剪至 [0, 2] 区间

用例:
  optimizer = OnlineWeightOptimizer({"industry": 1.0, "region": 1.0})
  optimizer.update({"score": 5, "features": ["industry", "region"]})
  current_weights = optimizer.get_weights()

数据契约:
  - feedback_data 是 dict, 必须包含 "score" (int, 1-5)
  - 可选键 "features": list[str] 表示本次反馈相关的特征名
  - 无 features 时: 对所有特征做全局学习率调整 (基础学习率 base_lr)
"""

import copy
import math
from typing import Optional


class OnlineWeightOptimizer:
    """AdaGrad 风格在线学习权重优化器

    Args:
        initial_weights: 初始权重字典 {特征名: 权重值}
        base_lr:         基础学习率 (默认 0.01)
        epsilon:         数值稳定常数, 避免除零 (默认 1e-8)
        l2_lambda:       L2 正则化强度 (默认 0.001)
        weight_min:      权重下界 (默认 0.0)
        weight_max:      权重上界 (默认 2.0)
        neutral_lr:      neutral 反馈的梯度幅值 (默认 0.1)
    """

    def __init__(
        self,
        initial_weights: dict,
        base_lr: float = 0.01,
        epsilon: float = 1e-8,
        l2_lambda: float = 0.001,
        weight_min: float = 0.0,
        weight_max: float = 2.0,
        neutral_lr: float = 0.1,
    ):
        # ── 校验 ──
        if not initial_weights:
            raise ValueError("initial_weights 不能为空")
        if base_lr <= 0:
            raise ValueError(f"base_lr 必须 > 0, 收到: {base_lr}")
        if l2_lambda < 0:
            raise ValueError(f"l2_lambda 不能为负, 收到: {l2_lambda}")
        if weight_min >= weight_max:
            raise ValueError(
                f"weight_min ({weight_min}) 必须 < weight_max ({weight_max})"
            )

        self._base_lr = base_lr
        self._epsilon = epsilon
        self._l2_lambda = l2_lambda
        self._weight_min = weight_min
        self._weight_max = weight_max
        self._neutral_lr = neutral_lr

        # ── 初始状态 ──
        self._initial_weights = {k: float(v) for k, v in initial_weights.items()}
        self._weights: dict[str, float] = copy.deepcopy(self._initial_weights)
        # 每个特征累积梯度平方和 (AdaGrad)
        self._grad_sq_sum: dict[str, float] = {k: 0.0 for k in self._initial_weights}
        # 权重变化历史
        self._history: list[dict] = []

    # ==================================================================
    # 公开接口
    # ==================================================================

    def update(self, feedback_data: dict) -> dict:
        """根据一条反馈信号更新特征权重

        Args:
            feedback_data: 包含以下键的字典:
                - "score":   int, 1-5 评分
                - "features": list[str], 可选, 关联的特征名列表
                - 可包含其他键 (如 "target_type", "target_id"), 会被忽略

        Returns:
            dict: 更新后的权重快照

        Raises:
            ValueError: feedback_data 缺少 "score" 或 score 无效
        """
        score = feedback_data.get("score")
        if score is None:
            raise ValueError("feedback_data 必须包含 'score' 字段")
        if not isinstance(score, int) or score < 1 or score > 5:
            raise ValueError(f"score 必须是 1-5 的整数, 收到: {score}")

        features = feedback_data.get("features")
        if features is not None and not isinstance(features, list):
            raise ValueError("features 必须是 list[str] 或 None")

        # ── 计算梯度方向 ──
        grad_direction = self._compute_grad_direction(score)

        # ── 确定待更新的特征集 ──
        if features and len(features) > 0:
            # 只更新 feedback_data 中指定的特征 (且必须是已知特征)
            target_features = [f for f in features if f in self._weights]
            if not target_features:
                # 指定的特征都不在已知集合中，降级为全局更新
                target_features = list(self._weights.keys())
        else:
            # 无 context: 全局学习率调整 (所有特征)
            target_features = list(self._weights.keys())

        # ── 逐特征 AdaGrad 更新 ──
        before = copy.deepcopy(self._weights)
        for feat in target_features:
            self._adagrad_step(feat, grad_direction)

        # ── 记录历史 ──
        entry = {
            "score": score,
            "features": features,
            "grad_direction": grad_direction,
            "target_features": target_features,
            "before": before,
            "after": copy.deepcopy(self._weights),
            "delta": {
                f: round(self._weights[f] - before.get(f, 0), 6)
                for f in target_features
            },
        }
        self._history.append(entry)

        return self._weights

    def get_weights(self) -> dict:
        """获取当前特征权重快照"""
        return copy.deepcopy(self._weights)

    def get_history(self) -> list[dict]:
        """获取所有更新历史记录"""
        return copy.deepcopy(self._history)

    def reset(self) -> None:
        """重置优化器到初始状态"""
        self._weights = copy.deepcopy(self._initial_weights)
        self._grad_sq_sum = {k: 0.0 for k in self._initial_weights}
        self._history.clear()

    # ==================================================================
    # 内部方法
    # ==================================================================

    def _compute_grad_direction(self, score: int) -> float:
        """根据评分计算梯度方向

        Args:
            score: 1-5 评分

        Returns:
            float: 梯度方向值 (正数=提升权重, 负数=降低权重)
        """
        if score >= 4:
            return 1.0
        elif score <= 2:
            return -1.0
        else:  # score == 3
            return self._neutral_lr

    def _adagrad_step(self, feature: str, raw_grad: float) -> None:
        """对单个特征执行 AdaGrad 风格更新步

        Args:
            feature:  特征名
            raw_grad: 当前梯度方向 (原始的, 未缩放)
        """
        w = self._weights[feature]

        # ── L2 正则化梯度: grad_reg = raw_grad - l2_lambda * w ──
        grad = raw_grad - self._l2_lambda * w

        # ── AdaGrad: 累积梯度平方 → 自适应学习率 ──
        self._grad_sq_sum[feature] += grad * grad
        adaptive_lr = self._base_lr / (
            math.sqrt(self._grad_sq_sum[feature]) + self._epsilon
        )

        # ── 权重更新 ──
        w_new = w + adaptive_lr * grad

        # ── 边界约束 ──
        w_new = max(self._weight_min, min(self._weight_max, w_new))

        self._weights[feature] = round(w_new, 6)

    def __repr__(self) -> str:
        return (
            f"OnlineWeightOptimizer("
            f"features={len(self._weights)}, "
            f"base_lr={self._base_lr}, "
            f"updates={len(self._history)})"
        )
