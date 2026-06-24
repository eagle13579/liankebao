"""SQLAlchemy ORM 数据模型"""

import os
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import DB_TYPE, Base


# === Stub Membership for non-multi-tenant mode ===
class _StubMembership:  # placeholder when IS_MULTI_TENANT=False
    __tablename__ = "memberships"
    pass


# ============================================================
# 多租户判断：PostgreSQL 模式下强制启用 organization_id
# ============================================================
_IS_MULTI_TENANT = (
    os.environ.get("IS_MULTI_TENANT", "true").lower() in ("true", "1", "yes") if True else DB_TYPE == "postgres"
)


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

    # 密码重置
    password_reset_token = Column(String(255), nullable=True, index=True, comment="密码重置令牌")
    password_reset_expires = Column(DateTime, nullable=True, comment="密码重置令牌过期时间")

    # 多租户
    organization_id = _org_fk()

    # 会员字段
    membership_tier = Column(String(20), nullable=False, default="free", comment="会员等级: free/gold/diamond/board")
    membership_expires_at = Column(DateTime, nullable=True, comment="会员过期时间")
    match_credits = Column(Integer, nullable=False, default=3, comment="对接券数量")

    # === 三层信任体系 L1: 身份认证 ===
    email_verified = Column(Boolean, default=False, comment="邮箱已验证")
    phone_verified = Column(Boolean, default=False, comment="手机号已验证")
    enterprise_verified = Column(Boolean, default=False, comment="企业认证通过")
    wechat_verified = Column(Boolean, default=False, comment="微信已绑定验证")
    verification_tier = Column(
        String(20), nullable=False, default="none", comment="认证层级: none/basic/standard/verified"
    )

    # 关系（仅多租户模式启用 ForeignKey 关系）
    if _IS_MULTI_TENANT:
        organization = relationship("Organization", foreign_keys=[organization_id])
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

    # 多租户
    organization_id = _org_fk()

    # 关系
    user = relationship("User", foreign_keys=[user_id])


class VisitorLog(Base):
    """访客行为日志（名片浏览/感兴趣记录）"""

    __tablename__ = "visitor_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    brochure_id = Column(Integer, ForeignKey("business_cards.id"), nullable=False, index=True)
    visitor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    page = Column(String(50), nullable=True)
    duration = Column(Integer, nullable=True)
    interested = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    organization_id = _org_fk()

    brochure = relationship("BusinessCard", foreign_keys=[brochure_id])
    visitor = relationship("User", foreign_keys=[visitor_id])


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
        String(20),
        nullable=False,
        default="pending",
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


class RevokedToken(Base):
    """已吊销JWT Token — DB持久化，防止重启后黑名单丢失"""

    __tablename__ = "revoked_tokens"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    jti = Column(String(64), unique=True, nullable=False, index=True, comment="JWT Token ID")
    revoked_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True, comment="Token原始过期时间")

    # 多租户
    organization_id = _org_fk()


