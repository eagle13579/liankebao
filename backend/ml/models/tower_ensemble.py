"""链客宝 — 三塔拼接推理 API (TowerEnsemble)

整合用户塔(UserTower)、企业塔(EnterpriseTower)、行为塔(BehaviorTower)，
实现企业-用户匹配评分与排序推理。

架构:
  MatchingScorer:
    score = α * cos(user_emb, ent_emb)
          + β * cos(behavior_emb, ent_emb)
          + γ * cos(user_emb, behavior_emb)

    权重默认: α=0.5 (用户-企业相似度), β=0.3 (行为-企业相似度), γ=0.2 (用户-行为一致性)

  MatchingAPI:
    predict(user_id, candidates) → 排序后的 [(enterprise, score), ...]

  OnlineWeightOptimizer:
    在线学习权重, 根据用户反馈 (点击/匹配成功) 调整 α/β/γ

Usage:
    from ml.models import MatchingScorer, MatchingAPI, OnlineWeightOptimizer

    scorer = MatchingScorer(user_tower, enterprise_tower, behavior_tower)
    score = scorer.score(user_feat_tensor, ent_feat_tensor, behavior_tensor, behavior_mask)

    api = MatchingAPI(scorer, user_encoder, ent_encoder, behavior_encoder)
    results = api.predict(user_id, candidate_list)

Author: 长乘 (P6, 内容部, 风格visionary适合组合创新)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS = {"alpha": 0.5, "beta": 0.3, "gamma": 0.2}

# ---------------------------------------------------------------------------
# 在线权重优化器
# ---------------------------------------------------------------------------
class OnlineWeightOptimizer:
    """在线权重优化器。

    根据用户隐式反馈 (点击/匹配成功) 在线调整 MatchingScorer 的三项权重。

    更新策略 (Bandit-like):
      α ← α + η * (reward - baseline) * (sim_user_ent - baseline_sim)
      (类似 Policy Gradient, 但简化)

    Args:
        lr: 学习率 (默认 0.01)
        baseline_decay: 基线衰减系数 (默认 0.9)
        initial_weights: 初始权重 dict {"alpha": 0.5, "beta": 0.3, "gamma": 0.2}
        weight_bounds: 权重范围 (默认 [0.1, 0.8])
    """

    def __init__(
        self,
        lr: float = 0.01,
        baseline_decay: float = 0.9,
        initial_weights: Optional[Dict[str, float]] = None,
        weight_bounds: Tuple[float, float] = (0.05, 0.9),
    ):
        self.lr = lr
        self.baseline_decay = baseline_decay
        self.weights = dict(initial_weights or DEFAULT_WEIGHTS)
        self.weight_bounds = weight_bounds

        # ── 状态 ──
        self.total_updates = 0
        self.reward_baseline = 0.0
        self.reward_history: List[float] = []
        self.weight_history: List[Dict[str, float]] = []

    def update(
        self,
        sim_user_ent: float,
        sim_behavior_ent: float,
        sim_user_behavior: float,
        reward: float,
    ) -> Dict[str, float]:
        """根据一次交互反馈更新权重。

        Args:
            sim_user_ent:      用户-企业余弦相似度
            sim_behavior_ent:  行为-企业余弦相似度
            sim_user_behavior: 用户-行为余弦相似度
            reward:            反馈奖励 (点击=1.0, 匹配成功=2.0, 无反应=0.0, 负反馈=-0.5)

        Returns:
            更新后的权重 dict
        """
        # ── 更新基线 ──
        self.reward_baseline = (
            self.baseline_decay * self.reward_baseline
            + (1 - self.baseline_decay) * reward
        )

        # ── 计算优势 (Advantage) ──
        advantage = reward - self.reward_baseline

        # ── 更新每个权重 ──
        # α: 如果用户-企业相似度高且有正反馈, 增大 α
        alpha_grad = advantage * (sim_user_ent - 0.5)
        self.weights["alpha"] += self.lr * alpha_grad

        # β: 如果行为-企业相似度高且有正反馈, 增大 β
        beta_grad = advantage * (sim_behavior_ent - 0.5)
        self.weights["beta"] += self.lr * beta_grad

        # γ: 如果用户-行为一致且正反馈, 增大 γ
        gamma_grad = advantage * (sim_user_behavior - 0.5)
        self.weights["gamma"] += self.lr * gamma_grad

        # ── 约束权重范围 ──
        lower, upper = self.weight_bounds
        for k in self.weights:
            self.weights[k] = max(lower, min(upper, self.weights[k]))

        # ── 归一化使权重和为 1 ──
        total = sum(self.weights.values())
        if total > 0:
            for k in self.weights:
                self.weights[k] /= total

        # ── 记录 ──
        self.total_updates += 1
        self.reward_history.append(reward)
        self.weight_history.append(dict(self.weights))

        return dict(self.weights)

    def get_weights(self) -> Dict[str, float]:
        """返回当前权重 (深拷贝)"""
        return dict(self.weights)

    def reset_weights(self, weights: Optional[Dict[str, float]] = None) -> None:
        """重置权重"""
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        self.reward_baseline = 0.0

    def __repr__(self) -> str:
        return (
            f"OnlineWeightOptimizer("
            f"α={self.weights['alpha']:.4f}, "
            f"β={self.weights['beta']:.4f}, "
            f"γ={self.weights['gamma']:.4f}, "
            f"updates={self.total_updates})"
        )


# ===================================================================
# 匹配评分器
# ===================================================================
class MatchingScorer:
    """三塔拼接匹配评分器。

    计算:
        score = α * cos(user_emb, ent_emb)
              + β * cos(behavior_emb, ent_emb)
              + γ * cos(user_emb, behavior_emb)

    Args:
        user_tower:       UserTower 实例
        enterprise_tower: EnterpriseTower 实例
        behavior_tower:   BehaviorTower 实例
        weights:          权重 dict {"alpha": 0.5, "beta": 0.3, "gamma": 0.2}
        use_online_opt:   是否使用 OnlineWeightOptimizer (默认 False)
    """

    def __init__(
        self,
        user_tower: nn.Module,
        enterprise_tower: nn.Module,
        behavior_tower: nn.Module,
        weights: Optional[Dict[str, float]] = None,
        use_online_opt: bool = False,
    ):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch is required for MatchingScorer.")

        self.user_tower = user_tower
        self.enterprise_tower = enterprise_tower
        self.behavior_tower = behavior_tower

        self.weights = dict(weights or DEFAULT_WEIGHTS)
        self.weight_optimizer: Optional[OnlineWeightOptimizer] = None
        if use_online_opt:
            self.weight_optimizer = OnlineWeightOptimizer(initial_weights=self.weights)

        # ── 设备 ──
        self.device = torch.device("cpu")
        # 自动检测设备
        params = list(self.user_tower.parameters())
        if params:
            self.device = params[0].device

    # ------------------------------------------------------------------
    # score: 单次评分
    # ------------------------------------------------------------------
    @torch.no_grad()
    def score(
        self,
        user_features: torch.Tensor,
        enterprise_features: torch.Tensor,
        behavior_sequence: Optional[torch.Tensor] = None,
        behavior_mask: Optional[torch.Tensor] = None,
    ) -> float:
        """计算用户与企业的匹配分数。

        Args:
            user_features:       (1, D_user) 用户特征
            enterprise_features: (1, D_ent) 企业特征
            behavior_sequence:   (1, S, D_behav) 行为序列 (可选)
            behavior_mask:       (1, S) 行为掩码 (可选)

        Returns:
            float: 0~1 匹配分数
        """
        # ── 确保 eval 模式 ──
        self.user_tower.eval()
        self.enterprise_tower.eval()
        self.behavior_tower.eval()

        # ── 移动到同一设备 ──
        user_features = user_features.to(self.device)
        enterprise_features = enterprise_features.to(self.device)

        # ── 计算嵌入 ──
        user_emb = self.user_tower(user_features)  # (1, 128)
        ent_emb = self.enterprise_tower(enterprise_features)  # (1, 128)

        # ── 计算相似度 ──
        sim_user_ent = F.cosine_similarity(user_emb, ent_emb, dim=1).item()

        # 如果没有行为数据, 只用 α 权重 (回退到双塔)
        if behavior_sequence is None:
            final_score = self.weights["alpha"] * sim_user_ent
            return float(max(0.0, min(1.0, final_score)))

        behavior_sequence = behavior_sequence.to(self.device)
        if behavior_mask is not None:
            behavior_mask = behavior_mask.to(self.device)

        behav_emb = self.behavior_tower(behavior_sequence, behavior_mask)  # (1, 128)

        sim_behavior_ent = F.cosine_similarity(behav_emb, ent_emb, dim=1).item()
        sim_user_behavior = F.cosine_similarity(user_emb, behav_emb, dim=1).item()

        # ── 计算加权分数 ──
        w = self.weights
        final_score = (
            w["alpha"] * sim_user_ent
            + w["beta"] * sim_behavior_ent
            + w["gamma"] * sim_user_behavior
        )

        # 记录最近相似度 (供权重优化使用)
        self._last_sims = (sim_user_ent, sim_behavior_ent, sim_user_behavior)

        return float(max(0.0, min(1.0, final_score)))

    # ------------------------------------------------------------------
    # forward: 批量评分 (返回张量)
    # ------------------------------------------------------------------
    @torch.no_grad()
    def forward(
        self,
        user_features: torch.Tensor,
        enterprise_features: torch.Tensor,
        behavior_sequence: Optional[torch.Tensor] = None,
        behavior_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """批量计算匹配分数。

        Args:
            user_features:       (1, D_user) 或 (B, D_user)
            enterprise_features: (1, D_ent) 或 (B, D_ent)
            behavior_sequence:   (1, S, D_behav) 或 None
            behavior_mask:       (1, S) 或 None

        Returns:
            (B,) 匹配分数张量
        """
        self.user_tower.eval()
        self.enterprise_tower.eval()
        self.behavior_tower.eval()

        user_features = user_features.to(self.device)
        enterprise_features = enterprise_features.to(self.device)

        user_emb = self.user_tower(user_features)
        ent_emb = self.enterprise_tower(enterprise_features)

        sim_user_ent = F.cosine_similarity(user_emb, ent_emb, dim=1)  # (B,) or (1,)

        if behavior_sequence is not None:
            behavior_sequence = behavior_sequence.to(self.device)
            if behavior_mask is not None:
                behavior_mask = behavior_mask.to(self.device)
            behav_emb = self.behavior_tower(behavior_sequence, behavior_mask)

            sim_behavior_ent = F.cosine_similarity(behav_emb, ent_emb, dim=1)
            sim_user_behavior = F.cosine_similarity(user_emb, behav_emb, dim=1)

            w = self.weights
            scores = (
                w["alpha"] * sim_user_ent
                + w["beta"] * sim_behavior_ent
                + w["gamma"] * sim_user_behavior
            )
        else:
            scores = self.weights["alpha"] * sim_user_ent

        return scores.clamp(0.0, 1.0)

    # ------------------------------------------------------------------
    # 权重管理
    # ------------------------------------------------------------------
    def update_weights(
        self,
        user_features: torch.Tensor,
        enterprise_features: torch.Tensor,
        behavior_sequence: Optional[torch.Tensor],
        behavior_mask: Optional[torch.Tensor],
        reward: float,
    ) -> Dict[str, float]:
        """根据反馈更新权重。

        Args:
            user_features:       用户特征
            enterprise_features: 企业特征
            behavior_sequence:   行为序列 (可选)
            behavior_mask:       行为掩码 (可选)
            reward:              反馈奖励

        Returns:
            更新后的权重 dict
        """
        if self.weight_optimizer is None:
            logger.warning("OnlineWeightOptimizer 未启用, 权重未更新")
            return dict(self.weights)

        # 先计算相似度 (使用 score 方法, 它会缓存到 _last_sims)
        self.score(
            user_features, enterprise_features,
            behavior_sequence, behavior_mask,
        )

        sim_user_ent, sim_behavior_ent, sim_user_behavior = self._last_sims
        new_weights = self.weight_optimizer.update(
            sim_user_ent, sim_behavior_ent, sim_user_behavior, reward,
        )
        self.weights = new_weights
        return new_weights

    def set_weights(self, weights: Dict[str, float]) -> None:
        """手动设置权重"""
        self.weights = dict(weights)

    def get_weights(self) -> Dict[str, float]:
        """获取当前权重"""
        return dict(self.weights)

    def __repr__(self) -> str:
        return (
            f"MatchingScorer("
            f"α={self.weights['alpha']:.3f}, "
            f"β={self.weights['beta']:.3f}, "
            f"γ={self.weights['gamma']:.3f}"
            f")"
        )


# ===================================================================
# 匹配推理 API
# ===================================================================
@dataclass
class MatchResult:
    """匹配结果数据类"""
    enterprise_id: Union[str, int]
    score: float
    sim_user_enterprise: float = 0.0
    sim_behavior_enterprise: float = 0.0
    sim_user_behavior: float = 0.0

    def __lt__(self, other: "MatchResult") -> bool:
        return self.score < other.score


class MatchingAPI:
    """三塔匹配推理 API。

    端到端推理管线: 用户特征 → 企业候选集 → 排序匹配。

    Args:
        scorer: MatchingScorer 实例
        user_encoder: UserFeatureEncoder 实例
        enterprise_encoder: EnterpriseFeatureEncoder 实例
        behavior_encoder: BehaviorSequenceEncoder 实例 (可选)
        top_k: 默认返回 top-K 结果 (默认 20)
        batch_size: 批量推理大小 (默认 64)
    """

    def __init__(
        self,
        scorer: MatchingScorer,
        user_encoder: Any,
        enterprise_encoder: Any,
        behavior_encoder: Optional[Any] = None,
        top_k: int = 20,
        batch_size: int = 64,
    ):
        self.scorer = scorer
        self.user_encoder = user_encoder
        self.enterprise_encoder = enterprise_encoder
        self.behavior_encoder = behavior_encoder
        self.top_k = top_k
        self.batch_size = batch_size

        self._validate_encoders()

    def _validate_encoders(self):
        """验证编码器状态"""
        if not hasattr(self.user_encoder, '_fitted') or not self.user_encoder._fitted:
            raise RuntimeError("user_encoder 尚未 fit")
        if not hasattr(self.enterprise_encoder, '_fitted') or not self.enterprise_encoder._fitted:
            raise RuntimeError("enterprise_encoder 尚未 fit")

    # ------------------------------------------------------------------
    # predict: 主推理入口
    # ------------------------------------------------------------------
    def predict(
        self,
        user_info: Union[Dict[str, Any], List[Dict[str, Any]]],
        candidates: List[Dict[str, Any]],
        behavior_sequences: Optional[Union[Dict, List[Dict], List[List[Dict]]]] = None,
        top_k: Optional[int] = None,
    ) -> List[MatchResult]:
        """执行匹配推理, 返回排序后的匹配列表。

        Args:
            user_info: 用户信息 dict (或 list[dict] 批量)
            candidates: 候选企业信息列表 [{"enterprise_id": ..., "registered_capital_log": ..., ...}, ...]
            behavior_sequences: 用户行为序列 (可选)
                - None: 只用双塔 (用户+企业)
                - Dict: 单条行为
                - List[Dict]: 行为序列
                - List[List[Dict]]: 批量行为序列
            top_k: 返回 top-K (默认使用实例的 top_k)

        Returns:
            List[MatchResult]: 按分数降序排列
        """
        top_k = top_k or self.top_k

        # ── 编码用户特征 ──
        user_tensor = self.user_encoder.transform(user_info)  # (1, D) 或 (B, D)

        # ── 编码行为序列 ──
        behavior_tensor = None
        behavior_mask = None
        if behavior_sequences is not None and self.behavior_encoder is not None:
            behavior_tensor, behavior_mask = self.behavior_encoder.transform(
                behavior_sequences
            )

        # ── 批量推理候选企业 ──
        all_results: List[MatchResult] = []
        n_candidates = len(candidates)

        for start in range(0, n_candidates, self.batch_size):
            end = min(start + self.batch_size, n_candidates)
            batch = candidates[start:end]

            # 编码企业特征
            ent_tensor = self.enterprise_encoder.transform(batch)  # (B, D_ent)

            # 如果用户是单条, 扩展为批量
            if user_tensor.dim() == 2 and user_tensor.size(0) == 1:
                u_tensor = user_tensor.expand(len(batch), -1)
            else:
                u_tensor = user_tensor

            # 行为扩展
            b_tensor = behavior_tensor
            b_mask = behavior_mask
            if b_tensor is not None and b_tensor.size(0) == 1 and len(batch) > 1:
                b_tensor = b_tensor.expand(len(batch), -1, -1)
                b_mask = b_mask.expand(len(batch), -1) if b_mask is not None else None

            # 批量评分 (使用 forward)
            scores = self.scorer.forward(u_tensor, ent_tensor, b_tensor, b_mask)

            # 收集结果
            for i, (score, ent) in enumerate(zip(scores.cpu().tolist(), batch)):
                ent_id = ent.get("enterprise_id", ent.get("id", f"ent_{start + i}"))
                all_results.append(MatchResult(
                    enterprise_id=ent_id,
                    score=score,
                ))

        # ── 排序 ──
        all_results.sort(key=lambda r: r.score, reverse=True)

        return all_results[:top_k]

    # ------------------------------------------------------------------
    # predict_with_feedback: 推理 + 反馈学习
    # ------------------------------------------------------------------
    def predict_with_feedback(
        self,
        user_info: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        behavior_sequences: Optional[Union[Dict, List[Dict]]] = None,
        feedback_reward: Optional[float] = None,
        top_k: Optional[int] = None,
    ) -> Tuple[List[MatchResult], Optional[Dict[str, float]]]:
        """推理并可选地更新权重。

        Args:
            user_info: 用户信息
            candidates: 候选企业列表
            behavior_sequences: 行为序列
            feedback_reward: 反馈奖励 (None=不更新权重)
            top_k: 返回 top-K

        Returns:
            (results, new_weights_or_None)
        """
        results = self.predict(user_info, candidates, behavior_sequences, top_k)

        new_weights = None
        if feedback_reward is not None and results:
            # 使用 top-1 结果的相似度更新权重
            user_tensor = self.user_encoder.transform(user_info)
            top_ent = candidates[0] if isinstance(candidates[0], dict) else candidates[0]

            # 使用 scorer.update_weights (需要找到匹配的候选)
            ent_tensor = self.enterprise_encoder.transform([top_ent])
            b_tensor, b_mask = None, None
            if behavior_sequences is not None and self.behavior_encoder is not None:
                b_tensor, b_mask = self.behavior_encoder.transform(behavior_sequences)

            new_weights = self.scorer.update_weights(
                user_tensor, ent_tensor, b_tensor, b_mask, feedback_reward,
            )

        return results, new_weights

    def __repr__(self) -> str:
        return (
            f"MatchingAPI("
            f"scorer={self.scorer}, "
            f"top_k={self.top_k}, "
            f"batch_size={self.batch_size})"
        )


# ===================================================================
# 简易测试 (python tower_ensemble.py)
# ===================================================================
def _test_matching_scorer_score():
    """TC1: MatchingScorer.score 基本评分"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    # 创建小模型
    from user_tower import UserTower
    from enterprise_tower import EnterpriseTower
    from behavior_tower import BehaviorTower

    user_tower = UserTower(num_features=4, embedding_dim=128, hidden_dims=[64, 128])
    ent_tower = EnterpriseTower(num_features=6, embedding_dim=128, hidden_dims=[64, 128])
    behav_tower = BehaviorTower(max_seq_len=5, feature_dim=8, hidden_dim=64)

    scorer = MatchingScorer(user_tower, ent_tower, behav_tower)

    u = torch.randn(1, 4)
    e = torch.randn(1, 6)
    b = torch.randn(1, 5, 8)
    m = torch.ones(1, 5, dtype=torch.bool)

    # 带行为数据
    score = scorer.score(u, e, b, m)
    assert isinstance(score, float), f"score 应为 float, 收到 {type(score)}"
    assert 0.0 <= score <= 1.0, f"score 应在 [0,1] 范围内, 收到 {score}"
    print(f"  ✓ test_matching_scorer_score (score={score:.6f})")


