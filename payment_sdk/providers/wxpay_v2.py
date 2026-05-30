"""微信支付 V2 提供者 — IPaymentProvider 实现

从 payment/wxpay/__init__.py 提取 V2 核心逻辑 (create_order_v2, build_v2_sign 等)。
纯函数 + 依赖注入，不持有全局状态。

对应的现有代码位置:
    - WxPayApi.create_order_v2()          → WxPayV2Provider.pay()
    - build_v2_sign()                       → sign.build_v2_sign() 复用
    - WxPayApi.query_by_out_trade_no() V2版  → WxPayV2Provider.query()
    - WxPayApi.create_refund() V2版         → WxPayV2Provider.refund()
    - verify_v2_sign()                      → WxPayV2Provider.callback_verify()
"""

import json
import logging
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional

from payment_sdk.config import WxPayConfig
from payment_sdk.http_delegate import HttpDelegate, HttpResponse
from payment_sdk.payment_provider import IPaymentProvider, PaymentResult, CallbackResult
from payment_sdk.sign import (
    generate_nonce,
    build_v2_sign,
    verify_v2_sign,
)

logger = logging.getLogger(__name__)


# ============================================================
# 常量
# ============================================================

WECHAT_API_BASE = "https://api.mch.weixin.qq.com"

V2_UNIFIED_ORDER = f"{WECHAT_API_BASE}/pay/unifiedorder"
V2_ORDER_QUERY = f"{WECHAT_API_BASE}/pay/orderquery"
V2_REFUND = f"{WECHAT_API_BASE}/secapi/pay/refund"
V2_REFUND_QUERY = f"{WECHAT_API_BASE}/pay/refundquery"
V2_CLOSE_ORDER = f"{WECHAT_API_BASE}/pay/closeorder"


# ============================================================
# 工具函数
# ============================================================

def _dict_to_xml(params: Dict[str, str]) -> str:
    """将字典转换为微信 V2 XML 格式"""
    root = ET.Element("xml")
    for k, v in params.items():
        child = ET.SubElement(root, k)
        child.text = str(v)
    return ET.tostring(root, encoding="utf-8").decode("utf-8")


def _xml_to_dict(xml_str: str) -> Optional[Dict[str, str]]:
    """将微信 V2 XML 响应解析为字典"""
    try:
        root = ET.fromstring(xml_str)
        return {child.tag: child.text for child in root}
    except Exception as e:
        logger.error(f"XML 解析失败: {e}")
        return None


# ============================================================
# WxPayV2Provider — 微信支付 V2 实现
# ============================================================