# ============================================================
# 创新引擎模型 (Innovation Engine)
# ============================================================
class BusinessHypothesis(Base):
    """商业假设"""

    __tablename__ = "business_hypotheses"

    id = Column(String(50), primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(30), nullable=False, default="growth")
    evidence_level = Column(String(20), nullable=False, default="low")
    risk_score = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")
    gate_status = Column(String(20), nullable=True, default="open")
    verify_metrics = Column(Text, nullable=True, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class InnovationExperiment(Base):
    """创新实验"""

    __tablename__ = "innovation_experiments"

    id = Column(String(50), primary_key=True, index=True)
    hypothesis_id = Column(String(50), ForeignKey("business_hypotheses.id"), nullable=False, index=True)
    method = Column(String(30), nullable=False, default="a_b_test")
    sample_size = Column(Integer, nullable=True)
    success_criteria = Column(Text, nullable=True)
    control_group_desc = Column(Text, nullable=True)
    experiment_group_desc = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


class InnovationOpportunity(Base):
    """创新机会"""

    __tablename__ = "innovation_opportunities"

    id = Column(String(50), primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    overall_score = Column(Float, nullable=False, default=0.0)
    confidence_score = Column(Float, nullable=False, default=0.0)
    urgency_score = Column(Float, nullable=False, default=0.0)
    business_value_score = Column(Float, nullable=False, default=0.0)
    source_signals = Column(Text, nullable=True, default="[]")
    source_insights = Column(Text, nullable=True, default="[]")
    action_steps = Column(Text, nullable=True, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# 审美评估引擎模型 (Design Review Engine)
# ============================================================
class DesignReviewReport(Base):
    """设计审查报告"""

    __tablename__ = "design_review_reports"

    id = Column(String(50), primary_key=True, index=True)
    report_data = Column(Text, nullable=True, default="{}")
    review_type = Column(String(30), nullable=True, default="full")
    overall_score = Column(Float, nullable=False, default=0.0)
    score_level = Column(String(20), nullable=True, default="fair")
    created_at = Column(DateTime, default=datetime.utcnow)


class AestheticScoreCardRecord(Base):
    """审美评分卡记录"""

    __tablename__ = "aesthetic_score_card_records"

    id = Column(String(50), primary_key=True, index=True)
    card_data = Column(Text, nullable=True, default="{}")
    overall_score = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# e签宝电子签约模型 (Esign)
# ============================================================


class EsignTemplate(Base):
    """e签宝合同模板（本地镜像）"""

    __tablename__ = "esign_templates"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    esign_template_id = Column(String(64), unique=True, nullable=False, index=True, comment="e签宝平台模板 ID")
    name = Column(String(200), nullable=False, comment="模板名称")
    file_id = Column(String(64), nullable=True, comment="e签宝文件 ID")
    status = Column(String(20), nullable=False, default="active", comment="状态: active/disabled")
    meta_data = Column(Text, nullable=True, default="{}", comment="扩展元数据(JSON)")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # 多租户
    organization_id = _org_fk()


class EsignContract(Base):
    """e签宝签署合同记录（本地镜像）"""

    __tablename__ = "esign_contracts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    esign_contract_id = Column(String(64), unique=True, nullable=False, index=True, comment="e签宝平台合同流程 ID")
    template_id = Column(
        Integer, ForeignKey("esign_templates.id"), nullable=True, index=True, comment="关联本地模板 ID"
    )
    contract_name = Column(String(200), nullable=True, comment="合同名称")
    status = Column(
        Integer, nullable=False, default=0, comment="签署状态: 0=待签署 1=签署中 2=已完成 3=已撤销 4=已过期"
    )
    status_label = Column(String(20), nullable=True, comment="状态中文描述")
    signers_json = Column(Text, nullable=True, default="[]", comment="签署方列表(JSON)")
    fields_json = Column(Text, nullable=True, default="[]", comment="填充字段(JSON)")
    sign_url = Column(String(500), nullable=True, comment="签署链接")
    expire_at = Column(DateTime, nullable=True, comment="签署截止时间")
    finish_time = Column(DateTime, nullable=True, comment="签署完成时间")
    meta_data = Column(Text, nullable=True, default="{}", comment="扩展数据(JSON)")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # 多租户
    organization_id = _org_fk()
    # 用户关联
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="发起用户ID")

    # 关系
    template = relationship("EsignTemplate", foreign_keys=[template_id])
    user = relationship("User", foreign_keys=[user_id])


# ============================================================
# 三层信任体系 — L1: 身份认证 / L2: 交互信誉 / L3: 信任评分
# ============================================================


class VerificationRequest(Base):
    """认证申请模型"""

    __tablename__ = "verification_requests"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(20), nullable=False, comment="认证类型: email/phone/enterprise")
    status = Column(String(20), nullable=False, default="pending", comment="pending/verified/rejected")
    evidence = Column(Text, nullable=True, comment="认证证明材料(JSON)")
    verified_at = Column(DateTime, nullable=True, comment="审核通过时间")
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    user = relationship("User", foreign_keys=[user_id])

    # 多租户
    organization_id = _org_fk()


# ============================================================
# 开发者门户模型
# ============================================================


class ApiKey(Base):
    """API Key模型 — 开发者门户"""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key_id = Column(String(64), unique=True, index=True, nullable=False, comment="公开标识ID (lk_xxx)")
    key_hash = Column(String(128), nullable=False, comment="API Key的SHA256哈希")
    key_prefix = Column(String(16), nullable=False, comment="Key前8位用于显示")
    name = Column(String(100), nullable=False, comment="Key名称")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    scopes = Column(String(500), nullable=False, default="read", comment="权限范围 JSON数组")
    tier = Column(String(20), nullable=False, default="free", comment="API等级: free/pro/enterprise")
    rate_limit_per_hour = Column(Integer, nullable=False, default=100)
    is_active = Column(Boolean, nullable=False, default=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)

    # 关系
    user = relationship("User", foreign_keys=[user_id])


class WebhookSubscriptionDB(Base):
    """Webhook订阅模型 — 数据库持久化"""

    __tablename__ = "webhook_subscriptions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sub_id = Column(String(64), unique=True, index=True, nullable=False, comment="订阅标识 (wh_xxx)")
    url = Column(String(1024), nullable=False, comment="回调URL")
    events = Column(String(500), nullable=False, comment="订阅事件类型 JSON数组")
    secret = Column(String(128), nullable=False, comment="HMAC签名密钥")
    active = Column(Boolean, nullable=False, default=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    last_delivery_at = Column(DateTime, nullable=True)
    last_delivery_status = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    user = relationship("User", foreign_keys=[user_id])


class ApiUsageLog(Base):
    """API调用日志 — 按API Key统计"""

    __tablename__ = "api_usage_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=False)
    latency_ms = Column(Integer, nullable=False, default=0)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class WebhookDeliveryLog(Base):
    """Webhook投递日志"""

    __tablename__ = "webhook_delivery_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    subscription_id = Column(Integer, ForeignKey("webhook_subscriptions.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    event_id = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, comment="success/failed/retrying")
    attempt = Column(Integer, nullable=False, default=1)
    response_code = Column(Integer, nullable=True)


# ============================================================
# 社交证明 — Logo墙 / 成功案例 / 数据看板
# ============================================================


class PartnerLogo(Base):
    """合作企业Logo"""

    __tablename__ = "partner_logos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="企业名称")
    logo_url = Column(String(500), nullable=False, comment="Logo图片URL")
    website = Column(String(500), nullable=True, comment="企业官网")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序权重")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CaseStudy(Base):
    """成功案例"""

    __tablename__ = "case_studies"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(200), nullable=False, comment="案例标题")
    description = Column(Text, nullable=True, comment="案例描述")
    image_url = Column(String(500), nullable=True, comment="案例图片URL")
    link_url = Column(String(500), nullable=True, comment="跳转链接")
    company_name = Column(String(200), nullable=True, comment="企业名称")
    tags = Column(String(500), nullable=True, comment="标签（逗号分隔）")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序权重")
    is_active = Column(Boolean, nullable=False, default=True)
    is_featured = Column(Boolean, nullable=False, default=False, comment="是否精选")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Contract(Base):
    """合同模型 — 交易履约核心"""

    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False, comment="合同标题")
    template_id = Column(String(100), nullable=True, comment="关联模板ID")
    status = Column(
        String(20),
        nullable=False,
        default="draft",
        comment="合同状态: draft/pending_sign/signed/in_progress/completed/terminated",
    )
    party_a_name = Column(String(200), nullable=False, comment="甲方名称（链客宝方）")
    party_b_name = Column(String(200), nullable=False, comment="乙方名称（签约方）")
    party_a_id_number = Column(String(100), nullable=True, comment="甲方证件号")
    party_b_id_number = Column(String(100), nullable=True, comment="乙方证件号")
    party_a_contact = Column(String(100), nullable=True, comment="甲方联系人")
    party_b_contact = Column(String(100), nullable=True, comment="乙方联系人")
    contract_amount = Column(Float, nullable=False, default=0.0, comment="合同金额")
    variables = Column(Text, nullable=True, comment="模板变量（JSON）")
    contract_text = Column(Text, nullable=True, comment="合同正文")
    esign_contract_id = Column(String(100), nullable=True, comment="e签宝合同流程ID")
    esign_template_id = Column(String(100), nullable=True, comment="e签宝模板ID")
    sign_url = Column(String(500), nullable=True, comment="签署链接")
    payment_status = Column(
        String(20), nullable=False, default="unpaid", comment="支付状态: unpaid/partial/paid/refunded"
    )
    related_order_id = Column(Integer, nullable=True, comment="关联订单ID")
    signed_at = Column(DateTime, nullable=True, comment="签署完成时间")
    started_at = Column(DateTime, nullable=True, comment="履行开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    terminated_at = Column(DateTime, nullable=True, comment="终止时间")
    notes = Column(Text, nullable=True, comment="备注")

    # 乐观锁 + 软删除
    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)

    # 多租户
    organization_id = _org_fk()

    # 关系
    user = relationship("User", foreign_keys=[user_id])


