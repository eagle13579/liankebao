"""功能：需求原点定位 — 保存用户注册时选择的核心痛点"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.schemas import ApiResponse, OnboardingPreferenceRequest, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post(
    "/onboarding-preference",
    summary="保存用户核心痛点选择",
    description="用户在注册流程中选择了「核心痛点」后，保存该偏好并返回更新后的用户信息",
)
def save_onboarding_preference(
    req: OnboardingPreferenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存用户注册时选择的核心痛点标签

    - low_acquisition_cost → 获客成本太高
    - lack_trust → 缺信任背书难成交
    - distribution_pain → 分销结算太麻烦
    """
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    user.onboarding_pain_point = req.pain_point
    db.commit()
    db.refresh(user)

    logger.info(
        "onboarding_preference_saved",
        extra={
            "user_id": user.id,
            "pain_point": req.pain_point,
        },
    )

    return ApiResponse(
        code=200,
        message="痛点偏好已保存",
        data=UserResponse.model_validate(user).model_dump(),
    )
