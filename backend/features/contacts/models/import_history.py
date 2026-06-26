"""
导入历史模型 (ImportHistory Model)
===================================
迁移自旧版链客宝 backend/modules/contacts/models/import_history.py
适配修改:
  - 使用 chainke-full 的 app.database.Base
  - datetime.utcnow -> func.now() (与 chainke-full 约定一致)
  - 添加 __table_args__ 和 to_dict() 方法
  - 关系使用字符串懒加载 (与其他模型模式一致)
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class ImportHistory(Base):
    """数据导入记录"""

    __tablename__ = "import_histories"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="执行导入的用户ID")
    module = Column(String(50), nullable=False, comment="导入模块: contacts/products")
    filename = Column(String(255), comment="导入文件名")
    total_rows = Column(Integer, default=0, comment="总行数")
    success_count = Column(Integer, default=0, comment="成功导入数")
    error_count = Column(Integer, default=0, comment="失败数")
    status = Column(
        String(20), default="completed", comment="状态: processing/completed/failed"
    )
    error_detail = Column(Text, comment="错误详情")
    created_at = Column(DateTime, default=func.now(), comment="创建时间")

    # 关系 (字符串懒加载)
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<ImportHistory(id={self.id}, module='{self.module}', status='{self.status}')>"

    def to_dict(self) -> dict:
        """转为可序列化字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "module": self.module,
            "filename": self.filename,
            "total_rows": self.total_rows,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "status": self.status,
            "error_detail": self.error_detail,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