class WxPayV2Provider(IPaymentProvider):
    """微信支付 V2 提供者 (XML/MD5 签名)

    基于微信支付 V2 API (统一下单、查询、退款、关闭)。
    所有操作使用 XML 格式 + MD5/HMAC-SHA256 签名。

    用法:
        provider = WxPayV2Provider(
            config=WxPayConfig.from_env(),
            http_delegate=HttpDelegate.with_ssl_cert(cert_path, key_path),
        )
        result = await provider.pay(openid="...", out_trade_no="...", total_fee=100, description="...")
    """

    def __init__(
        self,
        config: Optional[WxPayConfig] = None,
        http_delegate: Optional[HttpDelegate] = None,
    ):
        """初始化 V2 提供者

        Args:
            config: 微信支付配置。为 None 时从环境变量自动加载。
            http_delegate: HTTP 委托。为 None 时创建默认委托。
                          退款需要双向 SSL，请使用 HttpDelegate.with_ssl_cert()。
        """
        self._config = config or WxPayConfig.from_env()
        self._http = http_delegate or HttpDelegate.default()

    # ==================== IPaymentProvider 接口实现 ====================

    async def pay(
        self,
        openid: str,
        out_trade_no: str,
        total_fee: int,
        description: str,
        **kwargs: Any,
    ) -> PaymentResult:
        """微信 V2 统一下单 (JSAPI)

        Args:
            openid: 用户微信 openid
            out_trade_no: 商户订单号
            total_fee: 订单金额 (单位: 分)
            description: 商品描述 (最长 127 字符)
            **kwargs: 可选参数:
                spbill_create_ip: 客户端 IP (默认 127.0.0.1)
                trade_type: 交易类型 (默认 JSAPI)
                time_start: 交易起始时间
                time_expire: 交易过期时间

        Returns:
            PaymentResult
        """
        cfg = self._config
        spbill_create_ip = kwargs.get("spbill_create_ip", "127.0.0.1")
        trade_type = kwargs.get("trade_type", "JSAPI")

        params: Dict[str, str] = {
            "appid": cfg.app_id,
            "mch_id": cfg.mch_id,
            "nonce_str": generate_nonce(32),
            "body": description[:127],
            "out_trade_no": out_trade_no,
            "total_fee": str(total_fee),
            "spbill_create_ip": spbill_create_ip,
            "notify_url": cfg.notify_url,
            "trade_type": trade_type,
            "openid": openid,
        }

        # 可选参数
        if "time_start" in kwargs:
            params["time_start"] = kwargs["time_start"]
        if "time_expire" in kwargs:
            params["time_expire"] = kwargs["time_expire"]

        params["sign"] = build_v2_sign(params, cfg.api_key)

        xml_data = _dict_to_xml(params)
        headers = {"Content-Type": "text/xml; charset=utf-8", "Accept": "text/xml"}
        resp = await self._http.post(V2_UNIFIED_ORDER, data=xml_data, headers=headers)

        result_dict = _xml_to_dict(resp.body)
        if result_dict and result_dict.get("return_code") == "SUCCESS" and result_dict.get("result_code") == "SUCCESS":
            return PaymentResult.ok(
                data=result_dict,
                provider_order_id=result_dict.get("prepay_id", ""),
                out_trade_no=out_trade_no,
            )

        err_msg = (result_dict or {}).get("return_msg", resp.body) if result_dict else resp.body
        logger.error(f"V2 统一下单失败: {err_msg}")
        return PaymentResult.fail(message=err_msg)

    async def refund(
        self,
        out_trade_no: str,
        out_refund_no: str,
        refund_amount: int,
        total_amount: int,
        reason: Optional[str] = None,
        **kwargs: Any,
    ) -> PaymentResult:
        """微信 V2 退款

        注意: V2 退款需要双向 SSL 证书，请确保 http_delegate 已配置 with_ssl_cert()。

        Args:
            out_trade_no: 原商户订单号
            out_refund_no: 退款单号
            refund_amount: 退款金额 (分)
            total_amount: 原订单总金额 (分)
            reason: 退款原因
            **kwargs: 可选参数:
                refund_account: 退款账户 (REFUND_SOURCE_UNSETTLED_FUNDS 等)

        Returns:
            PaymentResult
        """
        cfg = self._config

        params: Dict[str, str] = {
            "appid": cfg.app_id,
            "mch_id": cfg.mch_id,
            "nonce_str": generate_nonce(32),
            "out_trade_no": out_trade_no,
            "out_refund_no": out_refund_no,
            "total_fee": str(total_amount),
            "refund_fee": str(refund_amount),
        }
        if reason:
            params["refund_desc"] = reason[:80]
        if "refund_account" in kwargs:
            params["refund_account"] = kwargs["refund_account"]
        params["notify_url"] = kwargs.get("notify_url", cfg.refund_notify_url or cfg.notify_url)

        params["sign"] = build_v2_sign(params, cfg.api_key)

        xml_data = _dict_to_xml(params)
        headers = {"Content-Type": "text/xml; charset=utf-8", "Accept": "text/xml"}

        # V2 退款需要双向 SSL
        http = self._http
        resp = await http.post(V2_REFUND, data=xml_data, headers=headers)

        result_dict = _xml_to_dict(resp.body)
        if result_dict and result_dict.get("return_code") == "SUCCESS" and result_dict.get("result_code") == "SUCCESS":
            return PaymentResult.ok(
                data=result_dict,
                provider_order_id=result_dict.get("refund_id", ""),
                out_trade_no=out_trade_no,
            )

        err_msg = (result_dict or {}).get("err_code_des", resp.body) if result_dict else resp.body
        logger.error(f"V2 退款失败: {err_msg}")
        return PaymentResult.fail(message=err_msg)

    async def query(
        self,
        out_trade_no: str,
        **kwargs: Any,
    ) -> PaymentResult:
        """微信 V2 订单查询

        Args:
            out_trade_no: 商户订单号
            **kwargs: 可选参数:
                transaction_id: 微信支付订单号 (二选一)

        Returns:
            PaymentResult
        """
        cfg = self._config

        params: Dict[str, str] = {
            "appid": cfg.app_id,
            "mch_id": cfg.mch_id,
            "nonce_str": generate_nonce(32),
        }
        if "transaction_id" in kwargs:
            params["transaction_id"] = kwargs["transaction_id"]
        else:
            params["out_trade_no"] = out_trade_no

        params["sign"] = build_v2_sign(params, cfg.api_key)

        xml_data = _dict_to_xml(params)
        headers = {"Content-Type": "text/xml; charset=utf-8", "Accept": "text/xml"}
        resp = await self._http.post(V2_ORDER_QUERY, data=xml_data, headers=headers)

        result_dict = _xml_to_dict(resp.body)
        if result_dict and result_dict.get("return_code") == "SUCCESS" and result_dict.get("result_code") == "SUCCESS":
            return PaymentResult.ok(
                data=result_dict,
                provider_order_id=result_dict.get("transaction_id", ""),
                out_trade_no=out_trade_no,
            )

        err_msg = (result_dict or {}).get("return_msg", resp.body) if result_dict else resp.body
        logger.error(f"V2 订单查询失败: {err_msg}")
        return PaymentResult.fail(message=err_msg)

    async def callback_verify(
        self,
        body: bytes,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> CallbackResult:
        """微信 V2 回调验签

        V2 回调参数通过 POST 表单传递 (XML 格式)。
        签名验证使用 MD5/HMAC-SHA256。

        Args:
            body: 回调请求体 (XML 字节)
            headers: 请求头 (V2 回调不需要特殊头)
            **kwargs: 可选参数:
                sign_type: 签名类型 (默认 MD5)

        Returns:
            CallbackResult
        """
        cfg = self._config
        sign_type = kwargs.get("sign_type", "MD5")

        body_str = body.decode("utf-8") if isinstance(body, bytes) else body
        params = _xml_to_dict(body_str)

        if params is None:
            return CallbackResult(verified=False, data=None, raw=body_str, message="XML 解析失败")

        is_valid = verify_v2_sign(params, cfg.api_key, sign_type)
        if is_valid:
            return CallbackResult(
                verified=True,
                data=params,
                raw=params,
                message="验签通过",
            )

        return CallbackResult(
            verified=False,
            data=params,
            raw=params,
            message="V2 签名验证失败",
        )

    # ==================== 附加方法 ====================

    async def close_order(self, out_trade_no: str) -> bool:
        """微信 V2 关闭订单"""
        cfg = self._config
        params = {
            "appid": cfg.app_id,
            "mch_id": cfg.mch_id,
            "out_trade_no": out_trade_no,
            "nonce_str": generate_nonce(32),
        }
        params["sign"] = build_v2_sign(params, cfg.api_key)

        xml_data = _dict_to_xml(params)
        headers = {"Content-Type": "text/xml; charset=utf-8", "Accept": "text/xml"}
        resp = await self._http.post(V2_CLOSE_ORDER, data=xml_data, headers=headers)

        result_dict = _xml_to_dict(resp.body)
        if result_dict and result_dict.get("return_code") == "SUCCESS":
            return True
        logger.error(f"V2 关闭订单失败: {out_trade_no}")
        return False

    async def query_refund(self, out_refund_no: str) -> PaymentResult:
        """微信 V2 退款查询"""
        cfg = self._config
        params = {
            "appid": cfg.app_id,
            "mch_id": cfg.mch_id,
            "out_refund_no": out_refund_no,
            "nonce_str": generate_nonce(32),
        }
        params["sign"] = build_v2_sign(params, cfg.api_key)

        xml_data = _dict_to_xml(params)
        headers = {"Content-Type": "text/xml; charset=utf-8", "Accept": "text/xml"}
        resp = await self._http.post(V2_REFUND_QUERY, data=xml_data, headers=headers)

        result_dict = _xml_to_dict(resp.body)
        if result_dict and result_dict.get("return_code") == "SUCCESS" and result_dict.get("result_code") == "SUCCESS":
            return PaymentResult.ok(
                data=result_dict,
                provider_order_id=result_dict.get("refund_id", ""),
                out_trade_no=out_refund_no,
            )

        err_msg = (result_dict or {}).get("return_msg", resp.body) if result_dict else resp.body
        logger.error(f"V2 退款查询失败: {err_msg}")
        return PaymentResult.fail(message=err_msg)

    @property
    def config(self) -> WxPayConfig:
        """获取当前配置"""
        return self._config
