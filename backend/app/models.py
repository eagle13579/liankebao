"""
链客宝 - 所有数据模型（向后兼容入口）
从 modules/{name}/models/ 中导入所有模型

维护说明:
- 新增模型请创建在对应模块的 models/ 目录下
- 并在下方 import
"""
# flake8: noqa: F401

from app.database import Base

# 导入各模块模型，确保 Alembic 能发现所有模型
from modules.auth.models.user import User
from modules.products.models.product import Product
from modules.orders.models.order import Order
from modules.contacts.models.contact import Contact
from modules.contacts.models.import_history import ImportHistory
from modules.activities.models.activity import Activity
from modules.needs.models.need import BusinessNeed
from modules.promoter.models.withdrawal import Withdrawal
from modules.external.models.external_module import ExternalModule
from modules.workflow.models.deal import Deal
from modules.workflow.models.event import Event

__all__ = [
    "User",
    "Product",
    "Order",
    "Contact",
    "ImportHistory",
    "Activity",
    "BusinessNeed",
    "Withdrawal",
    "ExternalModule",
    "Deal",
    "Event",
    "Base",
]
