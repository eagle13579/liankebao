"""订阅计费数据模型 — 单文件版

支持三种计费模式:
  - monthly   : 月付
  - yearly    : 年付 (通常享折扣)
  - usage     : 用量计费 (按调用量/次数计费)

模型:
  SubscriptionPlan — 订阅方案定义
  Subscription     — 用户订阅记录
  Invoice          — 发票/账单

关联:
  SubscriptionPlan 1:N Subscription
  Subscription     1:N Invoice
"""

import datetime
import enum
import uuid

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, Enum as SAEnum, JSON,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ===================================================================
# 枚举
# ===================================================================

class PlanTier(str, enum.Enum):
    """订阅等级"""
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class BillingMode(str, enum.Enum):
    """计费模式"""
    MONTHLY = "monthly"       # 月付
    YEARLY = "yearly"         # 年付
    USAGE = "usage"           # 用量计费


class SubscriptionStatus(str, enum.Enum):
    """订阅状态"""
    ACTIVE = "active"
    CANCELED = "canceled"
    EXPIRED = "expired"
    TRIALING = "trialing"
    PAST_DUE = "past_due"       # 逾期未付款


class InvoiceStatus(str, enum.Enum):
    """发票状态"""
    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"
    CANCELED = "canceled"
    OVERDUE = "overdue"


# ===================================================================
# SubscriptionPlan — 订阅方案
# ===================================================================

class SubscriptionPlan(Base):
    """订阅方案定义"""
    __tablename__ = "subscription_plans"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    tier = Column(SAEnum(PlanTier), nullable=False, unique=True, comment="方案等级")
    name = Column(String(100), nullable=False, comment="方案名称")
    description = Column(Text, default="", comment="方案描述")

    # 计费模式: monthly / yearly / usage
    billing_mode = Column(
        SAEnum(BillingMode), nullable=False, default=BillingMode.MONTHLY,
        comment="计费模式: monthly(月付)/yearly(年付)/usage(用量计费)",
    )

    # ── 月付 / 年付价格 ──────────────────────────────────────────
    price_monthly = Column(Float, default=0.0, comment="月付价格(元)")
    price_yearly = Column(Float, default=0.0, comment="年付价格(元)")

    # ── 用量计费相关 ─────────────────────────────────────────────
    usage_unit_price = Column(Float, default=0.0, comment="用量单价(元/单位)")
    usage_unit = Column(String(50), default="次", comment="用量单位: 次/条/MB等")
    usage_included = Column(Integer, default=0, comment="每月包含免费用量(单位)")
    overage_unit_price = Column(Float, default=0.0, comment="超额单价(元/单位)")

    # ── 功能限制 ─────────────────────────────────────────────────
    match_limit = Column(Integer, default=10, comment="每月匹配次数上限")
    ai_analysis = Column(Boolean, default=False, comment="是否支持AI分析")
    priority_support = Column(Boolean, default=False, comment="是否优先支持")
    custom_branding = Column(Boolean, default=False, comment="是否自定义品牌")
    api_access = Column(Boolean, default=False, comment="是否API访问")
    max_team_members = Column(Integer, default=1, comment="最大团队人数")

    # ── 元数据 ───────────────────────────────────────────────────
    is_active = Column(Boolean, default=True, comment="是否启用")
    sort_order = Column(Integer, default=0, comment="排序权重")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, comment="创建时间")
    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow, comment="更新时间",
    )

    # 关系
    subscriptions = relationship("Subscription", back_populates="plan", lazy="dynamic")

    def __repr__(self):
        return f"<SubscriptionPlan(id={self.id}, tier={self.tier}, name={self.name})>"

    def to_dict(self, include_subscriptions: bool = False) -> dict:
        """转为字典"""
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        if include_subscriptions and self.subscriptions:
            d["subscriptions"] = [s.to_dict() for s in self.subscriptions]
        return d

    def get_price(self, billing_cycle: str) -> float:
        """获取指定计费周期的价格"""
        if billing_cycle == BillingMode.YEARLY.value:
            return self.price_yearly
        elif billing_cycle == BillingMode.USAGE.value:
            return self.usage_unit_price
        return self.price_monthly


# ===================================================================
# Subscription — 用户订阅
# ===================================================================