class PaymentTransaction(Base):
    """支付交易记录 — 统一流水表"""

    __tablename__ = "payment_transactions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    order_id = Column(Integer, nullable=True, comment="关联订单ID")
    contract_id = Column(Integer, nullable=True, comment="关联合同ID")
    transaction_no = Column(String(100), unique=True, nullable=False, comment="商户交易号")
    platform = Column(String(10), nullable=False, comment="支付平台: wxpay/alipay")
    platform_trade_no = Column(String(100), nullable=True, comment="平台交易号")
    amount = Column(Float, nullable=False, comment="交易金额（元）")
    fee = Column(Float, nullable=False, default=0.0, comment="手续费")
    status = Column(String(20), nullable=False, default="pending", comment="pending/success/failed/refunded")
    trade_type = Column(String(20), nullable=False, default="payment", comment="payment/refund")
    description = Column(String(200), nullable=True, comment="交易描述")
    buyer_payee = Column(String(100), nullable=True, comment="付款方账号")
    paid_at = Column(DateTime, nullable=True, comment="支付完成时间")
    raw_data = Column(Text, nullable=True, comment="原始回调数据（JSON）")

    version = Column(BigInteger, nullable=False, default=1, comment="乐观锁版本号")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 多租户
    organization_id = _org_fk()

    # 关系
    user = relationship("User", foreign_keys=[user_id])


