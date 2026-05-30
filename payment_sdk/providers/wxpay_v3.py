"""微信支付 V3 提供者 — IPaymentProvider 实现

从 payment/wxpay/__init__.py 提取 V3 核心逻辑 (WxPayApi, WxPayAuth, WxPayCallback)。
纯函数 + 依赖注入，不持有全局状态。

对应的现有代码位置:
    - WxPayApi.create_jsapi_order()      → WxPayV3Provider.pay()
    - WxPayApi.create_refund()           → WxPayV3Provider.refund()
    - WxPayApi.query_by_out_trade_no()   → WxPayV3Provider.query()
    - WxPayCallback.verify_and_decrypt() → WxPayV3Provider.callback_verify()
"""

import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

from payment_sdk.config import WxPayConfig
from payment_sdk.http_delegate import HttpDelegate, HttpResponse
from payment_sdk.payment_provider import IPaymentProvider, PaymentResult, CallbackResult
from payment_sdk.sign import (
    generate_nonce,
    build_v3_sign_str,
    build_v3_response_sign_str,
    rsa_sign,
    rsa_verify_with_key,
    aes_gcm_decrypt,
)

logger = logging.getLogger(__name__)


# ============================================================
# 常量
# ============================================================

WECHAT_V3_BASE = "https://api.mch.weixin.qq.com/v3"

V3_JSAPI_PAY = "/v3/pay/transactions/jsapi"
V3_ORDER_QUERY_BY_OUT_TRADE_NO = "/v3/pay/transactions/out-trade-no/%s"
V3_ORDER_QUERY_BY_TRANSACTION_ID = "/v3/pay/transactions/id/%s"
V3_CLOSE_ORDER = "/v3/pay/transactions/out-trade-no/%s/close"
V3_REFUND = "/v3/refund/domestic/refunds"
V3_REFUND_QUERY = "/v3/refund/domestic/refunds/%s"


# ============================================================
# WxPayV3Provider — 微信支付 V3 实现
# ============================================================


