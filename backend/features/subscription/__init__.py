"""订阅模块

模型 (单文件版):
  - SubscriptionPlan  — 订阅方案
  - Subscription      — 用户订阅
  - Invoice           — 发票/账单

枚举:
  - PlanTier          — 方案等级
  - BillingMode       — 计费模式 (monthly/yearly/usage)
  - SubscriptionStatus — 订阅状态
  - InvoiceStatus     — 发票状态

路由:
  - routes.py         — FastAPI 路由 (prefix: /api/subscription)
"""
from .models import (
    SubscriptionPlan,
    Subscription,
    Invoice,
    PlanTier,
    BillingMode,
    SubscriptionStatus,
    InvoiceStatus,
    generate_invoice_no,
)
