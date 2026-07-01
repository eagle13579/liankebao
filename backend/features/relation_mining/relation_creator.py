"""自动关系创建器 — 将信号强度达标的关系写入UserRelation表"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .signal_schema import RelationSignal, SignalType
from .signal_scorer import compute_relation_strength, should_create_relation
from .signal_collector import collect_all_signals

logger = logging.getLogger(__name__)


def auto_create_relations(db: Session, threshold: float = 0.4) -> Dict[str, int]:
    """自动识别并创建关系边
    
    流程：
    1. 全量采集关系信号
    2. 按实体对分组
    3. 计算每组的关系强度
    4. 超过阈值的自动创建 UserRelation 边
    
    Returns:
        统计: {created, skipped, errors, total_signals}
    """
    stats = {"created": 0, "skipped": 0, "errors": 0, "total_signals": 0}
    
    try:
        from app.models.six_degrees import UserRelation
        from sqlalchemy import and_
        
        signals = collect_all_signals(db)
        stats["total_signals"] = len(signals)
        
        if not signals:
            logger.info("无关系信号，跳过自动创建")
            return stats
        
        # 按实体对分组
        from collections import defaultdict
        pairs: Dict[Tuple[int, str, int, str], List[RelationSignal]] = defaultdict(list)
        for s in signals:
            key = (min(s.from_entity_id, s.to_entity_id),
                   s.from_entity_type if s.from_entity_id <= s.to_entity_id else s.to_entity_type,
                   max(s.from_entity_id, s.to_entity_id),
                   s.to_entity_type if s.to_entity_id >= s.from_entity_id else s.from_entity_type)
            pairs[key].append(s)
        
        now = datetime.now(timezone.utc)
        
        for (eid1, type1, eid2, type2), pair_signals in pairs.items():
            # 跳过user-user外的类型（当前UserRelation模型只支持user-user）
            if type1 != "user" or type2 != "user":
                stats["skipped"] += 1
                continue
            
            # 计算强度
            should_create, strength = should_create_relation(pair_signals, threshold)
            
            if not should_create:
                stats["skipped"] += 1
                continue
            
            try:
                # 检查是否已存在
                existing = db.query(UserRelation).filter(
                    and_(
                        UserRelation.user_id == eid1,
                        UserRelation.related_user_id == eid2
                    )
                ).first()
                
                if existing:
                    # 更新信任度（取较高值）
                    if strength > existing.trust_score:
                        existing.trust_score = strength
                        existing.updated_at = now
                    stats["skipped"] += 1
                    continue
                
                # 创建新关系
                relation = UserRelation(
                    user_id=eid1,
                    related_user_id=eid2,
                    trust_score=strength,
                    relation_type="auto_discovered",
                    is_bidirectional=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(relation)
                stats["created"] += 1
                
            except Exception as e:
                logger.error(f"创建关系失败 ({eid1}->{eid2}): {e}")
                stats["errors"] += 1
        
        db.commit()
        logger.info(f"自动关系创建完成: 新建{stats['created']}条, 跳过{stats['skipped']}条")
        
    except Exception as e:
        logger.error(f"自动关系创建失败: {e}")
        db.rollback()
    
    return stats


def run_mining_pipeline(db: Session) -> dict:
    """运行完整的关系挖掘流水线
    
    1. 采集信号
    2. 评分
    3. 自动创建
    4. 返回报告
    """
    result = auto_create_relations(db)
    result["pipeline_status"] = "completed"
    return result
