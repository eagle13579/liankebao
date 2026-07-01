"""
多臂老虎机个性化引擎 (Thompson Sampling)
==========================================
基于 Beta 分布的 Thompson 采样实现，用于候选内容排序与在线学习。
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class Arm:
    """单臂 — Beta 分布参数"""
    arm_id: str
    alpha: float = 1.0
    beta: float = 1.0


class ThompsonSampling:
    """Thompson Sampling 选择器（纯 numpy 实现）"""

    def __init__(self):
        self.arms: list[Arm] = []

    def set_arms(self, arms: list[Arm]):
        self.arms = arms

    def select_arm(self, arms: Optional[list[Arm]] = None) -> int:
        """对每个臂从 Beta(alpha, beta) 采样，返回最大采样值对应的索引"""
        candidates = arms if arms is not None else self.arms
        samples = np.random.beta(
            [a.alpha for a in candidates],
            [a.beta for a in candidates],
        )
        return int(np.argmax(samples))

    def update(self, arm_index: int, reward: float):
        """根据奖励 (0/1) 更新臂的 Beta 分布参数"""
        arm = self.arms[arm_index]
        if reward >= 0.5:
            arm.alpha += 1.0
        else:
            arm.beta += 1.0

    def get_expected_value(self, arm_index: int) -> float:
        """返回臂的期望值 alpha / (alpha + beta)"""
        arm = self.arms[arm_index]
        return arm.alpha / (arm.alpha + arm.beta)


class BanditService:
    """多臂老虎机排序服务 — 管理用户与会话级别的 Thompson 采样"""

    def __init__(self, arms_config: Optional[dict] = None):
        self.ts = ThompsonSampling()
        # user_id -> {arm_id: Arm}
        self.user_arms: dict[str, dict[str, Arm]] = {}
        self.arms_config = arms_config or {}

    def _get_user_arms(self, user_id: str, candidate_ids: list[str]) -> list[Arm]:
        """获取或创建用户对候选臂的 Beta 参数"""
        if user_id not in self.user_arms:
            self.user_arms[user_id] = {}
        user_dict = self.user_arms[user_id]
        arms = []
        for cid in candidate_ids:
            if cid not in user_dict:
                user_dict[cid] = Arm(arm_id=cid, alpha=1.0, beta=1.0)
            arms.append(user_dict[cid])
        return arms

    def recommend(self, candidates: list, user_id: str, top_k: int = 10,
                  id_key: str = "id") -> list:
        """对候选列表应用 Thompson 采样排序，返回重排后的列表"""
        if not candidates:
            return []

        candidate_ids = [
            c[id_key] if isinstance(c, dict) else getattr(c, id_key)
            for c in candidates
        ]
        arms = self._get_user_arms(user_id, candidate_ids)
        self.ts.set_arms(arms)

        # Thompson 采样排序：每次选最优，移出候选
        remaining = list(candidates)
        remaining_ids = list(candidate_ids)
        reordered = []
        for _ in range(min(top_k, len(remaining))):
            arms_now = self._get_user_arms(user_id, remaining_ids)
            self.ts.set_arms(arms_now)
            idx = self.ts.select_arm()
            reordered.append(remaining.pop(idx))
            remaining_ids.pop(idx)

        return reordered

    def record_reward(self, user_id: str, arm_id: str, reward: float):
        """记录奖励并更新对应臂的 Beta 分布"""
        if user_id not in self.user_arms or arm_id not in self.user_arms[user_id]:
            # 首次见到的臂，先创建
            if user_id not in self.user_arms:
                self.user_arms[user_id] = {}
            self.user_arms[user_id][arm_id] = Arm(arm_id=arm_id, alpha=1.0, beta=1.0)
        arm = self.user_arms[user_id][arm_id]
        self.ts.arms = list(self.user_arms[user_id].values())
        arm_idx = [a.arm_id for a in self.ts.arms].index(arm_id)
        self.ts.update(arm_idx, reward)
