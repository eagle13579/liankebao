"""
链客宝 — 短信/邮件通知服务模块测试
===================================
测试覆盖:
  1. EmailSender 配置检测（未配置时降级）
  2. EmailSender 发送（mock SMTP）
  3. SMSSender 配置检测（未配置时降级）
  4. SMSSender 发送（mock HTTP/SDK）
  5. NotificationManager 统一接口（双渠道）
  6. NotificationManager.get_history
  7. NotificationRecord ORM 模型存取
  8. API POST /api/notifications/send
  9. API GET /api/notifications/{user_id}/history
  10. API 参数校验（无效渠道）
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch, PropertyMock

# 确保项目根目录在 sys.path
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.notification_service import (
    EmailSender,
    SMSSender,
    NotificationManager,
    NotificationRecord,
    register_user_contact,
    get_user_contact,
    get_notification_manager,
    REQUESTS_AVAILABLE,
)


# ===================================================================
# 测试辅助
# ===================================================================

def setup_module():
    """创建测试表"""
    Base.metadata.create_all(bind=engine)


def teardown_module():
    """清理数据"""
    db = SessionLocal()
    try:
        db.query(NotificationRecord).delete()
        db.commit()
    finally:
        db.close()


def _make_app() -> FastAPI:
    """构建含通知路由的 FastAPI 测试应用"""
    app = FastAPI(title="链客宝 Notification Test")
    try:
        from app.routers.notification_router import router
        if router is not None:
            app.include_router(router)
    except ImportError:
        raise RuntimeError("notification_router 未正确加载")
    return app


# ===================================================================
# TC1: EmailSender 配置检测
# ===================================================================

def test_email_sender_disabled_when_no_config():
    """TC1: 无 SMTP 配置时 is_enabled() 返回 False"""
    # 清除所有邮件相关环境变量
    with patch.dict(os.environ, {
        "SMTP_HOST": "",
        "SMTP_PORT": "",
        "SMTP_USER": "",
        "SMTP_PASS": "",
    }):
        sender = EmailSender()
        assert sender.is_enabled() is False
        assert sender.send("test@example.com", "Test", "Body") is False
    print("  ✓ TC1: 无配置时邮件发送器正确降级")


def test_email_sender_enabled_when_configured():
    """TC2: 有 SMTP 配置时 is_enabled() 返回 True"""
    with patch.dict(os.environ, {
        "SMTP_HOST": "smtp.test.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "user@test.com",
        "SMTP_PASS": "password123",
    }):
        sender = EmailSender()
        assert sender.is_enabled() is True
        assert sender.host == "smtp.test.com"
        assert sender.port == 587
        assert sender.user == "user@test.com"
    print("  ✓ TC2: 有配置时邮件发送器正确启用")


# ===================================================================
# TC3: EmailSender 发送 (mock)
# ===================================================================

def test_email_sender_send_success():
    """TC3: mock SMTP 发送成功"""
    with patch("app.notification_service.smtplib.SMTP") as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_instance

        sender = EmailSender()
        sender._enabled = True
        sender.user = "sender@test.com"
        sender.host = "smtp.test.com"
        sender.port = 587

        result = sender.send(
            to_email="recipient@test.com",
            subject="Hello",
            body="Test message",
        )
        assert result is True
        mock_instance.sendmail.assert_called_once()
        print("  ✓ TC3: mock SMTP 发送成功")


def test_email_sender_send_empty_recipient():
    """TC4: 空收件人时返回 False"""
    sender = EmailSender()
    sender._enabled = True
    assert sender.send("", "Subject", "Body") is False
    print("  ✓ TC4: 空收件人正确返回 False")


# ===================================================================
# TC5: SMSSender 配置检测
# ===================================================================

def test_sms_sender_disabled_when_no_config():
    """TC5: 无阿里云配置时 is_enabled() 返回 False"""
    with patch.dict(os.environ, {
        "ALIYUN_SMS_ACCESS_KEY": "",
        "ALIYUN_SMS_SECRET_KEY": "",
    }):
        sender = SMSSender()
        assert sender.is_enabled() is False
        assert sender.send("13800138000") is False
    print("  ✓ TC5: 无配置时短信发送器正确降级")


# ===================================================================
# TC6: SMSSender 发送 (mock SDK)
# ===================================================================

def test_sms_sender_sdk_success():
    """TC6: mock 阿里云 SDK 发送成功"""
    with patch("app.notification_service.SMSSender._try_sdk_send") as mock_sdk:
        mock_sdk.return_value = True
        sender = SMSSender()
        sender._enabled = True
        result = sender.send("13800138000", {"code": "123456"})
        assert result is True
        mock_sdk.assert_called_once_with("13800138000", {"code": "123456"})
    print("  ✓ TC6: mock SDK 发送成功")


def test_sms_sender_http_fallback():
    """TC7: SDK 不可用时降级到 HTTP API"""
    if not REQUESTS_AVAILABLE:
        print("  ✓ TC7: requests 不可用，跳过 HTTP 降级测试")
        return

    mock_response = MagicMock()
    mock_response.json.return_value = {"Code": "OK"}

    with patch("app.notification_service.SMSSender._try_sdk_send", return_value=False), \
         patch("app.notification_service._requests.post", return_value=mock_response):
        sender = SMSSender()
        sender._enabled = True
        sender.access_key = "test_key"
        sender.secret_key = "test_secret"
        result = sender.send("13800138000", {"code": "654321"})
        assert result is True
    print("  ✓ TC7: HTTP 降级发送成功")


# ===================================================================
# TC8: NotificationManager 统一接口
# ===================================================================

def test_manager_send_email_only():
    """TC8: 仅邮件渠道发送"""
    register_user_contact("user_email_only", email="u@test.com")

    mgr = NotificationManager()
    mgr.email_sender._enabled = True
    mgr.sms_sender._enabled = True

    with patch.object(mgr.email_sender, "send", return_value=True) as mock_email:
        results = mgr.send("user_email_only", "Title", "Body", channels=["email"])
        assert results == {"email": True}
        mock_email.assert_called_once_with(
            to_email="u@test.com", subject="Title", body="Body"
        )
    print("  ✓ TC8: 仅邮件渠道发送成功")


def test_manager_send_dual_channels():
    """TC9: 双渠道发送"""
    register_user_contact("user_dual", email="u@test.com", phone="13800138001")

    mgr = NotificationManager()
    mgr.email_sender._enabled = True
    mgr.sms_sender._enabled = True

    with patch.object(mgr.email_sender, "send", return_value=True), \
         patch.object(mgr.sms_sender, "send", return_value=True):
        results = mgr.send("user_dual", "Title", "验证码 123456", channels=["email", "sms"])
        assert results.get("email") is True
        assert results.get("sms") is True
    print("  ✓ TC9: 双渠道发送成功")


def test_manager_send_no_contact():
    """TC10: 无联系方式时返回 False"""
    results = NotificationManager().send("nonexistent_user", "Test", "Body")
    for ch, ok in results.items():
        assert ok is False
    print("  ✓ TC10: 无联系方式正确返回 False")


# ===================================================================
# TC11: NotificationManager.get_history
# ===================================================================

def test_manager_get_history():
    """TC11: 查询通知历史"""
    mgr = NotificationManager()
    register_user_contact("hist_user", email="h@test.com", phone="13800138002")
    mgr.email_sender._enabled = True
    mgr.sms_sender._enabled = True

    with patch.object(mgr.email_sender, "send", return_value=True), \
         patch.object(mgr.sms_sender, "send", return_value=True):
        mgr.send("hist_user", "Title1", "Body1")
        mgr.send("hist_user", "Title2", "Body2", channels=["sms"])

    history = mgr.get_history("hist_user")
    assert len(history) >= 2
    assert history[0]["user_id"] == "hist_user"
    print(f"  ✓ TC11: 查询到 {len(history)} 条历史记录")


# ===================================================================
# TC12: NotificationRecord ORM 模型
# ===================================================================

def test_notification_record_orm():
    """TC12: ORM 模型创建与查询"""
    db = SessionLocal()
    try:
        record = NotificationRecord(
            user_id="orm_test",
            channel="email",
            title="ORM Test",
            body="This is a test",
            status="success",
        )
        db.add(record)
        db.commit()
        assert record.id is not None

        fetched = db.query(NotificationRecord).filter(
            NotificationRecord.id == record.id
        ).first()
        assert fetched is not None
        assert fetched.user_id == "orm_test"
        assert fetched.channel == "email"

        d = fetched.to_dict()
        assert d["user_id"] == "orm_test"
        assert d["status"] == "success"
    finally:
        db.close()
    print("  ✓ TC12: ORM 模型存取正常")


# ===================================================================
# TC13-14: API 端点测试
# ===================================================================

@pytest.fixture
def test_client():
    app = _make_app()
    with TestClient(app) as client:
        yield client


def test_api_send_notification(test_client):
    """TC13: POST /api/notifications/send"""
    register_user_contact("api_user", email="api@test.com", phone="13800138003")

    payload = {
        "user_id": "api_user",
        "title": "API Test",
        "body": "Hello from API",
        "channels": ["email"],
    }

    with patch("app.notification_service.EmailSender.send", return_value=True):
        resp = test_client.post("/api/notifications/send", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "api_user"
        assert len(data["results"]) == 1
        assert data["results"][0]["channel"] == "email"
        assert data["results"][0]["success"] is True
    print("  ✓ TC13: POST /api/notifications/send 正常")


def test_api_send_invalid_channel(test_client):
    """TC14: POST 无效渠道应返回 422"""
    payload = {
        "user_id": "test_user",
        "title": "Test",
        "body": "Body",
        "channels": ["email", "wechat"],
    }
    resp = test_client.post("/api/notifications/send", json=payload)
    assert resp.status_code == 422
    print("  ✓ TC14: 无效渠道正确返回 422")


def test_api_send_empty_channels(test_client):
    """TC15: POST 空渠道列表应返回 422"""
    payload = {
        "user_id": "test_user",
        "title": "Test",
        "body": "Body",
        "channels": [],
    }
    resp = test_client.post("/api/notifications/send", json=payload)
    assert resp.status_code == 422
    print("  ✓ TC15: 空渠道列表正确返回 422")


def test_api_get_history(test_client):
    """TC16: GET /api/notifications/{user_id}/history"""
    register_user_contact("hist_api", email="hist@test.com", phone="13800138004")
    mgr = get_notification_manager()
    mgr.email_sender._enabled = True
    mgr.sms_sender._enabled = True

    with patch.object(mgr.email_sender, "send", return_value=True), \
         patch.object(mgr.sms_sender, "send", return_value=True):
        mgr.send("hist_api", "History Test", "Body", channels=["email"])

    resp = test_client.get("/api/notifications/hist_api/history?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    print(f"  ✓ TC16: GET history 返回 {len(data['items'])} 条记录")


# ===================================================================
# 入口
# ===================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("链客宝 — 短信/邮件通知服务模块测试")
    print("=" * 50)

    setup_module()

    tests = [
        test_email_sender_disabled_when_no_config,
        test_email_sender_enabled_when_configured,
        test_email_sender_send_success,
        test_email_sender_send_empty_recipient,
        test_sms_sender_disabled_when_no_config,
        test_sms_sender_sdk_success,
        test_sms_sender_http_fallback,
        test_manager_send_email_only,
        test_manager_send_dual_channels,
        test_manager_send_no_contact,
        test_manager_get_history,
        test_notification_record_orm,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: FAILED — {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    # API tests need the FastAPI test client
    print()
    print("-" * 50)
    print("API 端点测试 (pytest fixtures)")
    print("-" * 50)
    # pytest will run these separately

    teardown_module()

    print()
    print("=" * 50)
    print(f"结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 测试用例")
    print("=" * 50)
    sys.exit(1 if failed > 0 else 0)
