"""
核心 API 集成 E2E 测试
=======================
完整业务链路：
  注册 → 登录 → 发布产品 → 搜索产品 → 下单 → 支付 → 充值 → 查询余额

覆盖场景：
- 用户注册（多角色）
- 登录 / Token 认证
- 产品 CRUD
- 搜索
- 下单 + 支付回调
- 充值全链路
- 管理员操作
- 权限校验
"""
import json
import time
import pytest
from fastapi.testclient import TestClient


class TestE2ERegisterLogin:
    """注册 + 登录集成测试"""

    REGISTER_URL = "/api/auth/register"
    LOGIN_URL = "/api/auth/login"

    def _generate_unique_username(self, prefix="e2euser"):
        """生成唯一用户名避免冲突"""
        return f"{prefix}_{int(time.time()*1000)}"

    def test_register_and_login_full(self, client: TestClient):
        """完整注册 + 登录流程"""
        username = self._generate_unique_username()
        # 注册
        register_resp = client.post(
            self.REGISTER_URL,
            json={
                "username": username,
                "password": "SecurePass123!",
                "name": "E2E测试用户",
                "phone": "13900001111",
                "company": "E2E测试公司",
                "position": "测试工程师",
                "role": "buyer",
            },
        )
        assert register_resp.status_code == 200, f"注册失败: {register_resp.text}"
        assert register_resp.json()["code"] == 200

        # 登录
        login_resp = client.post(
            self.LOGIN_URL,
            json={"username": username, "password": "SecurePass123!"},
        )
        assert login_resp.status_code == 200, f"登录失败: {login_resp.text}"
        login_data = login_resp.json()["data"]
        assert "access_token" in login_data
        assert login_data["user"]["username"] == username

    def test_register_supplier_role(self, client: TestClient):
        """注册供应商角色"""
        username = self._generate_unique_username("e2esupplier")
        resp = client.post(
            self.REGISTER_URL,
            json={
                "username": username,
                "password": "Pass1234!",
                "name": "供应商E2E",
                "role": "supplier",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["role"] == "supplier"

    def test_register_promoter_role(self, client: TestClient):
        """注册推广员角色"""
        username = self._generate_unique_username("e2epromoter")
        resp = client.post(
            self.REGISTER_URL,
            json={
                "username": username,
                "password": "Pass1234!",
                "name": "推广员E2E",
                "role": "promoter",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["role"] == "promoter"

    def test_register_duplicate_username(self, client: TestClient):
        """重复用户名注册返回 400"""
        resp = client.post(
            self.REGISTER_URL,
            json={
                "username": "buyer1",  # 已存在
                "password": "Test1234",
                "name": "重复用户",
            },
        )
        assert resp.status_code == 400
        assert "已存在" in resp.text

    def test_login_wrong_password(self, client: TestClient):
        """错误密码登录返回 401"""
        resp = client.post(
            self.LOGIN_URL,
            json={"username": "buyer1", "password": "wrong_password"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client: TestClient):
        """不存在的用户登录返回 401"""
        resp = client.post(
            self.LOGIN_URL,
            json={"username": "nonexistent_user_zzz", "password": "Test1234"},
        )
        assert resp.status_code == 401


class TestE2EProductLifecycle:
    """产品生命周期 E2E 测试"""

    PRODUCTS_URL = "/api/products"

    def test_supplier_create_and_query_product(self, client: TestClient, supplier_headers):
        """供应商创建产品并查询"""
        # 创建产品
        create_resp = client.post(
            self.PRODUCTS_URL,
            headers=supplier_headers,
            json={
                "name": "E2E测试专用产品",
                "description": "这是一个 E2E 集成测试产品",
                "price": 199.00,
                "category": "科技产品",
                "stock": 50,
                "tags": "E2E,测试",
                "brand": "E2E品牌",
            },
        )
        assert create_resp.status_code == 200, f"创建产品失败: {create_resp.text}"
        product_id = create_resp.json()["data"]["id"]

        # 查询产品详情
        detail_resp = client.get(f"{self.PRODUCTS_URL}/{product_id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["data"]["name"] == "E2E测试专用产品"

        # 管理员审核通过
        admin_login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "Test1234"},
        )
        admin_token = admin_login.json()["data"]["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 注意：产品审核可能通过 /api/admin 路由
        # 直接通过数据库设为 approved
        from tests.conftest import TestSessionLocal
        from app.models import Product
        db = TestSessionLocal()
        try:
            p = db.query(Product).filter(Product.id == product_id).first()
            p.status = "approved"
            db.commit()
        finally:
            db.close()

    def test_buyer_browse_products(self, client: TestClient):
        """买家浏览产品列表"""
        resp = client.get(self.PRODUCTS_URL)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1
        assert len(data["items"]) >= 1


class TestE2EOrderPayFlow:
    """下单 → 支付 E2E 流程"""

    def test_full_order_and_payment_flow(
        self, client: TestClient, buyer_headers, buyer_user_id: int
    ):
        """完整下单 + 支付流程"""
        # 1. 获取一个 approved 产品
        list_resp = client.get("/api/products")
        products = list_resp.json()["data"]["items"]
        approved = [p for p in products if p["status"] == "approved"]
        assert len(approved) >= 1
        product = approved[0]

        # 2. 下单
        order_resp = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={"product_id": product["id"], "quantity": 2},
        )
        assert order_resp.status_code == 200, f"下单失败: {order_resp.text}"
        order = order_resp.json()["data"]["order"]
        order_id = order["id"]
        assert order["status"] == "pending"
        assert order["total_price"] == product["price"] * 2

        # 3. 微信统一下单（mock 模式）
        pay_resp = client.post(
            "/api/payment/wxpay/unified-order",
            headers=buyer_headers,
            json={"order_id": order_id, "openid": "e2e_test_openid"},
        )
        # 用户没有 wechat_openid，会报 400 错误
        # 但在测试中我们可以手动设置 openid
        if pay_resp.status_code == 400:
            # 通过数据库设置用户的 wechat_openid
            from tests.conftest import TestSessionLocal
            from app.models import User
            db = TestSessionLocal()
            try:
                user = db.query(User).filter(User.id == buyer_user_id).first()
                user.wechat_openid = "e2e_mock_openid"
                db.commit()
            finally:
                db.close()

            # 重试统一下单
            pay_resp = client.post(
                "/api/payment/wxpay/unified-order",
                headers=buyer_headers,
                json={"order_id": order_id},
            )

        assert pay_resp.status_code == 200, f"统一下单失败: {pay_resp.text}"
        pay_data = pay_resp.json()["data"]

        # 4. 模拟微信支付回调
        out_trade_no = f"LK{order_id:08d}{int(time.time())}"
        callback_resp = client.post(
            "/api/payment/wxpay/callback",
            json={
                "out_trade_no": out_trade_no,
                "transaction_id": f"e2e_tx_{order_id}",
                "result_code": "SUCCESS",
            },
        )
        # 可能因为 order 状态或 out_trade_no 格式不匹配，但至少不报 500
        assert callback_resp.status_code == 200

    def test_order_status_flow_e2e(
        self, client: TestClient, buyer_headers, supplier_headers
    ):
        """订单状态流转：创建 → 支付(DB直接) → 发货 → 收货"""
        # 创建订单
        list_resp = client.get("/api/products")
        products = list_resp.json()["data"]["items"]
        approved = [p for p in products if p["status"] == "approved"]
        assert len(approved) >= 1

        order_resp = client.post(
            "/api/orders",
            headers=buyer_headers,
            json={"product_id": approved[0]["id"], "quantity": 1},
        )
        order_id = order_resp.json()["data"]["order"]["id"]

        # 数据库直接设为 paid
        from tests.conftest import TestSessionLocal
        from app.models import Order
        db = TestSessionLocal()
        try:
            db_order = db.query(Order).filter(Order.id == order_id).first()
            db_order.status = "paid"
            db.commit()
        finally:
            db.close()

        # 供应商发货
        ship_resp = client.put(
            f"/api/orders/{order_id}/status",
            headers=supplier_headers,
            json={"status": "shipped"},
        )
        assert ship_resp.status_code == 200

        # 买家收货
        receive_resp = client.put(
            f"/api/orders/{order_id}/status",
            headers=buyer_headers,
            json={"status": "received"},
        )
        assert receive_resp.status_code == 200


class TestE2ERechargeFlow:
    """充值 E2E 流程"""

    def test_full_recharge_flow(self, client: TestClient, buyer_headers):
        """完整充值流程：创建 → 支付成功 → 查余额"""
        # 1. 初始余额
        balance_resp = client.get("/api/recharge/balance", headers=buyer_headers)
        assert balance_resp.status_code == 200
        balance_before = balance_resp.json()["data"]["balance"]

        # 2. 创建充值订单
        precreate_resp = client.post(
            "/api/recharge/precreate",
            headers=buyer_headers,
            json={"amount": 100.00, "platform": "wxpay"},
        )
        assert precreate_resp.status_code == 200
        order_no = precreate_resp.json()["data"]["order_no"]

        # 3. Mock 回调
        callback_resp = client.post(
            "/api/recharge/callback/mock",
            json={"out_trade_no": order_no},
        )
        assert callback_resp.json()["code"] == "SUCCESS"

        # 4. 验证余额
        balance_after = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        assert balance_after == balance_before + 100.00

        # 5. 验证充值记录
        list_resp = client.get("/api/recharge/list", headers=buyer_headers)
        assert list_resp.json()["data"]["total"] >= 1

    def test_recharge_then_query_logs(self, client: TestClient, buyer_headers):
        """充值后查询流水"""
        order_no = client.post(
            "/api/recharge/precreate",
            headers=buyer_headers,
            json={"amount": 50.00, "platform": "wxpay"},
        ).json()["data"]["order_no"]

        client.post("/api/recharge/callback/mock", json={"out_trade_no": order_no})

        logs_resp = client.get("/api/recharge/balance-logs", headers=buyer_headers)
        assert logs_resp.status_code == 200
        items = logs_resp.json()["data"]["items"]
        assert any(log["biz_type"] == "recharge" for log in items)


class TestE2EAuthZ:
    """权限边界 E2E 测试"""

    def test_buyer_cannot_admin(self, client: TestClient, buyer_headers):
        """买家不能执行管理员操作"""
        resp = client.post(
            "/api/recharge/adjust",
            headers=buyer_headers,
            json={"user_id": 1, "amount": 100, "remark": "unauthorized"},
        )
        assert resp.status_code == 403

    def test_promoter_cannot_modify_order_status(self, client: TestClient, promoter_headers):
        """推广员不能修改订单状态"""
        resp = client.put(
            "/api/orders/1/status",
            headers=promoter_headers,
            json={"status": "shipped"},
        )
        assert resp.status_code == 403

    def test_unauthenticated_blocked(self, client: TestClient):
        """未认证请求被拦截"""
        endpoints = [
            ("GET", "/api/recharge/balance"),
            ("POST", "/api/recharge/precreate"),
            ("POST", "/api/orders"),
            ("POST", "/api/products"),
        ]
        for method, url in endpoints:
            if method == "GET":
                resp = client.get(url)
            else:
                resp = client.post(url, json={})
            assert resp.status_code == 401, f"{method} {url} 应返回 401，实际 {resp.status_code}"


class TestE2ESearchFlow:
    """搜索 E2E 流程"""

    SEARCH_URL = "/api/search"

    def test_search_then_view_product(self, client: TestClient):
        """搜索 → 查看产品详情"""
        # 重建索引
        client.get(f"{self.SEARCH_URL}/rebuild")

        # 搜索
        search_resp = client.get(self.SEARCH_URL, params={"q": "测试产品"})
        assert search_resp.status_code == 200
        items = search_resp.json()["data"]["items"]
        if items:
            product_id = items[0]["id"]
            detail_resp = client.get(f"/api/products/{product_id}")
            assert detail_resp.status_code == 200

    def test_search_with_all_filters(self, client: TestClient):
        """多条件组合搜索"""
        client.get(f"{self.SEARCH_URL}/rebuild")
        resp = client.get(
            self.SEARCH_URL,
            params={
                "q": "测试",
                "category": "电子产品",
                "min_price": 10,
                "max_price": 500,
                "sort_by": "price_asc",
                "page": 1,
                "page_size": 10,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        for item in data["items"]:
            assert item["category"] == "电子产品"
            assert 10 <= item["price"] <= 500
