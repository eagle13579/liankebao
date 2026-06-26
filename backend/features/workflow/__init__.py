"""
链客宝工作流自动化引擎

从旧版 modules/workflow 迁移到 chainke-full features/workflow。
提供轻量级工作流引擎，支持事件/定时/条件触发器，
以及通知、活动日志、Deal阶段更新等动作。
"""
from features.workflow.workflow_engine import WorkflowEngine
from features.workflow.notifications import NotificationService

__all__ = ["WorkflowEngine", "NotificationService"]
