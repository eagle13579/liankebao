"""
微信支付模块 (WeChat Pay V3 + V2 兼容)
基于 IJPay ch-05 + ch-07

功能:
    - WxPayAuth — V3 鉴权头生成 (WECHATPAY2-SHA256-RSA2048)
    - WxPayCallback — 回调验证 (签名验证 + resource 解密)
    - WxPayApi — 统一下单 / 查询 / 退款 / 关闭
    - 兼容现有的 V2 接口签名
"""

import json
import time
import logging
from typing import Optional, Dict, Any, Tuple

from payment.config import WxPayConfig, get_config, PLATFORM_WXPAY
from payment.sign import (
    generate_nonce,
    build_v3_sign_str,
    build_v3_response_sign_str,
    rsa_sign,
    rsa_verify_with_key,
    aes_gcm_decrypt,
    build_v2_sign,
)
from payment.http_delegate import HttpDelegate, HttpResponse

logger = logging.getLogger(__name__)


# ============================================================
# 常量
# ============================================================

WECHAT_API_BASE = "https://api.mch.weixin.qq.com"
WECHAT_V3_BASE = "https://api.mch.weixin.qq.com/v3"

# V3 API 路径
V3_JSAPI_PAY = "/v3/pay/transactions/jsapi"
V3_ORDER_QUERY_BY_OUT_TRADE_NO = "/v3/pay/transactions/out-trade-no/%s"
V3_ORDER_QUERY_BY_TRANSACTION_ID = "/v3/pay/transactions/id/%s"
V3_CLOSE_ORDER = "/v3/pay/transactions/out-trade-no/%s/close"
V3_REFUND = "/v3/refund/domestic/refunds"
V3_REFUND_QUERY = "/v3/refund/domestic/refunds/%s"
V3_CERTIFICATES = "/v3/certificates"

# V2 API 路径
V2_UNIFIED_ORDER = f"{WECHAT_API_BASE}/pay/unifiedorder"
V2_ORDER_QUERY = f"{WECHAT_API_BASE}/pay/orderquery"
V2_REFUND = f"{WECHAT_API_BASE}/secapi/pay/refund"
V2_REFUND_QUERY = f"{WECHAT_API_BASE}/pay/refundquery"
V2_CLOSE_ORDER_URL = f"{WECHAT_API_BASE}/pay/closeorder"


# ============================================================
# WxPayAuth — V3 鉴权头生成
# ============================================================

class WxPayAuth:
    """
    微信 V3 API 鉴权头生成器

    生成 HTTP Authorization 头:
        WECHATPAY2-SHA256-RSA2048
        mchid=\"...\",nonce_str=\"...\",timestamp=\"...\",serial_no=\"...\",signature=\"...\"
    """

    def __init__(self, config: Optional[WxPayConfig] = None):
        self._config = config

    def _get_config(self) -> WxPayConfig:
        if self._config:
            return self._config
        cfg = get_config(PLATFORM_WXPAY)
        if not isinstance(cfg, WxPayConfig):
            raise TypeError(f"配置类型错误，期望 WxPayConfig，实际 {type(cfg)}")
        return cfg

    def _build_authorization(
        self, method: str, url_path: str, body: str = ""
    ) -> Tuple[str, str, str, str]:
        config = self._get_config()
        timestamp = str(int(time.time()))
        nonce = generate_nonce(32)
        sign_str = build_v3_sign_str(method, url_path, timestamp, nonce, body)

        signature = rsa_sign(sign_str, config.private_key_path)

        auth = (
            f'WECHATPAY2-SHA256-RSA2048 '
            f'mchid="{config.mch_id}",'
            f'nonce_str="{nonce}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{config.cert_serial_no}",'
            f'signature="{signature}"'
        )
        return auth, timestamp, nonce, signature

    def get_headers(self, method: str, url_path: str, body: str = "") -> Dict[str, str]:
        auth, timestamp, nonce, _ = self._build_authorization(method, url_path, body)
        return {
            "Authorization": auth,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "liankebao-payment/1.0",
        }


