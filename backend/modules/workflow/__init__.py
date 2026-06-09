"""
链客宝AI工作流自动化引擎
"""

__version__ = "1.0.0"

from modules.workflow.notifications import NotificationService
from modules.workflow.workflow_engine import WorkflowEngine

__all__ = ["WorkflowEngine", "NotificationService"]
