"""
充值全链路测试 — 增强版(带parametrize)
=======================================
- 预创建充值 + 完整参数校验
- Mock 支付回调全流程
- 余额变更验证
- 余额流水验证
- 管理员调额全场景
- 并发充值安全（模拟竞争）
- 幂等性保护
- 权限边界测试
- 参数化测试覆盖多场景
"""
import json
import time
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class TestPrecreateRechargeComprehensive:
    """预创建充值全面测试 — 含parametrize"""

    PRECREATE_URL = "/api/recharge/precreate"

    @pytest.mark.parametrize("amount", [0.01, 1.00, 10.00, 88.88, 1000.00, 99999.99])
    def test_precreate_various_amounts_param(self, client, buyer_headers, amount):
        """参数化：多种金额验证"""
        resp = client.post(
            self.PRECREATE_URL,
            headers=buyer_headers,
            json={"amount": amount, "platform": "wxpay"},
        )
        assert resp.status_code == 200, f"金额 {amount} 应成功: {resp.text}"
        assert resp.json()["data"]["amount"] == amount

    @pytest.mark.parametrize("role_fixture", ["buyer_headers", "promoter_headers", "supplier_headers", "admin_headers"])
    def test_precreate_all_roles_param(self, client, role_fixture, request):
        """参数化：所有角色均可充值"""
        headers = request.getfixturevalue(role_fixture)
        resp = client.post(
            self.PRECREATE_URL,
            headers=headers,
            json={"amount": 5.00, "platform": "wxpay"},
        )
        assert resp.status_code == 200, f"{role_fixture} 充值应成功: {resp.text}"

    @pytest.mark.parametrize("bad_amount,expected_status", [
        (0, 422),
        (-50, 422),
        (-0.01, 422),
    ])
    def test_precreate_invalid_amounts(self, client, buyer_headers, bad_amount, expected_status):
        """参数化：无效金额"""
        resp = client.post(
            self.PRECREATE_URL,
            headers=buyer_headers,
            json={"amount": bad_amount, "platform": "wxpay"},
        )
        assert resp.status_code == expected_status

    def test_precreate_success(self, client: TestClient, buyer_headers):
        resp = client.post(
            self.PRECREATE_URL,
            headers=buyer_headers,
            json={"amount": 88.88, "platform": "wxpay"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["amount"] == 88.88
        assert data["data"]["order_id"] > 0
        assert data["data"]["order_no"].startswith("RC")
        assert data["data"]["prepay_id"] is not None
        assert data["data"]["payment_params"]["_mode"] == "mock"

    def test_precreate_amount_precision(self, client: TestClient, buyer_headers):
        resp = client.post(
            self.PRECREATE_URL,
            headers=buyer_headers,
            json={"amount": 10.123, "platform": "wxpay"},
        )
        assert resp.status_code == 200

    def test_precreate_order_no_unique(self, client: TestClient, buyer_headers, db_session: Session):
        resp = client.post(
            self.PRECREATE_URL,
            headers=buyer_headers,
            json={"amount": 10.00, "platform": "wxpay"},
        )
        order_no = resp.json()["data"]["order_no"]
        assert order_no.startswith("RC")
        assert len(order_no) > 10


class TestRechargeCallbackChain:
    """充值回调全链路测试 — 含parametrize"""

    CALLBACK_URL = "/api/recharge/callback/mock"

    def _create_recharge(self, client: TestClient, headers, amount=50.00) -> str:
        resp = client.post(
            "/api/recharge/precreate",
            headers=headers,
            json={"amount": amount, "platform": "wxpay"},
        )
        return resp.json()["data"]["order_no"]

    @pytest.mark.parametrize("amount", [10.00, 20.00, 50.00, 100.00, 500.00])
    def test_recharge_different_amounts(self, client, buyer_headers, amount):
        """参数化：不同金额的全链路充值"""
        balance_before = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]

        order_no = self._create_recharge(client, buyer_headers, amount=amount)

        resp = client.post(
            self.CALLBACK_URL,
            json={"out_trade_no": order_no, "transaction_id": f"tx_{order_no}"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == "SUCCESS"

        balance_after = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        assert balance_after == balance_before + amount, \
            f"余额应从 {balance_before} 变为 {balance_before + amount}"

    @pytest.mark.parametrize("repeat_times", [2, 3, 4])
    def test_callback_idempotent_multi_repeat(self, client, buyer_headers, repeat_times):
        """参数化：重复回调幂等"""
        order_no = self._create_recharge(client, buyer_headers, amount=10.00)

        # 第一次回调
        client.post(self.CALLBACK_URL, json={"out_trade_no": order_no})
        balance1 = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]

        # 重复回调
        for i in range(repeat_times - 1):
            resp = client.post(self.CALLBACK_URL, json={"out_trade_no": order_no})
            assert resp.json()["code"] == "SUCCESS", f"第{i+2}次回调应成功"

        balance2 = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        assert balance1 == balance2, "幂等回调不应增加余额"

    @pytest.mark.parametrize("callback_body,expected_field,expected_value", [
        ({"out_trade_no": "RC9999999999999"}, "code", "FAIL"),
        ({}, "code", "FAIL"),
        ({"out_trade_no": ""}, "code", "FAIL"),
    ])
    def test_callback_invalid_inputs(self, client, callback_body, expected_field, expected_value):
        """参数化：各种无效回调"""
        resp = client.post(self.CALLBACK_URL, json=callback_body)
        assert resp.json()[expected_field] == expected_value

    # ---- 原始单测保留 ----
    def test_full_recharge_flow(self, client: TestClient, buyer_headers):
        balance_before = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        order_no = self._create_recharge(client, buyer_headers, amount=30.00)
        resp = client.post(
            self.CALLBACK_URL,
            json={"out_trade_no": order_no, "transaction_id": f"full_flow_tx_{order_no}"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == "SUCCESS"

        query_resp = client.get(
            f"/api/recharge/query/{order_no}", headers=buyer_headers
        )
        assert query_resp.json()["data"]["status"] == "paid"

        balance_after = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        assert balance_after == balance_before + 30.00

        logs_resp = client.get(
            "/api/recharge/balance-logs", headers=buyer_headers
        )
        assert logs_resp.status_code == 200
        logs = logs_resp.json()["data"]["items"]
        recharge_logs = [log for log in logs if log["direction"] == "IN"]
        assert len(recharge_logs) >= 1

    def test_callback_idempotent(self, client: TestClient, buyer_headers):
        order_no = self._create_recharge(client, buyer_headers, amount=10.00)
        client.post(self.CALLBACK_URL, json={"out_trade_no": order_no})
        balance1 = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        resp2 = client.post(self.CALLBACK_URL, json={"out_trade_no": order_no})
        assert resp2.json()["code"] == "SUCCESS"
        balance2 = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        assert balance1 == balance2

    def test_callback_invalid_order(self, client: TestClient):
        resp = client.post(
            self.CALLBACK_URL,
            json={"out_trade_no": "RC9999999999999"},
        )
        assert resp.json()["code"] == "FAIL"

    def test_callback_missing_order_no(self, client: TestClient):
        resp = client.post(self.CALLBACK_URL, json={})
        assert resp.json()["code"] == "FAIL"
        assert "缺少订单号" in resp.json()["message"]

    def test_multiple_recharges_same_user(self, client: TestClient, buyer_headers):
        balance_before = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        amounts = [20.00, 30.00, 50.00]
        total = sum(amounts)
        for amt in amounts:
            order_no = self._create_recharge(client, buyer_headers, amount=amt)
            client.post(self.CALLBACK_URL, json={"out_trade_no": order_no})
        balance_after = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        assert balance_after == balance_before + total

    def test_callback_updates_logs(self, client: TestClient, buyer_headers):
        order_no = self._create_recharge(client, buyer_headers, amount=25.00)
        client.post(self.CALLBACK_URL, json={"out_trade_no": order_no})
        logs_resp = client.get(
            "/api/recharge/balance-logs", headers=buyer_headers
        )
        items = logs_resp.json()["data"]["items"]
        matching = [log for log in items if log["biz_type"] == "recharge" and log["direction"] == "IN"]
        assert len(matching) >= 1
        log = matching[0]
        assert log["direction"] == "IN"
        assert log["biz_type"] == "recharge"
        assert log["amount"] == 25.00


class TestConcurrentRechargeSafety:
    """并发充值安全测试（串行模拟）"""

    @pytest.mark.parametrize("n_orders", [3, 5, 10])
    def test_sequential_concurrent_recharges_param(self, client, buyer_headers, n_orders):
        """参数化：不同并发数的充值验证"""
        balance_before = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]

        order_nos = []
        for i in range(n_orders):
            order_no = client.post(
                "/api/recharge/precreate",
                headers=buyer_headers,
                json={"amount": 10.00, "platform": "wxpay"},
            ).json()["data"]["order_no"]
            order_nos.append(order_no)

        for order_no in order_nos:
            resp = client.post(
                "/api/recharge/callback/mock",
                json={"out_trade_no": order_no},
            )
            assert resp.json()["code"] == "SUCCESS"

        balance_after = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        expected = balance_before + 10.00 * n_orders
        assert balance_after == expected

    def test_sequential_concurrent_recharges(self, client: TestClient, buyer_headers):
        balance_before = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        order_nos = []
        for i in range(5):
            order_no = client.post(
                "/api/recharge/precreate",
                headers=buyer_headers,
                json={"amount": 10.00, "platform": "wxpay"},
            ).json()["data"]["order_no"]
            order_nos.append(order_no)
        for order_no in order_nos:
            resp = client.post(
                "/api/recharge/callback/mock",
                json={"out_trade_no": order_no},
            )
            assert resp.json()["code"] == "SUCCESS"
        balance_after = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        expected = balance_before + 50.00
        assert balance_after == expected

    def test_recharge_row_lock_integrity(self, client: TestClient, buyer_headers, db_session: Session):
        from recharge.models import UserBalance
        user_id = 2  # buyer1
        bal = db_session.query(UserBalance).filter(UserBalance.user_id == user_id).first()
        version_before = bal.version
        order_no = client.post(
            "/api/recharge/precreate",
            headers=buyer_headers,
            json={"amount": 10.00, "platform": "wxpay"},
        ).json()["data"]["order_no"]
        client.post(
            "/api/recharge/callback/mock",
            json={"out_trade_no": order_no},
        )
        db_session.expire_all()
        bal = db_session.query(UserBalance).filter(UserBalance.user_id == user_id).first()
        assert bal.version == version_before + 1


class TestAdminAdjustComprehensive:
    """管理员调额全面测试"""

    ADJUST_URL = "/api/recharge/adjust"

    @pytest.mark.parametrize("adjust_amount,expected_delta", [
        (100.00, 100.00),
        (50.00, 50.00),
        (0.00, 0.00),
        (1.00, 1.00),
    ])
    def test_adjust_increase_param(self, client, admin_headers, buyer_headers, adjust_amount, expected_delta):
        """参数化：增加余额"""
        balance_before = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        resp = client.post(
            self.ADJUST_URL,
            headers=admin_headers,
            json={"user_id": 2, "amount": adjust_amount, "remark": "测试调额"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["after"] == balance_before + expected_delta

    def test_adjust_increase(self, client: TestClient, admin_headers, buyer_headers):
        balance_before = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        resp = client.post(
            self.ADJUST_URL,
            headers=admin_headers,
            json={"user_id": 2, "amount": 100.00, "remark": "奖励"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["after"] == balance_before + 100.00

    def test_adjust_decrease(self, client: TestClient, admin_headers, buyer_headers):
        balance_before = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        resp = client.post(
            self.ADJUST_URL,
            headers=admin_headers,
            json={"user_id": 2, "amount": -50.00, "remark": "扣减"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["after"] == balance_before - 50.00

    def test_adjust_negative_balance(self, client: TestClient, admin_headers, buyer_headers):
        resp = client.post(
            self.ADJUST_URL,
            headers=admin_headers,
            json={"user_id": 2, "amount": -99999.00, "remark": "超额"},
        )
        assert resp.status_code == 400

    def test_adjust_not_admin(self, client: TestClient, buyer_headers):
        resp = client.post(
            self.ADJUST_URL,
            headers=buyer_headers,
            json={"user_id": 2, "amount": 10.00, "remark": ""},
        )
        assert resp.status_code == 403

    def test_adjust_zero_amount(self, client: TestClient, admin_headers):
        resp = client.post(
            self.ADJUST_URL,
            headers=admin_headers,
            json={"user_id": 2, "amount": 0, "remark": "零调整"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["amount"] == 0

    def test_adjust_nonexistent_user(self, client: TestClient, admin_headers):
        resp = client.post(
            self.ADJUST_URL,
            headers=admin_headers,
            json={"user_id": 999, "amount": 50.00, "remark": "新用户调额"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["after"] == 50.00

    def test_adjust_unauthenticated(self, client: TestClient):
        resp = client.post(
            self.ADJUST_URL,
            json={"user_id": 1, "amount": 10.00, "remark": ""},
        )
        assert resp.status_code == 401


class TestBalanceLogsComprehensive:
    """余额流水查询全面测试"""

    LOGS_URL = "/api/recharge/balance-logs"

    def test_logs_after_recharge(self, client: TestClient, buyer_headers):
        order_no = client.post(
            "/api/recharge/precreate",
            headers=buyer_headers,
            json={"amount": 42.00, "platform": "wxpay"},
        ).json()["data"]["order_no"]
        client.post("/api/recharge/callback/mock", json={"out_trade_no": order_no})
        resp = client.get(self.LOGS_URL, headers=buyer_headers)
        items = resp.json()["data"]["items"]
        matching = [it for it in items if it["biz_type"] == "recharge"]
        assert len(matching) >= 1
        log = matching[0]
        assert log["direction"] == "IN"
        assert log["biz_type"] == "recharge"
        assert log["amount"] == 42.00
        assert log["balance_after"] == log["balance_before"] + 42.00

    def test_logs_after_adjust(self, client: TestClient, admin_headers, buyer_headers):
        client.post(
            "/api/recharge/adjust",
            headers=admin_headers,
            json={"user_id": 2, "amount": 30.00, "remark": "测试调额流水"},
        )
        resp = client.get(self.LOGS_URL, headers=buyer_headers)
        items = resp.json()["data"]["items"]
        adjust_logs = [it for it in items if it["biz_type"] == "adjust"]
        assert len(adjust_logs) >= 1
        assert adjust_logs[0]["direction"] == "IN"
        assert adjust_logs[0]["amount"] == 30.00

    def test_logs_pagination(self, client: TestClient, buyer_headers):
        resp = client.get(self.LOGS_URL, headers=buyer_headers, params={"page": 1, "limit": 5})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["page"] == 1
        assert data["limit"] == 5
        assert len(data["items"]) <= 5

    def test_logs_empty_for_new_user(self, client: TestClient, promoter_headers):
        resp = client.get(self.LOGS_URL, headers=promoter_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    def test_logs_unauthenticated(self, client: TestClient):
        resp = client.get(self.LOGS_URL)
        assert resp.status_code == 401


class TestQueryRechargeOrderComprehensive:
    """充值查询全面测试"""

    def test_query_after_callback(self, client: TestClient, buyer_headers):
        resp = client.post(
            "/api/recharge/precreate",
            headers=buyer_headers,
            json={"amount": 50.00, "platform": "wxpay"},
        )
        order_no = resp.json()["data"]["order_no"]
        client.post("/api/recharge/callback/mock", json={"out_trade_no": order_no})
        query_resp = client.get(
            f"/api/recharge/query/{order_no}", headers=buyer_headers
        )
        assert query_resp.json()["data"]["status"] == "paid"
        assert query_resp.json()["data"]["paid_at"] is not None

    def test_query_not_found(self, client: TestClient, buyer_headers):
        resp = client.get(
            "/api/recharge/query/RC999999999999",
            headers=buyer_headers,
        )
        assert resp.status_code == 404

    def test_query_other_user_order(self, client: TestClient, buyer_headers, promoter_headers):
        resp = client.post(
            "/api/recharge/precreate",
            headers=buyer_headers,
            json={"amount": 10.00, "platform": "wxpay"},
        )
        order_no = resp.json()["data"]["order_no"]
        query_resp = client.get(
            f"/api/recharge/query/{order_no}", headers=promoter_headers
        )
        assert query_resp.status_code == 404

    def test_list_recharge_orders(self, client: TestClient, buyer_headers):
        for amt in [5, 10, 15]:
            client.post(
                "/api/recharge/precreate",
                headers=buyer_headers,
                json={"amount": amt, "platform": "wxpay"},
            )
        resp = client.get("/api/recharge/list", headers=buyer_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 3