# ============================================================
# WxPayCallback — 回调验证
# ============================================================

class WxPayCallback:
    """
    微信支付回调通知处理

    功能:
        - 验证回调签名 (Wechatpay-Signature)
        - 解密 resource 中的加密数据 (AES-256-GCM)
    """

    def __init__(self, config: Optional[WxPayConfig] = None):
        self._config = config

    def _get_config(self) -> WxPayConfig:
        if self._config:
            return self._config
        cfg = get_config(PLATFORM_WXPAY)
        if not isinstance(cfg, WxPayConfig):
            raise TypeError(f"配置类型错误，期望 WxPayConfig，实际 {type(cfg)}")
        return cfg

    def verify_and_decrypt(
        self,
        body: bytes,
        wechatpay_signature: str,
        wechatpay_serial: str,
        wechatpay_timestamp: str,
        wechatpay_nonce: str,
    ) -> Optional[dict]:
        config = self._get_config()
        pub_key_pem = self._get_platform_cert(wechatpay_serial)
        if not pub_key_pem:
            logger.error(f"未找到平台证书: serial={wechatpay_serial}")
            return None

        body_str = body.decode("utf-8") if isinstance(body, bytes) else body
        sign_str = build_v3_response_sign_str(
            wechatpay_timestamp, wechatpay_nonce, body_str
        )

        if not rsa_verify_with_key(sign_str, wechatpay_signature, pub_key_pem):
            logger.error("微信支付回调验签失败")
            return None

        try:
            notify_data = json.loads(body_str)
        except json.JSONDecodeError:
            logger.error("回调 body 不是有效的 JSON")
            return None

        resource = notify_data.get("resource", {})
        ciphertext = resource.get("ciphertext", "")
        nonce = resource.get("nonce", "")
        associated_data = resource.get("associated_data", "")

        if not ciphertext or not config.api_v3_key:
            logger.warning("回调无加密数据或 V3 密钥未配置，返回原始数据")
            return notify_data

        plaintext = aes_gcm_decrypt(
            ciphertext, config.api_v3_key, nonce, associated_data
        )
        if plaintext is None:
            logger.error("回调 resource 解密失败")
            return None

        try:
            return json.loads(plaintext)
        except json.JSONDecodeError:
            logger.error("解密后数据不是有效的 JSON")
            return plaintext

    def _get_platform_cert(self, serial_no: str) -> Optional[bytes]:
        """获取微信平台证书公钥 (PEM 格式)"""
        cert_path = f"/certs/wechat_platform_{serial_no}.pem"
        try:
            with open(cert_path, "rb") as f:
                return f.read()
        except (FileNotFoundError, OSError):
            pass
        logger.warning(f"平台证书未缓存: serial={serial_no}，无法验签")
        return None


# ============================================================
# WxPayApi — 微信支付 API
# ============================================================