class SocialMetric(Base):
    """社交证明数据指标"""

    __tablename__ = "social_metrics"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False, comment="指标键名，如 total_matches")
    label = Column(String(200), nullable=False, comment="显示标签，如 '累计匹配数'")
    value = Column(String(100), nullable=False, comment="显示值，如 '10,000+'")
    icon = Column(String(50), nullable=True, comment="图标名称（emoji或lucide图标名）")
    suffix = Column(String(50), nullable=True, comment="后缀，如 '+' / '家'")
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    error_message = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Review(Base):
    """互评模型 (L2 交互信誉层)"""

    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="评价人")
    reviewee_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="被评价人")
    match_id = Column(Integer, nullable=True, index=True, comment="关联匹配事件ID")
    response_speed = Column(Integer, nullable=False, default=5, comment="响应速度 1-5")
    cooperation_willingness = Column(Integer, nullable=False, default=5, comment="合作意愿 1-5")
    info_accuracy = Column(Integer, nullable=False, default=5, comment="信息准确度 1-5")
    overall_rating = Column(Float, nullable=False, default=5.0, comment="综合评分(三字段均值)")
    comment = Column(Text, nullable=True, comment="评价内容")
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    reviewee = relationship("User", foreign_keys=[reviewee_id])

    # 多租户
    organization_id = _org_fk()


class TrustScore(Base):
    """信任评分模型 (L3 行为信号层)"""

    __tablename__ = "trust_scores"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True, index=True, comment="用户ID")
    total_score = Column(Integer, nullable=False, default=0, comment="信任总分 0-1000")
    completed_matches = Column(Integer, nullable=False, default=0, comment="已完成匹配数")
    response_rate = Column(Float, nullable=False, default=0.0, comment="响应率 0-100")
    avg_response_time = Column(Float, nullable=False, default=0.0, comment="平均响应时间(小时)")
    trust_tier = Column(String(20), nullable=False, default="bronze", comment="信任等级: bronze/silver/gold/platinum")
    last_calculated_at = Column(DateTime, nullable=True, comment="最后计算时间")

    # 关系
    user = relationship("User", foreign_keys=[user_id])

    # 多租户
    organization_id = _org_fk()
