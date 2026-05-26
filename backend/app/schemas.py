"""Pydantic 请求/响应模型"""
import re
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field, field_validator

# ===== 常量 =====
VALID_ROLES = ["buyer", "promoter", "supplier", "admin"]


# ===== 通用响应 =====
class ApiResponse(BaseModel):
    """统一API响应格式"""
    code: int = 200
    message: str = "success"
    data: Optional[object] = None


class PaginatedData(BaseModel):
    """分页数据"""
    total: int
    page: int = 1
    page_size: int = 20
    items: List


# ===== 用户 =====
class UserBase(BaseModel):
    username: str
    name: str
    phone: Optional[str] = None
    company: Optional[str] = None
    position: Optional[str] = None
    role: Optional[str] = "buyer"
    avatar: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserResponse(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class UserBrief(BaseModel):
    id: int
    username: str
    name: str
    role: str
    avatar: Optional[str] = None
    company: Optional[str] = None

    class Config:
        from_attributes = True


# ===== 认证 =====
# 邮箱/手机号正则
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
_PHONE_RE = re.compile(r'^1[3-9]\d{9}$')


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)


class WechatLoginRequest(BaseModel):
    code: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None
    company: Optional[str] = None
    position: Optional[str] = None
    role: Optional[str] = "buyer"

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip():
            if not _PHONE_RE.match(v):
                raise ValueError("手机号格式不正确，需为11位中国大陆手机号")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_ROLES:
            raise ValueError(f"角色值无效，仅支持: {', '.join(VALID_ROLES)}")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        # 允许字母、数字、下划线、中文
        if not re.match(r'^[\w\u4e00-\u9fff]+$', v):
            raise ValueError("用户名只能包含字母、数字、下划线和中文")
        return v


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    token: str
    user: UserResponse


# ===== 产品 =====
class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float = 0.0
    earn_per_share: float = 0.0
    category: Optional[str] = None
    stock: int = 0
    images: Optional[str] = None  # JSON字符串
    # 新增字段
    specs: Optional[str] = None
    details: Optional[str] = None
    brand: Optional[str] = None
    sale_price: Optional[float] = None
    video_url: Optional[str] = None
    tags: Optional[str] = None
    files: Optional[str] = None
    is_featured: Optional[int] = 0
    sort_order: Optional[int] = 0


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    earn_per_share: Optional[float] = None
    category: Optional[str] = None
    stock: Optional[int] = None
    images: Optional[str] = None
    specs: Optional[str] = None
    details: Optional[str] = None
    brand: Optional[str] = None
    sale_price: Optional[float] = None
    video_url: Optional[str] = None
    tags: Optional[str] = None
    files: Optional[str] = None
    is_featured: Optional[int] = None
    sort_order: Optional[int] = None


class ProductResponse(ProductBase):
    id: int
    status: str
    owner_id: int
    owner: Optional[UserBrief] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ===== 订单 =====
class OrderCreate(BaseModel):
    product_id: int
    quantity: int = 1
    promoter_id: Optional[int] = None


class OrderResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    product: Optional[ProductResponse] = None
    quantity: int
    total_price: float
    status: str
    promoter_id: Optional[int] = None
    commission: float = 0.0
    # === IJPay 支付字段 ===
    payment_platform: Optional[str] = None     # wxpay / alipay
    wx_transaction_id: Optional[str] = None     # V2 兼容
    transaction_id: Optional[str] = None        # 第三方支付订单号
    prepay_id: Optional[str] = None             # 微信预支付ID
    payment_time: Optional[datetime] = None     # 支付完成时间
    refund_id: Optional[str] = None             # 退款单号
    refund_time: Optional[datetime] = None      # 退款时间
    pay_time: Optional[datetime] = None         # 旧字段兼容
    created_at: datetime

    class Config:
        from_attributes = True


# ===== 推广 =====
class WithdrawRequest(BaseModel):
    amount: float = Field(..., gt=0)
    bank_info: Optional[str] = None  # JSON字符串


class WithdrawalResponse(BaseModel):
    id: int
    user_id: int
    amount: float
    status: str
    bank_info: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class EarningsResponse(BaseModel):
    total_earnings: float = 0.0       # 总收益
    withdrawable: float = 0.0          # 可提现金额
    withdrawn: float = 0.0             # 已提现金额
    pending_withdrawal: float = 0.0    # 提现中金额
    order_count: int = 0               # 推广订单数


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
    reason: Optional[str] = None

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
    sample_values: List[str] = Field(default_factory=list, description="该列的示例值")


