"""链客宝 — ML 模型模块

包含用户塔/企业塔/行为塔/场景塔等 DNN 子模型，
以及三塔拼接推理 API。

模块结构:
    user_tower.py         用户 Embedding 塔 (UserTower, UserFeatureEncoder)
    enterprise_tower.py   企业 Embedding 塔 (EnterpriseTower, EnterpriseFeatureEncoder)
    behavior_tower.py     行为序列塔 (BehaviorTower, BehaviorSequenceEncoder)
    tower_ensemble.py     三塔拼接推理 API (MatchingScorer, MatchingAPI)
"""

from .user_tower import UserTower, UserFeatureEncoder
from .enterprise_tower import EnterpriseTower, EnterpriseFeatureEncoder
from .behavior_tower import BehaviorTower, BehaviorSequenceEncoder
from .tower_ensemble import MatchingScorer, MatchingAPI, OnlineWeightOptimizer

__all__ = [
    # 用户塔
    "UserTower",
    "UserFeatureEncoder",
    # 企业塔
    "EnterpriseTower",
    "EnterpriseFeatureEncoder",
    # 行为塔
    "BehaviorTower",
    "BehaviorSequenceEncoder",
    # 三塔拼接
    "MatchingScorer",
    "MatchingAPI",
    "OnlineWeightOptimizer",
]
