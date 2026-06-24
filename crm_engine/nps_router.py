"""
链客宝 CRM — NPS 调查 & 续费提醒路由
===========================================
设计: 续费透明化 (反AR1/AR3/AR9)

包含:
  - NPS 调查 (4个端点)
  - 续费透明化提醒 (反AR3: 主动提醒 / 反AR9: 显式同意)
  - 一键取消会员 (反AR1: 取消迷宫)

集成:
  fastapi_payment.py 已导入: from crm_engine.nps_router import nps_router
  路由前缀: /api/crm
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

nps_router = APIRouter(prefix="/api/crm", tags=["续费透明化 & NPS"])

# ══════════════════════════════════════════════════════════════
# 内存存储（TODO: 替换为数据库）
# ══════════════════════════════════════════════════════════════

_renewal_notification_log: list[dict] = []
_cancellation_log: list[dict] = []
_consent_log: list[dict] = []
_memberships: dict[str, dict] = {}  # user_id -> membership info


# ══════════════════════════════════════════════════════════════
# Pydantic 模型
# ══════════════════════════════════════════════════════════════


class RenewalStatusResponse(BaseModel):
    """续费状态响应"""

    user_id: str
    tier: str
    expires_at: str
    days_remaining: int
    auto_renew: bool = False  # 始终为 False — 不做自动续费
    next_reminder: Optional[str] = None
    reminder_channels: list[str] = ["in_app", "email", "sms"]

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id": "uuid-xxx",
                "tier": "gold",
                "expires_at": "2026-07-07",
                "days_remaining": 30,
                "auto_renew": False,
                "next_reminder": "D-7 (站内信+邮件)",
                "reminder_channels": ["in_app", "email", "sms"],
            }
        }
    }


class RenewalConfirmRequest(BaseModel):
    """续费确认请求 (Opt-in)"""

    user_id: str = Field(..., min_length=1, max_length=64)
    tier: str = Field(..., pattern=r"^(gold|diamond|board)$")
    agreed_terms: bool = Field(..., description="已阅读并同意续费条款")
    agreed_opt_in: bool = Field(..., description="确认本次续费为主动行为")
    agreed_no_penalty: bool = Field(..., description="知道可随时取消且无违约金")

    @field_validator("agreed_terms", "agreed_opt_in", "agreed_no_penalty")
    @classmethod
    def must_be_true(cls, v: bool) -> bool:
        if not v:
            raise ValueError("所有同意项必须显式勾选 (opt-in)")
        return v


class CancelPreviewResponse(BaseModel):
    """取消预览响应"""

    user_id: str
    tier: str
    paid_amount: float
    days_total: int
    days_used: int
    refund_amount: float
    refund_method: str = "原路返回"


class CancellationLogResponse(BaseModel):
    """取消记录响应"""

    user_id: str
    tier: str
    refund_amount: float
    clicks_count: int
    cancelled_at: str


class NotificationPreferenceUpdate(BaseModel):
    """通知偏好更新"""

    email_enabled: bool = True
    sms_enabled: bool = True
    extra_early_reminder: bool = False  # 额外提前30天提醒


# ══════════════════════════════════════════════════════════════
#  辅助函数
# ══════════════════════════════════════════════════════════════


def _get_now_str() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_today() -> date:
    return date.today()


def _get_membership(user_id: str) -> Optional[dict]:
    """获取用户会员信息（模拟，生产环境替换为数据库查询）"""
    return _memberships.get(user_id)


def _calculate_refund(user_id: str) -> dict:
    """
    按比例计算退款金额
    反AR4: 无违约金，透明计算
    """
    membership = _get_membership(user_id)
    if not membership:
        raise HTTPException(status_code=404, detail="会员信息不存在")

    paid_amount = membership.get("paid_amount", 0)
    total_days = membership.get("total_days", 365)
    created_at = membership.get("created_at", _get_today())
    days_used = (_get_today() - created_at).days
    days_used = max(0, min(days_used, total_days))

    refund = 0.0
    # 7天内全额退款
    if days_used <= 7:
        refund = paid_amount
    else:
        refund = round((paid_amount / total_days) * (total_days - days_used), 2)

    return {
        "refund_amount": refund,
        "days_total": total_days,
        "days_used": days_used,
        "paid_amount": paid_amount,
    }


def _log_notification(user_id: str, tier: str, notify_type: str, channel: str) -> dict:
    """记录提醒发送日志"""
    entry = {
        "id": len(_renewal_notification_log) + 1,
        "user_id": user_id,
        "tier": tier,
        "notify_type": notify_type,
        "channel": channel,
        "status": "sent",
        "sent_at": _get_now_str(),
        "read_at": None,
    }
    _renewal_notification_log.append(entry)
    return entry


def _determine_next_reminder(days_remaining: int) -> Optional[str]:
    """根据剩余天数确定下次提醒类型"""
    if days_remaining > 7:
        return None  # 未到提醒周期
    if days_remaining >= 7:
        return "D-7 (站内信+邮件)"
    if days_remaining >= 3:
        return "D-3 (站内信+邮件+短信)"
    if days_remaining >= 1:
        return "D-1 (站内信+邮件+短信)"
    return None


# ══════════════════════════════════════════════════════════════
#  续费状态 & 提醒端点
# ══════════════════════════════════════════════════════════════


@nps_router.get(
    "/membership/renewal/status/{user_id}",
    response_model=RenewalStatusResponse,
    summary="续费状态查询",
    description="反AR3: 自动续费始终关闭，状态透明可查",
)
def get_renewal_status(
    user_id: str = Path(..., description="用户UUID"),
):
    """
    获取续费状态

    设计要点:
      - auto_renew 始终返回 False — 不做自动扣款 (反AR3)
      - 返回剩余天数和下次提醒时间 (反AR3: 主动透明)
    """
    membership = _get_membership(user_id)
    if not membership:
        # 默认免费会员
        return RenewalStatusResponse(
            user_id=user_id,
            tier="free",
            expires_at="N/A",
            days_remaining=0,
            auto_renew=False,
            next_reminder=None,
            reminder_channels=["in_app"],
        )

    expires_at = membership.get("expires_at", _get_today())
    if isinstance(expires_at, str):
        expires_at = date.fromisoformat(expires_at)
    days_remaining = (expires_at - _get_today()).days

    return RenewalStatusResponse(
        user_id=user_id,
        tier=membership.get("tier", "gold"),
        expires_at=expires_at.isoformat(),
        days_remaining=max(0, days_remaining),
        auto_renew=False,
        next_reminder=_determine_next_reminder(days_remaining),
        reminder_channels=["in_app", "email", "sms"],
    )


@nps_router.post(
    "/membership/renewal/confirm",
    status_code=status.HTTP_200_OK,
    summary="主动确认续费 (Opt-in)",
    description="反AR9: 用户必须显式勾选三条同意项+主动点击确认",
)
def confirm_renewal(
    body: RenewalConfirmRequest,
):
    """
    确认续费 (Opt-in)

    设计要点:
      - 三个复选框必须全部显式勾选 (反AR9: 同意定义权还给用户)
      - 不做自动扣款 (反AR3: 沉默≠同意)
      - 记录 consent_log 供审计 (反AR9: 可追溯)
    """
    # 记录同意日志 (审计追溯)
    consent_entry = {
        "id": len(_consent_log) + 1,
        "user_id": body.user_id,
        "tier": body.tier,
        "consent_type": "opt_in",
        "ip_address": "127.0.0.1",  # TODO: 从请求获取
        "user_agent": "FastAPI",  # TODO: 从请求获取
        "consent_items": [
            "agreed_terms",
            "agreed_opt_in",
            "agreed_no_penalty",
        ],
        "created_at": _get_now_str(),
    }
    _consent_log.append(consent_entry)

    logger.info(
        "续费确认: user=%s tier=%s consent_id=%d",
        body.user_id,
        body.tier,
        consent_entry["id"],
    )

    return {
        "code": 200,
        "message": "续费确认成功",
        "data": {
            "user_id": body.user_id,
            "tier": body.tier,
            "consent_id": consent_entry["id"],
            "confirmed_at": _get_now_str(),
            "next_step": "请完成支付",
        },
    }


@nps_router.get(
    "/membership/cancel/preview/{user_id}",
    response_model=CancelPreviewResponse,
    summary="取消预览 — 透明显示退款金额",
    description="反AR4: 取消前透明展示退款计算公式和金额",
)
def preview_cancellation(
    user_id: str = Path(..., description="用户UUID"),
):
    """
    取消预览

    设计要点:
      - 取消前展示退款金额 (反AR4: 无违约金)
      - 展示计算公式 (反AR9: 透明公开)
    """
    membership = _get_membership(user_id)
    if not membership:
        raise HTTPException(status_code=404, detail="无会员信息")

    refund = _calculate_refund(user_id)

    return CancelPreviewResponse(
        user_id=user_id,
        tier=membership.get("tier", "gold"),
        paid_amount=refund["paid_amount"],
        days_total=refund["days_total"],
        days_used=refund["days_used"],
        refund_amount=refund["refund_amount"],
        refund_method="原路返回",
    )


@nps_router.post(
    "/membership/cancel/{user_id}",
    summary="一键取消会员 (≤3次点击)",
    description="反AR1: 取消路径 ≤3次点击，无隐藏按钮，无挽留陷阱",
)
def cancel_membership(
    user_id: str = Path(..., description="用户UUID"),
    clicks_count: int = Query(3, ge=1, le=10, description="取消所用点击次数"),
):
    """
    一键取消会员

    设计要点:
      - 取消即生效，等待期为0 (反AR1: 无取消迷宫)
      - 退款自动计算并原路返回 (反AR4: 无违约金)
      - 记录取消日志 + 点击次数审计 (反AR1: 可追溯)
    """
    membership = _get_membership(user_id)
    if not membership:
        raise HTTPException(status_code=404, detail="无会员信息")

    # 计算退款
    refund = _calculate_refund(user_id)

    # 记录取消日志
    cancel_entry = {
        "id": len(_cancellation_log) + 1,
        "user_id": user_id,
        "tier": membership.get("tier", "gold"),
        "cancel_reason": "用户主动取消",
        "refund_amount": refund["refund_amount"],
        "refund_status": "processing",
        "clicks_count": clicks_count,
        "cancelled_at": _get_now_str(),
    }
    _cancellation_log.append(cancel_entry)

    # 降级会员 (TODO: 数据库更新)
    if user_id in _memberships:
        _memberships[user_id]["tier"] = "free"

    logger.info(
        "取消会员: user=%s tier=%s refund=%.2f clicks=%d",
        user_id,
        cancel_entry["tier"],
        refund["refund_amount"],
        clicks_count,
    )

    return {
        "code": 200,
        "message": "取消成功",
        "data": {
            "success": True,
            "refund_amount": refund["refund_amount"],
            "refund_method": "原路返回",
            "estimated_arrival": "T+0 (支付宝/微信) 或 T+1 (银行卡)",
            "cancellation_id": cancel_entry["id"],
        },
    }


# ══════════════════════════════════════════════════════════════
#  提醒 & 通知偏好端点
# ══════════════════════════════════════════════════════════════


@nps_router.get(
    "/membership/notifications/{user_id}",
    summary="获取续费提醒记录",
    description="反AR3: 所有提醒记录可查，审计透明",
)
def get_notification_history(
    user_id: str = Path(...),
    limit: int = Query(10, ge=1, le=100),
):
    """获取用户续费提醒历史"""
    user_logs = [e for e in _renewal_notification_log if e["user_id"] == user_id][
        -limit:
    ]

    return {
        "code": 200,
        "data": user_logs,
        "total": len(user_logs),
    }


@nps_router.put(
    "/membership/notifications/preferences/{user_id}",
    summary="更新续费提醒偏好",
    description="用户可关闭邮件/短信提醒（站内信不可关闭）",
)
def update_notification_preferences(
    user_id: str = Path(...),
    body: NotificationPreferenceUpdate = ...,
):
    """
    更新通知偏好

    设计要点:
      - 站内信不可关闭 (反AR3: 至少一种渠道强制触达)
      - 用户可关闭邮件/短信
      - 可开启额外提前30天提醒
    """
    # TODO: 持久化到数据库
    logger.info(
        "更新通知偏好: user=%s email=%s sms=%s extra=%s",
        user_id,
        body.email_enabled,
        body.sms_enabled,
        body.extra_early_reminder,
    )

    return {
        "code": 200,
        "message": "通知偏好已更新",
        "data": {
            "email_enabled": body.email_enabled,
            "sms_enabled": body.sms_enabled,
            "extra_early_reminder": body.extra_early_reminder,
            "in_app_enabled": True,  # 始终开启
        },
    }


# ══════════════════════════════════════════════════════════════
#  合规中心端点 (续费条款公开)
# ══════════════════════════════════════════════════════════════

_RENEWAL_TERMS = """
# 链客宝续费条款 v1.0

