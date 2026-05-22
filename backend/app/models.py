"""SQLAlchemy ORM 数据模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """用户模型"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    wechat_openid = Column(String(100), unique=True, nullable=True, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    company = Column(String(200), nullable=True)
    position = Column(String(100), nullable=True)
    role = Column(String(20), nullable=False, default="buyer")  # buyer/promoter/supplier/admin
    avatar = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    products = relationship("Product", back_populates="owner", foreign_keys="Product.owner_id")
    orders = relationship("Order", back_populates="user", foreign_keys="Order.user_id")
    promoter_orders = relationship("Order", back_populates="promoter", foreign_keys="Order.promoter_id")
    withdrawals = relationship("Withdrawal", back_populates="user")


class Product(Base):
    """产品模型"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False, default=0.0)
    earn_per_share = Column(Float, nullable=False, default=0.0)  # 推广分润/每单
    category = Column(String(100), nullable=True)
    stock = Column(Integer, nullable=False, default=0)
    images = Column(Text, nullable=True)  # JSON数组字符串（主图+轮播）
    status = Column(String(20), nullable=False, default="pending")  # pending/approved/rejected
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # === 新增真实商品字段 ===
    specs = Column(Text, nullable=True)       # JSON: 规格参数（如 {"尺寸":"10x20","重量":"0.5kg"}）
    details = Column(Text, nullable=True)      # HTML/Markdown: 富文本详情描述
    brand = Column(String(100), nullable=True) # 品牌
    sale_price = Column(Float, nullable=True)  # 建议零售价（和price组成价格区间）
    video_url = Column(String(500), nullable=True) # 产品视频
    tags = Column(String(500), nullable=True)  # 逗号分隔标签
    files = Column(Text, nullable=True)        # JSON: 关联文件资料
    is_featured = Column(Integer, default=0)   # 是否推荐 0/1
    sort_order = Column(Integer, default=0)    # 排序权重

    # 关系
    owner = relationship("User", back_populates="products", foreign_keys=[owner_id])
    orders = relationship("Order", back_populates="product")


class Order(Base):
    """订单模型"""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    total_price = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending/paid/shipped/received/refunded
    promoter_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    commission = Column(Float, nullable=False, default=0.0)

    # === 支付相关字段（IJPay 封装后统一） ===
    payment_platform = Column(String(10), nullable=True)    # 支付平台: wxpay / alipay
    wx_transaction_id = Column(String(100), nullable=True)  # 微信支付交易号 (V2 兼容)
    transaction_id = Column(String(100), nullable=True)     # 第三方支付订单号 (微信/支付宝)
    prepay_id = Column(String(100), nullable=True)          # 微信预支付ID
    payment_time = Column(DateTime, nullable=True)          # 支付完成时间
    refund_id = Column(String(100), nullable=True)          # 退款单号
    refund_time = Column(DateTime, nullable=True)           # 退款时间

    # === 兼容旧字段 ===
    pay_time = Column(DateTime, nullable=True)              # 旧字段，保留兼容

    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    user = relationship("User", back_populates="orders", foreign_keys=[user_id])
    product = relationship("Product", back_populates="orders")
    promoter = relationship("User", back_populates="promoter_orders", foreign_keys=[promoter_id])


class Contact(Base):
    """联系人模型（从导入的通讯录生成）"""
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(50), nullable=True, index=True)
    wechat_id = Column(String(100), nullable=True, index=True)
    company = Column(String(200), nullable=True)
    position = Column(String(100), nullable=True)
    email = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    tags = Column(String(500), nullable=True)
    source = Column(String(50), nullable=True, default="import")  # import / manual / wechat
    import_batch_id = Column(String(36), nullable=True, index=True)  # 导入批次UUID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    owner = relationship("User", foreign_keys=[owner_id])
    activities = relationship("Activity", back_populates="contact", cascade="all, delete-orphan")


class Activity(Base):
    """联系人活动时间线模型"""
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False, index=True)
    action_type = Column(String(50), nullable=False)  # note/call/meeting/email/wechat/order/import
    summary = Column(String(500), nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    contact = relationship("Contact", back_populates="activities")


class ImportHistory(Base):
    """导入历史记录"""
    __tablename__ = "import_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(10), nullable=False)  # csv / vcf
    total_rows = Column(Integer, nullable=False, default=0)
    imported_rows = Column(Integer, nullable=False, default=0)
    skipped_rows = Column(Integer, nullable=False, default=0)
    merged_rows = Column(Integer, nullable=False, default=0)
    duplicate_count = Column(Integer, nullable=False, default=0)
    field_mapping = Column(Text, nullable=True)  # JSON: 列名映射关系
    strategy = Column(String(20), nullable=False, default="skip")  # skip / merge / update
    status = Column(String(20), nullable=False, default="completed")  # pending / processing / completed / failed
    error_message = Column(Text, nullable=True)
    batch_id = Column(String(36), nullable=False, index=True)  # UUID批次号
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    user = relationship("User", foreign_keys=[user_id])


class Withdrawal(Base):
    """提现模型"""
    __tablename__ = "withdrawals"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending/approved/rejected
    bank_info = Column(Text, nullable=True)  # JSON字符串: 银行信息
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    user = relationship("User", back_populates="withdrawals")
