"""AI数字名片测试：生成/分享核心流程 + 边界条件"""
import json
import pytest
from fastapi.testclient import TestClient


class TestBusinessCard:
    """AI数字名片生成与分享测试"""

    def test_generate_card(self, client: TestClient, buyer_headers):
        """生成数字名片"""
        resp = client.post("/api/card/generate", headers=buyer_headers, json={
            "fields": {
                "name": "张三",
                "position": "CEO",
                "company": "创新科技有限公司",
                "phone": "13800000001",
                "email": "zhangsan@example.com",
                "wechat": "zhangsan_wx",
            }
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["share_token"] is not None
        assert data["data"]["share_url"] is not None
        assert data["data"]["name"] == "张三"
        # 验证持久化到数据库
        assert data["data"]["id"] is not None

    def test_get_card_by_token(self, client: TestClient, buyer_headers):
        """通过分享令牌获取名片（公开分享）"""
        # 先生成一张名片
        gen_resp = client.post("/api/card/generate", headers=buyer_headers, json={
            "fields": {
                "name": "李四",
                "position": "CTO",
                "company": "测试科技",
                "phone": "13800000002",
            }
        })
        assert gen_resp.status_code == 200
        share_token = gen_resp.json()["data"]["share_token"]

        # 通过 token 获取名片（无需认证）
        resp = client.get(f"/api/card/token/{share_token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["name"] == "李四"
        assert data["data"]["share_token"] == share_token
        assert "fields" in data["data"]
        assert data["data"]["fields"]["company"] == "测试科技"
        # 查看次数应递增
        assert data["data"]["view_count"] >= 1

    def test_get_card_invalid_token(self, client: TestClient):
        """使用无效的分享令牌获取名片应返回 404"""
        resp = client.get("/api/card/token/nonexistent_token_abc123")
        assert resp.status_code == 404
        data = resp.json()
        assert "不存在" in data.get("message", "") or "失效" in data.get("message", "")

    def test_get_nonexistent_card_by_id(self, client: TestClient):
        """获取不存在的名片 ID 返回 404"""
        resp = client.get("/api/card/99999")
        assert resp.status_code == 404

    def test_unauthorized_generate_card(self, client: TestClient):
        """未登录用户无法生成名片"""
        resp = client.post("/api/card/generate", json={
            "fields": {
                "name": "匿名用户",
                "company": "未知",
            }
        })
        assert resp.status_code in (401, 403)

    def test_list_my_cards(self, client: TestClient, buyer_headers):
        """获取当前用户的名片列表"""
        # 先生成一张名片
        gen_resp = client.post("/api/card/generate", headers=buyer_headers, json={
            "fields": {
                "name": "列表测试",
                "company": "列表公司",
                "phone": "13800000003",
            }
        })
        assert gen_resp.status_code == 200

        # 获取列表
        resp = client.get("/api/card", headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] >= 1
        assert any(item["name"] == "列表测试" for item in data["data"]["items"])
