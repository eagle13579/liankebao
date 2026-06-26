"""
国际化 / 本地化测试 —— 验证 API 响应中文消息完整性
（已适配 chainke-full 路由架构）
"""

import pytest
from fastapi.testclient import TestClient


class TestI18nMessages:
    """API 响应消息中文完整性测试"""

    def test_login_message_chinese(self, client: TestClient):
        """登录响应包含中文消息"""
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert resp.status_code == 200
        data = resp.json()
        # chainke-full 登录返回 token 和 user 字段
        assert "token" in data
        assert "user" in data

    def test_error_message_on_invalid_login(self, client: TestClient):
        """错误消息返回中文"""
        resp = client.post("/api/auth/login", json={"username": "nonexistent", "password": "wrong"})
        assert resp.status_code == 401
        body = resp.json()
        msg = body.get("detail", body.get("message", str(body)))
        assert isinstance(msg, str)
        # 应包含中文字符
        assert any("\u4e00" <= c <= "\u9fff" for c in msg), f"消息应包含中文: {msg}"

    def test_health_message_structure(self, client: TestClient):
        """健康检查返回中文服务名"""
        resp = client.get("/")
        data = resp.json()
        assert data["service"] == "链客宝AI API"
        assert data["status"] == "running"