## 一、续费原则
1.1 链客宝采用「主动确认续费」机制（Opt-in）。
1.2 链客宝不会对任何用户进行自动扣款续费。
1.3 每次续费前，用户必须登录并完成主动确认。

## 二、提醒机制
2.1 链客宝将在会员到期前7天、3天、1天发送主动提醒。
2.2 提醒渠道包括：站内信、邮件、短信。
2.3 用户可在「通知偏好」中关闭非核心渠道。

## 三、取消政策
3.1 用户可随时取消会员，无任何违约金。
3.2 取消后按剩余天数比例退款。
3.3 退款金额 = (已支付金额 ÷ 总天数) × 剩余天数。
3.4 退款原路返回，最迟 T+1 到账。

## 四、数据保留
4.1 会员到期/取消后，用户数据保留30天。
4.2 30天内付费恢复会员可恢复全部数据。
4.3 30天后数据按隐私政策处理。
"""


@nps_router.get(
    "/compliance/renewal/terms",
    summary="获取续费条款",
    description="反AR9: 续费条款公开可查",
)
def get_renewal_terms():
    """返回续费条款全文"""
    return {
        "code": 200,
        "version": "1.0",
        "effective_date": "2026-06-07",
        "content": _RENEWAL_TERMS.strip(),
    }


@nps_router.get(
    "/compliance/renewal/cancellation",
    summary="获取取消流程说明",
    description="反AR1: 取消流程透明公开",
)
def get_cancellation_policy():
    """返回取消流程说明"""
    return {
        "code": 200,
        "policy": {
            "steps": [
                "进入 账户设置 → 会员中心",
                "点击「取消会员」红色按钮",
                "阅读退款预览（按比例计算，无违约金）",
                "点击「确认取消」完成操作",
            ],
            "max_clicks": 3,
            "refund_formula": "退款金额 = (已支付金额 ÷ 总天数) × 剩余天数",
            "refund_timing": "原路返回，T+0 (支付宝/微信) 或 T+1 (银行卡)",
            "no_penalty": True,
        },
    }


@nps_router.get(
    "/compliance/renewal/refund",
    summary="获取退款计算公式",
    description="反AR4: 退款公式公开透明",
)
def get_refund_formula():
    """返回退款计算公式"""
    return {
        "code": 200,
        "formula": {
            "expression": "refund = (paid_amount / total_days) * (total_days - days_used)",
            "variables": {
                "paid_amount": "已支付金额",
                "total_days": "会员总天数",
                "days_used": "已使用天数",
            },
            "example": {
                "tier": "金卡会员 ¥999/年",
                "paid_amount": 999,
                "total_days": 365,
                "days_used": 120,
                "refund_amount": 670.68,
            },
            "full_refund_window_days": 7,
            "no_cancellation_fee": True,
        },
    }


# ══════════════════════════════════════════════════════════════
#  NPS 调查端点 (原有)
# ══════════════════════════════════════════════════════════════


class NpsSurvey(BaseModel):
    """NPS 调查请求"""

    user_id: str
    score: int = Field(..., ge=0, le=10)
    feedback: Optional[str] = Field(None, max_length=2000)
    category: Optional[str] = Field(None, max_length=64)


_nps_responses: list[dict] = []


@nps_router.post("/nps/submit", status_code=201, summary="提交 NPS 评分")
def submit_nps(body: NpsSurvey):
    """提交 NPS 评分"""
    entry = body.model_dump()
    entry["submitted_at"] = _get_now_str()
    entry["id"] = len(_nps_responses) + 1
    _nps_responses.append(entry)
    return {"code": 201, "message": "NPS 已记录", "id": entry["id"]}


@nps_router.get("/nps/stats", summary="NPS 统计概览")
def get_nps_stats():
    """返回 NPS 统计"""
    if not _nps_responses:
        return {"code": 200, "data": {"total": 0, "nps_score": 0}}

    scores = [r["score"] for r in _nps_responses]
    promoters = sum(1 for s in scores if s >= 9)
    passives = sum(1 for s in scores if 7 <= s <= 8)
    detractors = sum(1 for s in scores if s <= 6)
    total = len(scores)
    nps = round((promoters - detractors) / total * 100, 1)

    return {
        "code": 200,
        "data": {
            "total": total,
            "nps_score": nps,
            "promoters": promoters,
            "passives": passives,
            "detractors": detractors,
        },
    }


@nps_router.get("/nps/history/{user_id}", summary="用户 NPS 历史")
def get_nps_history(user_id: str = Path(...)):
    """返回用户的 NPS 历史"""
    user_responses = [r for r in _nps_responses if r["user_id"] == user_id]
    return {"code": 200, "data": user_responses, "total": len(user_responses)}