class WxPayV3Provider(IPaymentProvider):
    """微信支付 V3 提供者 (JSON/RSA 签名)

    基于微信支付 V3 API (JSAPI 统一下单、查询、退款、关闭)。
    所有操作使用 JSON 格式 + RSA-SHA256 签名 (WECHATPAY2-SHA256-RSA2048)。

    用法:
        provider = WxPayV3Provider(
            config=WxPayConfig.from_env(),
            http_delegate=HttpDelegate.default(),
        )
        result = await provider.pay(openid="...", out_trade_no="...", total_fee=100, description="...")
    """

    def __init__(
        self,
        config: Optional[WxPayConfig] = None,
        http_delegate: Optional[HttpDelegate] = None,
    ):
        """初始化 V3 提供者

        Args:
            config: 微信支付配置。为 None 时从环境变量自动加载。
            http_delegate: HTTP 委托。为 None 时创建默认委托。
        """
        self._config = config or WxPayConfig.from_env()
        self._http = http_delegate or HttpDelegate.default()

    # ==================== 鉴权头生成 ====================

    def _get_auth_headers(self, method: str, url_path: str, body: str = "") -> Dict[str, str]:
        """生成微信 V3 API 鉴权头

        Authorization: WECHATPAY2-SHA256-RSA2048 mchid="...",nonce_str="...",...
        """
        cfg = self._config
        timestamp = str(int(time.time()))
        nonce = generate_nonce(32)
        sign_str = build_v3_sign_str(method, url_path, timestamp, nonce, body)
        signature = rsa_sign(sign_str, cfg.private_key_path)

        auth = (
            f'WECHATPAY2-SHA256-RSA2048 '
            f'mchid="{cfg.mch_id}",'
            f'nonce_str="{nonce}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{cfg.cert_serial_no}",'
            f'signature="{signature}"'
        )
        return {
            "Authorization": auth,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "liankebao-payment/1.0",
        }

    # ==================== IPaymentProvider 接口实现 ====================

    async def pay(
        self,
        openid: str,
        out_trade_no: str,
        total_fee: int,
        description: str,
        **kwargs: Any,
    ) -> PaymentResult:
        """微信 V3 JSAPI 统一下单

        Args:
            openid: 用户微信 openid
            out_trade_no: 商户订单号
            total_fee: 订单金额 (单位: 分)
            description: 商品描述 (最长 127 字符)
            **kwargs: 可选参数:
                attach: 附加数据 (最长 127 字符)
                time_expire: 订单过期时间 (RFC 3339 格式)
                goods_tag: 商品标记

        Returns:
            PaymentResult
        """
        cfg = self._config

        body = {
            "appid": cfg.app_id,
            "mchid": cfg.mch_id,
            "description": description[:127],
            "out_trade_no": out_trade_no,
            "notify_url": cfg.notify_url,
            "amount": {"total": total_fee, "currency": "CNY"},
            "payer": {"openid": openid},
        }

        if "attach" in kwargs:
            body["attach"] = kwargs["attach"][:127]
        if "time_expire" in kwargs:
            body["time_expire"] = kwargs["time_expire"]
        if "goods_tag" in kwargs:
            body["goods_tag"] = kwargs["goods_tag"]

        body_json = json.dumps(body, ensure_ascii=False)
        headers = self._get_auth_headers("POST", V3_JSAPI_PAY, body_json)
        headers["Content-Type"] = "application/json"

        url = f"{WECHAT_V3_BASE}{V3_JSAPI_PAY}"
        resp = await self._http.post(url, data=body_json, headers=headers)

        if resp.is_success():
            result = resp.json()
            prepay_id = result.get("prepay_id", "") if result else ""
            if prepay_id:
                payment_params = self._build_jsapi_payment_params(prepay_id)
                return PaymentResult.ok(
                    data={
                        "prepay_id": prepay_id,
                        "payment_params": payment_params,
                    },
                    provider_order_id=prepay_id,
                    out_trade_no=out_trade_no,
                )

        logger.error(f"V3 JSAPI 统一下单失败: status={resp.status}, body={resp.body}")
        return PaymentResult.fail(message=f"统一下单失败: HTTP {resp.status}")

    async def refund(
        self,
        out_trade_no: str,
        out_refund_no: str,
        refund_amount: int,
        total_amount: int,
        reason: Optional[str] = None,
        **kwargs: Any,
    ) -> PaymentResult:
        """微信 V3 退款

        Args:
            out_trade_no: 原商户订单号
            out_refund_no: 退款单号
            refund_amount: 退款金额 (分)
            total_amount: 原订单总金额 (分)
            reason: 退款原因
            **kwargs: 可选参数:
                notify_url: 退款结果通知 URL

        Returns:
            PaymentResult
        """
        cfg = self._config

        body = {
            "out_trade_no": out_trade_no,
            "out_refund_no": out_refund_no,
            "amount": {"refund": refund_amount, "total": total_amount, "currency": "CNY"},
        }
        if reason:
            body["reason"] = reason
        body["notify_url"] = kwargs.get("notify_url", cfg.refund_notify_url or cfg.notify_url)

        body_json = json.dumps(body, ensure_ascii=False)
        headers = self._get_auth_headers("POST", V3_REFUND, body_json)
        headers["Content-Type"] = "application/json"

        # V3 退款需要双向 SSL (使用商户证书)
        http = HttpDelegate.with_ssl_cert(cfg.cert_path, cfg.private_key_path)
        url = f"{WECHAT_V3_BASE}{V3_REFUND}"
        resp = await http.post(url, data=body_json, headers=headers)

        if resp.is_success():
            result = resp.json()
            logger.info(f"V3 退款申请成功: out_refund_no={out_refund_no}")
            return PaymentResult.ok(
                data=result,
                provider_order_id=result.get("refund_id", ""),
                out_trade_no=out_trade_no,
            )

        logger.error(f"V3 退款申请失败: status={resp.status}, body={resp.body}")
        return PaymentResult.fail(message=f"退款失败: HTTP {resp.status}")

    async def query(
        self,
        out_trade_no: str,
        **kwargs: Any,
    ) -> PaymentResult:
        """微信 V3 订单查询

        Args:
            out_trade_no: 商户订单号
            **kwargs: 可选参数:
                transaction_id: 微信支付订单号 (优先使用)

        Returns:
            PaymentResult
        """
        cfg = self._config

        if "transaction_id" in kwargs:
            url_path = V3_ORDER_QUERY_BY_TRANSACTION_ID % kwargs["transaction_id"]
        else:
            url_path = V3_ORDER_QUERY_BY_OUT_TRADE_NO % out_trade_no
            url_path = f"{url_path}?mchid={cfg.mch_id}"

        headers = self._get_auth_headers("GET", url_path)
        url = f"{WECHAT_V3_BASE}{url_path}"
        resp = await self._http.get(url, headers=headers)

        if resp.is_success():
            result = resp.json()
            return PaymentResult.ok(
                data=result,
                provider_order_id=(result or {}).get("transaction_id", ""),
                out_trade_no=out_trade_no,
            )

        logger.error(f"V3 订单查询失败: {out_trade_no}, status={resp.status}")
        return PaymentResult.fail(message=f"订单查询失败: HTTP {resp.status}")

    async def callback_verify(
        self,
        body: bytes,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> CallbackResult:
        """微信 V3 回调验签

        V3 回调包含:
            - Wechatpay-Signature: Base64 签名
            - Wechatpay-Serial: 平台证书序列号
            - Wechatpay-Timestamp: 时间戳
            - Wechatpay-Nonce: 随机串
            - body: 回调 JSON (含 encrypted resource)

        Args:
            body: 回调请求体 (原始字节)
            headers: 请求头 (含 Wechatpay-* 签名相关头)
            **kwargs: 可选参数:
                platform_cert_map: {serial_no: pem_bytes} 平台证书映射
                decrypt: 是否解密 resource (默认 True)

        Returns:
            CallbackResult
        """
        cfg = self._config
        hdrs = headers or {}

        wechatpay_signature = hdrs.get("Wechatpay-Signature", "")
        wechatpay_serial = hdrs.get("Wechatpay-Serial", "")
        wechatpay_timestamp = hdrs.get("Wechatpay-Timestamp", "")
        wechatpay_nonce = hdrs.get("Wechatpay-Nonce", "")

        if not wechatpay_signature or not wechatpay_serial:
            return CallbackResult(verified=False, message="缺少 Wechatpay 签名头")

        # 获取平台证书
        platform_cert_map = kwargs.get("platform_cert_map", {})
        pub_key_pem = platform_cert_map.get(wechatpay_serial)
        if not pub_key_pem:
            # 尝试从本地文件加载
            pub_key_pem = self._load_platform_cert(wechatpay_serial)
        if not pub_key_pem:
            return CallbackResult(
                verified=False,
                message=f"未找到平台证书: serial={wechatpay_serial}",
            )

        body_str = body.decode("utf-8") if isinstance(body, bytes) else body
        sign_str = build_v3_response_sign_str(
            wechatpay_timestamp, wechatpay_nonce, body_str
        )

        if not rsa_verify_with_key(sign_str, wechatpay_signature, pub_key_pem):
            return CallbackResult(verified=False, raw=body_str, message="签名验证失败")

        # 解析 body JSON
        try:
            notify_data = json.loads(body_str)
        except json.JSONDecodeError:
            return CallbackResult(verified=False, raw=body_str, message="body 不是有效 JSON")

        # 解密 resource (默认解密)
        decrypt = kwargs.get("decrypt", True)
        if decrypt:
            resource = notify_data.get("resource", {})
            ciphertext = resource.get("ciphertext", "")
            nonce = resource.get("nonce", "")
            associated_data = resource.get("associated_data", "")

            if ciphertext and cfg.api_v3_key:
                plaintext = aes_gcm_decrypt(
                    ciphertext, cfg.api_v3_key, nonce, associated_data
                )
                if plaintext is None:
                    return CallbackResult(
                        verified=True,
                        data=notify_data,
                        raw=body_str,
                        message="签名通过但 resource 解密失败",
                    )
                try:
                    decrypted_data = json.loads(plaintext)
                except json.JSONDecodeError:
                    decrypted_data = plaintext

                return CallbackResult(
                    verified=True,
                    data=decrypted_data,
                    raw=notify_data,
                    message="验签通过",
                )

        return CallbackResult(
            verified=True,
            data=notify_data,
            raw=notify_data,
            message="验签通过 (未解密)",
        )

    # ==================== 内部方法 ====================

    def _build_jsapi_payment_params(self, prepay_id: str) -> Dict[str, str]:
        """构建 JSAPI 调起支付参数"""
        cfg = self._config
        timestamp = str(int(time.time()))
        nonce = generate_nonce(32)
        package = f"prepay_id={prepay_id}"
        sign_str = f"{cfg.app_id}\n{timestamp}\n{nonce}\n{package}\n"
        pay_sign = rsa_sign(sign_str, cfg.private_key_path)
        return {
            "appId": cfg.app_id,
            "timeStamp": timestamp,
            "nonceStr": nonce,
            "package": package,
            "signType": "RSA",
            "paySign": pay_sign,
        }

    def _load_platform_cert(self, serial_no: str) -> Optional[bytes]:
        """尝试从本地缓存加载微信平台证书"""
        cert_path = f"/certs/wechat_platform_{serial_no}.pem"
        try:
            with open(cert_path, "rb") as f:
                return f.read()
        except (FileNotFoundError, OSError):
            pass
        return None

    # ==================== 附加方法 ====================

    async def close_order(self, out_trade_no: str) -> bool:
        """微信 V3 关闭订单"""
        cfg = self._config
        body = json.dumps({"mchid": cfg.mch_id})
        headers = self._get_auth_headers("POST", V3_CLOSE_ORDER % out_trade_no, body)
        headers["Content-Type"] = "application/json"
        url = f"{WECHAT_V3_BASE}{V3_CLOSE_ORDER % out_trade_no}"
        resp = await self._http.post(url, data=body, headers=headers)
        if resp.is_success():
            logger.info(f"V3 订单关闭成功: {out_trade_no}")
            return True
        logger.error(f"V3 订单关闭失败: {out_trade_no}, status={resp.status}")
        return False

    async def query_refund(self, out_refund_no: str) -> PaymentResult:
        """微信 V3 退款查询"""
        url_path = V3_REFUND_QUERY % out_refund_no
        headers = self._get_auth_headers("GET", url_path)
        url = f"{WECHAT_V3_BASE}{url_path}"
        resp = await self._http.get(url, headers=headers)
        if resp.is_success():
            result = resp.json()
            return PaymentResult.ok(
                data=result,
                provider_order_id=(result or {}).get("refund_id", ""),
                out_trade_no=out_refund_no,
            )
        logger.error(f"V3 退款查询失败: {out_refund_no}, status={resp.status}")
        return PaymentResult.fail(message=f"退款查询失败: HTTP {resp.status}")

    @property
    def config(self) -> WxPayConfig:
        """获取当前配置"""
        return self._config