def _test_matching_scorer_no_behavior():
    """TC2: 无行为数据时的评分回退"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    from user_tower import UserTower
    from enterprise_tower import EnterpriseTower
    from behavior_tower import BehaviorTower

    user_tower = UserTower(num_features=4, embedding_dim=128, hidden_dims=[64, 128])
    ent_tower = EnterpriseTower(num_features=6, embedding_dim=128, hidden_dims=[64, 128])
    behav_tower = BehaviorTower(max_seq_len=5, feature_dim=8, hidden_dim=64)

    scorer = MatchingScorer(user_tower, ent_tower, behav_tower)

    u = torch.randn(1, 4)
    e = torch.randn(1, 6)

    # 无行为数据
    score = scorer.score(u, e)
    assert isinstance(score, float), f"score 应为 float, 收到 {type(score)}"
    assert 0.0 <= score <= 1.0, f"score 应在 [0,1] 范围内, 收到 {score}"
    print(f"  ✓ test_matching_scorer_no_behavior (score={score:.6f})")


def _test_matching_scorer_forward():
    """TC3: MatchingScorer.forward 批量评分"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    from user_tower import UserTower
    from enterprise_tower import EnterpriseTower
    from behavior_tower import BehaviorTower

    user_tower = UserTower(num_features=4, embedding_dim=128, hidden_dims=[64, 128])
    ent_tower = EnterpriseTower(num_features=6, embedding_dim=128, hidden_dims=[64, 128])
    behav_tower = BehaviorTower(max_seq_len=5, feature_dim=8, hidden_dim=64)

    scorer = MatchingScorer(user_tower, ent_tower, behav_tower)

    B = 3
    u = torch.randn(B, 4)
    e = torch.randn(B, 6)
    b = torch.randn(B, 5, 8)
    m = torch.ones(B, 5, dtype=torch.bool)

    scores = scorer.forward(u, e, b, m)
    assert scores.shape == (B,), f"forward 输出 shape 应为 ({B},), 收到 {scores.shape}"
    assert (scores >= 0).all() and (scores <= 1).all(), "分数应在 [0,1]"
    print(f"  ✓ test_matching_scorer_forward (scores={scores.tolist()})")


