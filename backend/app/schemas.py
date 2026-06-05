"""Pydantic 请求/响应模型"""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# ===== 常量 =====
VALID_ROLES = ["buyer", "promoter", "supplier", "admin"]


# ===== 通用响应 =====
class ApiResponse(BaseModel):
    """统一API响应格式"""

    code: int = 200
    message: str = "success"
    data: object | None = None


class PaginatedData(BaseModel):
    """分页数据"""

    total: int
    page: int = 1
    page_size: int = 20
    items: list


# ===== 用户 =====
class UserBase(BaseModel):
    username: str
    name: str
    phone: str | None = None
    company: str | None = None
    position: str | None = None
    role: str | None = "buyer"
    avatar: str | None = None


class UserCreate(UserBase):
    password: str


class UserResponse(UserBase):
    id: int
    created_at: datetime
    onboarding_pain_point: str | None = None

    class Config:
        from_attributes = True


class OnboardingPreferenceRequest(BaseModel):
    pain_point: str = Field(..., pattern=r"^(low_acquisition_cost|lack_trust|distribution_pain)$")


class UserBrief(BaseModel):
    id: int
    username: str
    name: str
    role: str
    avatar: str | None = None
    company: str | None = None

    class Config:
        from_attributes = True


# ===== 认证 =====
# 邮箱/手机号正则
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)


class WechatLoginRequest(BaseModel):
    code: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=100)
    phone: str | None = None
    company: str | None = None
    position: str | None = None
    role: str | None = "buyer"
    pain_point: str | None = Field(None, pattern=r"^(low_acquisition_cost|lack_trust|distribution_pain)$")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            if not _PHONE_RE.match(v):
                raise ValueError("手机号格式不正确，需为11位中国大陆手机号")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_ROLES:
            raise ValueError(f"角色值无效，仅支持: {', '.join(VALID_ROLES)}")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        # 允许字母、数字、下划线、中文
        if not re.match(r"^[\w\u4e00-\u9fff]+$", v):
            raise ValueError("用户名只能包含字母、数字、下划线和中文")
        return v


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class ForgotPasswordRequest(BaseModel):
    """忘记密码请求"""

    email: str = Field(..., description="注册邮箱（即username）")


class ResetPasswordRequest(BaseModel):
    """重置密码请求"""

    token: str = Field(..., min_length=1, description="重置令牌")
    password: str = Field(..., min_length=8, max_length=128, description="新密码")


class TokenResponse(BaseModel):
    token: str
    user: UserResponse


# ===== 产品 =====
class ProductBase(BaseModel):
    name: str
    description: str | None = None
    price: float = 0.0
    earn_per_share: float = 0.0
    category: str | None = None
    stock: int = 0
    images: str | None = None  # JSON字符串
    # 新增字段
    specs: str | None = None
    details: str | None = None
    brand: str | None = None
    sale_price: float | None = None
    video_url: str | None = None
    tags: str | None = None
    files: str | None = None
    is_featured: int | None = 0
    sort_order: int | None = 0
    brochure_id: str | None = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    earn_per_share: float | None = None
    category: str | None = None
    stock: int | None = None
    images: str | None = None
    specs: str | None = None
    details: str | None = None
    brand: str | None = None
    sale_price: float | None = None
    video_url: str | None = None
    tags: str | None = None
    files: str | None = None
    is_featured: int | None = None
    sort_order: int | None = None


class ProductResponse(ProductBase):
    id: int
    status: str
    owner_id: int
    owner: UserBrief | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# ===== 订单 =====
class OrderCreate(BaseModel):
    product_id: int
    quantity: int = 1
    promoter_id: int | None = None


class OrderResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    product: ProductResponse | None = None
    quantity: int
    total_price: float
    status: str
    promoter_id: int | None = None
    commission: float = 0.0
    # === IJPay 支付字段 ===
    payment_platform: str | None = None  # wxpay / alipay
    wx_transaction_id: str | None = None  # V2 兼容
    transaction_id: str | None = None  # 第三方支付订单号
    prepay_id: str | None = None  # 微信预支付ID
    payment_time: datetime | None = None  # 支付完成时间
    refund_id: str | None = None  # 退款单号
    refund_time: datetime | None = None  # 退款时间
    pay_time: datetime | None = None  # 旧字段兼容
    created_at: datetime

    class Config:
        from_attributes = True


# ===== 推广 =====
class WithdrawRequest(BaseModel):
    amount: float = Field(..., gt=0)
    bank_info: str | None = None  # JSON字符串


class WithdrawalResponse(BaseModel):
    id: int
    user_id: int
    amount: float
    status: str
    bank_info: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class EarningsResponse(BaseModel):
    total_earnings: float = 0.0  # 总收益
    withdrawable: float = 0.0  # 可提现金额
    withdrawn: float = 0.0  # 已提现金额
    pending_withdrawal: float = 0.0  # 提现中金额
    order_count: int = 0  # 推广订单数


