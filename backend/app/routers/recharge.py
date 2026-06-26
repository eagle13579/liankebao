"""链客宝 — 充值支付 API 路由
====================================
从旧版链客宝 recharge/routes.py 提取核心逻辑，适配 chainke-full 架构。

端点:
  POST /api/recharge/precreate     — 预创建充值单（支持微信/支付宝）
  GET  /api/recharge/query/{order_no}  — 查询充值单状态
  GET  /api/recharge/list          — 充值记录列表
  GET  /api/recharge/balance       — 查询余额 + 流水
  POST /api/recharge/adjust        — 管理员手动调额
  GET  /api/recharge/balance-logs  — 分页余额流水
"""

import logging
import random

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recharge", tags=["充值"])


# ===================================================================
# Pydantic 请求/响应模型
# ===================================================================


class PrecreateRequest(BaseModel):
    """预创建充值请求"""
    user_id: str = Field(..., min_length=1, max_length=64, description="用户标识")
    amount: float = Field(..., gt=0, description="充值金额（元），最小1元")
    platform: str = Field(default="wxpay", pattern="^(wxpay|alipay)$", description="支付平台")
    subject: str = Field(default="链客宝充值", max_length=128, description="充值标题")
    openid: str = Field(default="", description="支付平台用户标识（微信openid/支付宝buyer_id）")


class ApiResponse(BaseModel):
    """统一 API 响应"""
    code: int = Field(default=0, description="状态码: 0=成功")
    message: str = Field(default="success", description="提示信息")
    data: dict | None = Field(default=None, description="响应数据")


# ===================================================================
# 工具函数
# ===================================================================


def generate_order_no(user_id: str) -> str:
    """生成充值单号：RC{user_id}{YYYYMMDD}{4位随机数}"""
    import time
    ts = time.strftime("%Y%m%d")
    rand = f"{random.randint(1000, 9999)}"
    # user_id 取后6位，避免过长
    uid_part = user_id.replace("-", "")[-6:] if user_id else "000000"
    return f"RC{uid_part}{ts}{rand}"


async def call_alipay_pay(openid: str, out_trade_no: str, amount_fen: int, subject: str) -> dict | None:
    """调用支付宝统一下单"""
    try:
        from payment.providers.alipay import AliPayConfig, AliPayProvider
        config = AliPayConfig.from_env()
        if not config.is_configured:
            logger.info("支付宝未配置，跳过真实支付")
            return None
        provider = AliPayProvider(config=config)
        result = await provider.pay(
            openid=openid,
            out_trade_no=out_trade_no,
            total_fee=amount_fen,
            description=subject,
            trade_type="APP",
        )
        if result.success:
            return {
                "order_string": (result.data or {}).get("order_string", ""),
                "trade_type": "APP",
            }
        logger.warning(f"支付宝统一下单失败: {result.message}")
        return None
    except ImportError:
        logger.warning("支付宝模块未安装，跳过")
        return None
    except Exception as e:
        logger.warning(f"支付宝统一下单异常: {e}")
        return None


async def call_wxpay_pay(openid: str, out_trade_no: str, amount_fen: int, subject: str) -> dict | None:
    """调用微信支付统一下单（使用已有 payment_engine）"""
    try:
        # 尝试调用 payment_engine 的 _unified_order
        from payment.payment_engine import _unified_order
        result = await _unified_order(
            out_trade_no=out_trade_no,
            total_fee=amount_fen,
            description=subject,
            openid=openid,
            attach=f"recharge:{out_trade_no}",
        )
        return result
    except ImportError:
        logger.warning("payment_engine 模块未安装，跳过微信支付")
        return None
    except Exception as e:
        logger.warning(f"微信统一下单异常: {e}")
        return None


# ===================================================================
# POST /api/recharge/precreate   — 预创建充值单
# ===================================================================


