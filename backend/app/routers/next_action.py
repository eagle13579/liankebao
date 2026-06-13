"""评分后自动下一步行动推荐 API 路由

提供根据评分结果自动推荐下一步行动的 REST API 端点：
  - POST /api/next-action/recommend          — 单条评分推荐
  - POST /api/next-action/recommend-batch    — 批量评分推荐
  - GET  /api/next-action/rules              — 查看当前推荐规则
  - PUT  /api/next-action/rules              — 更新推荐规则（管理员）

设计对标：Salesforce Einstein Next Best Action
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.models import User
from app.schemas import ApiResponse
from app.services.action_recommender import (
    ActionRule,
    ActionType,
    ScoreLevel,
    get_action_recommender,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/next-action", tags=["下一步行动推荐"])

# ============================================================
# Pydantic 请求/响应模型
# ============================================================


class RecommendRequest(BaseModel):
    """单条评分推荐请求"""

    score: float = Field(
        ...,
        ge=0.0,
        description="评分值（来自匹配引擎），支持 0~100 或 0.0~1.0",
    )
    score_scale: str = Field(
        "0-100",
        description="分数制式：'0-100'（默认）或 '0-1'",
        pattern=r"^(0-100|0-1)$",
    )
    entity_id: int | None = Field(None, description="被评分实体 ID")
    entity_type: str | None = Field(
        None,
        description="实体类型：enterprise / product / supplier / need",
    )
    context: dict[str, Any] | None = Field(
        None, description="额外上下文信息"
    )


class RecommendBatchRequest(BaseModel):
    """批量评分推荐请求"""

    scores: list[RecommendRequest] = Field(
        ..., min_length=1, max_length=100, description="评分列表"
    )
    score_scale: str = Field(
        "0-100",
        description="分数制式（统一作用于所有评分）",
        pattern=r"^(0-100|0-1)$",
    )


class RuleConfigRequest(BaseModel):
    """推荐规则配置（管理员用）"""

    min_score: float = Field(..., ge=0.0, le=100.0, description="最低分数（含）")
    max_score: float = Field(..., ge=0.0, le=100.0, description="最高分数（含）")
    action_type: str = Field(
        ...,
        description="行动类型",
        pattern=r"^(sign_contract|invite_event|nurture_sequence|manual_review)$",
    )
    priority: int = Field(1, ge=1, description="优先级（数字越小越优先）")
    display_name: str = Field(..., min_length=1, max_length=50, description="前端展示名称")
    description: str = Field(
        ..., min_length=1, max_length=500, description="行动描述"
    )
    action_data: dict[str, Any] = Field(
        default_factory=dict, description="行动额外数据"
    )
    label: str | None = Field(
        None, description="分数段标签：high / medium / low",
        pattern=r"^(high|medium|low)?$",
    )


class UpdateRulesRequest(BaseModel):
    """更新规则请求"""

    rules: list[RuleConfigRequest] = Field(
        ..., min_length=1, max_length=20, description="规则列表"
    )


# ============================================================
# API 端点
# ============================================================


@router.post(
    "/recommend",
    summary="评分后推荐下一步行动",
    description="根据评分自动推荐最优下一步行动（签约/邀约对接会/培育序列）",
)
def recommend_next_action(
    req: RecommendRequest,
    current_user: User = Depends(get_current_user),
):
    """接收单个评分结果 → 返回推荐行动"""
    recommender = get_action_recommender()

    try:
        result = recommender.recommend(
            score=req.score,
            score_scale=req.score_scale,
            entity_id=req.entity_id,
            entity_type=req.entity_type,
            context=req.context,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "code": 200,
        "message": "success",
        "data": recommender.recommendation_to_dict(result),
    }


@router.post(
    "/recommend-batch",
    summary="批量评分推荐",
    description="批量接收多个评分结果，逐一返回推荐行动（支持最多100条）",
)
def recommend_next_action_batch(
    req: RecommendBatchRequest,
    current_user: User = Depends(get_current_user),
):
    """批量处理多个评分结果 → 返回推荐行动列表"""
    recommender = get_action_recommender()

    scores_input = []
    for item in req.scores:
        scores_input.append(
            {
                "score": item.score,
                "entity_id": item.entity_id,
                "entity_type": item.entity_type,
                "context": item.context,
            }
        )

    try:
        results = recommender.recommend_batch(
            scores=scores_input,
            score_scale=req.score_scale,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": len(results),
            "items": [
                recommender.recommendation_to_dict(r) for r in results
            ],
        },
    }


@router.get(
    "/rules",
    summary="查看推荐规则",
    description="获取当前行动推荐引擎的评分规则配置（含阈值、行动、优先级）",
)
def list_rules(
    current_user: User = Depends(get_current_user),
):
    """查看当前推荐规则列表"""
    recommender = get_action_recommender()
    rules = recommender.rules

    return {
        "code": 200,
        "message": "success",
        "data": {
            "total": len(rules),
            "rules": [
                {
                    "min_score": r.min_score,
                    "max_score": r.max_score,
                    "action_type": r.action_type.value,
                    "priority": r.priority,
                    "display_name": r.display_name,
                    "description": r.description,
                    "label": r.label.value if r.label else None,
                    "action_data": r.action_data,
                }
                for r in rules
            ],
        },
    }


@router.put(
    "/rules",
    summary="更新推荐规则（管理员）",
    description="动态更新行动推荐引擎的评分规则配置（需管理员权限，运行时热更新）",
)
def update_rules(
    req: UpdateRulesRequest,
    current_user: User = Depends(get_current_user),
):
    """更新推荐规则（管理员权限，运行时热更新）"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="仅管理员可更新推荐规则",
        )

    # 构建 ActionRule 列表
    rules = []
    for r in req.rules:
        try:
            action_type = ActionType(r.action_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"无效的行动类型: {r.action_type}",
            )

        label = None
        if r.label:
            try:
                label = ScoreLevel(r.label)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"无效的分数段标签: {r.label}",
                )

        rules.append(
            ActionRule(
                min_score=r.min_score,
                max_score=r.max_score,
                action_type=action_type,
                priority=r.priority,
                display_name=r.display_name,
                description=r.description,
                action_data=r.action_data,
                label=label,
            )
        )

    # 更新规则
    recommender = get_action_recommender()
    recommender.update_rules(rules)

    return {
        "code": 200,
        "message": "success",
        "data": {"updated_count": len(rules)},
    }
