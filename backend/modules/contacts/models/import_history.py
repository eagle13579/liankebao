"""
导入历史模型
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class ImportHistory(Base):
    """数据导入记录"""

    __tablename__ = "import_histories"

    id = Column(Integer, primary_key=True, index=True)
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
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 关系
    user = relationship("User", back_populates="import_histories")

    def __repr__(self):
        return f"<ImportHistory(id={self.id}, module='{self.module}', status='{self.status}')>"
