"""订单路由：创建订单/查看订单/更新订单状态/支付回调"""
import hashlib
import time
import os
import json
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Product, Order
from app.schemas import (
    ApiResponse, OrderCreate, OrderStatusRequest, OrderResponse,
)
from app.auth import get_current_user
from payment import (
    WxPayApi, WxPayConfig, WxPayCallback,
    get_config, has_config, PLATFORM_WXPAY,
    is_real_mode,
)
from invoice import get_order_invoice_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["订单"])

# 微信支付配置（从环境变量读取）
WECHAT_APPID = os.environ.get("WECHAT_APPID", "wxb4f6d89904200fd2")


@router.post("", response_model=ApiResponse)
def create_order(req: OrderCreate, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """创建订单并返回支付参数"""
    # 验证产品
    product = db.query(Product).filter(
        Product.id == req.product_id,
        Product.is_deleted == False,
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    if product.status != "approved":
        raise HTTPException(status_code=400, detail="产品未上架")
    if product.stock < req.quantity:
        raise HTTPException(status_code=400, detail="库存不足")

    # 计算价格
    total_price = product.price * req.quantity
    commission = 0.0

    # 如果有推广员，计算分润
    promoter = None
    if req.promoter_id:
        promoter = db.query(User).filter(
            User.id == req.promoter_id,
            User.role == "promoter",
            User.is_deleted == False,
        ).first()
        if not promoter:
            raise HTTPException(status_code=400, detail="推广员不存在")
        # 推广员分润 = 总价 * (earn_per_share%) 
        commission = total_price * (product.earn_per_share / 100)

    # 扣减库存
    product.stock -= req.quantity

    # 创建订单（初始状态为 pending，支付成功后才变为 paid）
    order = Order(
        user_id=current_user.id,
        product_id=req.product_id,
        quantity=req.quantity,
        total_price=total_price,
        status="pending",
        promoter_id=req.promoter_id,
        commission=commission,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # 生成支付参数（微信支付统一下单）
    import asyncio
    out_trade_no = f"LK{order.id:08d}{int(time.time())}"
    total_fee = int(total_price * 100)  # 元转分

    # 判断支付模式：有完整配置 + 模式为 real 才走真实微信API
    use_real = is_real_mode() and has_config(PLATFORM_WXPAY)

    if use_real:
        # 真实模式：调用微信统一下单
        openid = current_user.wechat_openid or ""
        if not openid:
            logger.warning(f"用户 {current_user.id} 无 wechat_openid，尝试用 mock 支付")
            payment_params = _mock_payment(order)
        else:
            try:
                wxpay = WxPayApi()
                result = asyncio.run(wxpay.create_jsapi_order(
                    openid=openid,
                    out_trade_no=out_trade_no,
                    total_fee=total_fee,
                    description=f"{product.name[:60]} x{req.quantity}",
                    attach=json.dumps({"order_id": order.id}),
                ))
            except Exception as e:
                logger.error(f"微信统一下单失败: {e}")
                result = None

            if result and result.get("prepay_id"):
                order.prepay_id = result["prepay_id"]
                db.commit()
                payment_params = result["payment_params"]
                payment_params["_mode"] = "real"
            else:
                logger.warning("微信统一下单失败，降级到 mock 模式")
                payment_params = _mock_payment(order)
    else:
        # Mock模式
        payment_params = _mock_payment(order)

    return ApiResponse(
        code=200,
        message="下单成功",
        data={
            "order": OrderResponse.model_validate(order).model_dump(),
            "payment": payment_params,
        },
    )


def _mock_payment(order: Order) -> dict:
    """生成 mock 支付参数"""
    timestamp = str(int(time.time()))
    nonce_str = hashlib.md5(f"{timestamp}{order.id}".encode()).hexdigest()[:16]
    prepay_id = f"wx{timestamp}{order.id}"

    # 保存 prepay_id
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        db_order = db.query(Order).filter(
            Order.id == order.id,
            Order.is_deleted == False,
        ).first()
        if db_order:
            db_order.prepay_id = prepay_id
            db.commit()
    except Exception:
        pass
    finally:
        db.close()

    raw = f"{WECHAT_APPID}\n{timestamp}\n{nonce_str}\nprepay_id={prepay_id}\n"
    pay_sign = hashlib.sha256(raw.encode()).hexdigest()[:32]

    return {
        "appId": WECHAT_APPID,
        "timeStamp": timestamp,
        "nonceStr": nonce_str,
        "package": f"prepay_id={prepay_id}",
        "signType": "RSA",
        "paySign": pay_sign,
        "_mode": "mock",
    }


@router.post("/pay-notify", response_model=None)
async def pay_notify(request: Request, db: Session = Depends(get_db)):
    """微信支付回调通知处理"""
    body = await request.body()
    logger.info(f"收到支付回调: {body[:200]}")

    # 获取回调头信息
    wechat_signature = request.headers.get("Wechatpay-Signature", "")
    wechat_serial = request.headers.get("Wechatpay-Serial", "")
    wechat_timestamp = request.headers.get("Wechatpay-Timestamp", "")
    wechat_nonce = request.headers.get("Wechatpay-Nonce", "")

    if is_real_mode() and has_config(PLATFORM_WXPAY) and wechat_signature:
        # 真实模式：使用新模块 WxPayCallback 验签
        callback = WxPayCallback()
        notify_data = callback.verify_and_decrypt(
            body=body,
            wechatpay_signature=wechat_signature,
            wechatpay_serial=wechat_serial,
            wechatpay_timestamp=wechat_timestamp,
            wechatpay_nonce=wechat_nonce,
        )
        if not notify_data:
            logger.error("支付回调验签失败")
            return {"code": "FAIL", "message": "验签失败"}
    else:
        # Mock模式：直接解析
        try:
            notify_data = json.loads(body)
            if "resource" in notify_data:
                # 模拟解密
                import base64
                try:
                    resource = notify_data["resource"]
                    ciphertext = resource.get("ciphertext", "")
                    if ciphertext:
                        plaintext = base64.b64decode(ciphertext).decode("utf-8")
                        notify_data = json.loads(plaintext)
                    else:
                        notify_data = {"out_trade_no": "", "transaction_id": f"mock_tx_{int(time.time())}"}
                except Exception:
                    notify_data = {"out_trade_no": "", "transaction_id": f"mock_tx_{int(time.time())}"}
            else:
                notify_data = notify_data
        except Exception:
            notify_data = {"out_trade_no": "", "transaction_id": f"mock_tx_{int(time.time())}"}

    logger.info(f"解析回调数据: {notify_data}")

    # 更新订单状态
    out_trade_no = notify_data.get("out_trade_no", "")
    transaction_id = notify_data.get("transaction_id", "") or notify_data.get("wx_transaction_id", "")

    if out_trade_no:
        # 从 out_trade_no 解析 order_id（格式: LK{order_id}....）
        if out_trade_no.startswith("LK"):
            try:
                order_id = int(out_trade_no[2:10])
            except (ValueError, IndexError):
                order_id = None
        else:
            order_id = None

        if order_id:
            order = db.query(Order).filter(
                Order.id == order_id,
                Order.is_deleted == False,
            ).first()
            if order and order.status == "pending":
                order.status = "paid"
                order.wx_transaction_id = transaction_id or f"mock_tx_{order.id}"
                order.pay_time = datetime.utcnow()
                db.commit()
                logger.info(f"订单 {order_id} 支付成功，状态更新为 paid")
                return {"code": "SUCCESS", "message": "成功"}
            elif order:
                logger.warning(f"订单 {order_id} 状态为 {order.status}，无需更新")
                return {"code": "SUCCESS", "message": "已处理"}
            else:
                logger.warning(f"订单 {order_id} 不存在")
        else:
            logger.warning(f"无法从 out_trade_no 解析 order_id: {out_trade_no}")

    # 尝试通过 prepay_id 匹配
    if transaction_id:
        order = db.query(Order).filter(
            Order.status == "pending",
            Order.prepay_id.isnot(None),
            Order.is_deleted == False,
        ).order_by(Order.id.desc()).first()
        if order:
            order.status = "paid"
            order.wx_transaction_id = transaction_id
            order.pay_time = datetime.utcnow()
            db.commit()
            logger.info(f"订单 {order.id} 支付成功（通过 prepay_id 匹配）")
            return {"code": "SUCCESS", "message": "成功"}

    return {"code": "SUCCESS", "message": "已接收"}


@router.get("", response_model=ApiResponse)
def get_orders(db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    """获取订单列表（按角色过滤）"""
    if current_user.role == "admin":
        # 管理员看所有订单
        orders = db.query(Order).filter(
            Order.is_deleted == False,
        ).order_by(Order.id.desc()).all()
    elif current_user.role == "supplier":
        # 产品方看自己产品的订单
        orders = db.query(Order).join(Product).filter(
            Product.owner_id == current_user.id,
            Order.is_deleted == False,
        ).order_by(Order.id.desc()).all()
    elif current_user.role == "promoter":
        # 推广员看自己推广的订单
        orders = db.query(Order).filter(
            Order.promoter_id == current_user.id,
            Order.is_deleted == False,
        ).order_by(Order.id.desc()).all()
    else:
        # 普通用户看自己的订单
        orders = db.query(Order).filter(
            Order.user_id == current_user.id,
            Order.is_deleted == False,
        ).order_by(Order.id.desc()).all()

    return ApiResponse(
        code=200,
        message="success",
        data={
            "total": len(orders),
            "items": [OrderResponse.model_validate(o).model_dump() for o in orders],
        },
    )


# 允许的状态流转
ALLOWED_TRANSITIONS = {
    "paid": ["shipped", "refunded"],
    "shipped": ["received", "refunded"],
    "received": ["refunded"],
    "refunded": [],
}


@router.put("/{order_id}/status", response_model=ApiResponse)
def update_order_status(
    order_id: int,
    req: OrderStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新订单状态（按角色限制）"""
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.is_deleted == False,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 检查权限
    is_admin = current_user.role == "admin"
    is_supplier = current_user.role == "supplier" and order.product.owner_id == current_user.id
    is_buyer = current_user.role in ("buyer",) and order.user_id == current_user.id

    if not (is_admin or is_supplier or is_buyer):
        raise HTTPException(status_code=403, detail="无权操作此订单")

    # 检查状态流转是否合法
    allowed = ALLOWED_TRANSITIONS.get(order.status, [])
    if req.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"状态不允许变更: {order.status} → {req.status}，可选: {allowed}",
        )

    # 普通用户只能确认收货或申请退款
    if is_buyer and req.status not in ["received", "refunded"]:
        raise HTTPException(status_code=403, detail="买家只能确认收货或申请退款")

    # 产品方只能发货
    if is_supplier and req.status not in ["shipped"]:
        raise HTTPException(status_code=403, detail="产品方只能发货")

    # 记录旧状态
    old_status = order.status

    # 如果申请退款，调用微信退款
    if req.status == "refunded" and order.wx_transaction_id:
        import asyncio
        try:
            wxpay = WxPayApi()
            refund_result = asyncio.run(wxpay.create_refund(
                out_trade_no=f"LK{order.id:08d}",
                out_refund_no=f"RF{order.id:08d}{int(time.time())}",
                refund_amount=int(order.total_price * 100),
                total_amount=int(order.total_price * 100),
                reason="用户申请退款",
            ))
            if refund_result:
                logger.info(f"订单 {order.id} 退款成功: {refund_result.get('refund_id')}")
        except Exception as e:
            logger.error(f"退款调用失败: {e}")
            # 即使退款API失败，仍允许状态变更（后续可人工处理）

    # 如果确认收货且有关联推广员，累加收益
    if req.status == "received" and order.promoter_id and order.commission > 0:
        pass  # 推广收益由 promoter earnings 查询时实时计算

    order.status = req.status
    db.commit()
    db.refresh(order)

    return ApiResponse(
        code=200,
        message=f"订单状态已变更: {old_status} → {req.status}",
        data=OrderResponse.model_validate(order).model_dump(),
    )


@router.get("/{order_id}", response_model=ApiResponse)
def get_order(order_id: int, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    """获取订单详情"""
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.is_deleted == False,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 权限检查
    is_admin = current_user.role == "admin"
    is_supplier = current_user.role == "supplier" and order.product.owner_id == current_user.id
    is_owner = order.user_id == current_user.id
    is_promoter = order.promoter_id == current_user.id

    if not (is_admin or is_supplier or is_owner or is_promoter):
        raise HTTPException(status_code=403, detail="无权查看此订单")
    
    order_data = OrderResponse.model_validate(order).model_dump()

    # 嵌入发票信息（仅订单所属用户可见）
    if is_owner or is_admin:
        order_data["invoice_info"] = get_order_invoice_info(order.id, db)

    return ApiResponse(
        code=200,
        message="success",
        data=order_data,
    )
