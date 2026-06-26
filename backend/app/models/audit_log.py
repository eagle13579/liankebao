"""链客宝 — 审计日志数据模型
================================
审计日志系统核心模型，记录所有用户操作和管理行为。

模型：
  AuditLog — ORM 模型，存储单条审计日志记录

记录内容：
  - 用户操作: 登录/注册/修改资料/创建名片/发起匹配/提交反馈
  - 管理操作: 修改flag/更新配置/删除数据
  - 敏感操作: 支付/API Key变更/权限修改
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, func
from app.database import Base


# ===================================================================
# AuditLog — 审计日志 ORM 模型
# ===================================================================
# 映射表: audit_logs
#
# 字段说明:
#   user_id      - 操作用户 ID
#   action       - 操作类型: login/register/update_profile/create_card/
#                  start_match/submit_feedback/admin_set_flag/
#                  admin_update_config/admin_delete_data/payment/
#                  api_key_change/permission_change
#   resource_type - 资源类型: user/card/match/feedback/config/payment/
#                   api_key/permission
#   resource_id   - 资源 ID（可选）
#   detail        - JSON 详情（可选），记录额外上下文
#   ip_address    - 客户端 IP 地址（可选）
#   user_agent    - 客户端 User-Agent（可选）
#   result        - 操作结果: success/failure
#   created_at    - 记录创建时间
# ===================================================================

class AuditLog(Base):
    """审计日志记录"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True, comment="操作用户ID")
    action = Column(String(64), nullable=False, index=True, comment="操作类型")
    resource_type = Column(String(64), nullable=True, index=True, comment="资源类型")
    resource_id = Column(String(128), nullable=True, index=True, comment="资源ID")
    detail = Column(JSON, nullable=True, default=dict, comment="详情JSON")
    ip_address = Column(String(45), nullable=True, comment="客户端IP地址")
    user_agent = Column(Text, nullable=True, comment="客户端User-Agent")
    result = Column(String(16), nullable=False, default="success", comment="操作结果: success/failure")
    created_at = Column(DateTime, default=func.now(), index=True, comment="创建时间")

    def __repr__(self):
        return (
            f"<AuditLog(id={self.id}, user={self.user_id}, "
            f"action={self.action}, result={self.result})>"
        )

    def to_dict(self) -> dict:
        """转为可序列化字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "detail": self.detail if isinstance(self.detail, dict) else {},
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "result": self.result,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
