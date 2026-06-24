"""
合同管理 API 路由
=================
提供合同CRUD、状态机流转、电子签名占位、支付关联等能力。

路由前缀: /api/contracts
标签: 合同管理

端点清单:
  GET    /api/contracts              — 合同列表（分页+筛选）
  POST   /api/contracts              — 创建合同
  GET    /api/contracts/{id}         — 合同详情
  PUT    /api/contracts/{id}         — 更新合同
  DELETE /api/contracts/{id}         — 删除合同（软删除）
  POST   /api/contracts/{id}/submit  — 提交签署（草稿→待签）
  POST   /api/contracts/{id}/sign    — 签署确认（待签→已签，占位）
  POST   /api/contracts/{id}/start   — 开始履行（已签→履行中）
  POST   /api/contracts/{id}/complete— 完成（履行中→完成）
  POST   /api/contracts/{id}/terminate— 终止（任意状态→终止）
  POST   /api/contracts/{id}/generate-pdf — 生成PDF（占位）
  GET    /api/contracts/{id}/transactions — 关联支付交易记录
"""

import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Contract, PaymentTransaction, User
from app.schemas import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contracts", tags=["合同管理"])

# ============================================================
# 合同状态机定义
# ============================================================
CONTRACT_STATUS_FLOW: dict[str, list[str]] = {
    "draft": ["pending_sign", "terminated"],
    "pending_sign": ["signed", "terminated"],
    "signed": ["in_progress", "terminated"],
    "in_progress": ["completed", "terminated"],
    "completed": [],
    "terminated": [],
}

CONTRACT_STATUS_LABELS: dict[str, str] = {
    "draft": "草稿",
    "pending_sign": "待签署",
    "signed": "已签署",
    "in_progress": "履行中",
    "completed": "已完成",
    "terminated": "已终止",
}

# ============================================================
# Pydantic 模型
# ============================================================


class ContractCreateRequest(BaseModel):
    """创建合同请求"""

    title: str = Field(..., min_length=1, max_length=200, description="合同标题")
    template_id: str | None = Field(None, description="关联模板ID")
    party_a_name: str = Field(..., min_length=1, max_length=200, description="甲方名称")
    party_b_name: str = Field(..., min_length=1, max_length=200, description="乙方名称")
    party_a_id_number: str | None = Field(None, description="甲方证件号")
    party_b_id_number: str | None = Field(None, description="乙方证件号")
    party_a_contact: str | None = Field(None, description="甲方联系人")
    party_b_contact: str | None = Field(None, description="乙方联系人")
    contract_amount: float = Field(0.0, ge=0, description="合同金额")
    variables: dict[str, Any] | None = Field(None, description="模板变量")
    contract_text: str | None = Field(None, description="合同正文")
    notes: str | None = Field(None, description="备注")


class ContractUpdateRequest(BaseModel):
    """更新合同请求"""

    title: str | None = Field(None, min_length=1, max_length=200)
    party_a_name: str | None = Field(None, min_length=1, max_length=200)
    party_b_name: str | None = Field(None, min_length=1, max_length=200)
    party_a_id_number: str | None = None
    party_b_id_number: str | None = None
    party_a_contact: str | None = None
    party_b_contact: str | None = None
    contract_amount: float | None = Field(None, ge=0)
    variables: dict[str, Any] | None = None
    contract_text: str | None = None
    notes: str | None = None


class StatusTransitionRequest(BaseModel):
    """状态变更请求"""

    reason: str | None = Field(None, description="变更原因")


# ============================================================
# 辅助函数
# ============================================================


def _validate_status_transition(current: str, target: str) -> None:
    """验证状态流转是否合法"""
    allowed = CONTRACT_STATUS_FLOW.get(current, [])
    if target not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不允许的状态流转: {CONTRACT_STATUS_LABELS.get(current, current)} → {CONTRACT_STATUS_LABELS.get(target, target)}。"
            f"允许的目标: {', '.join(CONTRACT_STATUS_LABELS.get(s, s) for s in allowed)}",
        )


def _get_contract_or_404(contract_id: int, user: User, db: Session) -> Contract:
    """获取合同并校验所有权"""
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.is_deleted == False).first()
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")
    if contract.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权操作此合同")
    return contract


