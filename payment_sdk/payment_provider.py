"""支付抽象接口 IPaymentProvider

定义统一的支付提供者接口：pay(), refund(), query(), callback_verify()。
所有具体支付实现（微信V2/V3、支付宝等）均实现此接口。

设计原则:
    - C-PAY-003: 纯函数 + 依赖注入，不持有全局状态
    - 所有方法均为 async，支持异步调用
    - 返回结构化结果类型 PaymentResult / CallbackResult
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ============================================================
# 结构化结果类型
# ============================================================


@dataclass
class PaymentResult:
    """支付操作统一结果

    Attributes:
        success: 操作是否成功
        code: 业务码 (SUCCESS/FAIL/等)
        message: 结果描述
        data: 接口返回的原始数据
        provider_order_id: 支付平台订单号 (如微信 transaction_id)
        out_trade_no: 商户订单号
    """
    success: bool = False
    code: str = ""
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    provider_order_id: str = ""
    out_trade_no: str = ""

    @classmethod
    def ok(cls, **kwargs) -> "PaymentResult":
        """快捷创建成功结果"""
        return cls(success=True, code="SUCCESS", **kwargs)

    @classmethod
    def fail(cls, message: str = "", code: str = "FAIL", **kwargs) -> "PaymentResult":
        """快捷创建失败结果"""
        return cls(success=False, code=code, message=message, **kwargs)


@dataclass
class CallbackResult:
    """支付回调验证结果

    Attributes:
        verified: 验签是否通过
        data: 解密/解析后的回调数据
        raw: 原始回调数据
        message: 验证描述
    """
    verified: bool = False
    data: Optional[Dict[str, Any]] = None
    raw: Any = None
    message: str = ""


# ============================================================
# 支付提供者抽象接口
# ============================================================


class IPaymentProvider(ABC):
    """支付提供者抽象接口

    所有支付渠道（微信V2、微信V3、支付宝等）必须实现此接口。

    使用方式:
        provider = WxPayV3Provider(config=my_config)
        result = await provider.pay(
            openid="oabc123",
            out_trade_no="ORDER2026001",
            total_fee=100,  # 分
            description="测试商品",
        )
    """

    @abstractmethod
    async def pay(
        self,
        openid: str,
        out_trade_no: str,
        total_fee: int,
        description: str,
        **kwargs: Any,
    ) -> PaymentResult:
        """统一下单 / 支付

        Args:
            openid: 用户支付平台标识 (微信 openid / 支付宝 buyer_id)
            out_trade_no: 商户订单号
            total_fee: 订单金额 (单位: 分)
            description: 商品描述
            **kwargs: 渠道特定参数

        Returns:
            PaymentResult
        """
        ...

    @abstractmethod
    async def refund(
        self,
        out_trade_no: str,
        out_refund_no: str,
        refund_amount: int,
        total_amount: int,
        reason: Optional[str] = None,
        **kwargs: Any,
    ) -> PaymentResult:
        """退款

        Args:
            out_trade_no: 原商户订单号
            out_refund_no: 退款单号
            refund_amount: 退款金额 (分)
            total_amount: 原订单总金额 (分)
            reason: 退款原因
            **kwargs: 渠道特定参数

        Returns:
            PaymentResult
        """
        ...

    @abstractmethod
    async def query(
        self,
        out_trade_no: str,
        **kwargs: Any,
    ) -> PaymentResult:
        """订单查询

        Args:
            out_trade_no: 商户订单号
            **kwargs: 渠道特定参数 (如 transaction_id)

        Returns:
            PaymentResult
        """
        ...

    @abstractmethod
    async def callback_verify(
        self,
        body: bytes,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> CallbackResult:
        """支付回调验签

        Args:
            body: 回调请求体 (原始字节)
            headers: 回调请求头 (含签名相关头)
            **kwargs: 渠道特定参数

        Returns:
            CallbackResult
        """
        ...