@router.post("/precreate", response_model=ApiResponse)
async def precreate_recharge(req: PrecreateRequest):
    """预创建充值单

    根据 platform 参数选择支付渠道：
    - wxpay: 微信支付
    - alipay: 支付宝支付

    返回前端调起支付所需的参数。
    """
    # 生成订单号
    order_no = generate_order_no(req.user_id)
    amount_fen = int(round(req.amount * 100))  # 元 → 分
    subject = req.subject

    payment_params = None
    real_pay_success = False

    # 根据平台调用对应支付
    if req.platform == "alipay":
        result = await call_alipay_pay(
            openid=req.openid,
            out_trade_no=order_no,
            amount_fen=amount_fen,
            subject=subject,
        )
        if result:
            payment_params = result
            real_pay_success = True
    elif req.platform == "wxpay":
        result = await call_wxpay_pay(
            openid=req.openid,
            out_trade_no=order_no,
            amount_fen=amount_fen,
            subject=subject,
        )
        if result:
            payment_params = result
            real_pay_success = True

    if not real_pay_success:
        # Mock 模式
        import hashlib
        import time as time_mod

        mock_app_id = "wxb4f6d89904200fd2"
        mock_ts = str(int(time_mod.time()))
        mock_nonce = hashlib.md5(f"{mock_ts}{order_no}".encode()).hexdigest()[:16]
        mock_prepay_id = f"wx{mock_ts}{hash(order_no) % 10000:04d}"

        if req.platform == "alipay":
            # 支付宝 mock
            mock_order_string = (
                f"app_id={mock_app_id}"
                f"&method=alipay.trade.app.pay"
                f"&timestamp={mock_ts}"
                f"&sign={mock_nonce}"
            )
            payment_params = {
                "order_string": mock_order_string,
                "trade_type": "APP",
                "_mode": "mock",
            }
        else:
            # 微信 mock
            raw = f"{mock_app_id}\n{mock_ts}\n{mock_nonce}\nprepay_id={mock_prepay_id}\n"
            mock_pay_sign = hashlib.sha256(raw.encode()).hexdigest()[:32]
            payment_params = {
                "appId": mock_app_id,
                "timeStamp": mock_ts,
                "nonceStr": mock_nonce,
                "package": f"prepay_id={mock_prepay_id}",
                "signType": "RSA",
                "paySign": mock_pay_sign,
                "_mode": "mock",
            }

        logger.info(
            f"Mock 充值预创建: order_no={order_no}, "
            f"amount={req.amount}, platform={req.platform}"
        )

    return ApiResponse(
        code=0,
        message="success" if real_pay_success else "success (mock)",
        data={
            "order_no": order_no,
            "amount": req.amount,
            "platform": req.platform,
            "payment_params": payment_params,
        },
    )


# ===================================================================
# GET /api/recharge/query/{order_no}   — 查询充值单
# ===================================================================


@router.get("/query/{order_no}", response_model=ApiResponse)
async def query_recharge_order(order_no: str):
    """查询充值单状态"""
    # TODO: 从数据库查询充值订单
    logger.info(f"查询充值单: {order_no}")
    return ApiResponse(
        code=0,
        message="success",
        data={
            "order_no": order_no,
            "status": "pending",
            "note": "数据库查询待实现",
        },
    )


# ===================================================================
# GET /api/recharge/list   — 充值记录列表
# ===================================================================


@router.get("/list", response_model=ApiResponse)
async def list_recharge_orders(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    user_id: str = Query("", description="用户标识过滤"),
):
    """充值记录列表（分页）"""
    # TODO: 从数据库分页查询
    logger.info(f"查询充值记录列表: page={page}, limit={limit}, user_id={user_id}")
    return ApiResponse(
        code=0,
        message="success",
        data={
            "total": 0,
            "page": page,
            "limit": limit,
            "items": [],
            "note": "数据库查询待实现",
        },
    )


# ===================================================================
# GET /api/recharge/balance   — 查询余额
# ===================================================================


@router.get("/balance", response_model=ApiResponse)
async def query_balance(user_id: str = Query(..., description="用户标识")):
    """查询用户余额及最近流水"""
    # TODO: 从数据库查询
    logger.info(f"查询用户余额: user_id={user_id}")
    return ApiResponse(
        code=0,
        message="success",
        data={
            "user_id": user_id,
            "balance": 0.00,
            "total_recharged": 0.00,
            "total_consumed": 0.00,
            "recent_logs": [],
            "note": "数据库查询待实现",
        },
    )


# ===================================================================
# POST /api/recharge/adjust   — 管理员调额
# ===================================================================


class AdjustRequest(BaseModel):
    """管理员调额请求"""
    user_id: str = Field(..., description="用户标识")
    amount: float = Field(..., description="调额金额（正数增加，负数减少）")
    remark: str = Field(default="", max_length=500, description="备注")


@router.post("/adjust", response_model=ApiResponse)
async def adjust_balance(req: AdjustRequest):
    """管理员手动调额"""
    # TODO: 实现余额调整逻辑
    logger.info(f"管理员调额: user_id={req.user_id}, amount={req.amount}, remark={req.remark}")
    return ApiResponse(
        code=0,
        message="success",
        data={
            "user_id": req.user_id,
            "amount": req.amount,
            "note": "数据库操作待实现",
        },
    )


# ===================================================================
# GET /api/recharge/balance-logs   — 余额流水
# ===================================================================


@router.get("/balance-logs", response_model=ApiResponse)
async def list_balance_logs(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    user_id: str = Query(..., description="用户标识"),
):
    """分页查询余额流水记录"""
    # TODO: 从数据库分页查询
    logger.info(f"查询余额流水: user_id={user_id}, page={page}, limit={limit}")
    return ApiResponse(
        code=0,
        message="success",
        data={
            "total": 0,
            "page": page,
            "limit": limit,
            "items": [],
            "note": "数据库查询待实现",
        },
    )