def _test_online_weight_optimizer():
    """TC4: OnlineWeightOptimizer 权重更新"""
    opt = OnlineWeightOptimizer(lr=0.1)

    # 初始权重
    w0 = opt.get_weights()
    assert abs(w0["alpha"] - 0.5) < 0.01

    # 正反馈更新: 用户-企业相似度高, 有正反馈 → α 应增大
    w1 = opt.update(
        sim_user_ent=0.9, sim_behavior_ent=0.3, sim_user_behavior=0.5, reward=1.0
    )
    assert opt.total_updates == 1
    assert all(0.05 <= v <= 0.9 for v in w1.values()), "权重应在范围内"
    assert abs(sum(w1.values()) - 1.0) < 0.01, "权重和应为 1"

    # 负反馈更新
    w2 = opt.update(
        sim_user_ent=0.2, sim_behavior_ent=0.8, sim_user_behavior=0.3, reward=-0.5
    )
    assert opt.total_updates == 2
    print(f"  ✓ test_online_weight_optimizer (w={w2})")


def _test_online_weight_reset():
    """TC5: 权重重置"""
    opt = OnlineWeightOptimizer()
    opt.update(sim_user_ent=0.5, sim_behavior_ent=0.5, sim_user_behavior=0.5, reward=1.0)
    opt.reset_weights()
    w = opt.get_weights()
    assert abs(w["alpha"] - 0.5) < 0.01
    assert abs(w["beta"] - 0.3) < 0.01
    assert abs(w["gamma"] - 0.2) < 0.01
    print("  ✓ test_online_weight_reset")


