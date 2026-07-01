"""关系挖掘 — API 路由"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/relation-mining",
    tags=["relation-mining"],
)


@router.post("/scan")
def scan_signals(db: Session = Depends(get_db)):
    """触发全量扫描，返回信号统计"""
    try:
        from features.relation_mining.signal_collector import collect_all_signals, signal_stats
        signals = collect_all_signals(db)
        stats = signal_stats(db)
        return {"success": True, "data": {"total_signals": len(signals), "stats": stats}}
    except Exception as e:
        logger.error(f"扫描失败: {e}")
        return {"success": False, "data": None, "message": str(e)}


@router.get("/signals")
def list_signals(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """列出所有关系信号"""
    try:
        from features.relation_mining.signal_collector import collect_all_signals
        from features.relation_mining.signal_scorer import get_signal_summary
        signals = collect_all_signals(db)
        result = []
        for s in signals[:limit]:
            result.append({
                "source_type": s.source_type.value,
                "from_entity_id": s.from_entity_id,
                "from_entity_type": s.from_entity_type,
                "to_entity_id": s.to_entity_id,
                "to_entity_type": s.to_entity_type,
                "signal_strength": s.signal_strength,
                "evidence": s.evidence[:200],
                "created_at": s.created_at.isoformat(),
            })
        return {"success": True, "data": {"signals": result, "total": len(signals), "returned": len(result)}}
    except Exception as e:
        logger.error(f"信号查询失败: {e}")
        return {"success": False, "data": None, "message": str(e)}


@router.get("/signals/{user_id}")
def user_signals(user_id: int, db: Session = Depends(get_db)):
    """查询特定用户的关系信号"""
    try:
        from features.relation_mining.signal_collector import collect_signals_for_user
        from features.relation_mining.signal_scorer import compute_relation_strength
        signals = collect_signals_for_user(db, user_id)
        return {
            "success": True,
            "data": {
                "user_id": user_id,
                "total_signals": len(signals),
                "strength": compute_relation_strength(signals),
                "signals": [
                    {
                        "source_type": s.source_type.value,
                        "from_entity_id": s.from_entity_id,
                        "to_entity_id": s.to_entity_id,
                        "signal_strength": s.signal_strength,
                        "evidence": s.evidence[:100],
                    }
                    for s in signals[:30]
                ],
            },
        }
    except Exception as e:
        logger.error(f"用户信号查询失败: {e}")
        return {"success": False, "data": None, "message": str(e)}


@router.post("/auto-create")
def auto_create(db: Session = Depends(get_db)):
    """触发自动创建关系边"""
    try:
        from features.relation_mining.relation_creator import auto_create_relations
        stats = auto_create_relations(db)
        return {"success": True, "data": stats}
    except Exception as e:
        logger.error(f"自动创建失败: {e}")
        return {"success": False, "data": None, "message": str(e)}


@router.get("/stats")
def mining_stats(db: Session = Depends(get_db)):
    """关系挖掘统计"""
    try:
        from features.relation_mining.signal_collector import signal_stats
        stats = signal_stats(db)
        return {"success": True, "data": stats}
    except Exception as e:
        return {"success": False, "data": None, "message": str(e)}
