"""
链客宝工作流自动化引擎
"""
__version__ = "1.0.0"

from modules.workflow.workflow_engine import WorkflowEngine
from modules.workflow.notifications import NotificationService

__all__ = ["WorkflowEngine", "NotificationService"]
