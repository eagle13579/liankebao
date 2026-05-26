"""
充值模块测试
=============
- 预创建充值订单（mock 模式）
- 查询充值订单
- 查询用户余额
- 充值记录列表
- Mock 支付回调
- 余额流水查询
- 管理员调额
- 权限边界测试
"""

import pytest
from fastapi.testclient import TestClient


class TestPrecreateRecharge:
    """预创建充值订单测试"""

    PRECREATE_URL = "/api/recharge/precreate"

    def test_precreate_success(self, client: TestClient, buyer_headers):
        """买家成功预创建充值订单（mock 模式）"""
        resp = client.post(
            self.PRECREATE_URL,
            headers=buyer_headers,
            json={"amount": 50.00, "platform": "wxpay"},
        )
        assert resp.status_code == 200, f"预创建充值应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert "mock" in data["message"].lower()
        assert data["data"]["amount"] == 50.00
        assert data["data"]["order_id"] > 0
        assert "RC" in data["data"]["order_no"]
        assert data["data"]["prepay_id"] is not None
        assert data["data"]["payment_params"]["_mode"] == "mock"

    def test_precreate_min_amount(self, client: TestClient, buyer_headers):
        """最小金额 0.01 元"""
        resp = client.post(
            self.PRECREATE_URL,
            headers=buyer_headers,
            json={"amount": 0.01, "platform": "wxpay"},
        )
        # Pydantic Field(gt=0) 通过，0.01 > 0
        assert resp.status_code == 200, f"最小金额应成功: {resp.text}"

    def test_precreate_zero_amount(self, client: TestClient, buyer_headers):
        """金额为 0 应返回 422"""
        resp = client.post(
            self.PRECREATE_URL,
            headers=buyer_headers,
            json={"amount": 0, "platform": "wxpay"},
        )
        assert resp.status_code == 422, "金额为 0 应被拒绝"

    def test_precreate_negative_amount(self, client: TestClient, buyer_headers):
        """金额为负数应返回 422"""
        resp = client.post(
            self.PRECREATE_URL,
            headers=buyer_headers,
            json={"amount": -10, "platform": "wxpay"},
        )
        assert resp.status_code == 422, "负金额应被拒绝"

    def test_precreate_invalid_platform(self, client: TestClient, buyer_headers):
        """非 wxpay 平台应返回 400"""
        resp = client.post(
            self.PRECREATE_URL,
            headers=buyer_headers,
            json={"amount": 10.00, "platform": "alipay"},
        )
        # 路由层校验：暂仅支持微信支付
        assert resp.status_code == 400, "非 wxpay 平台应被拒绝"
        assert "仅支持微信支付" in resp.text

    def test_precreate_unauthenticated(self, client: TestClient):
        """未认证用户预创建充值应返回 401"""
        resp = client.post(
            self.PRECREATE_URL,
            json={"amount": 10.00, "platform": "wxpay"},
        )
        assert resp.status_code == 401

    def test_precreate_all_roles(self, client: TestClient, buyer_headers, promoter_headers, supplier_headers, admin_headers):
        """所有角色都能充值"""
        for headers in [buyer_headers, promoter_headers, supplier_headers, admin_headers]:
            resp = client.post(
                self.PRECREATE_URL,
                headers=headers,
                json={"amount": 1.00, "platform": "wxpay"},
            )
            assert resp.status_code == 200, f"角色充值应成功: {resp.text}"


class TestQueryRechargeOrder:
    """查询充值订单测试"""

    def test_query_order_success(self, client: TestClient, buyer_headers):
        """查询自己的充值订单"""
        # 先创建充值订单
        create_resp = client.post(
            "/api/recharge/precreate",
            headers=buyer_headers,
            json={"amount": 100.00, "platform": "wxpay"},
        )
        order_no = create_resp.json()["data"]["order_no"]

        # 查询
        resp = client.get(
            f"/api/recharge/query/{order_no}",
            headers=buyer_headers,
        )
        assert resp.status_code == 200, f"查询订单应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["order_no"] == order_no
        assert data["data"]["amount"] == 100.00
        assert data["data"]["status"] == "pending"
        assert data["data"]["platform"] == "wxpay"

    def test_query_order_not_found(self, client: TestClient, buyer_headers):
        """查询不存在的订单返回 404"""
        resp = client.get(
            "/api/recharge/query/RC9999999999999999",
            headers=buyer_headers,
        )
        assert resp.status_code == 404

    def test_query_order_other_user(self, client: TestClient, buyer_headers, promoter_headers):
        """A 用户无法查询 B 用户的充值订单"""
        # buyer 创建订单
        create_resp = client.post(
            "/api/recharge/precreate",
            headers=buyer_headers,
            json={"amount": 10.00, "platform": "wxpay"},
        )
        order_no = create_resp.json()["data"]["order_no"]

        # promoter 查询 buyer 的订单
        resp = client.get(
            f"/api/recharge/query/{order_no}",
            headers=promoter_headers,
        )
        assert resp.status_code == 404, "其他用户不应看到此订单"

    def test_query_order_unauthenticated(self, client: TestClient):
        """未认证查询返回 401"""
        resp = client.get("/api/recharge/query/RC123456")
        assert resp.status_code == 401


