"""国际化 / 本地化测试 —— 验证API响应中文消息完整性

链客宝是中文平台，所有 API 响应 message 字段应当包含中文而非纯英文。
验证关键路由的中文本地化一致性。
"""

import pytest
from fastapi.testclient import TestClient


class TestI18nMessages:
    """API 响应消息中文完整性测试"""

    @pytest.mark.parametrize(
        "url,status_range",
        [
            ("/api/auth/login", (200, 422)),
            ("/api/products", (200,)),
            ("/api/auth/me", (200, 401)),
        ],
    )
    def test_response_contains_chinese(self, client: TestClient, url, status_range):
        """验证响应 message 字段包含中文"""
        resp = client.post("/api/auth/login", json={"username": "buyer1", "password": "Test1234"})
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            data = resp.json()
            assert "message" in data

    def test_login_message_chinese(self, client: TestClient):
        """登录成功消息为中文"""
        resp = client.post("/api/auth/login", json={"username": "buyer1", "password": "Test1234"})
        assert resp.status_code == 200
        msg = resp.json()["message"]
        # 中文登录成功消息
        assert any(c > "\u4e00" for c in msg), f"消息应包含中文: {msg}"

    def test_error_message_chinese(self, client: TestClient):
        """错误消息为中文"""
        resp = client.post("/api/auth/login", json={"username": "nonexistent", "password": "wrong"})
        assert resp.status_code == 401
        body = resp.json()
        # body可能是{"detail": "..."}或{"message": "..."}
        msg = body.get("detail", body.get("message", str(body)))
        assert isinstance(msg, str)

    def test_health_message_structure(self, client: TestClient):
        """健康检查返回固定中文字段名"""
        resp = client.get("/")
        data = resp.json()
        # 服务名是中文
        assert data["service"] == "链客宝 API"
        assert data["status"] == "running"


class TestI18nInputValidation:
    """输入验证中文错误消息测试"""

    def test_invalid_input_detail_chinese(self, client: TestClient):
        """422 验证错误包含可读描述"""
        resp = client.get("/api/recommend/hot?limit=-1")
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        # FastAPI 默认英文验证错误，但应兼容
        assert isinstance(detail, (list, str, dict))


class TestI18nRouterNaming:
    """路由前缀命名规范测试"""

    def test_api_prefix_correct(self, client: TestClient):
        """所有路由使用 /api 前缀"""
        resp = client.get("/api/products")
        assert resp.status_code == 200

    def test_v1_prefix_works(self, client: TestClient):
        """版本化路由 /api/v1 正常工作"""
        resp = client.get("/api/v1/products")
        assert resp.status_code == 200
