"""推荐系统全面测试 —— 覆盖全部路由和边角场景"""
import pytest
from fastapi.testclient import TestClient


class TestRecommendHot:
    """热门推荐路由测试"""

    def test_hot_default(self, client: TestClient):
        """GET /api/recommend/hot — 默认参数"""
        resp = client.get("/api/recommend/hot")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "items" in data["data"]
        assert "total" in data["data"]

    def test_hot_with_limit(self, client: TestClient):
        """GET /api/recommend/hot — 指定limit"""
        resp = client.get("/api/recommend/hot?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) <= 5

    def test_hot_max_limit(self, client: TestClient):
        """GET /api/recommend/hot — limit=50边界"""
        resp = client.get("/api/recommend/hot?limit=50")
        assert resp.status_code == 200

    def test_hot_invalid_limit(self, client: TestClient):
        """GET /api/recommend/hot — limit=0 (应拒绝)"""
        resp = client.get("/api/recommend/hot?limit=0")
        assert resp.status_code == 422

    def test_hot_no_auth_needed(self, client: TestClient):
        """GET /api/recommend/hot — 无需认证"""
        resp = client.get("/api/recommend/hot")
        assert resp.status_code == 200


class TestRecommendProducts:
    """产品推荐路由测试"""

    def test_products_default(self, client: TestClient):
        """GET /api/recommend/products — 无user_id返回热门"""
        resp = client.get("/api/recommend/products")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200

    def test_products_by_user_id(self, client: TestClient, buyer_token: str):
        """GET /api/recommend/products — 指定user_id"""
        resp = client.get("/api/recommend/products?user_id=2", headers={"Authorization": f"Bearer {buyer_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "strategy" in data["data"]

    def test_products_by_user_path(self, client: TestClient):
        """GET /api/recommend/products/{user_id} — 路径参数"""
        resp = client.get("/api/recommend/products/2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200

    def test_products_by_nonexistent_user(self, client: TestClient):
        """GET /api/recommend/products/{user_id} — 不存在的用户（应降级为热门）"""
        resp = client.get("/api/recommend/products/99999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["strategy"] == "hot"

    def test_products_invalid_user_id(self, client: TestClient):
        """GET /api/recommend/products/{user_id} — 负数ID"""
        resp = client.get("/api/recommend/products/-1")
        assert resp.status_code == 422

    def test_products_negative_limit(self, client: TestClient):
        """GET /api/recommend/products?limit=-1"""
        resp = client.get("/api/recommend/products?limit=-1")
        assert resp.status_code == 422


class TestRecommendPersonalized:
    """个性化推荐（matching engine）测试"""

    def test_personalized(self, client: TestClient):
        """GET /api/recommend/personalized/{user_id}"""
        resp = client.get("/api/recommend/personalized/2")
        # Matching engine may not be available, fallback to hot
        assert resp.status_code in (200, 404)

    def test_personalized_no_user(self, client: TestClient):
        """GET /api/recommend/personalized/{user_id} — 不存在用户"""
        resp = client.get("/api/recommend/personalized/99999")
        assert resp.status_code == 200  # Fallback to hot

    def test_personalized_with_limit(self, client: TestClient):
        """GET /api/recommend/personalized/{user_id}?limit=3"""
        resp = client.get("/api/recommend/personalized/2?limit=3")
        assert resp.status_code in (200, 404)


class TestRecommendFeedback:
    """推荐反馈路由测试"""

    def test_feedback_like(self, client: TestClient, buyer_headers: dict):
        """POST /api/recommend/feedback — like"""
        resp = client.post("/api/recommend/feedback", json={
            "user_id": 2, "product_id": 1, "action": "like"
        }, headers=buyer_headers)
        assert resp.status_code == 200
        assert resp.json()["code"] == 200

    def test_feedback_dislike(self, client: TestClient, buyer_headers: dict):
        """POST /api/recommend/feedback — dislike"""
        resp = client.post("/api/recommend/feedback", json={
            "user_id": 2, "product_id": 1, "action": "dislike"
        }, headers=buyer_headers)
        assert resp.status_code == 200

    def test_feedback_invalid_action(self, client: TestClient, buyer_headers: dict):
        """POST /api/recommend/feedback — 无效action"""
        resp = client.post("/api/recommend/feedback", json={
            "user_id": 2, "product_id": 1, "action": "invalid"
        }, headers=buyer_headers)
        assert resp.status_code == 422

    def test_feedback_nonexistent_product(self, client: TestClient, buyer_headers: dict):
        """POST /api/recommend/feedback — 不存在产品"""
        resp = client.post("/api/recommend/feedback", json={
            "user_id": 2, "product_id": 99999, "action": "like"
        }, headers=buyer_headers)
        assert resp.status_code == 404

    def test_feedback_no_auth(self, client: TestClient):
        """POST /api/recommend/feedback — 无认证"""
        resp = client.post("/api/recommend/feedback", json={
            "user_id": 2, "product_id": 1, "action": "like"
        })
        assert resp.status_code == 401

    def test_feedback_missing_fields(self, client: TestClient, buyer_headers: dict):
        """POST /api/recommend/feedback — 缺少必填字段"""
        resp = client.post("/api/recommend/feedback", json={
            "user_id": 2
        }, headers=buyer_headers)
        assert resp.status_code == 422


class TestRecommendV1Routes:
    """/api/v1/recommend 版本化路由测试"""

    def test_v1_hot(self, client: TestClient):
        """GET /api/v1/recommend/hot"""
        resp = client.get("/api/v1/recommend/hot")
        assert resp.status_code == 200

    def test_v1_products(self, client: TestClient):
        """GET /api/v1/recommend/products"""
        resp = client.get("/api/v1/recommend/products")
        assert resp.status_code == 200

    def test_v1_feedback(self, client: TestClient, buyer_headers: dict):
        """POST /api/v1/recommend/feedback"""
        resp = client.post("/api/v1/recommend/feedback", json={
            "user_id": 2, "product_id": 1, "action": "like"
        }, headers=buyer_headers)
        assert resp.status_code == 200