# ===== 管理后台 =====
class DashboardResponse(BaseModel):
    total_users: int = 0
    total_products: int = 0
    total_orders: int = 0
    total_revenue: float = 0.0
    today_orders: int = 0
    pending_review_products: int = 0
    pending_withdrawals: int = 0


class ProductReviewRequest(BaseModel):
    action: str  # approve 或 reject
    reason: str | None = None


class UpdateUserRoleRequest(BaseModel):
    """管理员修改用户角色请求"""

    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"角色值无效，仅支持: {', '.join(VALID_ROLES)}")
        return v


class OrderStatusRequest(BaseModel):
    status: str  # 新状态: pending, paid, shipped, received, refunded, cancelled


# ===== 导入引擎 =====


class FieldMappingItem(BaseModel):
    """单个字段映射项"""

    csv_column: str = Field(..., description="CSV中的列名")
    standard_field: str = Field("", description="映射到的标准字段，空表示不映射")
    sample_values: list[str] = Field(default_factory=list, description="该列的示例值")


class ImportPreviewRequest(BaseModel):
    """导入预览请求（文件上传后调用）"""

    pass  # 文件通过 UploadFile 传递


class ImportPreviewResponse(BaseModel):
    """导入预览响应"""

    batch_id: str
    total_rows: int
    preview_rows: list[dict] = Field(default_factory=list)
    headers: list[str] = Field(default_factory=list)
    field_mapping: dict[str, str] = Field(default_factory=dict)
    mapped_preview: list[dict] = Field(default_factory=list)
    suggestions: dict | None = None


class DuplicateInfo(BaseModel):
    """重复信息"""

    row_index: int
    matched_contact_id: int | None = None
    matched_name: str = ""
    similarity_score: float = 0.0
    match_type: str = ""  # name_fuzzy / phone_exact / wechat_exact / company_fuzzy


class ImportConfirmRequest(BaseModel):
    """确认导入请求"""

    batch_id: str = Field(..., description="预览时返回的批次ID")
    field_mapping: dict[str, str] = Field(..., description="最终确认的列名映射")
    strategy: str = Field("skip", description="去重策略: skip / merge / update")
    # 如果为空，则默认对所有重复项应用同一策略
    duplicates: list[DuplicateInfo] | None = Field(None, description="每个重复项的处理方式")


class ImportConfirmResponse(BaseModel):
    """确认导入响应"""

    batch_id: str
    import_id: int = 0
    total_rows: int = 0
    imported_rows: int = 0
    skipped_rows: int = 0
    merged_rows: int = 0
    duplicate_count: int = 0
    strategy: str = "skip"


class ImportHistoryItem(BaseModel):
    """导入历史条目"""

    id: int
    filename: str
    file_type: str
    total_rows: int
    imported_rows: int
    skipped_rows: int
    merged_rows: int
    duplicate_count: int
    strategy: str
    status: str
    error_message: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ImportHistoryResponse(BaseModel):
    """导入历史列表响应"""

    total: int = 0
    page: int = 1
    page_size: int = 20
    items: list[ImportHistoryItem] = Field(default_factory=list)


# ===== 联系人 =====
class ContactBase(BaseModel):
    """联系人基础字段"""

    name: str = Field(..., min_length=1, max_length=100, description="姓名")
    phone: str | None = Field(None, max_length=50, description="手机号")
    wechat_id: str | None = Field(None, max_length=100, description="微信号")
    company: str | None = Field(None, max_length=200, description="公司")
    position: str | None = Field(None, max_length=100, description="职位")
    email: str | None = Field(None, max_length=200, description="邮箱")
    notes: str | None = Field(None, description="备注")
    tags: str | None = Field(None, max_length=500, description="标签（逗号分隔）")
    source: str | None = Field("manual", max_length=50, description="来源: import/manual/wechat")


class ContactCreate(ContactBase):
    """创建联系人"""

    pass


class ContactUpdate(BaseModel):
    """更新联系人（所有字段可选）"""

    name: str | None = Field(None, min_length=1, max_length=100)
    phone: str | None = Field(None, max_length=50)
    wechat_id: str | None = Field(None, max_length=100)
    company: str | None = Field(None, max_length=200)
    position: str | None = Field(None, max_length=100)
    email: str | None = Field(None, max_length=200)
    notes: str | None = None
    tags: str | None = Field(None, max_length=500)
    source: str | None = Field(None, max_length=50)


class ContactResponse(ContactBase):
    """联系人响应"""

    id: int
    owner_id: int
    import_batch_id: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContactListResponse(BaseModel):
    """联系人列表响应"""

    total: int = 0
    page: int = 1
    page_size: int = 20
    items: list[ContactResponse] = Field(default_factory=list)


