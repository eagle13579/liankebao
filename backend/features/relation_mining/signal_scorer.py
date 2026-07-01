"""关系强度评分器 — 将关系信号转化为0.0~1.0的信任分数"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .signal_schema import RelationSignal, SignalType

logger = logging.getLogger(__name__)


# 信号类型权重配置
SIGNAL_WEIGHTS = {
    SignalType.CONTRACT_COLLABORATION: 0.30,     # 合同合作 — 最强信号
    SignalType.ORDER_PARTICIPATION: 0.25,         # 交易完成 — 强信号
    SignalType.ENTERPRISE_QUERY: 0.15,            # 企业查询 — 中等
    SignalType.CRM_PIPELINE_SHARED: 0.20,         # CRM管道 — 较强
    SignalType.SIX_DEGREE_EXTENSION: 0.10,        # 二度推荐 — 弱信号
    SignalType.SAME_ORGANIZATION: 0.20,           # 同组织 — 较强
}

# 信号时效衰减（天）
SIGNAL_DECAY_DAYS = {
    SignalType.CONTRACT_COLLABORATION: 730,       # 2年有效
    SignalType.ORDER_PARTICIPATION: 365,          # 1年有效
    SignalType.ENTERPRISE_QUERY: 90,              # 3个月有效
    SignalType.CRM_PIPELINE_SHARED: 180,          # 6个月有效
    SignalType.SIX_DEGREE_EXTENSION: 60,          # 2个月有效
    SignalType.SAME_ORGANIZATION: 365,            # 1年有效
}


def compute_relation_strength(signals: List[RelationSignal]) -> float:
    """计算实体间的关系强度（0.0~1.0）
    
    算法：
    1. 每种信号类型有基础权重
    2. 同类型信号叠加（但不超过该类型的上限）
    3. 时效衰减（越旧的信号权重越低）
    4. 最终分数 = 加权平均
    """
    if not signals:
        return 0.0
    
    now = datetime.now(timezone.utc)
    weighted_sum = 0.0
    total_weight = 0.0
    
    # 按类型分组
    by_type: Dict[SignalType, List[RelationSignal]] = {}
    for s in signals:
        if s.source_type not in by_type:
            by_type[s.source_type] = []
        by_type[s.source_type].append(s)
    
    for stype, stype_signals in by_type.items():
        base_weight = SIGNAL_WEIGHTS.get(stype, 0.1)
        decay_days = SIGNAL_DECAY_DAYS.get(stype, 180)
        
        # 同类型信号叠加（用对数防止无限增长）
        n = len(stype_signals)
        type_strength = min(1.0, 0.3 + 0.3 * (n ** 0.5))
        
        # 时效衰减
        max_age_days = max(
            ((now - s.created_at).total_seconds() / 86400)
            for s in stype_signals
        )
        if max_age_days >= decay_days:
            time_factor = 0.1  # 过期信号保留最低权重
        else:
            time_factor = 1.0 - (max_age_days / decay_days) * 0.7
        
        # 信号自身强度也参与计算
        avg_signal_strength = sum(s.signal_strength for s in stype_signals) / n
        
        composite = type_strength * time_factor * avg_signal_strength
        weighted_sum += base_weight * composite
        total_weight += base_weight
    
    if total_weight == 0:
        return 0.0
    
    return round(min(1.0, weighted_sum / total_weight), 3)


def get_signal_summary(signals: List[RelationSignal]) -> dict:
    """生成关系信号摘要"""
    by_type = {}
    for s in signals:
        key = s.source_type.value
        if key not in by_type:
            by_type[key] = {"count": 0, "latest": None, "evidence": []}
        by_type[key]["count"] += 1
        if by_type[key]["latest"] is None or s.created_at > by_type[key]["latest"]:
            by_type[key]["latest"] = s.created_at
        by_type[key]["evidence"].append(s.evidence[:100])
    
    return {
        "total_signals": len(signals),
        "by_type": by_type,
        "strength": compute_relation_strength(signals),
        "primary_source": max(by_type.keys(), key=lambda k: by_type[k]["count"]) if by_type else None,
    }


def should_create_relation(signals: List[RelationSignal], threshold: float = 0.4) -> Tuple[bool, float]:
    """判断是否应该自动创建关系边
    
    Args:
        signals: 实体间的关系信号列表
        threshold: 创建关系的最小强度阈值
    
    Returns:
        (should_create, strength)
    """
    strength = compute_relation_strength(signals)
    return strength >= threshold, strength