def _contract_to_dict(contract: Contract) -> dict[str, Any]:
    """合同对象转字典"""
    return {
        "id": contract.id,
        "user_id": contract.user_id,
        "title": contract.title,
        "template_id": contract.template_id,
        "status": contract.status,
        "status_label": CONTRACT_STATUS_LABELS.get(contract.status, contract.status),
        "party_a_name": contract.party_a_name,
        "party_b_name": contract.party_b_name,
        "party_a_id_number": contract.party_a_id_number,
        "party_b_id_number": contract.party_b_id_number,
        "party_a_contact": contract.party_a_contact,
        "party_b_contact": contract.party_b_contact,
        "contract_amount": contract.contract_amount,
        "variables": json.loads(contract.variables) if contract.variables else None,
        "contract_text": contract.contract_text,
        "esign_contract_id": contract.esign_contract_id,
        "esign_template_id": contract.esign_template_id,
        "sign_url": contract.sign_url,
        "payment_status": contract.payment_status,
        "related_order_id": contract.related_order_id,
        "signed_at": contract.signed_at.isoformat() if contract.signed_at else None,
        "started_at": contract.started_at.isoformat() if contract.started_at else None,
        "completed_at": contract.completed_at.isoformat() if contract.completed_at else None,
        "terminated_at": contract.terminated_at.isoformat() if contract.terminated_at else None,
        "notes": contract.notes,
        "created_at": contract.created_at.isoformat() if contract.created_at else None,
        "updated_at": contract.updated_at.isoformat() if contract.updated_at else None,
    }


# ============================================================
# API 端点
# ============================================================


@router.get("", response_model=ApiResponse, summary="合同列表")
async def list_contracts(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
    status_filter: str | None = Query(None, alias="status", description="按状态筛选"),
    keyword: str = Query("", description="搜索关键字（标题/乙方名称）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取合同列表，支持分页、状态筛选和关键字搜索。

    普通用户仅查看自己的合同，管理员可查看全部。
    """
    query = db.query(Contract).filter(Contract.is_deleted == False)

    if current_user.role != "admin":
        query = query.filter(Contract.user_id == current_user.id)

    if status_filter:
        if status_filter not in CONTRACT_STATUS_FLOW:
            raise HTTPException(
                status_code=400,
                detail=f"无效的状态值: {status_filter}。可选: {', '.join(CONTRACT_STATUS_FLOW.keys())}",
            )
        query = query.filter(Contract.status == status_filter)

    if keyword:
        like = f"%{keyword}%"
        query = query.filter(Contract.title.ilike(like) | Contract.party_b_name.ilike(like))

    total = query.count()
    contracts = query.order_by(Contract.created_at.desc()).offset((page - 1) * size).limit(size).all()

    return ApiResponse(
        code=200,
        message="获取合同列表成功",
        data={
            "total": total,
            "page": page,
            "page_size": size,
            "items": [_contract_to_dict(c) for c in contracts],
        },
    )


@router.post("", response_model=ApiResponse, summary="创建合同")
async def create_contract(
    req: ContractCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    创建新的合同（初始状态为 draft/草稿）。

    创建后可调用 POST /api/contracts/{id}/submit 提交签署。
    """
    contract = Contract(
        user_id=current_user.id,
        title=req.title,
        template_id=req.template_id,
        status="draft",
        party_a_name=req.party_a_name,
        party_b_name=req.party_b_name,
        party_a_id_number=req.party_a_id_number,
        party_b_id_number=req.party_b_id_number,
        party_a_contact=req.party_a_contact,
        party_b_contact=req.party_b_contact,
        contract_amount=req.contract_amount,
        variables=json.dumps(req.variables, ensure_ascii=False) if req.variables else None,
        contract_text=req.contract_text,
        notes=req.notes,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)

    logger.info(
        "合同创建成功: user=%s, contract_id=%s, title=%s",
        current_user.id,
        contract.id,
        contract.title,
    )

    return ApiResponse(
        code=200,
        message="合同创建成功",
        data=_contract_to_dict(contract),
    )


@router.get("/{contract_id}", response_model=ApiResponse, summary="合同详情")
async def get_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个合同的完整详情"""
    contract = _get_contract_or_404(contract_id, current_user, db)
    return ApiResponse(
        code=200,
        message="获取合同详情成功",
        data=_contract_to_dict(contract),
    )


@router.put("/{contract_id}", response_model=ApiResponse, summary="更新合同")
async def update_contract(
    contract_id: int,
    req: ContractUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新合同信息。

    仅当合同处于 draft/草稿 状态时可编辑。已进入签署流程后不允许修改。
    """
    contract = _get_contract_or_404(contract_id, current_user, db)

    if contract.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"仅草稿状态可编辑，当前状态: {CONTRACT_STATUS_LABELS.get(contract.status, contract.status)}",
        )

    update_data = req.model_dump(exclude_unset=True)
    if "variables" in update_data and update_data["variables"] is not None:
        update_data["variables"] = json.dumps(update_data["variables"], ensure_ascii=False)

    for field, value in update_data.items():
        setattr(contract, field, value)

    db.commit()
    db.refresh(contract)

    logger.info("合同更新成功: user=%s, contract_id=%s", current_user.id, contract_id)

    return ApiResponse(
        code=200,
        message="合同更新成功",
        data=_contract_to_dict(contract),
    )


@router.delete("/{contract_id}", response_model=ApiResponse, summary="删除合同")
async def delete_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """软删除合同（仅草稿状态可删除）"""
    contract = _get_contract_or_404(contract_id, current_user, db)

    if contract.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"仅草稿状态可删除，当前状态: {CONTRACT_STATUS_LABELS.get(contract.status, contract.status)}",
        )

    contract.is_deleted = True
    contract.deleted_at = datetime.utcnow()
    db.commit()

    logger.info("合同已删除: user=%s, contract_id=%s", current_user.id, contract_id)

    return ApiResponse(code=200, message="合同已删除")