def _test_matching_api_predict():
    """TC6: MatchingAPI.predict 端到端"""
    try:
        import pandas as pd
    except ImportError:
        print("  ⚠ pandas 不可用, 跳过测试")
        return

    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    from user_tower import UserTower, UserFeatureEncoder
    from enterprise_tower import EnterpriseTower, EnterpriseFeatureEncoder
    from behavior_tower import BehaviorTower, BehaviorSequenceEncoder

    # ── 创建并 fit 编码器 ──
    user_encoder = UserFeatureEncoder(embedding_dim=4)
    user_df = pd.DataFrame({
        "industry_code": [1, 2], "scale": [10, 50], "region_code": [1, 2],
        "cooperation_type": ["supply", "demand"], "budget_level": ["low", "high"],
    })
    user_encoder.fit(user_df)

    ent_encoder = EnterpriseFeatureEncoder()
    ent_df = pd.DataFrame({
        "registered_capital_log": [1.0, 2.0], "established_years": [3, 5],
        "industry_code": [1, 2], "enterprise_scale": [1, 2],
        "credit_rating": [3, 4], "risk_count": [0, 1],
    })
    ent_encoder.fit(ent_df)

    behav_encoder = BehaviorSequenceEncoder(max_seq_len=5, feature_dim=16)
    behav_df = pd.DataFrame({
        "behavior_type": ["view", "browse"], "timestamp_gap": [0.0, 1.0],
        "duration": [5.0, 30.0], "target_id": [101, 102], "action_value": [1.0, 2.0],
    })
    behav_encoder.fit(behav_df)

    # ── 创建塔 ──
    user_tower = UserTower(num_features=user_encoder.total_feature_dim, embedding_dim=128, hidden_dims=[64, 128])
    ent_tower = EnterpriseTower(num_features=6, embedding_dim=128, hidden_dims=[64, 128])
    behav_tower = BehaviorTower(max_seq_len=5, feature_dim=16, hidden_dim=64)

    # ── 创建 scorer 和 API ──
    scorer = MatchingScorer(user_tower, ent_tower, behav_tower)
    api = MatchingAPI(scorer, user_encoder, ent_encoder, behav_encoder, top_k=5)

    # ── 推理 ──
    user_info = {"industry_code": 1, "scale": 20, "region_code": 2,
                 "cooperation_type": "supply", "budget_level": "low"}

    candidates = [
        {"enterprise_id": 1, "registered_capital_log": 1.0, "established_years": 3,
         "industry_code": 1, "enterprise_scale": 1, "credit_rating": 3, "risk_count": 0},
        {"enterprise_id": 2, "registered_capital_log": 2.0, "established_years": 5,
         "industry_code": 2, "enterprise_scale": 2, "credit_rating": 4, "risk_count": 1},
        {"enterprise_id": 3, "registered_capital_log": 3.0, "established_years": 10,
         "industry_code": 3, "enterprise_scale": 3, "credit_rating": 5, "risk_count": 2},
    ]

    behavior = [
        {"behavior_type": "view", "timestamp_gap": 0.0, "duration": 5.0, "target_id": 101, "action_value": 1.0},
        {"behavior_type": "browse", "timestamp_gap": 1.0, "duration": 30.0, "target_id": 102, "action_value": 2.0},
    ]

    results = api.predict(user_info, candidates, behavior)
    assert len(results) <= 5, f"返回结果应 ≤5, 收到 {len(results)}"
    assert all(isinstance(r, MatchResult) for r in results)
    # 检查是否按分数降序
    for i in range(len(results) - 1):
        assert results[i].score >= results[i + 1].score, "结果应按分数降序排列"
    print(f"  ✓ test_matching_api_predict (results={len(results)}, top_score={results[0].score:.4f})")


