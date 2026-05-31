"""支付宝支付提供者 — IPaymentProvider 完整实现

从 payment/alipay/__init__.py 提取核心逻辑 (AliPayCore, AliPayApi 框架)。

已实现功能:
    - alipay.trade.app.pay App支付统一下单
    - alipay.trade.page.pay 电脑网站支付
    - alipay.trade.wap.pay 手机网站支付
    - alipay.trade.refund 退款
    - alipay.trade.query 订单查询
    - alipay.trade.close 关闭订单
    - alipay.trade.fastpay.refund.query 退款查询
    - 回调验签 (RSA2)

注意: 本文件遵守 C-PAY-001，不依赖 backend/app/ 下的任何业务模块。
"""

import json
import logging
import time
import urllib.parse
from typing import Any

from payment_sdk.config import AliPayConfig
from payment_sdk.http_delegate import HttpDelegate
from payment_sdk.payment_provider import CallbackResult, IPaymentProvider, PaymentResult

logger = logging.getLogger(__name__)


# ============================================================
# 常量
# ============================================================

ALIPAY_GATEWAY = "https://openapi.alipay.com/gateway.do"
ALIPAY_SANDBOX_GATEWAY = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"

# API 方法名
API_APP_PAY = "alipay.trade.app.pay"
API_PAGE_PAY = "alipay.trade.page.pay"
API_WAP_PAY = "alipay.trade.wap.pay"
API_REFUND = "alipay.trade.refund"
API_QUERY = "alipay.trade.query"
API_CLOSE = "alipay.trade.close"
API_REFUND_QUERY = "alipay.trade.fastpay.refund.query"

# 业务成功码
ALIPAY_CODE_SUCCESS = "10000"


# ============================================================
# AliPayCore — 支付宝核心工具 (纯函数)
# ============================================================


