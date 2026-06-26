"""订阅计费服务层"""
import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from features.subscription.models import (
    SubscriptionPlan, Subscription, Invoice, InvoiceStatus,
    PlanTier, SubscriptionStatus, BillingMode,
    generate_invoice_no,
)


class SubscriptionService:
    def __init__(self):
        self.db = SessionLocal()

    def __del__(self):
        self.db.close()

    def list_active_plans(self):
        plans = self.db.query(SubscriptionPlan).filter(
            SubscriptionPlan.is_active == True
        ).order_by(SubscriptionPlan.sort_order).all()
        return [p.to_dict() for p in plans]

    def get_user_subscription(self, user_id: int):
        sub = self.db.query(Subscription).filter(
            Subscription.user_id == user_id,
            Subscription.status.in_([
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.TRIALING,
            ])
        ).first()
        return sub

    def create_subscription(
        self, user_id: int, plan_id: int,
        billing_mode: str = "monthly",
        payment_provider: str = "alipay",
    ):
        # Verify plan exists
        plan = self.db.query(SubscriptionPlan).filter(
            SubscriptionPlan.id == plan_id,
            SubscriptionPlan.is_active == True
        ).first()
        if not plan:
            raise ValueError("定价方案不存在")

        # Cancel existing active subscription
        existing = self.get_user_subscription(user_id)
        if existing:
            existing.status = SubscriptionStatus.CANCELED
            existing.canceled_at = datetime.datetime.utcnow()

        # Calculate period
        now = datetime.datetime.utcnow()
        if billing_mode == BillingMode.YEARLY.value:
            period_end = now + datetime.timedelta(days=365)
        else:
            period_end = now + datetime.timedelta(days=30)

        sub = Subscription(
            user_id=user_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
            billing_mode=BillingMode(billing_mode),
            current_period_start=now,
            current_period_end=period_end,
            payment_provider=payment_provider,
            usage_included=plan.usage_included,
        )
        self.db.add(sub)
        self.db.flush()

        # Create invoice (only for monthly/yearly)
        price = plan.get_price(billing_mode)
        tax = round(price * 0.06, 2)
        total = round(price + tax, 2)

        invoice = Invoice(
            invoice_no=generate_invoice_no(user_id),
            user_id=user_id,
            subscription_id=sub.id,
            amount=price,
            tax=tax,
            total=total,
            status=InvoiceStatus.PAID,
            billing_type="subscription",
            billing_cycle=billing_mode,
            payment_method=payment_provider,
            paid_at=now,
            description=f"{plan.name} {billing_mode} subscription"
        )
        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def cancel_subscription(self, user_id: int):
        sub = self.get_user_subscription(user_id)
        if not sub:
            raise ValueError("无活跃订阅")
        sub.status = SubscriptionStatus.CANCELED
        sub.canceled_at = datetime.datetime.utcnow()
        sub.auto_renew = False
        self.db.commit()

    def upgrade_subscription(self, user_id: int, new_plan_id: int):
        sub = self.get_user_subscription(user_id)
        if not sub:
            raise ValueError("无活跃订阅")
        plan = self.db.query(SubscriptionPlan).filter_by(id=new_plan_id, is_active=True).first()
        if not plan:
            raise ValueError("定价方案不存在")

        # Check upgrade: new plan must have higher sort_order
        old_plan = self.db.query(SubscriptionPlan).filter_by(id=sub.plan_id).first()
        if old_plan and plan.sort_order <= old_plan.sort_order:
            raise ValueError("只能升级到更高方案")

        sub.plan_id = new_plan_id
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def get_user_invoices(self, user_id: int):
        return self.db.query(Invoice).filter(
            Invoice.user_id == user_id
        ).order_by(Invoice.issued_at.desc()).all()
