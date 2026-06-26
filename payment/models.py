"""链客宝 — 支付订单数据模型
================================
支付系统核心 ORM 模型，基于 SQLAlchemy + SQLite。

模型：
  PaymentOrder — 订单表，记录每笔支付订单的完整生命周期

订单状态流转:
  pending → paid (支付成功)
  pending → closed (用户取消/超时关闭)
  paid    → refunded (退款)
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, func, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ===================================================================
# 数据库引擎 & 会话 (独立 SQLite 文件)
# ===================================================================
SQLALCHEMY_DATABASE_URL = "sqlite:///./payment.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ===================================================================
# PaymentOrder — 支付订单 ORM 模型
# ===================================================================
# 映射表: payment_orders
#
# 字段说明:
#   id               - 自增主键
#   order_no         - 业务订单号（唯一），生成规则: PAY + yyyyMMdd + 8位UUID短码
#   user_id          - 用户标识（微信 openid / 系统 userid）
#   amount           - 订单金额，单位：分（避免浮点数精度问题）
#   currency         - 币种，默认 CNY
#   status           - 订单状态: pending / paid / closed / refunded
#   channel          - 支付渠道: wechat / alipay / balance
#   channel_order_no - 渠道侧订单号（支付成功后回填）
#   subject          - 订单标题（如"会员充值"）
#   body             - 订单描述（详细说明）
#   notify_url       - 异步通知回调地址
#   return_url       - 同步跳转地址（支付完成后前端跳转）
#   extra            - 附加数据（JSON 格式，透传）
#   paid_at          - 支付完成时间
#   closed_at        - 订单关闭时间
#   created_at       - 创建时间
#   updated_at       - 最后更新时间
# ===================================================================


def generate_order_no() -> str:
    """生成唯一订单号: PAY + 日期(8位) + UUID短码(8位)"""
    date_part = datetime.utcnow().strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:8].upper()
    return f"PAY{date_part}{short_uuid}"


class PaymentOrder(Base):
    """支付订单记录"""
    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_no = Column(
        String(32), unique=True, nullable=False, index=True,
        comment="业务订单号",
    )
    user_id = Column(String(64), nullable=False, index=True, comment="用户标识")
    amount = Column(Integer, nullable=False, comment="订单金额(分)")
    currency = Column(String(8), nullable=False, default="CNY", comment="币种")
    status = Column(
        String(16), nullable=False, default="pending", index=True,
        comment="订单状态: pending/paid/closed/refunded",
    )
    channel = Column(
        String(16), nullable=True, default="wechat",
        comment="支付渠道: wechat/alipay/balance",
    )
    channel_order_no = Column(
        String(128), nullable=True, comment="渠道订单号",
    )
    subject = Column(String(128), nullable=False, comment="订单标题")
    body = Column(Text, nullable=True, comment="订单描述")
    notify_url = Column(String(256), nullable=True, comment="异步通知地址")
    return_url = Column(String(256), nullable=True, comment="同步跳转地址")
    extra = Column(JSON, nullable=True, default=dict, comment="附加数据")
    paid_at = Column(DateTime, nullable=True, comment="支付完成时间")
    closed_at = Column(DateTime, nullable=True, comment="订单关闭时间")
    created_at = Column(
        DateTime, default=func.now(), nullable=False, comment="创建时间",
    )
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False,
        comment="最后更新时间",
    )

    def __repr__(self) -> str:
        return (
            f"<PaymentOrder(id={self.id}, order_no={self.order_no}, "
            f"user={self.user_id}, amount={self.amount}, "
            f"status={self.status})>"
        )

    def to_dict(self) -> dict:
        """转为可序列化字典"""
        return {
            "id": self.id,
            "order_no": self.order_no,
            "user_id": self.user_id,
            "amount": self.amount,
            "currency": self.currency,
            "status": self.status,
            "channel": self.channel,
            "channel_order_no": self.channel_order_no,
            "subject": self.subject,
            "body": self.body,
            "notify_url": self.notify_url,
            "return_url": self.return_url,
            "extra": self.extra if isinstance(self.extra, dict) else {},
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ===================================================================
# 初始化
# ===================================================================


def init_db():
    """创建所有表（若无）"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI 依赖注入 — 获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
