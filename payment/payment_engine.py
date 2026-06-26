"""
WeChat Pay V3 Payment Engine
=============================
- 统一下单 (JSAPI)    POST /api/v1/pay/unified-order
- 订单查询             GET  /api/v1/pay/order/{out_trade_no}
- 支付回调             POST /api/v1/pay/callback
- 退款 (骨架)          POST /api/v1/pay/refund

商户号 / APIv3密钥 / 证书路径 均从 os.environ 读取。
FastAPI + httpx, ≤500 行
"""

import os
import json
import time
import uuid
import logging
from typing import Optional, Dict, Any

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logger = logging.getLogger("payment_engine")
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# 配置 (环境变量)
# ---------------------------------------------------------------------------
MCHID = os.environ.get("WECHAT_MCHID", "")
APPID = os.environ.get("WECHAT_APPID", "")
APIV3_KEY = os.environ.get("WECHAT_APIV3_KEY", "")
MCH_SERIAL_NO = os.environ.get("WECHAT_MCH_SERIAL_NO", "")
MCH_PRIVATE_KEY_PATH = os.environ.get("WECHAT_MCH_PRIVATE_KEY_PATH", "")
NOTIFY_URL = os.environ.get("WECHAT_NOTIFY_URL", "")

WECHAT_API_BASE = "https://api.mch.weixin.qq.com"

# ---------------------------------------------------------------------------
# 辅助: 加载商户私钥 (RSA PKCS#8 PEM)
# ---------------------------------------------------------------------------
def _load_private_key() -> bytes:
    """返回 PEM 格式私钥的 bytes, 供 httpx ClientCert 使用 或 手动签名."""
    with open(MCH_PRIVATE_KEY_PATH, "rb") as f:
        return f.read()

