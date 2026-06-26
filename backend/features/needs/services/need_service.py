"""
商业需求服务层 (Need Service)
==============================
迁移自旧版链客宝商机模块，提供商业需求的 CRUD 管理。

用法:
    from features.needs.services import NeedService
    service = NeedService(db)
    need = service.create_need(...)
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from features.needs.models.need import BusinessNeed

logger = logging.getLogger(__name__)


class NeedService:
    """商业需求业务服务"""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # 基础查询
    # ------------------------------------------------------------------

    def _base_query(self):
        """基础需求查询"""
        return self.db.query(BusinessNeed)

    # ------------------------------------------------------------------
    # create_need — 创建需求
    # ------------------------------------------------------------------

    def create_need(
        self,
        title: str,
        owner_id: int,
        description: Optional[str] = None,
        category: Optional[str] = None,
        budget: Optional[float] = None,
        contact_name: Optional[str] = None,
        contact_phone: Optional[str] = None,
    ) -> BusinessNeed:
        """创建新商业需求"""
        need = BusinessNeed(
            title=title,
            owner_id=owner_id,
            description=description,
            category=category,
            budget=budget,
            status="open",
            contact_name=contact_name,
            contact_phone=contact_phone,
        )
        self.db.add(need)
        self.db.commit()
        self.db.refresh(need)
        logger.info("需求创建成功: id=%d, owner=%d, title='%s'", need.id, owner_id, title)
        return need

    # ------------------------------------------------------------------
    # get_need — 查询单个需求
    # ------------------------------------------------------------------

    def get_need(self, need_id: int) -> Optional[BusinessNeed]:
        """根据 ID 查询需求"""
        return self._base_query().filter(BusinessNeed.id == need_id).first()

    # ------------------------------------------------------------------
    # list_needs — 需求列表（分页）
    # ------------------------------------------------------------------

    def list_needs(
        self,
        page: int = 1,
        limit: int = 20,
        owner_id: Optional[int] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> tuple[list[BusinessNeed], int]:
        """分页查询需求列表

        Args:
            page:     页码，从 1 开始
            limit:    每页条数
            owner_id: 按发布人筛选
            category: 按分类筛选
            status:   按状态筛选
            search:   搜索关键词（匹配标题/描述）

        Returns:
            (items, total) 元组
        """
        query = self._base_query()

        if owner_id is not None:
            query = query.filter(BusinessNeed.owner_id == owner_id)
        if category:
            query = query.filter(BusinessNeed.category == category)
        if status:
            query = query.filter(BusinessNeed.status == status)
        if search:
            keyword = f"%{search}%"
            query = query.filter(
                BusinessNeed.title.ilike(keyword)
                | BusinessNeed.description.ilike(keyword)
            )

        total = query.count()
        items = (
            query
            .order_by(desc(BusinessNeed.updated_at))
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return items, total

    # ------------------------------------------------------------------
    # update_need — 更新需求
    # ------------------------------------------------------------------

    def update_need(
        self,
        need_id: int,
        **kwargs,
    ) -> BusinessNeed:
        """更新需求（仅更新传入的非 None 字段）

        Args:
            need_id:   需求 ID
            **kwargs:  要更新的字段

        Returns:
            BusinessNeed ORM 实例

        Raises:
            ValueError: 需求不存在
        """
        need = self.get_need(need_id)
        if need is None:
            raise ValueError(f"需求不存在: id={need_id}")

        for field, value in kwargs.items():
            if value is not None:
                setattr(need, field, value)

        self.db.commit()
        self.db.refresh(need)
        logger.info("需求更新成功: id=%d", need_id)
        return need

    # ------------------------------------------------------------------
    # delete_need — 删除需求
    # ------------------------------------------------------------------

    def delete_need(self, need_id: int) -> None:
        """删除需求

        Args:
            need_id: 需求 ID

        Raises:
            ValueError: 需求不存在
        """
        need = self.get_need(need_id)
        if need is None:
            raise ValueError(f"需求不存在: id={need_id}")

        self.db.delete(need)
        self.db.commit()
        logger.info("需求已删除: id=%d", need_id)

    # ------------------------------------------------------------------
    # respond_need — 响应需求（更新状态）
    # ------------------------------------------------------------------

    def respond_need(self, need_id: int) -> BusinessNeed:
        """响应需求（将状态改为 responding）

        Args:
            need_id: 需求 ID

        Raises:
            ValueError: 需求不存在
        """
        need = self.get_need(need_id)
        if need is None:
            raise ValueError(f"需求不存在: id={need_id}")

        if need.status != "open":
            raise ValueError(f"需求状态不允许响应: 当前状态={need.status}")

        need.status = "responding"
        self.db.commit()
        self.db.refresh(need)
        logger.info("需求已响应: id=%d", need_id)
        return need

    # ------------------------------------------------------------------
    # fulfill_need — 完成需求
    # ------------------------------------------------------------------

    def fulfill_need(self, need_id: int) -> BusinessNeed:
        """完成需求（将状态改为 fulfilled）

        Args:
            need_id: 需求 ID

        Raises:
            ValueError: 需求不存在
        """
        need = self.get_need(need_id)
        if need is None:
            raise ValueError(f"需求不存在: id={need_id}")

        need.status = "fulfilled"
        self.db.commit()
        self.db.refresh(need)
        logger.info("需求已完成: id=%d", need_id)
        return need

    # ------------------------------------------------------------------
    # close_need — 关闭需求
    # ------------------------------------------------------------------

    def close_need(self, need_id: int) -> BusinessNeed:
        """关闭需求（将状态改为 closed）

        Args:
            need_id: 需求 ID

        Raises:
            ValueError: 需求不存在
        """
        need = self.get_need(need_id)
        if need is None:
            raise ValueError(f"需求不存在: id={need_id}")

        need.status = "closed"
        self.db.commit()
        self.db.refresh(need)
        logger.info("需求已关闭: id=%d", need_id)
        return need
