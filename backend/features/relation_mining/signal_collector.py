"""关系信号采集器 — 从多个数据源扫描并输出关系信号"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from .signal_schema import RelationSignal, SignalType, SignalSource

logger = logging.getLogger(__name__)


def collect_all_signals(db: Session) -> List[RelationSignal]:
    """全量扫描所有数据源，返回所有关系信号"""
    signals: List[RelationSignal] = []
    
    # 1. 从合同中提取
    signals.extend(_collect_from_contracts(db))
    
    # 2. 从订单中提取
    signals.extend(_collect_from_orders(db))
    
    # 3. 从企业互动中提取
    signals.extend(_collect_from_enterprise_interactions(db))
    
    # 4. 从CRM管道中提取
    signals.extend(_collect_from_crm_pipeline(db))
    
    # 5. 从现有关系链扩展
    signals.extend(_collect_six_degree_extensions(db))
    
    logger.info(f"关系信号采集完成: 共 {len(signals)} 条")
    return signals


def collect_signals_for_user(db: Session, user_id: int) -> List[RelationSignal]:
    """为特定用户扫描关系信号"""
    all_signals = collect_all_signals(db)
    return [s for s in all_signals 
            if s.from_entity_id == user_id or s.to_entity_id == user_id]


def signal_stats(db: Session) -> dict:
    """信号统计数据"""
    signals = collect_all_signals(db)
    stats = {}
    for s in signals:
        key = s.source_type.value
        stats[key] = stats.get(key, 0) + 1
    stats["total"] = len(signals)
    return stats


def _collect_from_contracts(db: Session) -> List[RelationSignal]:
    """从合同表提取关系信号：同一合同的甲乙双方"""
    signals = []
    try:
        from app.models import Contract  # type: ignore
        contracts = db.query(Contract).filter(
            Contract.status == "signed"
        ).all()
        seen_pairs = set()
        for c in contracts:
            if hasattr(c, 'party_a_id') and hasattr(c, 'party_b_id') and c.party_a_id and c.party_b_id:
                pair = (min(c.party_a_id, c.party_b_id), max(c.party_a_id, c.party_b_id))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    signals.append(RelationSignal(
                        source_type=SignalType.CONTRACT_COLLABORATION,
                        source=SignalSource.CONTRACTS,
                        from_entity_id=c.party_a_id,
                        from_entity_type="enterprise",
                        to_entity_id=c.party_b_id,
                        to_entity_type="enterprise",
                        signal_strength=0.8,
                        evidence=f"合同 #{c.id}: 双方签署完成",
                        metadata={"contract_id": c.id}
                    ))
    except Exception as e:
        logger.warning(f"合同信号采集失败: {e}")
    return signals


def _collect_from_orders(db: Session) -> List[RelationSignal]:
    """从订单表提取关系信号：同一商机的参与方"""
    signals = []
    try:
        from app.models import Order  # type: ignore
        orders = db.query(Order).filter(Order.status.in_(["completed", "in_progress"])).all()
        seen = set()
        for o in orders:
            if hasattr(o, 'buyer_id') and hasattr(o, 'seller_id') and o.buyer_id and o.seller_id:
                pair = (min(o.buyer_id, o.seller_id), max(o.buyer_id, o.seller_id))
                if pair not in seen:
                    seen.add(pair)
                    signals.append(RelationSignal(
                        source_type=SignalType.ORDER_PARTICIPATION,
                        source=SignalSource.ORDERS,
                        from_entity_id=o.buyer_id,
                        from_entity_type="user",
                        to_entity_id=o.seller_id,
                        to_entity_type="user",
                        signal_strength=0.7,
                        evidence=f"订单 #{o.id}: 交易完成",
                        metadata={"order_id": o.id, "amount": getattr(o, 'amount', None)}
                    ))
    except Exception as e:
        logger.warning(f"订单信号采集失败: {e}")
    return signals


def _collect_from_enterprise_interactions(db: Session) -> List[RelationSignal]:
    """从企业互动日志提取关系信号"""
    signals = []
    try:
        from app.models import EnterpriseQuery  # type: ignore
        queries = db.query(EnterpriseQuery).order_by(EnterpriseQuery.created_at.desc()).limit(1000).all()
        user_enterprise_count = {}
        for q in queries:
            if hasattr(q, 'user_id') and hasattr(q, 'enterprise_id'):
                key = (q.user_id, q.enterprise_id)
                if key not in user_enterprise_count:
                    user_enterprise_count[key] = 0
                user_enterprise_count[key] += 1
        for (uid, eid), count in user_enterprise_count.items():
            if count >= 3:  # 查询同一企业≥3次视为强信号
                signals.append(RelationSignal(
                    source_type=SignalType.ENTERPRISE_QUERY,
                    source=SignalSource.ENTERPRISE_CRAWLER,
                    from_entity_id=uid,
                    from_entity_type="user",
                    to_entity_id=eid,
                    to_entity_type="enterprise",
                    signal_strength=min(0.9, 0.3 + count * 0.1),
                    evidence=f"用户 #{uid} 查询企业 #{eid} 共 {count} 次",
                    metadata={"query_count": count}
                ))
    except Exception as e:
        logger.warning(f"企业互动信号采集失败: {e}")
    return signals


def _collect_from_crm_pipeline(db: Session) -> List[RelationSignal]:
    """从CRM管道提取关系信号"""
    signals = []
    try:
        from app.models import CRMPipeline  # type: ignore
        pipelines = db.query(CRMPipeline).filter(
            CRMPipeline.status.in_(["active", "won"])
        ).all()
        for p in pipelines:
            if hasattr(p, 'user_id') and hasattr(p, 'client_id') and p.user_id and p.client_id:
                signals.append(RelationSignal(
                    source_type=SignalType.CRM_PIPELINE_SHARED,
                    source=SignalSource.CRM_PIPELINE,
                    from_entity_id=p.user_id,
                    from_entity_type="user",
                    to_entity_id=p.client_id,
                    to_entity_type="enterprise",
                    signal_strength=0.6,
                    evidence=f"CRM管道 #{p.id}: 阶段={getattr(p, 'stage', 'N/A')}",
                    metadata={"pipeline_id": p.id, "stage": getattr(p, 'stage', None)}
                ))
    except Exception as e:
        logger.warning(f"CRM信号采集失败: {e}")
    return signals


def _collect_six_degree_extensions(db: Session) -> List[RelationSignal]:
    """从现有关系链扩展：共同好友推荐"""
    signals = []
    try:
        from app.models.six_degrees import UserRelation  # type: ignore
        relations = db.query(UserRelation).filter(UserRelation.trust_score > 0.5).all()
        # 构建邻接表
        adj = {}
        for r in relations:
            for uid in [r.user_id, r.related_user_id]:
                if uid not in adj:
                    adj[uid] = set()
                other = r.related_user_id if r.user_id == uid else r.user_id
                adj[uid].add(other)
        # 寻找二度连接
        for uid, neighbors in adj.items():
            for n in neighbors:
                if n in adj:
                    for nn in adj[n]:
                        if nn != uid and nn not in neighbors:
                            signals.append(RelationSignal(
                                source_type=SignalType.SIX_DEGREE_EXTENSION,
                                source=SignalSource.USER_RELATIONS,
                                from_entity_id=uid,
                                from_entity_type="user",
                                to_entity_id=nn,
                                to_entity_type="user",
                                signal_strength=0.5,
                                evidence=f"通过 {n} 的二度连接推荐",
                                metadata={"via_user_id": n}
                            ))
    except Exception as e:
        logger.warning(f"六度扩展信号采集失败: {e}")
    return signals
