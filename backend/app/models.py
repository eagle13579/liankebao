"""SQLAlchemy ORM 数据模型"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import DB_TYPE, Base

# ============================================================
# 多租户判断：PostgreSQL 模式下强制启用 organization_id
# ============================================================
_IS_MULTI_TENANT = DB_TYPE == "postgres"


def _org_fk():
    """返回 organization_id 外键定义（仅多租户模式启用）"""
    if not _IS_MULTI_TENANT:
        return Column(Integer, nullable=True, default=None)
    return Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)


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
    onboarding_pain_point = Column(
        String(50), nullable=True, comment="用户核心痛点标签: low_acquisition_cost / lack_trust / distribution_pain"
    )
    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)
    # 轻量会员字段
    membership_tier = Column(String(20), nullable=False, default="free", comment="会员等级: free/gold/diamond")
    membership_expires_at = Column(DateTime, nullable=True, comment="会员过期时间")
    match_credits = Column(Integer, nullable=False, default=3, comment="剩余对接券数")
    brochure_id = Column(String(64), nullable=True, comment="关联电子画册ID")

    # 密码重置
    password_reset_token = Column(String(255), nullable=True, index=True, comment="密码重置令牌")
    password_reset_expires = Column(DateTime, nullable=True, comment="密码重置令牌过期时间")

    # 多租户
    organization_id = _org_fk()

    # 会员字段
    membership_tier = Column(String(20), nullable=False, default="free", comment="会员等级: free/gold/diamond/board")
    membership_expires_at = Column(DateTime, nullable=True, comment="会员过期时间")
    match_credits = Column(Integer, nullable=False, default=3, comment="对接券数量")

    # 关系（仅多租户模式启用 ForeignKey 关系）
    if _IS_MULTI_TENANT:
        organization = relationship("Organization", back_populates="users", foreign_keys=[organization_id])
        memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")
    else:
        memberships = relationship(
            "OrganizationMember",
            back_populates="user",
            primaryjoin="User.id==OrganizationMember.user_id",
            foreign_keys="OrganizationMember.user_id",
            cascade="all, delete-orphan",
        )
    products = relationship("Product", back_populates="owner", foreign_keys="Product.owner_id")
    orders = relationship("Order", back_populates="user", foreign_keys="Order.user_id")
    promoter_orders = relationship("Order", back_populates="promoter", foreign_keys="Order.promoter_id")
    withdrawals = relationship("Withdrawal", back_populates="user")
    membership_orders = relationship("MembershipOrder", back_populates="user", cascade="all, delete-orphan")
    match_credit_logs = relationship("MatchCreditLog", back_populates="user", cascade="all, delete-orphan")


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
    specs = Column(Text, nullable=True)  # JSON: 规格参数（如 {"尺寸":"10x20","重量":"0.5kg"}）
    details = Column(Text, nullable=True)  # HTML/Markdown: 富文本详情描述
    brand = Column(String(100), nullable=True)  # 品牌
    sale_price = Column(Float, nullable=True)  # 建议零售价（和price组成价格区间）
    video_url = Column(String(500), nullable=True)  # 产品视频
    tags = Column(String(500), nullable=True)  # 逗号分隔标签
    files = Column(Text, nullable=True)  # JSON: 关联文件资料
    is_featured = Column(Integer, default=0)  # 是否推荐 0/1
    sort_order = Column(Integer, default=0)  # 排序权重
    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    deleted_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)
    # 轻量会员字段
    membership_tier = Column(String(20), nullable=False, default="free", comment="会员等级: free/gold/diamond")
    membership_expires_at = Column(DateTime, nullable=True, comment="会员过期时间")
    match_credits = Column(Integer, nullable=False, default=3, comment="剩余对接券数")
    brochure_id = Column(String(64), nullable=True, comment="关联电子画册ID")

    # 多租户
    organization_id = _org_fk()

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
    payment_platform = Column(String(10), nullable=True)  # 支付平台: wxpay / alipay
    wx_transaction_id = Column(String(100), nullable=True)  # 微信支付交易号 (V2 兼容)
    transaction_id = Column(String(100), nullable=True)  # 第三方支付订单号 (微信/支付宝)
    prepay_id = Column(String(100), nullable=True)  # 微信预支付ID
    payment_time = Column(DateTime, nullable=True)  # 支付完成时间
    refund_id = Column(String(100), nullable=True)  # 退款单号
    refund_time = Column(DateTime, nullable=True)  # 退款时间

    # === 兼容旧字段 ===
    pay_time = Column(DateTime, nullable=True)  # 旧字段，保留兼容

    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)
    # 轻量会员字段
    membership_tier = Column(String(20), nullable=False, default="free", comment="会员等级: free/gold/diamond")
    membership_expires_at = Column(DateTime, nullable=True, comment="会员过期时间")
    match_credits = Column(Integer, nullable=False, default=3, comment="剩余对接券数")
    brochure_id = Column(String(64), nullable=True, comment="关联电子画册ID")

    # 多租户
    organization_id = _org_fk()

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
    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)
    # 轻量会员字段
    membership_tier = Column(String(20), nullable=False, default="free", comment="会员等级: free/gold/diamond")
    membership_expires_at = Column(DateTime, nullable=True, comment="会员过期时间")
    match_credits = Column(Integer, nullable=False, default=3, comment="剩余对接券数")
    brochure_id = Column(String(64), nullable=True, comment="关联电子画册ID")

    # 多租户
    organization_id = _org_fk()

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
    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)
    # 轻量会员字段
    membership_tier = Column(String(20), nullable=False, default="free", comment="会员等级: free/gold/diamond")
    membership_expires_at = Column(DateTime, nullable=True, comment="会员过期时间")
    match_credits = Column(Integer, nullable=False, default=3, comment="剩余对接券数")
    brochure_id = Column(String(64), nullable=True, comment="关联电子画册ID")

    # 多租户
    organization_id = _org_fk()

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
    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)
    # 轻量会员字段
    membership_tier = Column(String(20), nullable=False, default="free", comment="会员等级: free/gold/diamond")
    membership_expires_at = Column(DateTime, nullable=True, comment="会员过期时间")
    match_credits = Column(Integer, nullable=False, default=3, comment="剩余对接券数")
    brochure_id = Column(String(64), nullable=True, comment="关联电子画册ID")

    # 多租户
    organization_id = _org_fk()

    # 关系
    user = relationship("User", foreign_keys=[user_id])


class BusinessNeed(Base):
    """需求模型（供需匹配）"""

    __tablename__ = "business_needs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)  # 大健康/企业服务/科技产品/教育培训/消费品
    budget = Column(String(100), nullable=True)  # 预算范围，如"10万-50万"
    region = Column(String(100), nullable=True)  # 地区
    contact_name = Column(String(100), nullable=False)
    contact_phone = Column(String(20), nullable=True)
    status = Column(String(20), nullable=False, default="open")  # open/closed
    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)
    # 轻量会员字段
    membership_tier = Column(String(20), nullable=False, default="free", comment="会员等级: free/gold/diamond")
    membership_expires_at = Column(DateTime, nullable=True, comment="会员过期时间")
    match_credits = Column(Integer, nullable=False, default=3, comment="剩余对接券数")
    brochure_id = Column(String(64), nullable=True, comment="关联电子画册ID")

    # 多租户
    organization_id = _org_fk()

    # 关系
    user = relationship("User", foreign_keys=[user_id])


class BusinessCard(Base):
    """AI数字名片模型"""

    __tablename__ = "business_cards"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    fields = Column(Text, nullable=False)  # JSON: {name,position,company,phone,email,wechat,address,website}
    share_token = Column(String(64), unique=True, index=True, nullable=False)
    view_count = Column(Integer, nullable=False, default=0)
    cover_image = Column(String(500), nullable=True)  # 名片封面图
    album_meta = Column(Text, nullable=True)  # JSON: 翻页图册元数据
    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)
    # 轻量会员字段
    membership_tier = Column(String(20), nullable=False, default="free", comment="会员等级: free/gold/diamond")
    membership_expires_at = Column(DateTime, nullable=True, comment="会员过期时间")
    match_credits = Column(Integer, nullable=False, default=3, comment="剩余对接券数")
    brochure_id = Column(String(64), nullable=True, comment="关联电子画册ID")

    # 多租户
    organization_id = _org_fk()

    # 关系
    user = relationship("User", foreign_keys=[user_id])


class UserEvent(Base):
    """用户行为事件埋点模型"""

    __tablename__ = "user_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # 未登录用户可为空
    event_type = Column(
        String(50), nullable=False, index=True
    )  # product_view, product_click, search, need_view, add_cart
    target_type = Column(String(50), nullable=True)  # product, need, contact
    target_id = Column(Integer, nullable=True)
    search_keyword = Column(String(200), nullable=True)  # 搜索事件的关键词
    session_id = Column(String(100), nullable=True)
    page_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # 多租户
    organization_id = _org_fk()

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
    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)
    # 轻量会员字段
    membership_tier = Column(String(20), nullable=False, default="free", comment="会员等级: free/gold/diamond")
    membership_expires_at = Column(DateTime, nullable=True, comment="会员过期时间")
    match_credits = Column(Integer, nullable=False, default=3, comment="剩余对接券数")
    brochure_id = Column(String(64), nullable=True, comment="关联电子画册ID")

    # 多租户
    organization_id = _org_fk()

    # 关系
    user = relationship("User", back_populates="withdrawals")


class Deal(Base):
    """商机/Deal模型"""

    __tablename__ = "deals"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False, index=True)
    value = Column(Float, default=0.0)
    stage = Column(String(50), default="leads", index=True)
    probability = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    expected_close_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # 关系
    owner = relationship("User", foreign_keys=[owner_id], lazy="joined")
    creator = relationship("User", foreign_keys=[user_id], lazy="joined")


class DealActivity(Base):
    """商机活动日志"""

    __tablename__ = "deal_activities"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    deal_id = Column(Integer, ForeignKey("deals.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action_type = Column(String(50), nullable=False)
    summary = Column(String(500), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 企业知识图谱模型
# ============================================================


class Enterprise(Base):
    """企业模型（商业匹配核心实体）"""

    __tablename__ = "enterprises"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), index=True, nullable=False, comment="企业全称")
    short_name = Column(String(100), nullable=True, comment="企业简称")
    credit_code = Column(String(18), unique=True, nullable=True, comment="统一社会信用代码")
    legal_person = Column(String(100), nullable=True, comment="法定代表人")
    registered_capital = Column(String(50), nullable=True, comment="注册资本")
    established_date = Column(String(20), nullable=True, comment="成立日期")
    industry = Column(String(100), nullable=True, comment="行业分类")
    region = Column(String(100), nullable=True, comment="地区")
    business_scope = Column(Text, nullable=True, comment="经营范围")
    tags = Column(String(500), nullable=True, comment="标签(逗号分隔)")
    website = Column(String(500), nullable=True, comment="企业官网")
    data_source = Column(String(20), default="manual", comment="数据来源: manual/crawl/api")
    confidence = Column(Integer, default=50, comment="数据置信度 0-100")
    extra = Column(Text, nullable=True, comment="扩展JSON")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    source_relations = relationship(
        "EnterpriseRelation",
        foreign_keys="EnterpriseRelation.source_id",
        back_populates="source_enterprise",
        cascade="all, delete-orphan",
    )
    target_relations = relationship(
        "EnterpriseRelation",
        foreign_keys="EnterpriseRelation.target_id",
        back_populates="target_enterprise",
        cascade="all, delete-orphan",
    )


class EnterpriseRelation(Base):
    """企业关系图谱"""

    __tablename__ = "enterprise_relations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("enterprises.id"), index=True, nullable=False)
    target_id = Column(Integer, ForeignKey("enterprises.id"), index=True, nullable=False)
    relation_type = Column(
        String(30),
        nullable=False,
        comment="关系类型: invest/compete/supply/subsidiary/partner/customer",
    )
    relation_label = Column(String(100), nullable=True, comment="关系描述")
    confidence = Column(Integer, default=50, comment="置信度 0-100")
    source = Column(String(20), default="manual", comment="来源: manual/crawl/ai_infer")
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    source_enterprise = relationship("Enterprise", foreign_keys=[source_id], back_populates="source_relations")
    target_enterprise = relationship("Enterprise", foreign_keys=[target_id], back_populates="target_relations")


# ============================================================
# 私董会（Private Board）模型
# ============================================================


class PrivateBoardOrder(Base):
    """私董会申请/订单模型"""

    __tablename__ = "private_board_orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False, default=19999.00, comment="支付金额（元）")
    status = Column(
        String(20), nullable=False, default="pending",
        comment="pending/approved/rejected/paid/cancelled",
    )
    # 申请信息
    company = Column(String(200), nullable=False, comment="企业全称")
    revenue = Column(String(100), nullable=True, comment="年营收")
    industry = Column(String(100), nullable=True, comment="所属行业")
    position = Column(String(100), nullable=True, comment="职位")
    referrer = Column(String(100), nullable=True, comment="推荐人姓名/ID")
    referrer_notes = Column(Text, nullable=True, comment="推荐人备注")
    # 审核相关
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True, comment="审核人ID")
    approved_at = Column(DateTime, nullable=True, comment="审核时间")
    reject_reason = Column(String(500), nullable=True, comment="拒绝原因")
    # 支付相关
    pay_time = Column(DateTime, nullable=True, comment="支付完成时间")
    expires_at = Column(DateTime, nullable=True, comment="私董会会员过期时间")
    transaction_id = Column(String(100), nullable=True, comment="第三方支付订单号")
    prepay_id = Column(String(100), nullable=True, comment="微信预支付ID")
    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 多租户
    organization_id = _org_fk()

    # 关系
    user = relationship("User", foreign_keys=[user_id])
    approver = relationship("User", foreign_keys=[approved_by])


# ============================================================
# 会员系统模型
# ============================================================


class MembershipOrder(Base):
    """会员升级订单模型"""

    __tablename__ = "membership_orders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tier = Column(String(20), nullable=False, comment="升级目标等级: gold/diamond/board")
    amount = Column(Float, nullable=False, comment="支付金额（元）")
    status = Column(String(20), nullable=False, default="pending", comment="pending/paid/cancelled/refunded")
    payment_platform = Column(String(10), nullable=True, comment="支付平台: wxpay/alipay")
    transaction_id = Column(String(100), nullable=True, comment="第三方支付订单号")
    prepay_id = Column(String(100), nullable=True, comment="微信预支付ID")
    paid_at = Column(DateTime, nullable=True, comment="支付完成时间")
    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)

    # 多租户
    organization_id = _org_fk()

    # 关系
    user = relationship("User", back_populates="membership_orders", foreign_keys=[user_id])


class MatchCreditLog(Base):
    """对接券使用日志模型"""

    __tablename__ = "match_credit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Integer, nullable=False, comment="变动数量（正数=增加，负数=消耗）")
    balance_after = Column(Integer, nullable=False, comment="变动后剩余数量")
    reason = Column(String(100), nullable=False, comment="变动原因: upgrade_reward/use/refund/admin_adjust")
    related_type = Column(String(50), nullable=True, comment="关联类型: matching_event/order/admin")
    related_id = Column(Integer, nullable=True, comment="关联ID")
    created_at = Column(DateTime, default=datetime.utcnow)

    # 多租户
    organization_id = _org_fk()

    # 关系
    user = relationship("User", back_populates="match_credit_logs", foreign_keys=[user_id])


class OnlineMatchingEvent(Base):
    """线上对接会活动模型"""

    __tablename__ = "online_matching_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(200), nullable=False, comment="活动标题")
    description = Column(Text, nullable=True, comment="活动描述")
    cover_image = Column(String(500), nullable=True, comment="活动封面图")
    event_date = Column(DateTime, nullable=False, comment="活动日期")
    end_date = Column(DateTime, nullable=True, comment="活动结束日期")
    location = Column(String(200), nullable=True, comment="活动地点/线上会议链接")
    max_participants = Column(Integer, nullable=False, default=100, comment="最大参与人数")
    current_participants = Column(Integer, nullable=False, default=0, comment="当前报名人数")
    price = Column(Float, nullable=False, default=0.0, comment="参与价格（0=免费）")
    status = Column(String(20), nullable=False, default="draft", comment="draft/published/ongoing/completed/cancelled")
    tags = Column(String(500), nullable=True, comment="标签(逗号分隔)")
    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)

    # 多租户
    organization_id = _org_fk()

    # 关系
    registrations = relationship("OnlineMatchingRegistration", back_populates="event", cascade="all, delete-orphan")


class OnlineMatchingRegistration(Base):
    """线上对接会报名模型"""

    __tablename__ = "online_matching_registrations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("online_matching_events.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="confirmed", comment="pending/confirmed/cancelled/attended")
    company = Column(String(200), nullable=True, comment="报名时填写的公司")
    position = Column(String(100), nullable=True, comment="报名时填写的职位")
    phone = Column(String(20), nullable=True, comment="报名时填写的电话")
    notes = Column(Text, nullable=True, comment="报名备注/需求说明")
    created_at = Column(DateTime, default=datetime.utcnow)

    # 多租户
    organization_id = _org_fk()

    # 关系
    event = relationship("OnlineMatchingEvent", back_populates="registrations", foreign_keys=[event_id])
    user = relationship("User", foreign_keys=[user_id])


class OnlineMatchingFeedback(Base):
    """线上对接会反馈模型"""

    __tablename__ = "online_matching_feedback"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("online_matching_events.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    rating = Column(Integer, nullable=False, default=5, comment="评分 1-5")
    comment = Column(Text, nullable=True, comment="反馈内容")
    created_at = Column(DateTime, default=datetime.utcnow)

    # 多租户
    organization_id = _org_fk()

    # 关系
    event = relationship("OnlineMatchingEvent", foreign_keys=[event_id])
    user = relationship("User", foreign_keys=[user_id])