def _test_matching_api_no_behavior():
    """TC7: MatchingAPI 无行为序列推理"""
    try:
        import pandas as pd
    except ImportError:
        print("  ⚠ pandas 不可用, 跳过测试")
        return

    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    from user_tower import UserTower, UserFeatureEncoder
    from enterprise_tower import EnterpriseTower, EnterpriseFeatureEncoder
    from behavior_tower import BehaviorTower

    user_encoder = UserFeatureEncoder(embedding_dim=4)
    user_df = pd.DataFrame({
        "industry_code": [1], "scale": [10], "region_code": [1],
        "cooperation_type": ["supply"], "budget_level": ["low"],
    })
    user_encoder.fit(user_df)

    ent_encoder = EnterpriseFeatureEncoder()
    ent_df = pd.DataFrame({
        "registered_capital_log": [1.0], "established_years": [3],
        "industry_code": [1], "enterprise_scale": [1],
        "credit_rating": [3], "risk_count": [0],
    })
    ent_encoder.fit(ent_df)

    user_tower = UserTower(num_features=user_encoder.total_feature_dim, embedding_dim=128, hidden_dims=[64, 128])
    ent_tower = EnterpriseTower(num_features=6, embedding_dim=128, hidden_dims=[64, 128])
    behav_tower = BehaviorTower(max_seq_len=5, feature_dim=16, hidden_dim=64)

    scorer = MatchingScorer(user_tower, ent_tower, behav_tower)
    api = MatchingAPI(scorer, user_encoder, ent_encoder, top_k=3)

    # 无行为序列
    results = api.predict(
        {"industry_code": 1, "scale": 10, "region_code": 1,
         "cooperation_type": "supply", "budget_level": "low"},
        [{"enterprise_id": 1, "registered_capital_log": 1.0, "established_years": 3,
          "industry_code": 1, "enterprise_scale": 1, "credit_rating": 3, "risk_count": 0}],
    )
    assert len(results) == 1
    print(f"  ✓ test_matching_api_no_behavior (score={results[0].score:.4f})")


