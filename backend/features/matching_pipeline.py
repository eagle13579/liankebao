"""
链客宝 — 三塔DNN匹配推理管道
===============================
将 TowerEnsemble 接入匹配路由，提供线上推理能力。

架构:
  1. 懒加载三塔引擎 (LazySingleton)
  2. dnn_score(user_info, enterprise_info, db) → float 匹配分数
  3. dnn_match(user_id, candidates, db) → list[dict] 匹配结果
  4. 模型加载失败自动回退 (返回 None, 由调用方决定)

用法:
    from features.matching_pipeline import dnn_match, pipeline_ready

    if pipeline_ready():
        results = dnn_match(need_id, db=db)
        # ...

依赖:
  - backend/ml/models/tower_ensemble.py (MatchingScorer, MatchingAPI)
  - backend/ml/models/user_tower.py (UserTower, UserFeatureEncoder)
  - backend/ml/models/enterprise_tower.py (EnterpriseTower, EnterpriseFeatureEncoder)
  - backend/ml/models/behavior_tower.py (BehaviorTower, BehaviorSequenceEncoder)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 全局引擎状态 (懒加载单例)
# ---------------------------------------------------------------------------
_ENGINE = None          # MatchingAPI 实例 or None
_ENGINE_LOADED = False  # 是否已尝试加载
_ENGINE_FAILED = False  # 是否加载失败

# 模型权重路径
_MODELS_DIR = Path(__file__).resolve().parent.parent / "ml" / "models"
_CHECKPOINTS_DIR = _MODELS_DIR / "checkpoints"


# ---------------------------------------------------------------------------
# 内部工具: Torch 可用性检测
# ---------------------------------------------------------------------------
def _torch_available():
    try:
        import torch
        return True
    except ImportError:
        return False


def _checkpoint_path(name: str) -> Optional[Path]:
    """查找指定名称的 checkpoint 文件"""
    for ext in [".pt", ".pth"]:
        p = _CHECKPOINTS_DIR / f"{name}{ext}"
        if p.exists():
            return p
    return None


def _model_path(name: str) -> Optional[Path]:
    """查找模型脚本文件"""
    for ext in [".py"]:
        p = _MODELS_DIR / f"{name}{ext}"
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# 编码器拟合辅助: 从数据库抽取样本数据
# ---------------------------------------------------------------------------
def _fit_user_encoder(user_encoder, db) -> bool:
    """从数据库 BusinessCard 数据拟合用户编码器"""
    try:
        import pandas as pd
        from app.models import BusinessCard

        # 查询用户相关数据 (取最近200条名片)
        cards = (
            db.query(BusinessCard)
            .order_by(BusinessCard.updated_at.desc())
            .limit(200)
            .all()
        )

        if not cards:
            logger.warning("[MatchingPipeline] 数据库无名片数据，使用模拟数据拟合用户编码器")
            return _fit_user_encoder_synthetic(user_encoder)

        rows = []
        for c in cards:
            fields = c.fields if isinstance(c.fields, dict) else {}
            rows.append({
                "industry_code": fields.get("industry_code", 0),
                "scale": fields.get("scale", 10),
                "region_code": fields.get("region_code", 0),
                "cooperation_type": fields.get("cooperation_type", "unknown"),
                "budget_level": fields.get("budget_level", "unknown"),
            })

        df = pd.DataFrame(rows)
        user_encoder.fit(df)
        logger.info("[MatchingPipeline] 用户编码器从数据库拟合成功 (%d 条)", len(df))
        return True

    except Exception as e:
        logger.warning("[MatchingPipeline] 数据库拟合用户编码器失败: %s", e)
        return _fit_user_encoder_synthetic(user_encoder)


def _fit_user_encoder_synthetic(user_encoder) -> bool:
    """使用模拟数据拟合用户编码器 (备用方案)"""
    try:
        import pandas as pd

        df = pd.DataFrame({
            "industry_code": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "scale": [10, 50, 100, 500, 1000, 10, 50, 100, 500, 1000],
            "region_code": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "cooperation_type": ["supply", "demand", "cooperation", "investment",
                                 "supply", "demand", "cooperation", "investment", "supply", "demand"],
            "budget_level": ["low", "medium", "high", "premium",
                            "low", "medium", "high", "premium", "low", "medium"],
        })
        user_encoder.fit(df)
        logger.info("[MatchingPipeline] 用户编码器使用模拟数据拟合成功")
        return True
    except Exception as e:
        logger.error("[MatchingPipeline] 模拟拟合用户编码器失败: %s", e)
        return False


def _fit_ent_encoder(ent_encoder, db) -> bool:
    """从数据库企业数据拟合企业编码器"""
    try:
        import pandas as pd
        from app.models import BusinessCard

        cards = (
            db.query(BusinessCard)
            .order_by(BusinessCard.updated_at.desc())
            .limit(200)
            .all()
        )

        if not cards:
            logger.warning("[MatchingPipeline] 数据库无名片数据，使用模拟数据拟合企业编码器")
            return _fit_ent_encoder_synthetic(ent_encoder)

        rows = []
        for c in cards:
            fields = c.fields if isinstance(c.fields, dict) else {}
            rows.append({
                "registered_capital_log": float(fields.get("registered_capital_log", fields.get("registered_capital", 0))) or 0.0,
                "established_years": float(fields.get("established_years", fields.get("years", 0))) or 0.0,
                "industry_code": float(fields.get("industry_code", 0)),
                "enterprise_scale": float(fields.get("enterprise_scale", fields.get("scale", 1))) or 1.0,
                "credit_rating": float(fields.get("credit_rating", 3)) or 3.0,
                "risk_count": float(fields.get("risk_count", 0)),
            })

        df = pd.DataFrame(rows)
        ent_encoder.fit(df)
        logger.info("[MatchingPipeline] 企业编码器从数据库拟合成功 (%d 条)", len(df))
        return True

    except Exception as e:
        logger.warning("[MatchingPipeline] 数据库拟合企业编码器失败: %s", e)
        return _fit_ent_encoder_synthetic(ent_encoder)


def _fit_ent_encoder_synthetic(ent_encoder) -> bool:
    """使用模拟数据拟合企业编码器 (备用方案)"""
    try:
        import pandas as pd

        df = pd.DataFrame({
            "registered_capital_log": [1.0, 2.0, 3.0, 4.0, 5.0],
            "established_years": [3, 5, 10, 15, 20],
            "industry_code": [1, 2, 3, 4, 5],
            "enterprise_scale": [1, 2, 3, 2, 4],
            "credit_rating": [3, 4, 5, 2, 3],
            "risk_count": [0, 1, 5, 10, 3],
        })
        ent_encoder.fit(df)
        logger.info("[MatchingPipeline] 企业编码器使用模拟数据拟合成功")
        return True
    except Exception as e:
        logger.error("[MatchingPipeline] 模拟拟合企业编码器失败: %s", e)
        return False


def _fit_behav_encoder(behav_encoder, db) -> bool:
    """拟合行为编码器 (使用模拟数据)"""
    try:
        import pandas as pd

        df = pd.DataFrame({
            "behavior_type": ["view", "browse", "match_view", "feedback_like", "search"],
            "timestamp_gap": [0.0, 1.0, 2.0, 3.0, 4.0],
            "duration": [5.0, 30.0, 10.0, 60.0, 15.0],
            "target_id": [101, 102, 103, 104, 105],
            "action_value": [1.0, 2.0, 3.0, 4.0, 5.0],
        })
        behav_encoder.fit(df)
        logger.info("[MatchingPipeline] 行为编码器使用模拟数据拟合成功")
        return True
    except Exception as e:
        logger.warning("[MatchingPipeline] 拟合行为编码器失败: %s", e)
        return False


# ---------------------------------------------------------------------------
# 加载或初始化三塔引擎 (懒加载, 仅执行一次)
# ---------------------------------------------------------------------------
def load_engine(db=None) -> bool:
    """加载或初始化三塔匹配引擎。

    Args:
        db: SQLAlchemy Session (用于从数据库拟合编码器, 可选)

    Returns:
        bool: 引擎是否就绪
    """
    global _ENGINE, _ENGINE_LOADED, _ENGINE_FAILED

    # ── 已加载 → 直接返回状态 ──
    if _ENGINE_LOADED:
        return _ENGINE is not None

    # ── 已失败 → 不再重试 ──
    if _ENGINE_FAILED:
        return False

    # ── 检查 PyTorch ──
    if not _torch_available():
        logger.warning("[MatchingPipeline] PyTorch 不可用，三塔推理不可用")
        _ENGINE_FAILED = True
        _ENGINE_LOADED = True
        return False

    try:
        import torch
        from ml.models.user_tower import UserTower, UserFeatureEncoder
        from ml.models.enterprise_tower import EnterpriseTower, EnterpriseFeatureEncoder
        from ml.models.behavior_tower import BehaviorTower, BehaviorSequenceEncoder
        from ml.models.tower_ensemble import MatchingScorer, MatchingAPI
    except ImportError as e:
        logger.warning("[MatchingPipeline] 模型模块导入失败: %s", e)
        _ENGINE_FAILED = True
        _ENGINE_LOADED = True
        return False

    try:
        # ── Step 1: 创建编码器并拟合 ──
        user_encoder = UserFeatureEncoder(embedding_dim=16)
        ent_encoder = EnterpriseFeatureEncoder()
        behav_encoder = BehaviorSequenceEncoder(max_seq_len=50, feature_dim=32)

        if db is not None:
            _fit_user_encoder(user_encoder, db)
            _fit_ent_encoder(ent_encoder, db)
        else:
            _fit_user_encoder_synthetic(user_encoder)
            _fit_ent_encoder_synthetic(ent_encoder)
        _fit_behav_encoder(behav_encoder, db)

        # ── Step 2: 创建塔 ──
        user_tower = UserTower(
            num_features=user_encoder.total_feature_dim,
            embedding_dim=128,
            hidden_dims=[256, 128],
        )
        ent_tower = EnterpriseTower(
            num_features=6,
            embedding_dim=128,
            hidden_dims=[256, 128],
        )
        behav_tower = BehaviorTower(
            max_seq_len=50,
            feature_dim=32,
            hidden_dim=128,
        )

        # ── Step 3: 加载 checkpoint 权重 (如果存在) ──
        loaded_any = False
        user_ckpt = _checkpoint_path("user_tower")
        if user_ckpt:
            try:
                state = torch.load(str(user_ckpt), map_location="cpu", weights_only=True)
                user_tower.load_state_dict(state, strict=False)
                logger.info("[MatchingPipeline] 加载 user_tower 权重: %s", user_ckpt.name)
                loaded_any = True
            except Exception as e:
                logger.warning("[MatchingPipeline] 加载 user_tower 权重失败: %s", e)

        ent_ckpt = _checkpoint_path("enterprise_tower")
        if ent_ckpt:
            try:
                state = torch.load(str(ent_ckpt), map_location="cpu", weights_only=True)
                ent_tower.load_state_dict(state, strict=False)
                logger.info("[MatchingPipeline] 加载 enterprise_tower 权重: %s", ent_ckpt.name)
                loaded_any = True
            except Exception as e:
                logger.warning("[MatchingPipeline] 加载 enterprise_tower 权重失败: %s", e)

        behav_ckpt = _checkpoint_path("behavior_tower")
        if behav_ckpt:
            try:
                state = torch.load(str(behav_ckpt), map_location="cpu", weights_only=True)
                behav_tower.load_state_dict(state, strict=False)
                logger.info("[MatchingPipeline] 加载 behavior_tower 权重: %s", behav_ckpt.name)
                loaded_any = True
            except Exception as e:
                logger.warning("[MatchingPipeline] 加载 behavior_tower 权重失败: %s", e)

        # ── Step 4: scorer & API ──
        scorer = MatchingScorer(user_tower, ent_tower, behav_tower)
        api = MatchingAPI(
            scorer=scorer,
            user_encoder=user_encoder,
            enterprise_encoder=ent_encoder,
            behavior_encoder=behav_encoder,
            top_k=20,
            batch_size=64,
        )

        _ENGINE = api
        _ENGINE_LOADED = True
        _ENGINE_FAILED = False

        if loaded_any:
            logger.info("[MatchingPipeline] 三塔引擎加载成功 (已加载权重文件)")
        else:
            logger.info("[MatchingPipeline] 三塔引擎初始化成功 (使用随机权重, 未找到 checkpoint 文件)")

        return True

    except Exception as e:
        logger.error("[MatchingPipeline] 三塔引擎初始化失败: %s", e, exc_info=True)
        _ENGINE_FAILED = True
        _ENGINE_LOADED = True
        _ENGINE = None
        return False


# ---------------------------------------------------------------------------
# 检查引擎就绪状态
# ---------------------------------------------------------------------------
def pipeline_ready() -> bool:
    """返回三塔推理管道是否就绪"""
    if not _ENGINE_LOADED:
        # 未尝试加载 → 返回 False (调用者需先调用 load_engine)
        return False
    return _ENGINE is not None


# ---------------------------------------------------------------------------
# DNN 匹配: 输入用户ID / 企业ID → 返回排序后的匹配结果
# ---------------------------------------------------------------------------
def dnn_match(
    need_id: int,
    db,
    offset: int = 0,
    limit: int = 20,
) -> Optional[List[Dict[str, Any]]]:
    """使用三塔DNN模型执行匹配推理。

    Args:
        need_id: 需求名片ID (User)
        db: SQLAlchemy Session
        offset: 分页偏移
        limit: 分页大小

    Returns:
        List[dict] 格式与 matching_engine._simple_match 兼容:
            [{"id": ..., "title": ..., "description": ...,
              "match_score": ..., "match_reasons": [...], "strategy": "dnn"},
             ...]
        或 None (模型不可用)
    """
    # ── 确保引擎已加载 ──
    if not _ENGINE_LOADED:
        if not load_engine(db):
            return None

    api = _ENGINE
    if api is None:
        return None

    try:
        import torch
        from app.models import BusinessCard

        # ── 查询用户名片 ──
        user_card = db.query(BusinessCard).filter(BusinessCard.id == need_id).first()
        if not user_card:
            logger.warning("[MatchingPipeline] 用户名片不存在: need_id=%d", need_id)
            return None

        user_fields = user_card.fields if isinstance(user_card.fields, dict) else {}

        # ── 查询所有候选企业 (排除自身) ──
        candidates = (
            db.query(BusinessCard)
            .filter(BusinessCard.id != need_id)
            .order_by(BusinessCard.updated_at.desc())
            .all()
        )

        if not candidates:
            return []

        # ── 构建用户信息 dict (符合 UserFeatureEncoder 期望的字段) ──
        user_info = {
            "industry_code": user_fields.get("industry_code", 0),
            "scale": user_fields.get("scale", 10),
            "region_code": user_fields.get("region_code", 0),
            "cooperation_type": user_fields.get("cooperation_type", "unknown"),
            "budget_level": user_fields.get("budget_level", "unknown"),
        }

        # ── 构建候选企业列表 ──
        candidate_list = []
        for c in candidates:
            f = c.fields if isinstance(c.fields, dict) else {}
            candidate_list.append({
                "enterprise_id": c.id,
                "registered_capital_log": float(f.get("registered_capital_log", f.get("registered_capital", 0))) or 0.0,
                "established_years": float(f.get("established_years", 0)) or 0.0,
                "industry_code": float(f.get("industry_code", 0)),
                "enterprise_scale": float(f.get("enterprise_scale", f.get("scale", 1))) or 1.0,
                "credit_rating": float(f.get("credit_rating", 3)) or 3.0,
                "risk_count": float(f.get("risk_count", 0)),
            })

        # ── 执行推理 ──
        # 使用 predict (不带行为序列, 自动回退双塔)
        results = api.predict(user_info, candidate_list, behavior_sequences=None, top_k=limit + offset)

        # ── 转换为匹配结果格式 ──
        matched_items = []
        for r in results:
            # 找到对应的名片
            ent_id = int(r.enterprise_id)
            card = next((c for c in candidates if c.id == ent_id), None)
            if card is None:
                continue
            card_fields = card.fields if isinstance(card.fields, dict) else {}

            matched_items.append({
                "id": ent_id,
                "title": card_fields.get("name", card_fields.get("company", f"名片#{ent_id}")),
                "description": card_fields.get("description", ""),
                "category": card_fields.get("category", ""),
                "match_score": round(r.score, 4),
                "match_reasons": [f"DNN三塔匹配 (score={r.score:.4f})"],
                "strategy": "dnn",
            })

        # ── 分页 ──
        return matched_items[offset:offset + limit]

    except Exception as e:
        logger.error("[MatchingPipeline] DNN匹配推理失败: %s", e, exc_info=True)
        return None


def dnn_score(
    need_id: int,
    enterprise_id: int,
    db,
) -> Optional[float]:
    """计算单个用户与单个企业的三塔匹配分数。

    Args:
        need_id: 需求名片ID
        enterprise_id: 企业名片ID
        db: SQLAlchemy Session

    Returns:
        float 0~1 匹配分数, 或 None (模型不可用/查询失败)
    """
    # ── 确保引擎已加载 ──
    if not _ENGINE_LOADED:
        if not load_engine(db):
            return None

    api = _ENGINE
    if api is None:
        return None

    try:
        from app.models import BusinessCard

        # ── 查询两张名片 ──
        user_card = db.query(BusinessCard).filter(BusinessCard.id == need_id).first()
        ent_card = db.query(BusinessCard).filter(BusinessCard.id == enterprise_id).first()

        if not user_card or not ent_card:
            return None

        uf = user_card.fields if isinstance(user_card.fields, dict) else {}
        ef = ent_card.fields if isinstance(ent_card.fields, dict) else {}

        user_info = {
            "industry_code": uf.get("industry_code", 0),
            "scale": uf.get("scale", 10),
            "region_code": uf.get("region_code", 0),
            "cooperation_type": uf.get("cooperation_type", "unknown"),
            "budget_level": uf.get("budget_level", "unknown"),
        }

        ent_info = {
            "enterprise_id": enterprise_id,
            "registered_capital_log": float(ef.get("registered_capital_log", ef.get("registered_capital", 0))) or 0.0,
            "established_years": float(ef.get("established_years", 0)) or 0.0,
            "industry_code": float(ef.get("industry_code", 0)),
            "enterprise_scale": float(ef.get("enterprise_scale", ef.get("scale", 1))) or 1.0,
            "credit_rating": float(ef.get("credit_rating", 3)) or 3.0,
            "risk_count": float(ef.get("risk_count", 0)),
        }

        results = api.predict(user_info, [ent_info], behavior_sequences=None, top_k=1)
        if results:
            return round(results[0].score, 4)
        return 0.0

    except Exception as e:
        logger.error("[MatchingPipeline] DNN单对评分失败: %s", e)
        return None


def reset_engine():
    """重置引擎状态 (用于测试/热更新)"""
    global _ENGINE, _ENGINE_LOADED, _ENGINE_FAILED
    _ENGINE = None
    _ENGINE_LOADED = False
    _ENGINE_FAILED = False
    logger.info("[MatchingPipeline] 引擎状态已重置")


# ---------------------------------------------------------------------------
# 模块自检
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("[MatchingPipeline] 三塔DNN匹配推理管道 v1.0")
    print(f"  PyTorch: {'✓' if _torch_available() else '✗'}")
    print(f"  模型目录: {_MODELS_DIR}")
    print(f"  Checkpoints: {_CHECKPOINTS_DIR}")
    for ckpt in _CHECKPOINTS_DIR.glob("*.pt"):
        print(f"    - {ckpt.name}")
    for ckpt in _CHECKPOINTS_DIR.glob("*.pth"):
        print(f"    - {ckpt.name}")

    ready = load_engine(db=None)
    print(f"  引擎就绪: {'✓' if ready else '✗'}")
    print()
    if ready:
        print("  OK - 三塔推理管道加载成功")
    else:
        print("  OK - 三塔推理管道未加载 (将使用关键词匹配回退)")
    print()