class TestListRechargeOrders:
    """充值记录列表测试"""

    LIST_URL = "/api/recharge/list"

    def test_list_orders(self, client: TestClient, buyer_headers):
        """用户查看自己的充值记录"""
        # 先创建几条充值订单
        for amt in [10, 20, 30]:
            client.post(
                "/api/recharge/precreate",
                headers=buyer_headers,
                json={"amount": amt, "platform": "wxpay"},
            )

        resp = client.get(self.LIST_URL, headers=buyer_headers)
        assert resp.status_code == 200, f"查询充值记录应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] >= 3
        assert len(data["data"]["items"]) >= 3

    def test_list_orders_pagination(self, client: TestClient, buyer_headers):
        """分页"""
        resp = client.get(self.LIST_URL, headers=buyer_headers, params={"page": 1, "limit": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["page"] == 1
        assert data["data"]["limit"] == 1
        assert len(data["data"]["items"]) <= 1

    def test_list_orders_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
        resp = client.get(self.LIST_URL)
        assert resp.status_code == 401


class TestBalance:
    """余额查询测试"""

    BALANCE_URL = "/api/recharge/balance"

    def test_balance_query(self, client: TestClient, buyer_headers):
        """查询余额（买家有 seed balance=100）"""
        resp = client.get(self.BALANCE_URL, headers=buyer_headers)
        assert resp.status_code == 200, f"查询余额应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["balance"] == 100.00
        assert data["data"]["total_recharged"] == 200.00
        assert data["data"]["total_consumed"] == 100.00
        assert "recent_logs" in data["data"]

    def test_balance_no_previous_record(self, client: TestClient, promoter_headers):
        """没有余额记录的用户返回 balance=0"""
        resp = client.get(self.BALANCE_URL, headers=promoter_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["balance"] == 0.00
        assert data["data"]["total_recharged"] == 0.00

    def test_balance_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
        resp = client.get(self.BALANCE_URL)
        assert resp.status_code == 401


class TestBalanceLogs:
    """余额流水查询测试"""

    LOGS_URL = "/api/recharge/balance-logs"

    def test_list_logs(self, client: TestClient, buyer_headers):
        """查询余额流水"""
        resp = client.get(self.LOGS_URL, headers=buyer_headers)
        assert resp.status_code == 200, f"查询流水应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        # buyer 没有写入流水记录，但可以查询（为空）
        assert "items" in data["data"]
        assert data["data"]["total"] >= 0

    def test_list_logs_pagination(self, client: TestClient, buyer_headers):
        """分页"""
        resp = client.get(self.LOGS_URL, headers=buyer_headers, params={"page": 1, "limit": 10})
        assert resp.status_code == 200

    def test_list_logs_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
        resp = client.get(self.LOGS_URL)
        assert resp.status_code == 401


class TestMockCallback:
    """Mock 支付回调测试"""

    CALLBACK_URL = "/api/recharge/callback/mock"

    def test_mock_callback_success(self, client: TestClient, buyer_headers):
        """Mock 回调处理成功"""
        # 先创建充值订单
        create_resp = client.post(
            "/api/recharge/precreate",
            headers=buyer_headers,
            json={"amount": 66.00, "platform": "wxpay"},
        )
        order_no = create_resp.json()["data"]["order_no"]
        order_id = create_resp.json()["data"]["order_id"]

        # 调用 mock 回调
        resp = client.post(
            self.CALLBACK_URL,
            json={
                "out_trade_no": order_no,
                "transaction_id": f"mock_tx_{order_id}",
            },
        )
        assert resp.status_code == 200, f"Mock 回调应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == "SUCCESS"
        assert "成功" in data["message"]

        # 验证订单状态已更新
        query_resp = client.get(
            f"/api/recharge/query/{order_no}",
            headers=buyer_headers,
        )
        assert query_resp.json()["data"]["status"] == "paid"

        # 验证余额已增加
        balance_resp = client.get("/api/recharge/balance", headers=buyer_headers)
        # seed balance=100, 充值 66.00 -> 166.00
        assert balance_resp.json()["data"]["balance"] == 166.00

    def test_mock_callback_idempotent(self, client: TestClient, buyer_headers):
        """重复回调幂等（第二次调用不应增加余额）"""
        create_resp = client.post(
            "/api/recharge/precreate",
            headers=buyer_headers,
            json={"amount": 10.00, "platform": "wxpay"},
        )
        order_no = create_resp.json()["data"]["order_no"]

        # 第 1 次回调
        client.post(self.CALLBACK_URL, json={"out_trade_no": order_no})

        # 获取当前余额
        balance_before = client.get("/api/recharge/balance", headers=buyer_headers).json()["data"]["balance"]

        # 第 2 次回调（幂等）
        resp = client.post(self.CALLBACK_URL, json={"out_trade_no": order_no})
        assert resp.status_code == 200
        # 第二次 SUCCESS 但不会增加余额
        balance_after = client.get("/api/recharge/balance", headers=buyer_headers).json()["data"]["balance"]
        # seed=100, 第一次充值10 -> 110, 第二次幂等不增加
        assert balance_before == balance_after

    def test_mock_callback_invalid_order(self, client: TestClient):
        """不存在的订单号返回 FAIL"""
        resp = client.post(
            self.CALLBACK_URL,
            json={"out_trade_no": "RC9999999999999999"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == "FAIL"

    def test_mock_callback_empty_order_no(self, client: TestClient):
        """缺少订单号返回 FAIL"""
        resp = client.post(self.CALLBACK_URL, json={})
        assert resp.status_code == 200
        assert resp.json()["code"] == "FAIL"
        assert "缺少订单号" in resp.json()["message"]


class TestAdminAdjust:
    """管理员调额测试"""

    ADJUST_URL = "/api/recharge/adjust"

    def test_adjust_increase(self, client: TestClient, admin_headers, buyer_headers):
        """管理员增加用户余额"""
        # 获取 buyer 当前余额
        balance_before = client.get("/api/recharge/balance", headers=buyer_headers).json()["data"]["balance"]

        resp = client.post(
            self.ADJUST_URL,
            headers=admin_headers,
            json={
                "user_id": 2,  # buyer1
                "amount": 50.00,
                "remark": "测试调额",
            },
        )
        assert resp.status_code == 200, f"调额应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["before"] == balance_before
        assert data["data"]["after"] == balance_before + 50.00
        assert data["data"]["amount"] == 50.00

        # 验证余额已更新
        balance_after = client.get("/api/recharge/balance", headers=buyer_headers).json()["data"]["balance"]
        assert balance_after == balance_before + 50.00

    def test_adjust_decrease(self, client: TestClient, admin_headers, buyer_headers):
        """管理员减少用户余额"""
        balance_before = client.get("/api/recharge/balance", headers=buyer_headers).json()["data"]["balance"]

        resp = client.post(
            self.ADJUST_URL,
            headers=admin_headers,
            json={
                "user_id": 2,
                "amount": -30.00,
                "remark": "扣减测试",
            },
        )
        assert resp.status_code == 200, f"扣减应成功: {resp.text}"
        data = resp.json()
        assert data["data"]["before"] == balance_before
        assert data["data"]["after"] == balance_before - 30.00

    def test_adjust_negative_balance(self, client: TestClient, admin_headers, buyer_headers):
        """扣减超过余额应返回 400"""
        resp = client.post(
            self.ADJUST_URL,
            headers=admin_headers,
            json={
                "user_id": 2,
                "amount": -99999.00,
                "remark": "超额扣减",
            },
        )
        assert resp.status_code == 400, "超额扣减应被拒绝"
        assert "余额不足" in resp.text

    def test_adjust_not_admin(self, client: TestClient, buyer_headers):
        """非管理员调额应返回 403"""
        resp = client.post(
            self.ADJUST_URL,
            headers=buyer_headers,
            json={"user_id": 2, "amount": 10.00, "remark": "非管理员"},
        )
        assert resp.status_code == 403

    def test_adjust_unauthenticated(self, client: TestClient):
        """未认证调额返回 401"""
        resp = client.post(
            self.ADJUST_URL,
            json={"user_id": 1, "amount": 10.00, "remark": ""},
        )
        assert resp.status_code == 401
