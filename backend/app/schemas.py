"""Pydantic 请求/响应模型"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


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
class LoginRequest(BaseModel):
    username: str
    password: str


class WechatLoginRequest(BaseModel):
    code: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    name: str
    phone: Optional[str] = None
    company: Optional[str] = None
    position: Optional[str] = None
    role: Optional[str] = "buyer"


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

class OrderStatusRequest(BaseModel):
    status: str  # 新状态: pending, paid, shipped, received, refunded, cancelled
