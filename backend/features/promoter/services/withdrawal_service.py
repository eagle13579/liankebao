"""
提现服务层 (Withdrawal Service)
================================
迁移自旧版链客宝 backend/modules/promoter/services/
提供提现申请的 CRUD 与审核管理。

用法:
    from features.promoter.services import WithdrawalService
    service = WithdrawalService(db)
    withdrawal = service.create_withdrawal(...)
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from features.promoter.models.withdrawal import Withdrawal

logger = logging.getLogger(__name__)


class WithdrawalService:
    """提现业务服务"""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # create_withdrawal — 创建提现申请
    # ------------------------------------------------------------------

    def create_withdrawal(
        self,
        user_id: int,
        amount: float,
        bank_info: Optional[str] = None,
    ) -> Withdrawal:
        """创建提现申请

        Args:
            user_id:    推广员 ID
            amount:     提现金额
            bank_info:  收款信息 JSON（可选）

        Returns:
            Withdrawal ORM 实例
        """
        withdrawal = Withdrawal(
            user_id=user_id,
            amount=amount,
            bank_info=bank_info,
            status="pending",
        )
        self.db.add(withdrawal)
        self.db.commit()
        self.db.refresh(withdrawal)
        logger.info(
            "提现申请创建成功: id=%d, user_id=%d, amount=%.2f",
            withdrawal.id,
            user_id,
            amount,
        )
        return withdrawal

    # ------------------------------------------------------------------
    # get_withdrawal — 查询单个提现申请
    # ------------------------------------------------------------------

    def get_withdrawal(self, withdrawal_id: int) -> Optional[Withdrawal]:
        """根据 ID 查询提现申请"""
        return self.db.query(Withdrawal).filter(Withdrawal.id == withdrawal_id).first()

    # ------------------------------------------------------------------
    # list_withdrawals — 提现列表（分页）
    # ------------------------------------------------------------------

    def list_withdrawals(
        self,
        page: int = 1,
        limit: int = 20,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> tuple[list[Withdrawal], int]:
        """分页查询提现列表

        Args:
            page:     页码，从 1 开始
            limit:    每页条数
            user_id:  按推广员过滤（可选）
            status:   按状态过滤（可选）

        Returns:
            (items, total) 元组
        """
        query = self.db.query(Withdrawal)

        if user_id is not None:
            query = query.filter(Withdrawal.user_id == user_id)
        if status is not None:
            query = query.filter(Withdrawal.status == status)

        total = query.count()
        items = (
            query.order_by(Withdrawal.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return items, total

    # ------------------------------------------------------------------
    # update_withdrawal — 更新提现申请信息
    # ------------------------------------------------------------------

    def update_withdrawal(
        self,
        withdrawal_id: int,
        bank_info: Optional[str] = None,
    ) -> Withdrawal:
        """更新提现申请信息（仅允许修改收款信息）

        Args:
            withdrawal_id:  提现 ID
            bank_info:      新的收款信息（可选）

        Returns:
            Withdrawal ORM 实例

        Raises:
            ValueError: 提现申请不存在
        """
        withdrawal = self.db.query(Withdrawal).filter(Withdrawal.id == withdrawal_id).first()
        if withdrawal is None:
            raise ValueError(f"提现申请不存在: id={withdrawal_id}")

        if bank_info is not None:
            withdrawal.bank_info = bank_info

        self.db.commit()
        self.db.refresh(withdrawal)
        logger.info("提现申请更新成功: id=%d", withdrawal_id)
        return withdrawal

    # ------------------------------------------------------------------
    # review_withdrawal — 审核提现申请
    # ------------------------------------------------------------------

    VALID_TRANSITIONS: dict[str, set[str]] = {
        "pending": {"approved", "rejected"},
        "approved": set(),
        "rejected": set(),
    }

    def review_withdrawal(
        self,
        withdrawal_id: int,
        new_status: str,
        reviewed_by: int,
        review_note: Optional[str] = None,
    ) -> Withdrawal:
        """审核提现申请（含状态机校验）

        Args:
            withdrawal_id:  提现 ID
            new_status:     目标状态 (approved/rejected)
            reviewed_by:    审核人 ID
            review_note:    审核备注（可选）

        Returns:
            Withdrawal ORM 实例

        Raises:
            ValueError: 提现申请不存在或状态转换非法
        """
        withdrawal = self.db.query(Withdrawal).filter(Withdrawal.id == withdrawal_id).first()
        if withdrawal is None:
            raise ValueError(f"提现申请不存在: id={withdrawal_id}")

        allowed = self.VALID_TRANSITIONS.get(withdrawal.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"非法状态转换: {withdrawal.status} → {new_status} "
                f"(允许: {', '.join(sorted(allowed)) or '无'})"
            )

        withdrawal.status = new_status
        withdrawal.reviewed_by = reviewed_by
        if review_note is not None:
            withdrawal.review_note = review_note

        self.db.commit()
        self.db.refresh(withdrawal)
        logger.info(
            "提现申请审核完成: id=%d, %s → %s (审核人=%d)",
            withdrawal_id,
            withdrawal.status,
            new_status,
            reviewed_by,
        )
        return withdrawal

    # ------------------------------------------------------------------
    # delete_withdrawal — 删除提现申请
    # ------------------------------------------------------------------

    def delete_withdrawal(self, withdrawal_id: int) -> None:
        """删除提现申请（物理删除）

        Args:
            withdrawal_id: 提现 ID

        Raises:
            ValueError: 提现申请不存在
        """
        withdrawal = self.db.query(Withdrawal).filter(Withdrawal.id == withdrawal_id).first()
        if withdrawal is None:
            raise ValueError(f"提现申请不存在: id={withdrawal_id}")

        self.db.delete(withdrawal)
        self.db.commit()
        logger.info("提现申请已删除: id=%d", withdrawal_id)
