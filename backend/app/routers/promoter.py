"""推广员路由：收益查询/提现 + 小程序码"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func
from datetime import datetime

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models import User, Order, Withdrawal, Product
from app.schemas import (
    ApiResponse, WithdrawRequest, WithdrawalResponse,
)
from app.auth import get_current_user
from wechat_qrcode import (
    get_wxacode_unlimited,
    build_promoter_scene,
    is_wechat_configured,
)

router = APIRouter(prefix="/api/promoter", tags=["推广员"])


@router.get("/earnings", response_model=ApiResponse)
def get_earnings(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """获取推广员收益"""
    if current_user.role != "promoter":
        raise HTTPException(status_code=403, detail="仅推广员可查看收益")

    # 计算总收益：已收货订单的commission总和
    total_earnings = db.query(sa_func.coalesce(sa_func.sum(Order.commission), 0.0)).filter(
        Order.promoter_id == current_user.id,
        Order.status == "received",
        Order.commission > 0,
    ).scalar()

    # 已提现总额
    withdrawn = db.query(sa_func.coalesce(sa_func.sum(Withdrawal.amount), 0.0)).filter(
        Withdrawal.user_id == current_user.id,
        Withdrawal.status == "approved",
    ).scalar()

    # 待审核提现
    pending = db.query(sa_func.coalesce(sa_func.sum(Withdrawal.amount), 0.0)).filter(
        Withdrawal.user_id == current_user.id,
        Withdrawal.status == "pending",
    ).scalar()

    available = total_earnings - withdrawn - pending

    order_count = db.query(Order).filter(
        Order.promoter_id == current_user.id,
    ).count()

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total_earnings": round(total_earnings, 2),
            "withdrawn": round(withdrawn, 2),
            "pending": round(pending, 2),
            "available": round(available, 2),
            "order_count": order_count,
        },
    )


@router.post("/withdraw", response_model=ApiResponse)
def withdraw(req: WithdrawRequest, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    """发起提现"""
    if current_user.role != "promoter":
        raise HTTPException(status_code=403, detail="仅推广员可提现")

    # 计算可提现金额
    from sqlalchemy import func as sa_func
    total_earnings = db.query(sa_func.coalesce(sa_func.sum(Order.commission), 0.0)).filter(
        Order.promoter_id == current_user.id,
        Order.status == "received",
    ).scalar()

    withdrawn = db.query(sa_func.coalesce(sa_func.sum(Withdrawal.amount), 0.0)).filter(
        Withdrawal.user_id == current_user.id,
        Withdrawal.status == "approved",
    ).scalar()

    pending = db.query(sa_func.coalesce(sa_func.sum(Withdrawal.amount), 0.0)).filter(
        Withdrawal.user_id == current_user.id,
        Withdrawal.status == "pending",
    ).scalar()

    available = total_earnings - withdrawn - pending

    if req.amount > available:
        raise HTTPException(
            status_code=400,
            detail=f"可提现金额不足。可提现: ¥{available:.2f}，申请: ¥{req.amount:.2f}",
        )

    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="提现金额必须大于0")

    withdrawal = Withdrawal(
        user_id=current_user.id,
        amount=req.amount,
        status="pending",
        bank_info=req.bank_info or "",
    )
    db.add(withdrawal)
    db.commit()
    db.refresh(withdrawal)

    return ApiResponse(
        code=200,
        message="提现申请已提交，等待审核",
        data=WithdrawalResponse.model_validate(withdrawal).model_dump(),
    )


@router.get("/withdrawals", response_model=ApiResponse)
def get_withdrawals(db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """获取提现记录"""
    if current_user.role != "promoter":
        raise HTTPException(status_code=403, detail="仅推广员可查看提现记录")

    withdrawals = db.query(Withdrawal).filter(
        Withdrawal.user_id == current_user.id,
    ).order_by(Withdrawal.id.desc()).all()

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total": len(withdrawals),
            "items": [WithdrawalResponse.model_validate(w).model_dump() for w in withdrawals],
        },
    )


@router.get("/wxacode")
async def get_wxacode(
    product_id: int = Query(..., description="产品ID"),
    page: str = Query("pages/product/index", description="小程序页面路径"),
    width: int = Query(280, ge=128, le=1280, description="二维码宽度"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取推广小程序码（微信原生 wxacode.getUnlimited 接口）

    - 有微信配置：调用微信 API 返回小程序码图片（image/png）
    - 无微信配置：自动降级为本地生成二维码（Mock 模式）

    场景参数 scene 格式: "pid={product_id}&uid={promoter_id}"
    """
    if current_user.role != "promoter":
        raise HTTPException(status_code=403, detail="仅推广员可操作")

    # 验证产品
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    # 构建 scene 参数（最长 32 字符）
    scene = build_promoter_scene(product_id, current_user.id)

    # 调用 wechat_qrcode 模块生成小程序码
    result = await get_wxacode_unlimited(
        scene=scene,
        page=page,
        width=width,
    )

    # 返回图片（或降级二维码图片）
    return Response(
        content=result["image_data"],
        media_type=result["content_type"],
        headers={
            "X-QR-Mock": "true" if result.get("is_mock") else "false",
            "X-QR-Scene": scene,
            "X-QR-Page": page,
        },
    )


@router.get("/wxacode-info", response_model=ApiResponse)
async def get_wxacode_info(
    product_id: int = Query(..., description="产品ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取推广小程序码的元信息（不返回图片，仅返回场景信息和降级状态）
    供前端判断是否使用微信原生码。
    """
    if current_user.role != "promoter":
        raise HTTPException(status_code=403, detail="仅推广员可操作")

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    scene = build_promoter_scene(product_id, current_user.id)
    share_url = f"https://www.go-aiport.com/share?pid={product_id}&uid={current_user.id}"

    return ApiResponse(
        code=200,
        message="success",
        data={
            "scene": scene,
            "page": "pages/product/index",
            "share_url": share_url,
            "product_name": product.name,
            "product_price": product.price,
            "is_wechat_native": is_wechat_configured(),
            "qrcode_url": f"/api/promoter/wxacode?product_id={product_id}&width=280",
        },
    )
