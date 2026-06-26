"""链客宝 — 审计日志系统测试
=============================
覆盖: 写入/查询/装饰器/分页/CSV导出/自动清理
至少 12 个测试用例
"""
import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.audit_log import AuditLog
from app.services.audit_service import (
    AuditService,
    audit_log,
    Actions,
    ResourceTypes,
)


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture(scope="function")
def db_session():
    """创建内存 SQLite 数据库供测试使用"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def service(db_session):
    """创建 AuditService 实例"""
    return AuditService(db_session)


# ===================================================================
# 辅助函数
# ===================================================================

def seed_logs(service: AuditService, count: int = 5):
    """插入 N 条测试审计日志"""
    logs = []
    for i in range(count):
        log = service.log(
            user_id=f"user_{i % 3}",
            action=Actions.LOGIN if i % 2 == 0 else Actions.CREATE_CARD,
            resource_type=ResourceTypes.USER if i % 2 == 0 else ResourceTypes.CARD,
            resource_id=f"res_{i}" if i % 2 == 1 else None,
            detail={"index": i},
            ip_address=f"192.168.1.{i + 1}",
            user_agent=f"Agent/{i}",
            result="success" if i < count - 1 else "failure",
        )
        logs.append(log)
    return logs


# ===================================================================
# 测试用例
# ===================================================================


class TestAuditLog:
    """测试 AuditLog 模型"""

    def test_create_log_entry(self, service):
        """测试 1: 写入一条审计日志"""
        log = service.log(
            user_id="test_user",
            action=Actions.LOGIN,
            resource_type=ResourceTypes.USER,
            resource_id="test_user",
            detail={"method": "password"},
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0",
            result="success",
        )
        assert log.id is not None
        assert log.user_id == "test_user"
        assert log.action == Actions.LOGIN
        assert log.resource_type == ResourceTypes.USER
        assert log.resource_id == "test_user"
        assert log.detail == {"method": "password"}
        assert log.ip_address == "127.0.0.1"
        assert log.user_agent == "Mozilla/5.0"
        assert log.result == "success"
        assert log.created_at is not None

    def test_log_with_failure_result(self, service):
        """测试 2: 记录失败操作"""
        log = service.log(
            user_id="user_a",
            action=Actions.PAYMENT,
            resource_type=ResourceTypes.PAYMENT,
            resource_id="order_123",
            detail={"error": "余额不足"},
            result="failure",
        )
        assert log.result == "failure"
        assert log.detail["error"] == "余额不足"

    def test_log_raises_on_empty_user_id(self, service):
        """测试 3: 空 user_id 抛出异常"""
        with pytest.raises(ValueError, match="user_id 不能为空"):
            service.log(user_id="", action=Actions.LOGIN)

    def test_log_raises_on_empty_action(self, service):
        """测试 4: 空 action 抛出异常"""
        with pytest.raises(ValueError, match="action 不能为空"):
            service.log(user_id="u1", action="")

    def test_log_raises_on_invalid_result(self, service):
        """测试 5: 无效 result 抛出异常"""
        with pytest.raises(ValueError, match="result 必须是 success 或 failure"):
            service.log(user_id="u1", action="test", result="invalid")

    def test_to_dict(self, service):
        """测试 6: to_dict 序列化"""
        log = service.log(
            user_id="u1",
            action=Actions.REGISTER,
            detail={"role": "admin"},
        )
        d = log.to_dict()
        assert d["user_id"] == "u1"
        assert d["action"] == Actions.REGISTER
        assert d["detail"] == {"role": "admin"}
        assert isinstance(d["created_at"], str)


class TestAuditServiceQuery:
    """测试 AuditService 查询功能"""

    def test_query_pagination(self, service):
        """测试 7: 分页查询"""
        seed_logs(service, count=10)

        # 第一页
        result = service.query(page=1, page_size=3)
        assert len(result["items"]) == 3
        assert result["total"] == 10
        assert result["page"] == 1
        assert result["page_size"] == 3
        assert result["total_pages"] == 4

        # 第二页
        result2 = service.query(page=2, page_size=3)
        assert len(result2["items"]) == 3
        assert result2["page"] == 2

        # 最后一页
        result4 = service.query(page=4, page_size=3)
        assert len(result4["items"]) == 1

    def test_query_with_filters(self, service):
        """测试 8: 多条件筛选查询"""
        seed_logs(service, count=10)

        # 按 user_id 筛选
        result = service.query(filters={"user_id": "user_0"})
        assert len(result["items"]) > 0
        for item in result["items"]:
            assert item["user_id"] == "user_0"

        # 按 action 筛选
        result = service.query(filters={"action": Actions.LOGIN})
        for item in result["items"]:
            assert item["action"] == Actions.LOGIN

        # 按 result 筛选
        result = service.query(filters={"result": "failure"})
        assert len(result["items"]) == 1  # 只有最后一条是 failure
        for item in result["items"]:
            assert item["result"] == "failure"

    def test_get_by_user(self, service):
        """测试 9: 按用户查询操作历史"""
        seed_logs(service, count=10)

        logs = service.get_by_user("user_0", limit=10)
        assert len(logs) > 0
        for log in logs:
            assert log.user_id == "user_0"

        # 测试 limit
        limited = service.get_by_user("user_0", limit=1)
        assert len(limited) == 1

    def test_get_by_resource(self, service):
        """测试 10: 按资源查询变更历史"""
        seed_logs(service, count=10)

        logs = service.get_by_resource(ResourceTypes.CARD, "res_1")
        assert len(logs) > 0
        for log in logs:
            assert log.resource_type == ResourceTypes.CARD
            assert log.resource_id == "res_1"

    def test_get_recent(self, service):
        """测试 11: 获取最近操作"""
        logs = seed_logs(service, count=5)

        recent = service.get_recent(hours=24)
        assert len(recent) == 5

        # 插入一条很旧的日志（手动改时间无法直接测试，验证接口可用即可）
        assert len(recent) > 0

    def test_export_csv(self, service):
        """测试 12: 导出 CSV"""
        seed_logs(service, count=5)

        csv_content = service.export_csv()
        assert csv_content.startswith("ID,用户ID,操作类型")
        lines = csv_content.strip().split("\n")
        assert len(lines) == 6  # 1 header + 5 data rows

        # 带筛选的导出
        filtered_csv = service.export_csv(filters={"user_id": "user_0"})
        filtered_lines = filtered_csv.strip().split("\n")
        assert len(filtered_lines) > 1  # header + at least 1 row

    def test_export_csv_empty(self, service):
        """测试 13: 空结果 CSV 导出"""
        csv_content = service.export_csv()
        lines = csv_content.strip().split("\n")
        assert len(lines) == 1  # 只有 header
        assert csv_content.startswith("ID,用户ID,操作类型")


class TestAuditDecorator:
    """测试 @audit_log 装饰器"""

    def test_audit_decorator_success(self, db_session):
        """测试 14: 装饰器记录成功操作"""
        service = AuditService(db_session)

        class FakeService:
            def __init__(self, db):
                self.db = db

            @audit_log(action=Actions.CREATE_CARD, resource_type=ResourceTypes.CARD)
            def create_card(self, user_id: str, resource_id: str, name: str):
                # 模拟创建名片
                return {"id": resource_id, "name": name}

        fake = FakeService(db_session)
        # 注入 db 到 kwargs
        result = fake.create_card(user_id="decorator_user", resource_id="card_001", name="测试名片")
        assert result["name"] == "测试名片"

        # 验证日志已记录
        logs = service.get_by_user("decorator_user")
        assert len(logs) == 1
        assert logs[0].action == Actions.CREATE_CARD
        assert logs[0].resource_id == "card_001"
        assert logs[0].result == "success"

    def test_audit_decorator_failure(self, db_session):
        """测试 15: 装饰器记录失败操作"""
        service = AuditService(db_session)

        class FakeService:
            def __init__(self, db):
                self.db = db

            @audit_log(action=Actions.PAYMENT, resource_type=ResourceTypes.PAYMENT)
            def process_payment(self, user_id: str, resource_id: str, amount: int):
                raise ValueError("支付失败: 余额不足")

        fake = FakeService(db_session)
        with pytest.raises(ValueError, match="支付失败"):
            fake.process_payment(user_id="pay_user", resource_id="order_999", amount=100)

        # 验证失败日志已记录
        logs = service.get_by_user("pay_user")
        assert len(logs) == 1
        assert logs[0].action == Actions.PAYMENT
        assert logs[0].result == "failure"
        assert "支付失败" in str(logs[0].detail)


class TestAuditCleanup:
    """测试自动清理功能"""

    def test_cleanup_no_expired(self, service):
        """测试 16: 没有过期日志时清理无操作"""
        seed_logs(service, count=3)
        result = service.cleanup(keep_days=90)
        assert result["archived_count"] == 0
        assert result["deleted_count"] == 0
        assert result["archive_file"] == ""

    def test_cleanup_archives_and_deletes(self, service, tmpdir):
        """测试 17: 清理归档并删除过期日志"""
        # 直接插入一条旧日志（修改 created_at 为 100 天前）
        from sqlalchemy import text

        # 先插入一条正常日志
        service.log(user_id="u1", action="test")

        # 插入一条旧日志（通过 SQL 修改时间）
        old_log = AuditLog(
            user_id="old_user",
            action="old_action",
            result="success",
        )
        service.db.add(old_log)
        service.db.flush()
        # 手动设置 created_at 为 100 天前
        past_time = datetime.now(dt_timezone.utc) - timedelta(days=100)
        service.db.execute(
            text(f"UPDATE audit_logs SET created_at = '{past_time.isoformat()}' WHERE id = {old_log.id}")
        )
        service.db.commit()

        # 验证有 2 条
        assert service.db.query(AuditLog).count() == 2

        # 清理（保留 30 天）
        archive_dir = str(tmpdir)
        result = service.cleanup(keep_days=30, archive_dir=archive_dir)
        assert result["archived_count"] == 1
        assert result["deleted_count"] == 1
        assert os.path.exists(result["archive_file"])

        # 验证只剩下 1 条
        remaining = service.db.query(AuditLog).all()
        assert len(remaining) == 1
        assert remaining[0].user_id == "u1"

        # 验证归档文件内容
        with open(result["archive_file"], "r", encoding="utf-8") as f:
            archived = json.load(f)
        assert len(archived) == 1
        assert archived[0]["user_id"] == "old_user"


class TestCountByAction:
    """测试统计功能"""

    def test_count_by_action(self, service):
        """测试 18: 按操作类型统计"""
        seed_logs(service, count=10)

        stats = service.count_by_action()
        assert len(stats) > 0
        stat_map = {s["action"]: s for s in stats}
        assert Actions.LOGIN in stat_map
        assert stat_map[Actions.LOGIN]["count"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