def _test_match_result_dataclass():
    """TC8: MatchResult 排序"""
    r1 = MatchResult(enterprise_id=1, score=0.9)
    r2 = MatchResult(enterprise_id=2, score=0.5)
    r3 = MatchResult(enterprise_id=3, score=0.7)

    sorted_results = sorted([r1, r2, r3], reverse=True)
    assert sorted_results[0].score == 0.9
    assert sorted_results[1].score == 0.7
    assert sorted_results[2].score == 0.5
    print("  ✓ test_match_result_dataclass")


# ===================================================================
# 主入口
# ===================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  三塔拼接推理 API — 单元测试")
    print("=" * 60)
    print()

    tests = [
        ("MatchingScorer.score 基本评分", _test_matching_scorer_score),
        ("无行为数据评分回退", _test_matching_scorer_no_behavior),
        ("MatchingScorer.forward 批量评分", _test_matching_scorer_forward),
        ("OnlineWeightOptimizer 权重更新", _test_online_weight_optimizer),
        ("权重重置", _test_online_weight_reset),
        ("MatchingAPI.predict 端到端", _test_matching_api_predict),
        ("MatchingAPI 无行为序列", _test_matching_api_no_behavior),
        ("MatchResult 排序", _test_match_result_dataclass),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print("-" * 60)
    print(f"  结果: {passed} 通过, {failed} 失败, {len(tests)} 总计")
    if failed == 0:
        print("  ✓ 全部通过!")
    else:
        print("  ✗ 存在失败的测试!")
    print("=" * 60)