# ===== 活动 =====
class ActivityBase(BaseModel):
    """活动基础字段"""

    action_type: str = Field(..., max_length=50, description="活动类型: note/call/meeting/email/wechat/order/import")
    summary: str | None = Field(None, max_length=500, description="摘要")
    detail: str | None = Field(None, description="详细内容")


class ActivityCreate(ActivityBase):
    """创建活动"""

    pass


class ActivityResponse(ActivityBase):
    """活动响应"""

    id: int
    contact_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ===== 供需匹配（BusinessNeed） =====
class BusinessNeedBase(BaseModel):
    """需求基础字段"""

    title: str = Field(..., min_length=1, max_length=200, description="需求标题")
    description: str | None = Field(None, description="需求描述")
    category: str | None = Field(None, max_length=50, description="品类: 大健康/企业服务/科技产品/教育培训/消费品")
    budget: str | None = Field(None, max_length=100, description="预算范围")
    region: str | None = Field(None, max_length=100, description="地区")
    contact_name: str = Field(..., min_length=1, max_length=100, description="联系人")
    contact_phone: str | None = Field(None, max_length=20, description="联系电话")


class BusinessNeedCreate(BusinessNeedBase):
    """创建需求"""

    pass


class BusinessNeedUpdate(BaseModel):
    """更新需求（所有字段可选）"""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(None, max_length=50)
    budget: str | None = Field(None, max_length=100)
    region: str | None = Field(None, max_length=100)
    contact_name: str | None = Field(None, min_length=1, max_length=100)
    contact_phone: str | None = Field(None, max_length=20)
    status: str | None = Field(None, pattern=r"^(open|closed)$")


class BusinessNeedResponse(BusinessNeedBase):
    """需求响应"""

    id: int
    user_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    user: UserBrief | None = None

    class Config:
        from_attributes = True


# ===== 多租户 =====
class OrganizationCreate(BaseModel):
    """创建组织"""

    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9\-]+$")
    plan: str = "free"
    settings: dict | None = None


class OrganizationResponse(BaseModel):
    """组织响应"""

    id: int
    name: str
    slug: str
    plan: str
    settings: dict | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class MembershipCreate(BaseModel):
    """创建成员关系"""

    user_id: int
    org_id: int
    role: str = "member"


class MembershipResponse(BaseModel):
    """成员关系响应"""

    id: int
    user_id: int
    org_id: int
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


# ===== CRM =====
class DealCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    value: float | None = 0.0
    stage: str = "leads"
    probability: int | None = 0
    owner_id: int | None = None
    expected_close_date: str | None = None
    notes: str | None = None


class DealUpdate(BaseModel):
    title: str | None = None
    value: float | None = None
    stage: str | None = None
    probability: int | None = None
    owner_id: int | None = None
    expected_close_date: str | None = None
    notes: str | None = None


class DealActivityCreate(BaseModel):
    action_type: str = Field(..., max_length=50)
    summary: str = Field(..., max_length=500)
    detail: str | None = None


# ===== 企业知识图谱 =====


class EnterpriseCreate(BaseModel):
    """创建企业请求"""

    name: str = Field(..., min_length=1, max_length=200)
    short_name: str | None = None
    credit_code: str | None = Field(None, max_length=18)
    legal_person: str | None = None
    registered_capital: str | None = None
    established_date: str | None = None
    industry: str | None = None
    region: str | None = None
    business_scope: str | None = None
    tags: str | None = None
    website: str | None = None
    data_source: str = "manual"
    confidence: int = 50
    extra: str | None = None


class EnterpriseUpdate(BaseModel):
    """更新企业请求"""

    short_name: str | None = None
    credit_code: str | None = None
    legal_person: str | None = None
    registered_capital: str | None = None
    established_date: str | None = None
    industry: str | None = None
    region: str | None = None
    business_scope: str | None = None
    tags: str | None = None
    website: str | None = None
    confidence: int | None = None
    extra: str | None = None


class EnterpriseResponse(BaseModel):
    """企业响应"""

    id: int
    name: str
    short_name: str | None = None
    credit_code: str | None = None
    legal_person: str | None = None
    registered_capital: str | None = None
    established_date: str | None = None
    industry: str | None = None
    region: str | None = None
    business_scope: str | None = None
    tags: str | None = None
    website: str | None = None
    data_source: str = "manual"
    confidence: int = 50
    extra: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class EnterpriseRelationCreate(BaseModel):
    """创建企业关系请求"""

    target_id: int
    relation_type: str = Field(..., pattern=r"^(invest|compete|supply|subsidiary|partner|customer)$")
    relation_label: str | None = None
    confidence: int = 50
    source: str = "manual"


class EnterpriseRelationResponse(BaseModel):
    """企业关系响应"""

    id: int
    source_id: int
    target_id: int
    relation_type: str
    relation_label: str | None = None
    confidence: int = 50
    source: str = "manual"
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class EnterpriseEnrichRequest(BaseModel):
    """企业信息补全请求"""

    name: str = Field(..., min_length=1, max_length=200)