# ============================================================
# 状态机流转端点
# ============================================================


@router.post("/{contract_id}/submit", response_model=ApiResponse, summary="提交签署")
async def submit_contract(
    contract_id: int,
    req: StatusTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    提交合同进入签署流程（草稿→待签）。

    此操作会触发以下流程：
    1. 验证合同信息完整性
    2. （占位）生成PDF合同文件
    3. （占位）调用e签宝创建签署流程
    4. 状态更新为 pending_sign
    """
    contract = _get_contract_or_404(contract_id, current_user, db)
    _validate_status_transition(contract.status, "pending_sign")

    if not contract.contract_text:
        raise HTTPException(status_code=400, detail="合同正文为空，请先填充合同内容")

    # 占位：生成PDF并上传e签宝
    # TODO: 实际集成时调用 PDF 生成服务 + e签宝 API
    esign_contract_id = f"esign_mock_{contract.id}_{int(datetime.utcnow().timestamp())}"
    sign_url = f"https://esign.example.com/sign/{esign_contract_id}"

    contract.status = "pending_sign"
    contract.esign_contract_id = esign_contract_id
    contract.sign_url = sign_url
    db.commit()
    db.refresh(contract)

    logger.info(
        "合同已提交签署: user=%s, contract_id=%s, esign_id=%s",
        current_user.id,
        contract_id,
        esign_contract_id,
    )

    return ApiResponse(
        code=200,
        message="合同已提交签署，等待对方确认",
        data=_contract_to_dict(contract),
    )


@router.post("/{contract_id}/sign", response_model=ApiResponse, summary="确认签署")
async def sign_contract(
    contract_id: int,
    req: StatusTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    确认签署合同（待签→已签）。

    实际集成时此端点应由 e签宝回调触发或用户主动调用。
    """
    contract = _get_contract_or_404(contract_id, current_user, db)
    _validate_status_transition(contract.status, "signed")

    contract.status = "signed"
    contract.signed_at = datetime.utcnow()
    db.commit()
    db.refresh(contract)

    logger.info(
        "合同已签署: user=%s, contract_id=%s",
        current_user.id,
        contract_id,
    )

    return ApiResponse(
        code=200,
        message="合同签署成功",
        data=_contract_to_dict(contract),
    )


@router.post("/{contract_id}/start", response_model=ApiResponse, summary="开始履行")
async def start_contract(
    contract_id: int,
    req: StatusTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """开始履行合同（已签→履行中）"""
    contract = _get_contract_or_404(contract_id, current_user, db)
    _validate_status_transition(contract.status, "in_progress")

    contract.status = "in_progress"
    contract.started_at = datetime.utcnow()
    db.commit()
    db.refresh(contract)

    logger.info(
        "合同开始履行: user=%s, contract_id=%s",
        current_user.id,
        contract_id,
    )

    return ApiResponse(
        code=200,
        message="合同已进入履行阶段",
        data=_contract_to_dict(contract),
    )


@router.post("/{contract_id}/complete", response_model=ApiResponse, summary="完成合同")
async def complete_contract(
    contract_id: int,
    req: StatusTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """完成合同（履行中→完成）"""
    contract = _get_contract_or_404(contract_id, current_user, db)
    _validate_status_transition(contract.status, "completed")

    contract.status = "completed"
    contract.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(contract)

    logger.info(
        "合同已完成: user=%s, contract_id=%s",
        current_user.id,
        contract_id,
    )

    return ApiResponse(
        code=200,
        message="合同已完成",
        data=_contract_to_dict(contract),
    )


@router.post("/{contract_id}/terminate", response_model=ApiResponse, summary="终止合同")
async def terminate_contract(
    contract_id: int,
    req: StatusTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """终止合同（可随时终止，草稿/待签/已签/履行中→终止）"""
    contract = _get_contract_or_404(contract_id, current_user, db)
    _validate_status_transition(contract.status, "terminated")

    contract.status = "terminated"
    contract.terminated_at = datetime.utcnow()
    db.commit()
    db.refresh(contract)

    logger.info(
        "合同已终止: user=%s, contract_id=%s",
        current_user.id,
        contract_id,
    )

    return ApiResponse(
        code=200,
        message="合同已终止",
        data=_contract_to_dict(contract),
    )


# ============================================================
# 电子签名占位端点
# ============================================================


@router.post("/{contract_id}/generate-pdf", response_model=ApiResponse, summary="生成PDF")
async def generate_contract_pdf(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    生成合同PDF（占位实现）。

    实际集成时将：
    1. 使用 reportlab/weasyprint 将 contract_text 渲染为PDF
    2. 在PDF末尾添加签名栏
    3. 上传至存储服务或直接返回文件流
    """
    contract = _get_contract_or_404(contract_id, current_user, db)

    if not contract.contract_text:
        raise HTTPException(status_code=400, detail="合同正文为空")

    # 占位：返回合同文本信息供前端预览
    # TODO: 实际PDF生成逻辑
    pdf_placeholder = {
        "contract_id": contract.id,
        "title": contract.title,
        "page_count": 1,
        "signature_bar": {
            "has_signature_bar": True,
            "party_a_position": "末尾左栏",
            "party_b_position": "末尾右栏",
            "party_a_name": contract.party_a_name,
            "party_b_name": contract.party_b_name,
        },
        "preview_text": contract.contract_text[:500] + "..."
        if len(contract.contract_text or "") > 500
        else contract.contract_text,
        "download_url": f"/api/contracts/{contract.id}/pdf",  # 占位
    }

    return ApiResponse(
        code=200,
        message="PDF生成成功（占位）",
        data=pdf_placeholder,
    )


# ============================================================
# 支付关联端点
# ============================================================


@router.get("/{contract_id}/transactions", response_model=ApiResponse, summary="关联交易记录")
async def get_contract_transactions(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取合同关联的所有支付交易记录"""
    contract = _get_contract_or_404(contract_id, current_user, db)

    transactions = (
        db.query(PaymentTransaction)
        .filter(
            PaymentTransaction.contract_id == contract.id,
        )
        .order_by(PaymentTransaction.created_at.desc())
        .all()
    )

    return ApiResponse(
        code=200,
        message="获取交易记录成功",
        data={
            "contract_id": contract.id,
            "contract_title": contract.title,
            "total": len(transactions),
            "items": [
                {
                    "id": t.id,
                    "transaction_no": t.transaction_no,
                    "platform": t.platform,
                    "amount": t.amount,
                    "status": t.status,
                    "trade_type": t.trade_type,
                    "description": t.description,
                    "paid_at": t.paid_at.isoformat() if t.paid_at else None,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in transactions
            ],
        },
    )