class ImportPreviewRequest(BaseModel):
    """导入预览请求（文件上传后调用）"""
    pass  # 文件通过 UploadFile 传递


class ImportPreviewResponse(BaseModel):
    """导入预览响应"""
    batch_id: str
    total_rows: int
    preview_rows: List[dict] = Field(default_factory=list)
    headers: List[str] = Field(default_factory=list)
    field_mapping: Dict[str, str] = Field(default_factory=dict)
    mapped_preview: List[dict] = Field(default_factory=list)
    suggestions: Optional[dict] = None


class DuplicateInfo(BaseModel):
    """重复信息"""
    row_index: int
    matched_contact_id: Optional[int] = None
    matched_name: str = ""
    similarity_score: float = 0.0
    match_type: str = ""  # name_fuzzy / phone_exact / wechat_exact / company_fuzzy


class ImportConfirmRequest(BaseModel):
    """确认导入请求"""
    batch_id: str = Field(..., description="预览时返回的批次ID")
    field_mapping: Dict[str, str] = Field(..., description="最终确认的列名映射")
    strategy: str = Field("skip", description="去重策略: skip / merge / update")
    # 如果为空，则默认对所有重复项应用同一策略
    duplicates: Optional[List[DuplicateInfo]] = Field(None, description="每个重复项的处理方式")


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
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ImportHistoryResponse(BaseModel):
    """导入历史列表响应"""
    total: int = 0
    page: int = 1
    page_size: int = 20
    items: List[ImportHistoryItem] = Field(default_factory=list)


# ===== 联系人 =====
class ContactBase(BaseModel):
    """联系人基础字段"""
    name: str = Field(..., min_length=1, max_length=100, description="姓名")
    phone: Optional[str] = Field(None, max_length=50, description="手机号")
    wechat_id: Optional[str] = Field(None, max_length=100, description="微信号")
    company: Optional[str] = Field(None, max_length=200, description="公司")
    position: Optional[str] = Field(None, max_length=100, description="职位")
    email: Optional[str] = Field(None, max_length=200, description="邮箱")
    notes: Optional[str] = Field(None, description="备注")
    tags: Optional[str] = Field(None, max_length=500, description="标签（逗号分隔）")
    source: Optional[str] = Field("manual", max_length=50, description="来源: import/manual/wechat")


class ContactCreate(ContactBase):
    """创建联系人"""
    pass


class ContactUpdate(BaseModel):
    """更新联系人（所有字段可选）"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    wechat_id: Optional[str] = Field(None, max_length=100)
    company: Optional[str] = Field(None, max_length=200)
    position: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None
    tags: Optional[str] = Field(None, max_length=500)
    source: Optional[str] = Field(None, max_length=50)


class ContactResponse(ContactBase):
    """联系人响应"""
    id: int
    owner_id: int
    import_batch_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContactListResponse(BaseModel):
    """联系人列表响应"""
    total: int = 0
    page: int = 1
    page_size: int = 20
    items: List[ContactResponse] = Field(default_factory=list)


# ===== 活动 =====
class ActivityBase(BaseModel):
    """活动基础字段"""
    action_type: str = Field(..., max_length=50, description="活动类型: note/call/meeting/email/wechat/order/import")
    summary: Optional[str] = Field(None, max_length=500, description="摘要")
    detail: Optional[str] = Field(None, description="详细内容")


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
    description: Optional[str] = Field(None, description="需求描述")
    category: Optional[str] = Field(None, max_length=50, description="品类: 大健康/企业服务/科技产品/教育培训/消费品")
    budget: Optional[str] = Field(None, max_length=100, description="预算范围")
    region: Optional[str] = Field(None, max_length=100, description="地区")
    contact_name: str = Field(..., min_length=1, max_length=100, description="联系人")
    contact_phone: Optional[str] = Field(None, max_length=20, description="联系电话")


class BusinessNeedCreate(BusinessNeedBase):
    """创建需求"""
    pass


class BusinessNeedUpdate(BaseModel):
    """更新需求（所有字段可选）"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=50)
    budget: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=100)
    contact_name: Optional[str] = Field(None, min_length=1, max_length=100)
    contact_phone: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = Field(None, pattern=r"^(open|closed)$")


class BusinessNeedResponse(BusinessNeedBase):
    """需求响应"""
    id: int
    user_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    user: Optional[UserBrief] = None

    class Config:
        from_attributes = True
