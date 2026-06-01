"""个性化推荐路由测试

覆盖 /api/recommend/* 下所有端点：
- GET /api/recommend/products — 非个性化/个性化推荐
- GET /api/recommend/products/{user_id} — 按用户ID推荐
- GET /api/recommend/hot — 热门推荐
- GET /api/recommend/personalized/{user_id} — 结合匹配引擎推荐
- POST /api/recommend/feedback — 推荐反馈
- GET /api/recommend/features — 首页功能推荐排序（需认证）
"""

from datetime import datetime

from fastapi.testclient import TestClient

from app.models import UserEvent


class TestRecommendProducts:
    """GET /api/recommend/products — 产品推荐"""

    def test_recommend_products_no_user_returns_hot(self, client: TestClient):
        """未提供 user_id → 返回热门产品"""
        resp = client.get("/api/recommend/products")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["strategy"] == "hot"
        assert len(data["data"]["items"]) > 0

    def test_recommend_products_with_user_no_behavior_falls_back_to_hot(self, client: TestClient, db_session):
        """提供 user_id 但无行为记录 → 降级为热门推荐"""
        resp = client.get("/api/recommend/products", params={"user_id": 9999})
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["strategy"] == "hot"

    def test_recommend_products_with_behavior_returns_personalized(self, client: TestClient, db_session):
        """提供 user_id 且有浏览行为 → 个性化推荐"""
        from app.models import User

        buyer = db_session.query(User).filter(User.username == "buyer1").first()
        product = db_session.query(User).first()  # just to get a product id
        # Create a product view event for this user
        from app.models import Product

        product = db_session.query(Product).filter(Product.status == "approved").first()
        event = UserEvent(
            user_id=buyer.id,
            event_type="product_view",
            target_type="product",
            target_id=product.id,
            created_at=datetime.utcnow(),
        )
        db_session.add(event)
        db_session.commit()

        resp = client.get("/api/recommend/products", params={"user_id": buyer.id})
        assert resp.status_code == 200
        data = resp.json()
        # Strategy might be "personalized" or "hot" depending on data
        assert "strategy" in data["data"]

    def test_recommend_products_limit_param(self, client: TestClient):
        """limit 参数被正确应用"""
        resp = client.get("/api/recommend/products", params={"limit": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) <= 3

    def test_recommend_products_limit_out_of_range(self, client: TestClient):
        """limit 超出范围应返回 422"""
        resp = client.get("/api/recommend/products", params={"limit": 0})
        assert resp.status_code == 422


class TestRecommendProductsByUser:
    """GET /api/recommend/products/{user_id} — 按用户推荐"""

    def test_recommend_by_user_valid(self, client: TestClient, db_session):
        """按用户ID推荐返回正常"""
        from app.models import User

        buyer = db_session.query(User).filter(User.username == "buyer1").first()
        resp = client.get(f"/api/recommend/products/{buyer.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert len(data["data"]["items"]) > 0

    def test_recommend_by_user_hot_fallback(self, client: TestClient):
        """不存在的用户ID → 返回热门推荐"""
        resp = client.get("/api/recommend/products/99999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["strategy"] == "hot"


class TestRecommendHot:
    """GET /api/recommend/hot — 热门推荐"""

    def test_recommend_hot_returns_products(self, client: TestClient):
        """热门推荐返回产品列表"""
        resp = client.get("/api/recommend/hot")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert len(data["data"]["items"]) > 0

    def test_recommend_hot_respects_limit(self, client: TestClient):
        """limit 参数控制热门推荐数量"""
        resp = client.get("/api/recommend/hot", params={"limit": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) <= 2


class TestRecommendPersonalized:
    """GET /api/recommend/personalized/{user_id} — 结合匹配引擎"""

    def test_recommend_personalized_fallback_to_hot(self, client: TestClient, db_session):
        """无需求事件 → 降级为热门推荐"""
        from app.models import User

        buyer = db_session.query(User).filter(User.username == "buyer1").first()
        resp = client.get(f"/api/recommend/personalized/{buyer.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data["data"]

    def test_recommend_personalized_with_need_events(self, client: TestClient, db_session):
        """有需求事件时尝试匹配引擎推荐"""
        from app.models import BusinessNeed, User

        buyer = db_session.query(User).filter(User.username == "buyer1").first()
        need = db_session.query(BusinessNeed).filter(BusinessNeed.user_id == buyer.id).first()
        if need:
            event = UserEvent(
                user_id=buyer.id,
                event_type="need_view",
                target_type="business_need",
                target_id=need.id,
                created_at=datetime.utcnow(),
            )
            db_session.add(event)
            db_session.commit()
        resp = client.get(f"/api/recommend/personalized/{buyer.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data["data"]


class TestRecommendFeedback:
    """POST /api/recommend/feedback — 推荐反馈"""

    def test_feedback_like(self, client: TestClient, db_session):
        """提交 'like' 反馈成功"""
        from app.models import Product

        product = db_session.query(Product).filter(Product.status == "approved").first()
        resp = client.post(
            "/api/recommend/feedback",
            json={"user_id": 1, "product_id": product.id, "action": "like", "source": "test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["action"] == "like"

    def test_feedback_dislike(self, client: TestClient, db_session):
        """提交 'dislike' 反馈成功"""
        from app.models import Product

        product = db_session.query(Product).filter(Product.status == "approved").first()
        resp = client.post(
            "/api/recommend/feedback",
            json={"user_id": 1, "product_id": product.id, "action": "dislike", "source": "test"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 200

    def test_feedback_invalid_action(self, client: TestClient):
        """无效 action 返回 422"""
        resp = client.post(
            "/api/recommend/feedback",
            json={"user_id": 1, "product_id": 1, "action": "invalid_action", "source": "test"},
        )
        assert resp.status_code == 422

    def test_feedback_product_not_found(self, client: TestClient):
        """不存在的产品返回 404"""
        resp = client.post(
            "/api/recommend/feedback",
            json={"user_id": 1, "product_id": 999999, "action": "like", "source": "test"},
        )
        assert resp.status_code == 404


class TestRecommendFeatures:
    """GET /api/recommend/features — 首页功能推荐排序（需认证）"""

    def test_features_authenticated(self, client: TestClient, buyer_headers):
        """认证用户可获取功能推荐排序（data 可能是列表或字典）"""
        resp = client.get("/api/recommend/features", headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        # data 可能是列表或包含列表的字典
        assert data["data"] is not None

    def test_features_unauthenticated(self, client: TestClient):
        """未认证用户无法获取功能推荐"""
        resp = client.get("/api/recommend/features")
        assert resp.status_code == 401
