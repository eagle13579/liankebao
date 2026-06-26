"""
联系人服务层 (Contact Service)
==============================
迁移自旧版链客宝联系人模块，提供联系人 CRUD 与搜索管理。

用法:
    from features.contacts.services import ContactService
    service = ContactService(db)
    contact = service.create_contact(...)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from features.contacts.models.contact import Contact
from features.contacts.models.import_history import ImportHistory

logger = logging.getLogger(__name__)


class ContactService:
    """联系人业务服务"""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # 基础查询
    # ------------------------------------------------------------------

    def _base_query(self, owner_id: int):
        """当前用户的未删除联系人查询"""
        return self.db.query(Contact).filter(
            Contact.owner_id == owner_id,
            Contact.is_deleted == False,
        )

    # ------------------------------------------------------------------
    # create_contact — 创建联系人
    # ------------------------------------------------------------------

    def create_contact(
        self,
        owner_id: int,
        name: str,
        phone: Optional[str] = None,
        wechat_id: Optional[str] = None,
        company: Optional[str] = None,
        position: Optional[str] = None,
        email: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[str] = None,
        source: str = "manual",
    ) -> Contact:
        """创建新联系人"""
        contact = Contact(
            owner_id=owner_id,
            name=name,
            phone=phone,
            wechat_id=wechat_id,
            company=company,
            position=position,
            email=email,
            notes=notes,
            tags=tags,
            source=source,
        )
        self.db.add(contact)
        self.db.commit()
        self.db.refresh(contact)
        logger.info("联系人创建成功: id=%d, owner=%d, name='%s'", contact.id, owner_id, name)
        return contact

    # ------------------------------------------------------------------
    # get_contact — 查询单个联系人
    # ------------------------------------------------------------------

    def get_contact(self, contact_id: int, owner_id: int) -> Optional[Contact]:
        """根据 ID 和 owner 查询联系人"""
        return (
            self._base_query(owner_id)
            .filter(Contact.id == contact_id)
            .first()
        )

    # ------------------------------------------------------------------
    # list_contacts — 联系人列表（分页）
    # ------------------------------------------------------------------

    def list_contacts(
        self,
        owner_id: int,
        page: int = 1,
        limit: int = 20,
        search: Optional[str] = None,
        tags: Optional[str] = None,
    ) -> tuple[list[Contact], int]:
        """分页查询联系人列表

        Args:
            owner_id: 所属用户 ID
            page:     页码，从 1 开始
            limit:    每页条数
            search:   搜索关键词（匹配姓名/电话/公司）
            tags:     标签筛选（逗号分隔）

        Returns:
            (items, total) 元组
        """
        query = self._base_query(owner_id)

        # 搜索关键词
        if search:
            keyword = f"%{search}%"
            query = query.filter(
                Contact.name.ilike(keyword)
                | Contact.phone.ilike(keyword)
                | Contact.company.ilike(keyword)
            )

        # 标签筛选
        if tags:
            for t in tags.split(","):
                t = t.strip()
                if t:
                    query = query.filter(Contact.tags.contains(t))

        total = query.count()
        items = (
            query
            .order_by(desc(Contact.updated_at))
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return items, total

    # ------------------------------------------------------------------
    # search_contacts — FTS 搜索联系人
    # ------------------------------------------------------------------

    def search_contacts(
        self,
        owner_id: int,
        q: str,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Contact], int]:
        """全文搜索联系人（姓名/电话/微信号/公司/职位/邮箱/备注）"""
        keyword = f"%{q}%"
        query = self._base_query(owner_id).filter(
            Contact.name.ilike(keyword)
            | Contact.phone.ilike(keyword)
            | Contact.wechat_id.ilike(keyword)
            | Contact.company.ilike(keyword)
            | Contact.position.ilike(keyword)
            | Contact.email.ilike(keyword)
            | Contact.notes.ilike(keyword)
        )

        total = query.count()
        items = (
            query
            .order_by(desc(Contact.updated_at))
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return items, total

    # ------------------------------------------------------------------
    # list_tags — 获取标签列表
    # ------------------------------------------------------------------

    def list_tags(self, owner_id: int) -> list[str]:
        """获取当前用户所有标签列表（去重排序）"""
        contacts = self._base_query(owner_id).all()
        tag_set: set = set()
        for c in contacts:
            if c.tags:
                for t in c.tags.split(","):
                    t = t.strip()
                    if t:
                        tag_set.add(t)
        return sorted(tag_set)

    # ------------------------------------------------------------------
    # update_contact — 更新联系人
    # ------------------------------------------------------------------

    def update_contact(
        self,
        contact_id: int,
        owner_id: int,
        **kwargs,
    ) -> Contact:
        """更新联系人（仅更新传入的非 None 字段）

        Args:
            contact_id: 联系人 ID
            owner_id:   所属用户 ID
            **kwargs:   要更新的字段

        Returns:
            Contact ORM 实例

        Raises:
            ValueError: 联系人不存在
        """
        contact = self.get_contact(contact_id, owner_id)
        if contact is None:
            raise ValueError(f"联系人不存在: id={contact_id}")

        for field, value in kwargs.items():
            if value is not None:
                setattr(contact, field, value)

        self.db.commit()
        self.db.refresh(contact)
        logger.info("联系人更新成功: id=%d", contact_id)
        return contact

    # ------------------------------------------------------------------
    # delete_contact — 软删除联系人
    # ------------------------------------------------------------------

    def delete_contact(self, contact_id: int, owner_id: int) -> None:
        """软删除联系人

        Args:
            contact_id: 联系人 ID
            owner_id:   所属用户 ID

        Raises:
            ValueError: 联系人不存在
        """
        contact = self.get_contact(contact_id, owner_id)
        if contact is None:
            raise ValueError(f"联系人不存在: id={contact_id}")

        contact.is_deleted = True
        contact.deleted_at = datetime.utcnow()
        self.db.commit()
        logger.info("联系人已删除: id=%d", contact_id)

    # ------------------------------------------------------------------
    # batch_create_contacts — 批量创建联系人
    # ------------------------------------------------------------------

    def batch_create_contacts(
        self,
        owner_id: int,
        contacts_data: list[dict],
    ) -> list[Contact]:
        """批量创建联系人（用于导入确认）

        Args:
            owner_id:       所属用户 ID
            contacts_data:  联系人数据列表

        Returns:
            创建的 Contact 实例列表
        """
        created: list[Contact] = []
        for data in contacts_data:
            contact = Contact(
                owner_id=owner_id,
                name=data["name"],
                phone=data.get("phone"),
                wechat_id=data.get("wechat_id"),
                company=data.get("company"),
                position=data.get("position"),
                email=data.get("email"),
                notes=data.get("notes"),
                tags=data.get("tags"),
                source=data.get("source") or "import",
            )
            self.db.add(contact)
            created.append(contact)

        self.db.commit()
        for c in created:
            self.db.refresh(c)

        logger.info("批量创建联系人成功: owner=%d, count=%d", owner_id, len(created))
        return created

    # ------------------------------------------------------------------
    # seed_contacts — 生成测试数据
    # ------------------------------------------------------------------

    def seed_contacts(self, owner_id: int) -> int:
        """为指定用户生成测试联系人数据

        Returns:
            实际创建的联系人数量
        """
        sample_contacts = [
            {"name": "张伟", "phone": "13800138001", "company": "阿里巴巴", "position": "技术总监", "tags": "VIP,技术,合作伙伴"},
            {"name": "李娜", "phone": "13900139002", "company": "腾讯科技", "position": "产品经理", "tags": "客户,产品"},
            {"name": "王强", "phone": "13700137003", "company": "百度", "position": "销售总监", "tags": "潜在客户,销售"},
            {"name": "赵敏", "phone": "13600136004", "company": "京东集团", "position": "运营总监", "tags": "VIP,合作伙伴"},
            {"name": "刘洋", "phone": "13500135005", "company": "字节跳动", "position": "HRBP", "tags": "人力资源,潜在客户"},
            {"name": "陈静", "phone": "13400134006", "company": "华为技术", "position": "研发经理", "tags": "技术,合作伙伴"},
            {"name": "杨磊", "phone": "13300133007", "company": "小米科技", "position": "市场总监", "tags": "市场,潜在客户"},
            {"name": "黄丽", "phone": "13200132008", "company": "美团", "position": "商务拓展", "tags": "商务,客户"},
            {"name": "周杰", "phone": "13100131009", "company": "拼多多", "position": "供应链总监", "tags": "供应链,合作伙伴"},
            {"name": "吴芳", "phone": "13000130010", "company": "网易", "position": "产品运营", "tags": "运营,潜在客户"},
            {"name": "孙鹏", "phone": "15900159011", "company": "比亚迪", "position": "采购经理", "tags": "采购,客户"},
            {"name": "马小红", "phone": "15800158012", "company": "顺丰速运", "position": "区域总监", "tags": "物流,合作伙伴"},
        ]
        count = 0
        for data in sample_contacts:
            existing = (
                self.db.query(Contact)
                .filter(
                    Contact.owner_id == owner_id,
                    Contact.phone == data["phone"],
                    Contact.is_deleted == False,
                )
                .first()
            )
            if existing:
                continue
            contact = Contact(
                owner_id=owner_id,
                name=data["name"],
                phone=data["phone"],
                company=data["company"],
                position=data["position"],
                tags=data["tags"],
                source="seed",
            )
            self.db.add(contact)
            count += 1
        self.db.commit()
        logger.info("测试联系人生成完成: owner=%d, created=%d", owner_id, count)
        return count

    # ------------------------------------------------------------------
    # tags_helpers — 标签转换工具
    # ------------------------------------------------------------------

    @staticmethod
    def tags_str_to_list(tags_val: Optional[str]) -> list[str]:
        """将逗号分隔的标签字符串转为数组"""
        if not tags_val:
            return []
        if isinstance(tags_val, list):
            return tags_val
        return [t.strip() for t in tags_val.split(",") if t.strip()]