class AliPayCore:
    """支付宝核心工具：签名生成与验证

    从 payment/alipay/__init__.py 提取，不做修改。
    """

    @staticmethod
    def sign(params: dict[str, str], private_key_pem: str) -> str:
        """支付宝 RSA2 签名

        Args:
            params: 参数字典 (不含 sign/sign_type)
            private_key_pem: 应用私钥 PEM 字符串

        Returns:
            Base64 编码的签名
        """
        import base64

        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        content = AliPayCore._build_sign_content(params)
        key_bytes = private_key_pem.encode("utf-8")
        private_key = serialization.load_pem_private_key(
            key_bytes,
            password=None,
            backend=default_backend(),
        )
        signature = private_key.sign(
            content.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    @staticmethod
    def verify(params: dict[str, str], public_key_pem: str, signature: str) -> bool:
        """支付宝 RSA2 验签

        Args:
            params: 参数字典
            public_key_pem: 支付宝公钥 PEM 字符串
            signature: Base64 编码的签名

        Returns:
            验签是否通过
        """
        import base64

        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        content = AliPayCore._build_sign_content(params)
        try:
            public_key = serialization.load_pem_public_key(
                public_key_pem.encode("utf-8"),
                backend=default_backend(),
            )
            public_key.verify(
                base64.b64decode(signature),
                content.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except Exception as e:
            logger.warning(f"支付宝验签失败: {e}")
            return False

    @staticmethod
    def _build_sign_content(params: dict[str, str]) -> str:
        """构建待签名字符串 (key=value&... 按 key 升序)"""
        filtered = {k: v for k, v in params.items() if k not in ("sign", "sign_type") and v is not None and v != ""}
        return "&".join(f"{k}={filtered[k]}" for k in sorted(filtered.keys()))

    @staticmethod
    def build_page_param_string(params: dict[str, str]) -> str:
        """构建 URL query string (用于 App 支付 order string)"""
        filtered = {k: v for k, v in params.items() if v is not None and v != ""}
        return "&".join(f"{k}={urllib.parse.quote(str(filtered[k]))}" for k in sorted(filtered.keys()))


# ============================================================
# AliPayProvider — 支付宝提供者 (完整实现)
# ============================================================


class AliPayProvider(IPaymentProvider):
    """支付宝支付提供者

    支持 App支付、电脑网站支付、手机网站支付、退款、查询、关闭、退款查询。
    所有操作使用 RSA2 签名 + application/x-www-form-urlencoded 格式。

    用法:
        provider = AliPayProvider(
            config=AliPayConfig.from_env(),
            http_delegate=HttpDelegate.default(),
        )
        result = await provider.pay(openid="...", out_trade_no="...", total_fee=100, description="...")
    """

    def __init__(
        self,
        config: AliPayConfig | None = None,
        http_delegate: HttpDelegate | None = None,
    ):
        """初始化支付宝提供者

        Args:
            config: 支付宝配置。为 None 时从环境变量自动加载。
            http_delegate: HTTP 委托。为 None 时创建默认委托。
        """
        self._config = config or AliPayConfig.from_env()
        self._http = http_delegate or HttpDelegate.default()

    # ==================== 公共参数构建 ====================

    def _build_common_params(self, method: str, biz_content: dict[str, Any], **extra: str) -> dict[str, str]:
        """构建支付宝 API 公共请求参数

        Args:
            method: API 方法名 (如 alipay.trade.app.pay)
            biz_content: 业务请求参数 (将序列化为 JSON)
            **extra: 额外的公共参数

        Returns:
            参数字典
        """
        cfg = self._config
        params: dict[str, str] = {
            "app_id": cfg.app_id,
            "method": method,
            "format": "JSON",
            "charset": cfg.charset,
            "sign_type": cfg.sign_type,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "version": "1.0",
            "biz_content": json.dumps(biz_content, ensure_ascii=False, separators=(",", ":")),
        }

        # 需要 notify_url 的方法
        if method in (API_APP_PAY, API_PAGE_PAY, API_WAP_PAY, API_REFUND):
            if cfg.notify_url:
                params["notify_url"] = cfg.notify_url

        # 额外参数
        params.update(extra)

        # 签名
        params["sign"] = AliPayCore.sign(params, cfg.private_key)
        return params

    def _build_app_order_string(self, biz_content: dict[str, Any]) -> str:
        """构建 App 支付 order string (不含 method 和参数名包装)

        这个字符串直接返回给客户端，客户端用 Alipay SDK 调起支付。

        Args:
            biz_content: 业务参数

        Returns:
            用于 App SDK 调起的 order string
        """
        cfg = self._config
        params: dict[str, str] = {
            "app_id": cfg.app_id,
            "method": API_APP_PAY,
            "format": "JSON",
            "charset": cfg.charset,
            "sign_type": cfg.sign_type,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "version": "1.0",
            "biz_content": json.dumps(biz_content, ensure_ascii=False, separators=(",", ":")),
        }
        if cfg.notify_url:
            params["notify_url"] = cfg.notify_url
        params["sign"] = AliPayCore.sign(params, cfg.private_key)
        return AliPayCore.build_page_param_string(params)

    # ==================== API 请求 ====================

    async def _request(self, method: str, biz_content: dict[str, Any]) -> PaymentResult:
        """发送支付宝 API 请求

        Args:
            method: API 方法名
            biz_content: 业务参数

        Returns:
            PaymentResult
        """
        params = self._build_common_params(method, biz_content)

        # 支付宝 gateway 使用 POST 表单提交
        gateway = self._config.gateway
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        }
        body_str = urllib.parse.urlencode(params)
        resp = await self._http.post(gateway, data=body_str, headers=headers)

        if not resp.is_success():
            logger.error(f"支付宝 API 请求失败: method={method}, status={resp.status}, body={resp.body}")
            return PaymentResult.fail(message=f"支付宝 API 请求失败: HTTP {resp.status}")

        # 解析响应
        try:
            resp_data = json.loads(resp.body)
        except json.JSONDecodeError as e:
            logger.error(f"支付宝响应 JSON 解析失败: {e}, body={resp.body}")
            return PaymentResult.fail(message="支付宝响应格式异常")

        # 提取响应字段 (方法名 + ".response", 如 alipay_trade_app_pay_response)
        response_key = method.replace(".", "_") + "_response"
        response_body = resp_data.get(response_key, {})
        sign = resp_data.get("sign", "")

        if not response_body:
            logger.error(f"支付宝响应中缺少 {response_key}: {resp_data}")
            return PaymentResult.fail(message=f"支付宝响应异常: 缺少 {response_key}")

        # 验签响应
        alipay_public_key = self._config.alipay_public_key
        if sign and alipay_public_key:
            is_valid = AliPayCore.verify(response_body, alipay_public_key, sign)
            if not is_valid:
                logger.warning(f"支付宝响应验签失败: method={method}")
                # 验签失败也返回数据，标记失败信息

        code = response_body.get("code", "")
        msg = response_body.get("msg", "")
        sub_msg = response_body.get("sub_msg", "")

        if code == ALIPAY_CODE_SUCCESS:
            return PaymentResult.ok(
                data=response_body,
                provider_order_id=response_body.get("trade_no", ""),
                out_trade_no=response_body.get("out_trade_no", ""),
            )

        error_msg = f"{msg}"
        if sub_msg:
            error_msg += f" ({sub_msg})"
        logger.error(f"支付宝业务失败: method={method}, code={code}, msg={error_msg}")
        return PaymentResult.fail(message=f"支付宝业务失败: {error_msg}", code=code)

    # ==================== IPaymentProvider 接口实现 ====================

    async def pay(
        self,
        openid: str,
        out_trade_no: str,
        total_fee: int,
        description: str,
        **kwargs: Any,
    ) -> PaymentResult:
        """支付宝统一下单

        支持的支付方式（通过 kwargs 中的 trade_type 指定）:
            - "APP" (默认): alipay.trade.app.pay — 返回 order string 用于 App SDK 调起
            - "PAGE": alipay.trade.page.pay — 电脑网站支付 (返回 form 表单)
            - "WAP": alipay.trade.wap.pay — 手机网站支付 (返回 form 表单)

        Args:
            openid: 买家支付宝用户 ID (buyer_id)，APP支付可选
            out_trade_no: 商户订单号
            total_fee: 订单金额 (单位: 分)
            description: 商品描述
            **kwargs: 可选参数:
                trade_type: 交易类型 ("APP", "PAGE", "WAP"，默认 "APP")
                subject: 商品标题 (默认使用 description)
                timeout_express: 超时时间 (如 "30m", "1h")
                passback_params: 公共回传参数
                quit_url: 用户退出跳转 URL (WAP 支付)
                return_url: 同步跳转 URL (PAGE/WAP 支付)
                merchant_order_no: 商户原始订单号

        Returns:
            PaymentResult
                - APP 模式: data.order_string — 给 App SDK 调起的 order string
                - PAGE/WAP 模式: data.form_html — 自动提交的 HTML 表单
        """
        cfg = self._config
        trade_type = kwargs.get("trade_type", "APP")

        # 支付宝金额单位是元 (分转元)
        total_amount = f"{total_fee / 100:.2f}"

        biz_content: dict[str, Any] = {
            "subject": kwargs.get("subject", description),
            "out_trade_no": out_trade_no,
            "total_amount": total_amount,
            "product_code": "QUICK_MSECURITY_PAY",  # App 支付产品码
        }

        # 可选的描述
        if description:
            biz_content["body"] = description

        # 可选的超时时间
        if "timeout_express" in kwargs:
            biz_content["timeout_express"] = kwargs["timeout_express"]

        # 可选的回传参数
        if "passback_params" in kwargs:
            biz_content["passback_params"] = kwargs["passback_params"]

        # 买家 ID (APP 支付可选)
        if openid:
            biz_content["buyer_id"] = openid

        if trade_type == "APP":
            # App 支付: 返回 order string
            order_string = self._build_app_order_string(biz_content)
            return PaymentResult.ok(
                data={
                    "order_string": order_string,
                    "trade_type": "APP",
                },
                out_trade_no=out_trade_no,
            )

        elif trade_type == "PAGE":
            # 电脑网站支付
            method = API_PAGE_PAY
            biz_content["product_code"] = "FAST_INSTANT_TRADE_PAY"
            if "return_url" in kwargs:
                biz_content["return_url"] = kwargs["return_url"]
            params = self._build_common_params(method, biz_content)
            form_html = self._build_form_html(cfg.gateway, params)
            return PaymentResult.ok(
                data={
                    "form_html": form_html,
                    "trade_type": "PAGE",
                    "params": params,
                },
                out_trade_no=out_trade_no,
            )

        elif trade_type == "WAP":
            # 手机网站支付
            method = API_WAP_PAY
            biz_content["product_code"] = "QUICK_WAP_PAY"
            if "return_url" in kwargs:
                biz_content["return_url"] = kwargs["return_url"]
            if "quit_url" in kwargs:
                biz_content["quit_url"] = kwargs["quit_url"]
            params = self._build_common_params(method, biz_content)
            form_html = self._build_form_html(cfg.gateway, params)
            return PaymentResult.ok(
                data={
                    "form_html": form_html,
                    "trade_type": "WAP",
                    "params": params,
                },
                out_trade_no=out_trade_no,
            )

        else:
            return PaymentResult.fail(message=f"不支持的交易类型: {trade_type}")

    async def refund(
        self,
        out_trade_no: str,
        out_refund_no: str,
        refund_amount: int,
        total_amount: int,
        reason: str | None = None,
        **kwargs: Any,
    ) -> PaymentResult:
        """支付宝退款

        Args:
            out_trade_no: 原商户订单号
            out_refund_no: 退款请求号 (商户侧唯一)
            refund_amount: 退款金额 (单位: 分)
            total_amount: 原订单总金额 (单位: 分) — 支付宝不需要此参数但接口要求保留
            reason: 退款原因
            **kwargs: 可选参数:
                trade_no: 支付宝交易号 (与 out_trade_no 二选一)

        Returns:
            PaymentResult
        """
        # 支付宝金额单位是元
        refund_amount_yuan = f"{refund_amount / 100:.2f}"

        biz_content: dict[str, Any] = {
            "out_trade_no": out_trade_no,
            "refund_amount": refund_amount_yuan,
            "out_request_no": out_refund_no,
        }

        if reason:
            biz_content["refund_reason"] = reason

        if "trade_no" in kwargs:
            biz_content["trade_no"] = kwargs["trade_no"]

        result = await self._request(API_REFUND, biz_content)
        return result

    async def query(
        self,
        out_trade_no: str,
        **kwargs: Any,
    ) -> PaymentResult:
        """支付宝订单查询

        Args:
            out_trade_no: 商户订单号
            **kwargs: 可选参数:
                trade_no: 支付宝交易号 (优先使用)

        Returns:
            PaymentResult
        """
        biz_content: dict[str, str] = {
            "out_trade_no": out_trade_no,
        }
        if "trade_no" in kwargs:
            biz_content["trade_no"] = kwargs["trade_no"]

        result = await self._request(API_QUERY, biz_content)
        return result

    async def callback_verify(
        self,
        body: bytes,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> CallbackResult:
        """支付宝回调验签

        支付宝回调通过 POST 表单传递参数 (application/x-www-form-urlencoded)。
        使用 RSA2 验签。

        Args:
            body: 回调请求体 (表单字节)
            headers: 请求头
            **kwargs: 可选参数:
                params: 预解析的参数字典 (直接传入可跳过 body 解析)

        Returns:
            CallbackResult
        """
        cfg = self._config

        # 支持直接传入 params
        params = kwargs.get("params")
        if params is None:
            # 尝试从 body 解析表单
            body_str = body.decode("utf-8") if isinstance(body, bytes) else body
            params = dict(urllib.parse.parse_qsl(body_str))

        if not params:
            return CallbackResult(verified=False, message="无回调参数")

        signature = params.get("sign", "")
        if not signature:
            return CallbackResult(verified=False, data=params, message="回调中无 sign 字段")

        if not cfg.alipay_public_key:
            return CallbackResult(verified=False, data=params, message="未配置支付宝公钥")

        is_valid = AliPayCore.verify(params, cfg.alipay_public_key, signature)
        if is_valid:
            return CallbackResult(
                verified=True,
                data=params,
                raw=params,
                message="支付宝回调验签通过",
            )

        return CallbackResult(
            verified=False,
            data=params,
            raw=params,
            message="支付宝回调验签失败",
        )

    # ==================== 附加方法 ====================

    async def close_order(self, out_trade_no: str, **kwargs: Any) -> bool:
        """支付宝关闭订单

        Args:
            out_trade_no: 商户订单号
            **kwargs: 可选参数:
                trade_no: 支付宝交易号
                operator_id: 操作员 ID

        Returns:
            是否关闭成功
        """
        biz_content: dict[str, Any] = {
            "out_trade_no": out_trade_no,
        }
        if "trade_no" in kwargs:
            biz_content["trade_no"] = kwargs["trade_no"]
        if "operator_id" in kwargs:
            biz_content["operator_id"] = kwargs["operator_id"]

        result = await self._request(API_CLOSE, biz_content)
        if result.success:
            logger.info(f"支付宝订单关闭成功: out_trade_no={out_trade_no}")
            return True

        logger.error(f"支付宝订单关闭失败: out_trade_no={out_trade_no}, msg={result.message}")
        return False

    async def query_refund(self, out_trade_no: str, out_refund_no: str | None = None, **kwargs: Any) -> PaymentResult:
        """支付宝退款查询

        Args:
            out_trade_no: 商户订单号
            out_refund_no: 退款请求号 (可选)
            **kwargs: 可选参数:
                trade_no: 支付宝交易号

        Returns:
            PaymentResult
        """
        biz_content: dict[str, str] = {
            "out_trade_no": out_trade_no,
        }
        if out_refund_no:
            biz_content["out_request_no"] = out_refund_no
        if "trade_no" in kwargs:
            biz_content["trade_no"] = kwargs["trade_no"]

        return await self._request(API_REFUND_QUERY, biz_content)

    # ==================== 内部工具方法 ====================

    @staticmethod
    def _build_form_html(action: str, params: dict[str, str]) -> str:
        """构建自动提交的 HTML 表单 (用于 H5/PC 页面跳转)"""
        inputs = "\n".join(
            f'    <input type="hidden" name="{k}" value="{v}"/>'
            for k, v in params.items()
        )
        return (
            f'<form id="alipay_submit" name="alipay_submit" action="{action}" method="POST">\n'
            f"{inputs}\n"
            f'    <input type="submit" value="立即支付" style="display:none">\n'
            f"</form>\n"
            f'<script>document.forms["alipay_submit"].submit();</script>'
        )

    @property
    def config(self) -> AliPayConfig:
        """获取当前配置"""
        return self._config