class Subscription(Base):
    """用户订阅记录"""
    __tablename__ = "subscriptions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="用户ID")
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False, comment="方案ID")

    status = Column(
        SAEnum(SubscriptionStatus), default=SubscriptionStatus.TRIALING,
        comment="订阅状态: active/canceled/expired/trialing/past_due",
    )

    # 计费模式 (冗余自 plan, 便于独立查询)
    billing_mode = Column(
        SAEnum(BillingMode), nullable=False, default=BillingMode.MONTHLY,
        comment="计费模式: monthly/yearly/usage",
    )

    # ── 周期 ─────────────────────────────────────────────────────
    current_period_start = Column(DateTime, default=datetime.datetime.utcnow, comment="当前周期开始")
    current_period_end = Column(DateTime, nullable=True, comment="当前周期结束")
    trial_end = Column(DateTime, nullable=True, comment="试用结束时间")
    canceled_at = Column(DateTime, nullable=True, comment="取消时间")

    # ── 用量计费 (usage 模式) ─────────────────────────────────────
    usage_consumed = Column(Integer, default=0, comment="当前周期已用量")
    usage_included = Column(Integer, default=0, comment="当前周期免费额度")
    usage_overage = Column(Integer, default=0, comment="当前周期超额用量")

    # ── 支付 ─────────────────────────────────────────────────────
    payment_provider = Column(String(50), default="alipay", comment="支付渠道: alipay/wxpay")
    payment_id = Column(String(255), nullable=True, comment="支付流水号")
    auto_renew = Column(Boolean, default=True, comment="自动续费")
    extra = Column(JSON, nullable=True, default=dict, comment="附加数据")

    # ── 时间戳 ───────────────────────────────────────────────────
    created_at = Column(DateTime, default=datetime.datetime.utcnow, comment="创建时间")
    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow, comment="更新时间",
    )

    # 关系
    plan = relationship("SubscriptionPlan", back_populates="subscriptions", lazy="joined")
    user = relationship("User", lazy="joined")
    invoices = relationship("Invoice", back_populates="subscription", lazy="dynamic")

    def __repr__(self):
        return (
            f"<Subscription(id={self.id}, user_id={self.user_id}, "
            f"plan_id={self.plan_id}, status={self.status})>"
        )

    def to_dict(self) -> dict:
        """转为字典"""
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        if self.plan:
            d["plan"] = self.plan.to_dict()
        # 移除 SQLAlchemy relationship 对象，避免序列化错误
        for rel in ("plan", "user", "invoices"):
            d.pop(rel, None)
        # 确保日期可以序列化
        for date_field in (
            "current_period_start", "current_period_end",
            "trial_end", "canceled_at", "created_at", "updated_at",
        ):
            val = d.get(date_field)
            if isinstance(val, datetime.datetime):
                d[date_field] = val.isoformat()
        return d

    def is_active(self) -> bool:
        """订阅是否有效"""
        return self.status in (
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIALING,
        )

    def consume_usage(self, units: int = 1) -> int:
        """记录用量消耗，返回超额的用量数"""
        self.usage_consumed = (self.usage_consumed or 0) + units
        included = self.usage_included or 0
        overage = max(0, self.usage_consumed - included)
        self.usage_overage = overage
        return overage


# ===================================================================
# Invoice — 发票/账单
# ===================================================================

def generate_invoice_no(user_id: int) -> str:
    """生成唯一发票号: INV + 日期(8位) + UUID短码(8位)"""
    date_part = datetime.datetime.utcnow().strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:8].upper()
    return f"INV{date_part}{short_uuid}"


class Invoice(Base):
    """发票 / 账单记录"""
    __tablename__ = "invoices"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_no = Column(
        String(50), unique=True, nullable=False, index=True, comment="发票号",
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="用户ID")
    subscription_id = Column(
        Integer, ForeignKey("subscriptions.id"), nullable=True, comment="关联订阅ID",
    )

    # ── 金额 ─────────────────────────────────────────────────────
    amount = Column(Float, nullable=False, comment="净金额(元)")
    tax = Column(Float, default=0.0, comment="税额(元)")
    total = Column(Float, nullable=False, comment="合计金额(元)")
    currency = Column(String(8), default="CNY", comment="币种")

    # ── 状态与类型 ───────────────────────────────────────────────
    status = Column(
        SAEnum(InvoiceStatus), default=InvoiceStatus.PENDING,
        comment="发票状态: pending/paid/refunded/canceled/overdue",
    )
    billing_type = Column(
        String(20), default="subscription",
        comment="账单类型: subscription(订阅)/one_time(一次性)/refund(退款)/usage(用量)",
    )
    billing_cycle = Column(
        String(20), default="monthly",
        comment="计费周期: monthly/yearly/usage",
    )

    # ── 支付信息 ─────────────────────────────────────────────────
    payment_method = Column(String(50), default="alipay", comment="支付方式")
    payment_id = Column(String(255), nullable=True, comment="支付流水号(渠道侧)")
    extra = Column(JSON, nullable=True, default=dict, comment="附加数据(含支付回调原始数据)")

    # ── 描述 ─────────────────────────────────────────────────────
    description = Column(Text, default="", comment="发票描述")
    line_items = Column(JSON, nullable=True, default=list, comment="明细条目")

    # ── 时间戳 ───────────────────────────────────────────────────
    issued_at = Column(DateTime, default=datetime.datetime.utcnow, comment="开票时间")
    paid_at = Column(DateTime, nullable=True, comment="支付时间")
    due_at = Column(DateTime, nullable=True, comment="截止付款时间")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, comment="创建时间")
    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow, comment="更新时间",
    )

    # 关系
    subscription = relationship("Subscription", back_populates="invoices", lazy="joined")

    def __repr__(self):
        return (
            f"<Invoice(id={self.id}, invoice_no={self.invoice_no}, "
            f"user_id={self.user_id}, total={self.total}, status={self.status})>"
        )

    def to_dict(self) -> dict:
        """转为字典"""
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        d.pop("subscription", None)
        # 序列化日期字段
        for date_field in (
            "issued_at", "paid_at", "due_at", "created_at", "updated_at",
        ):
            val = d.get(date_field)
            if isinstance(val, datetime.datetime):
                d[date_field] = val.isoformat()
        return d

    def mark_paid(self, payment_id: str, paid_at: datetime.datetime = None) -> None:
        """标记为已支付"""
        self.status = InvoiceStatus.PAID
        self.payment_id = payment_id
        self.paid_at = paid_at or datetime.datetime.utcnow()

    def mark_refunded(self) -> None:
        """标记为已退款"""
        self.status = InvoiceStatus.REFUNDED