# ---------------------------------------------------------------------------
# 辅助: 生成请求签名 (WeChatPay-V2-SHA256-RSA2048)
# ---------------------------------------------------------------------------
def _build_auth_token(method: str, url_path: str, body: str = "",
                      private_key_pem: bytes = None) -> str:
    """
    构造 Authorization 请求头值。
    WECHATPAY2-SHA256-RSA2048 schema
    """
    nonce = uuid.uuid4().hex
    timestamp = str(int(time.time()))
    message = f"{method}\n{url_path}\n{timestamp}\n{nonce}\n{body}\n"

    if private_key_pem is None:
        private_key_pem = _load_private_key()

    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend

    key = serialization.load_pem_private_key(
        private_key_pem, password=None, backend=default_backend()
    )
    signature = base64.b64encode(
        key.sign(message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    ).decode("utf-8")

    parts = (
        f'mchid="{MCHID}"',
        f'nonce_str="{nonce}"',
        f'timestamp="{timestamp}"',
        f'serial_no="{MCH_SERIAL_NO}"',
        f'signature="{signature}"',
    )
    return "WECHATPAY2-SHA256-RSA2048 " + ",".join(parts)


# ---------------------------------------------------------------------------
# 辅助: HMAC-SHA256 (用于回调 resource 的 associated_data 验证)
# ---------------------------------------------------------------------------
import hmac
import base64

def _hmac_sha256(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


# ---------------------------------------------------------------------------
# 辅助: AES-256-GCM 解密 (WeChat Pay 回调 resource)
# ---------------------------------------------------------------------------
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def _decrypt_resource(associated_data: str, nonce: str, ciphertext: str) -> Dict[str, Any]:
    """
    解密 WeChat Pay 回调通知中的 resource 字段。
    APIV3_KEY 作为对称密钥。
    """
    key_bytes = APIV3_KEY.encode("utf-8")  # 32 字节
    nonce_bytes = nonce.encode("utf-8")
    aad_bytes = associated_data.encode("utf-8")
    ct_bytes = base64.b64decode(ciphertext)

    aesgcm = AESGCM(key_bytes)
    plaintext = aesgcm.decrypt(nonce_bytes, ct_bytes, aad_bytes)
    return json.loads(plaintext.decode("utf-8"))


# ---------------------------------------------------------------------------
# 辅助: 验证回调通知签名 (WeChat Pay 平台证书)
# ---------------------------------------------------------------------------
async def _verify_callback_signature(
    request: Request, body_bytes: bytes
) -> bool:
    """
    验证 WeChat Pay 回调请求的签名。
    从请求头获取 Wechatpay-Signature / Wechatpay-Timestamp / Wechatpay-Nonce /
    Wechatpay-Serial。
    使用缓存或实时获取的 WeChat Pay 平台公钥。
    """
    signature = request.headers.get("Wechatpay-Signature", "")
    timestamp = request.headers.get("Wechatpay-Timestamp", "")
    nonce = request.headers.get("Wechatpay-Nonce", "")
    serial = request.headers.get("Wechatpay-Serial", "")

    if not all([signature, timestamp, nonce, serial]):
        logger.warning("缺少回调签名头字段")
        return False

    # 1) 获取 WeChat Pay 平台公钥
    public_key_pem = await _get_platform_public_key(serial)
    if public_key_pem is None:
        logger.error("无法获取平台公钥, serial=%s", serial)
        return False

    # 2) 构造待签名字符串
    message = f"{timestamp}\n{nonce}\n{body_bytes.decode('utf-8')}\n"

    # 3) 验证签名
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend

    try:
        pub_key = serialization.load_pem_public_key(
            public_key_pem.encode("utf-8") if isinstance(public_key_pem, str)
            else public_key_pem,
            backend=default_backend(),
        )
        sig_bytes = base64.b64decode(signature)
        pub_key.verify(sig_bytes, message.encode("utf-8"),
                       padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception as exc:
        logger.warning("回调签名验证失败: %s", exc)
        return False


# ---------------------------------------------------------------------------
# 缓存: WeChat Pay 平台证书
# ---------------------------------------------------------------------------
_platform_certs: Dict[str, str] = {}   # serial_no -> public_key_pem
_certs_expire_at: float = 0.0

async def _get_platform_public_key(serial_no: str) -> Optional[str]:
    """从本地缓存或远程获取平台公钥 PEM."""
    now = time.time()
    if serial_no in _platform_certs and now < _certs_expire_at:
        return _platform_certs[serial_no]

    # 远程获取 https://api.mch.weixin.qq.com/v3/certificates
    url_path = "/v3/certificates"
    url = f"{WECHAT_API_BASE}{url_path}"
    private_key_pem = _load_private_key()
    auth = _build_auth_token("GET", url_path, "", private_key_pem)

    async with httpx.AsyncClient(verify=True) as client:
        resp = await client.get(url, headers={"Authorization": auth})
        if resp.status_code != 200:
            logger.error("获取平台证书失败: %d %s", resp.status_code, resp.text)
            return None

        data = resp.json()
        for cert_info in data.get("data", []):
            sno = cert_info.get("serial_no", "")
            encrypt_cert = cert_info.get("encrypt_certificate", {})

            # 平台证书本身也是 AES-GCM 加密的
            pem = _decrypt_resource(
                encrypt_cert.get("associated_data", ""),
                encrypt_cert.get("nonce", ""),
                encrypt_cert.get("ciphertext", ""),
            )
            _platform_certs[sno] = pem
            # 缓存有效期: 证书有效期内, 保守设为 4 小时
            _certs_expire_at = now + 14400

    return _platform_certs.get(serial_no)


# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------
app = FastAPI(title="Payment Engine", version="1.0.0")


# ---------------------------------------------------------------------------
# 内部: 下单
# ---------------------------------------------------------------------------
async def _unified_order(
    out_trade_no: str,
    total_fee: int,
    description: str,
    openid: str,
    attach: str = "",
) -> Dict[str, Any]:
    """
    调用 WeChat Pay V3 JSAPI 统一下单接口。
    返回 prepay_id 及调起支付所需的参数包。
    """
    url_path = "/v3/pay/transactions/jsapi"
    url = f"{WECHAT_API_BASE}{url_path}"

    body_dict = {
        "appid": APPID,
        "mchid": MCHID,
        "description": description,
        "out_trade_no": out_trade_no,
        "notify_url": NOTIFY_URL,
        "amount": {"total": total_fee, "currency": "CNY"},
        "payer": {"openid": openid},
    }
    if attach:
        body_dict["attach"] = attach

    body_json = json.dumps(body_dict, ensure_ascii=False, separators=(",", ":"))
    private_key_pem = _load_private_key()
    auth = _build_auth_token("POST", url_path, body_json, private_key_pem)

    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "payment-engine/1.0",
    }

    async with httpx.AsyncClient(verify=True) as client:
        resp = await client.post(url, headers=headers, content=body_json)
        if resp.status_code not in (200, 204):
            err_text = resp.text
            logger.error("统一下单失败: %d %s", resp.status_code, err_text)
            raise HTTPException(status_code=502, detail=f"微信下单失败: {err_text}")

        result = resp.json()
        prepay_id = result.get("prepay_id")
        if not prepay_id:
            raise HTTPException(status_code=502, detail="微信未返回 prepay_id")

    # 构造 JSAPI 调起支付参数
    nonce = uuid.uuid4().hex
    timestamp = str(int(time.time()))
    package = f"prepay_id={prepay_id}"
    sign_message = f"{APPID}\n{timestamp}\n{nonce}\n{package}\n"

    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend

    key = serialization.load_pem_private_key(
        private_key_pem, password=None, backend=default_backend()
    )
    pay_sign = base64.b64encode(
        key.sign(sign_message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    ).decode("utf-8")

    return {
        "prepay_id": prepay_id,
        "pay_params": {
            "appId": APPID,
            "timeStamp": timestamp,
            "nonceStr": nonce,
            "package": package,
            "signType": "RSA",
            "paySign": pay_sign,
        },
    }


# ---------------------------------------------------------------------------
# 内部: 查询订单
# ---------------------------------------------------------------------------
async def _query_order(out_trade_no: str) -> Dict[str, Any]:
    """查询微信支付订单状态."""
    url_path = f"/v3/pay/transactions/out-trade-no/{out_trade_no}"
    url = f"{WECHAT_API_BASE}{url_path}?mchid={MCHID}"

    private_key_pem = _load_private_key()
    auth = _build_auth_token("GET", url_path, "", private_key_pem)

    headers = {
        "Authorization": auth,
        "Accept": "application/json",
        "User-Agent": "payment-engine/1.0",
    }

    async with httpx.AsyncClient(verify=True) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            err_text = resp.text
            logger.error("订单查询失败: %d %s", resp.status_code, err_text)
            raise HTTPException(status_code=502, detail=f"订单查询失败: {err_text}")
        return resp.json()


# ---------------------------------------------------------------------------
# 内部: 处理支付回调 (更新订单状态占位)
# ---------------------------------------------------------------------------
def _update_order_status(out_trade_no: str, transaction_id: str,
                         trade_state: str, **kwargs) -> None:
    """
    更新订单状态。实际项目应替换为数据库写入逻辑。
    Args:
        out_trade_no: 商户订单号
        transaction_id: 微信支付订单号
        trade_state: SUCCESS / REFUND / NOTPAY / CLOSED / REVOKED
    """
    logger.info(
        "订单状态更新: out_trade_no=%s, transaction_id=%s, trade_state=%s, extra=%s",
        out_trade_no, transaction_id, trade_state, kwargs,
    )
    # TODO: 写入数据库
    # from your.models import Order
    # Order.objects.filter(out_trade_no=out_trade_no).update(
    #     transaction_id=transaction_id,
    #     status=...,
    #     paid_at=...,
    # )


# ---------------------------------------------------------------------------
# REST 端点
# ---------------------------------------------------------------------------

@app.post("/api/v1/pay/unified-order")
async def unified_order_api(payload: Dict[str, Any]):
    """
    统一下单 (JSAPI)
    请求体: { out_trade_no, total_fee, description, openid, attach? }
    """
    out_trade_no = payload.get("out_trade_no")
    total_fee = payload.get("total_fee")
    description = payload.get("description")
    openid = payload.get("openid")
    attach = payload.get("attach", "")

    if not all([out_trade_no, total_fee, description, openid]):
        raise HTTPException(status_code=400, detail="缺少必填参数")

    result = await _unified_order(out_trade_no, total_fee, description, openid, attach)
    return {"code": 0, "message": "ok", "data": result}


@app.get("/api/v1/pay/order/{out_trade_no}")
async def query_order_api(out_trade_no: str):
    """查询订单状态."""
    order_info = await _query_order(out_trade_no)
    return {"code": 0, "message": "ok", "data": order_info}


@app.post("/api/v1/pay/callback")
async def payment_callback(request: Request):
    """
    微信支付结果通知回调。
    验签 -> 解密 resource -> 更新订单状态。
    """
    body_bytes = await request.body()

    # 1) 验签
    valid = await _verify_callback_signature(request, body_bytes)
    if not valid:
        logger.warning("回调验签失败, body=%s", body_bytes[:200])
        raise HTTPException(status_code=401, detail="签名验证失败")

    # 2) 解密 resource
    try:
        body = json.loads(body_bytes)
        resource = body.get("resource", {})
        event_data = _decrypt_resource(
            resource.get("associated_data", ""),
            resource.get("nonce", ""),
            resource.get("ciphertext", ""),
        )
    except Exception as exc:
        logger.error("回调数据解密失败: %s", exc)
        raise HTTPException(status_code=400, detail="解密失败")

    # 3) 更新订单状态
    out_trade_no = event_data.get("out_trade_no", "")
    transaction_id = event_data.get("transaction_id", "")
    trade_state = event_data.get("trade_state", "")
    trade_state_desc = event_data.get("trade_state_desc", "")

    _update_order_status(
        out_trade_no=out_trade_no,
        transaction_id=transaction_id,
        trade_state=trade_state,
        trade_state_desc=trade_state_desc,
    )

    # 4) 返回成功应答 (WeChat Pay 要求)
    return JSONResponse(
        content={"code": "SUCCESS", "message": "成功"},
        status_code=200,
    )


@app.post("/api/v1/pay/refund")
async def refund_api(payload: Dict[str, Any]):
    """
    退款 API 骨架。
    请求体: { out_trade_no, refund_amount, total_amount, reason?, out_refund_no? }
    """
    out_trade_no = payload.get("out_trade_no")
    refund_amount = payload.get("refund_amount")
    total_amount = payload.get("total_amount")
    reason = payload.get("reason", "")
    out_refund_no = payload.get("out_refund_no", str(uuid.uuid4()).replace("-", ""))

    if not all([out_trade_no, refund_amount, total_amount]):
        raise HTTPException(status_code=400, detail="缺少必填参数")

    url_path = "/v3/refund/domestic/refunds"
    url = f"{WECHAT_API_BASE}{url_path}"

    body_dict = {
        "out_trade_no": out_trade_no,
        "out_refund_no": out_refund_no,
        "amount": {
            "refund": refund_amount,
            "total": total_amount,
            "currency": "CNY",
        },
    }
    if reason:
        body_dict["reason"] = reason

    body_json = json.dumps(body_dict, ensure_ascii=False, separators=(",", ":"))
    private_key_pem = _load_private_key()
    auth = _build_auth_token("POST", url_path, body_json, private_key_pem)

    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "payment-engine/1.0",
    }

    async with httpx.AsyncClient(verify=True) as client:
        resp = await client.post(url, headers=headers, content=body_json)
        if resp.status_code not in (200, 204):
            err_text = resp.text
            logger.error("退款请求失败: %d %s", resp.status_code, err_text)
            raise HTTPException(status_code=502, detail=f"退款失败: {err_text}")

        result = resp.json()
        return {"code": 0, "message": "ok", "data": result}


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------
@app.get("/api/v1/pay/health")
async def health():
    return {"status": "ok", "mchid": MCHID}