class WxPayApi:
    """微信支付 API 封装 (V3 + V2)"""

    def __init__(
        self,
        config: Optional[WxPayConfig] = None,
        http_delegate: Optional[HttpDelegate] = None,
        use_v2: bool = False,
    ):
        self._config = config
        self._http = http_delegate or HttpDelegate.default()
        self._use_v2 = use_v2

    def _get_config(self) -> WxPayConfig:
        if self._config:
            return self._config
        cfg = get_config(PLATFORM_WXPAY)
        if not isinstance(cfg, WxPayConfig):
            raise TypeError(f"配置类型错误，期望 WxPayConfig，实际 {type(cfg)}")
        return cfg

    def _get_auth(self) -> WxPayAuth:
        return WxPayAuth(self._config)

    # ===== V3 JSAPI 统一下单 =====

    async def create_jsapi_order(
        self,
        openid: str,
        out_trade_no: str,
        total_fee: int,
        description: str,
        attach: Optional[str] = None,
        time_expire: Optional[str] = None,
        goods_tag: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        config = self._get_config()
        auth = self._get_auth()

        body = {
            "appid": config.app_id,
            "mchid": config.mch_id,
            "description": description[:127],
            "out_trade_no": out_trade_no,
            "notify_url": config.notify_url,
            "amount": {"total": total_fee, "currency": "CNY"},
            "payer": {"openid": openid},
        }
        if attach:
            body["attach"] = attach[:127]
        if time_expire:
            body["time_expire"] = time_expire
        if goods_tag:
            body["goods_tag"] = goods_tag

        body_json = json.dumps(body, ensure_ascii=False)
        headers = auth.get_headers("POST", V3_JSAPI_PAY, body_json)
        headers["Content-Type"] = "application/json"

        url = f"{WECHAT_V3_BASE}{V3_JSAPI_PAY}"
        resp = await self._http.post(url, data=body_json, headers=headers)

        if resp.is_success():
            result = resp.json()
            prepay_id = result.get("prepay_id", "") if result else ""
            if prepay_id:
                payment_params = self._build_jsapi_payment_params(prepay_id)
                return {
                    "prepay_id": prepay_id,
                    "payment_params": payment_params,
                }
        else:
            logger.error(f"JSAPI 统一下单失败: status={resp.status}, body={resp.body}")
        return None

    def _build_jsapi_payment_params(self, prepay_id: str) -> Dict[str, str]:
        config = self._get_config()
        timestamp = str(int(time.time()))
        nonce = generate_nonce(32)
        package = f"prepay_id={prepay_id}"
        sign_str = f"{config.app_id}\n{timestamp}\n{nonce}\n{package}\n"
        pay_sign = rsa_sign(sign_str, config.private_key_path)
        return {
            "appId": config.app_id,
            "timeStamp": timestamp,
            "nonceStr": nonce,
            "package": package,
            "signType": "RSA",
            "paySign": pay_sign,
        }

    # ===== V3 订单查询 =====

    async def query_by_out_trade_no(self, out_trade_no: str) -> Optional[dict]:
        config = self._get_config()
        auth = self._get_auth()
        url_path = V3_ORDER_QUERY_BY_OUT_TRADE_NO % out_trade_no
        url_path_with_params = f"{url_path}?mchid={config.mch_id}"
        headers = auth.get_headers("GET", url_path_with_params)
        url = f"{WECHAT_V3_BASE}{url_path_with_params}"
        resp = await self._http.get(url, headers=headers)
        if resp.is_success():
            return resp.json()
        logger.error(f"订单查询失败: {out_trade_no}, status={resp.status}")
        return None

    async def query_by_transaction_id(self, transaction_id: str) -> Optional[dict]:
        config = self._get_config()
        auth = self._get_auth()
        url_path = V3_ORDER_QUERY_BY_TRANSACTION_ID % transaction_id
        url_path_with_params = f"{url_path}?mchid={config.mch_id}"
        headers = auth.get_headers("GET", url_path_with_params)
        url = f"{WECHAT_V3_BASE}{url_path_with_params}"
        resp = await self._http.get(url, headers=headers)
        if resp.is_success():
            return resp.json()
        logger.error(f"订单查询失败: tx={transaction_id}, status={resp.status}")
        return None

    # ===== V3 关闭订单 =====

    async def close_order(self, out_trade_no: str) -> bool:
        config = self._get_config()
        auth = self._get_auth()
        body = json.dumps({"mchid": config.mch_id})
        headers = auth.get_headers("POST", V3_CLOSE_ORDER % out_trade_no, body)
        headers["Content-Type"] = "application/json"
        url = f"{WECHAT_V3_BASE}{V3_CLOSE_ORDER % out_trade_no}"
        resp = await self._http.post(url, data=body, headers=headers)
        if resp.is_success():
            logger.info(f"订单关闭成功: {out_trade_no}")
            return True
        logger.error(f"订单关闭失败: {out_trade_no}, status={resp.status}")
        return False

    # ===== V3 退款 =====

    async def create_refund(
        self,
        out_trade_no: str,
        out_refund_no: str,
        refund_amount: int,
        total_amount: int,
        reason: Optional[str] = None,
        notify_url: Optional[str] = None,
    ) -> Optional[dict]:
        config = self._get_config()
        auth = self._get_auth()
        body = {
            "out_trade_no": out_trade_no,
            "out_refund_no": out_refund_no,
            "amount": {"refund": refund_amount, "total": total_amount, "currency": "CNY"},
        }
        if reason:
            body["reason"] = reason
        body["notify_url"] = notify_url or config.refund_notify_url or config.notify_url

        body_json = json.dumps(body, ensure_ascii=False)
        headers = auth.get_headers("POST", V3_REFUND, body_json)
        headers["Content-Type"] = "application/json"

        http = HttpDelegate.with_ssl_cert(config.cert_path, config.private_key_path)
        url = f"{WECHAT_V3_BASE}{V3_REFUND}"
        resp = await http.post(url, data=body_json, headers=headers)

        if resp.is_success():
            logger.info(f"退款申请成功: out_refund_no={out_refund_no}")
            return resp.json()
        logger.error(f"退款申请失败: status={resp.status}, body={resp.body}")
        return None

    async def query_refund(self, out_refund_no: str) -> Optional[dict]:
        auth = self._get_auth()
        url_path = V3_REFUND_QUERY % out_refund_no
        headers = auth.get_headers("GET", url_path)
        url = f"{WECHAT_V3_BASE}{url_path}"
        resp = await self._http.get(url, headers=headers)
        if resp.is_success():
            return resp.json()
        logger.error(f"退款查询失败: {out_refund_no}, status={resp.status}")
        return None

    # ===== V2 兼容接口 =====

    async def create_order_v2(
        self,
        openid: str,
        out_trade_no: str,
        total_fee: int,
        description: str,
        spbill_create_ip: str = "127.0.0.1",
    ) -> Optional[dict]:
        import xml.etree.ElementTree as ET
        config = self._get_config()
        params = {
            "appid": config.app_id,
            "mch_id": config.mch_id,
            "nonce_str": generate_nonce(32),
            "body": description[:127],
            "out_trade_no": out_trade_no,
            "total_fee": str(total_fee),
            "spbill_create_ip": spbill_create_ip,
            "notify_url": config.notify_url,
            "trade_type": "JSAPI",
            "openid": openid,
        }
        params["sign"] = build_v2_sign(params, config.api_key)

        root = ET.Element("xml")
        for k, v in params.items():
            child = ET.SubElement(root, k)
            child.text = str(v)
        xml_data = ET.tostring(root, encoding="utf-8").decode("utf-8")

        headers = {"Content-Type": "text/xml; charset=utf-8", "Accept": "text/xml"}
        resp = await self._http.post(V2_UNIFIED_ORDER, data=xml_data, headers=headers)
        try:
            root = ET.fromstring(resp.body)
            return {child.tag: child.text for child in root}
        except Exception as e:
            logger.error(f"V2 统一下单 XML 解析失败: {e}")
            return None

    @classmethod
    def from_config(cls, config: Optional[WxPayConfig] = None) -> "WxPayApi":
        return cls(config=config)

    @classmethod
    def v2_compat(cls, config: Optional[WxPayConfig] = None) -> "WxPayApi":
        return cls(config=config, use_v2=True)


__all__ = [
    "WxPayAuth",
    "WxPayCallback",
    "WxPayApi",
    "WECHAT_V3_BASE",
    "V3_JSAPI_PAY",
    "V3_ORDER_QUERY_BY_OUT_TRADE_NO",
    "V3_ORDER_QUERY_BY_TRANSACTION_ID",
    "V3_CLOSE_ORDER",
    "V3_REFUND",
    "V3_REFUND_QUERY",
    "V3_CERTIFICATES",
]
