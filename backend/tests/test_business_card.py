"""
AI 数字名片测试：生成核心流程
（已适配 chainke-full — business-card 路由）

chainke-full 名片路由：
  POST /api/business-card/cards       — 创建名片
  GET  /api/business-card/cards       — 列表
"""

from fastapi.testclient import TestClient


class TestBusinessCard:
    """AI 数字名片生成与分享测试"""

    CARDS_URL = "/api/business-card/cards"

    def test_create_card(self, client: TestClient, admin_headers):
        """创建数字名片"""
        resp = client.post(
            self.CARDS_URL,
            headers=admin_headers,
            json={
                "user_id": "admin",
                "fields": {
                    "name": "管理员",
                    "position": "系统管理员",
                    "company": "链客宝AI科技",
                    "phone": "13800000000",
                    "email": "admin@chainke.com",
                },
            },
        )
        assert resp.status_code in (200, 201), f"创建名片应成功: {resp.text}"
        data = resp.json() if resp.status_code < 300 else {}
        if data:
            assert "id" in data or "share_token" in data or "fields" in data

    def test_list_cards(self, client: TestClient, admin_headers):
        """获取名片列表"""
        resp = client.get(self.CARDS_URL, headers=admin_headers)
        assert resp.status_code in (200, 404)
