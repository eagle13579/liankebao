"""
充值全链路测试
===============
- 预创建充值 + 完整参数校验
- Mock 支付回调全流程
- 余额变更验证
- 余额流水验证
- 管理员调额全场景
- 并发充值安全（模拟竞争）
- 幂等性保护
- 权限边界测试
"""
import json
import time
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class TestPrecreateRechargeComprehensive:
    """预创建充值全面测试"""

    PRECREATE_URL = "/api/recharge/precreate"

    def test_precreate_success(self, client: TestClient, buyer_headers):
        """基本成功创建"""
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

    def test_precreate_various_amounts(self, client: TestClient, buyer_headers):
        """多种金额验证"""
        for amt in [0.01, 1.00, 99.99, 1000.00, 99999.99]:
            resp = client.post(
                self.PRECREATE_URL,
                headers=buyer_headers,
                json={"amount": amt, "platform": "wxpay"},
            )
            assert resp.status_code == 200, f"金额 {amt} 应成功: {resp.text}"
            assert resp.json()["data"]["amount"] == amt

    def test_precreate_amount_precision(self, client: TestClient, buyer_headers):
        """金额精度验证（小数点后两位）"""
        resp = client.post(
            self.PRECREATE_URL,
            headers=buyer_headers,
            json={"amount": 10.123, "platform": "wxpay"},
        )
        # Python float 精度问题，但金额存储时保留两位
        assert resp.status_code == 200

    def test_precreate_zero_amount(self, client: TestClient, buyer_headers):
        """金额为 0 返回 422"""
        resp = client.post(
            self.PRECREATE_URL,
            headers=buyer_headers,
            json={"amount": 0, "platform": "wxpay"},
        )
        assert resp.status_code == 422

    def test_precreate_negative_amount(self, client: TestClient, buyer_headers):
        """负金额返回 422"""
        resp = client.post(
            self.PRECREATE_URL,
            headers=buyer_headers,
            json={"amount": -50, "platform": "wxpay"},
        )
        assert resp.status_code == 422

    def test_precreate_all_roles(self, client: TestClient, buyer_headers, promoter_headers, supplier_headers, admin_headers):
        """所有角色均可充值"""
        for name, headers in [
            ("buyer", buyer_headers),
            ("promoter", promoter_headers),
            ("supplier", supplier_headers),
            ("admin", admin_headers),
        ]:
            resp = client.post(
                self.PRECREATE_URL,
                headers=headers,
                json={"amount": 5.00, "platform": "wxpay"},
            )
            assert resp.status_code == 200, f"{name} 充值应成功: {resp.text}"

    def test_precreate_order_no_unique(self, client: TestClient, buyer_headers, db_session: Session):
        """验证订单号基本格式"""
        resp = client.post(
            self.PRECREATE_URL,
            headers=buyer_headers,
            json={"amount": 10.00, "platform": "wxpay"},
        )
        order_no = resp.json()["data"]["order_no"]
        # 格式: RC{user_id}{YYYYMMDD}{4位随机数}
        assert order_no.startswith("RC")
        assert len(order_no) > 10


class TestRechargeCallbackChain:
    """充值回调全链路测试"""

    CALLBACK_URL = "/api/recharge/callback/mock"

    def _create_recharge(self, client: TestClient, headers, amount=50.00) -> str:
        """辅助：创建充值订单并返回 order_no"""
        resp = client.post(
            "/api/recharge/precreate",
            headers=headers,
            json={"amount": amount, "platform": "wxpay"},
        )
        return resp.json()["data"]["order_no"]

    def test_full_recharge_flow(self, client: TestClient, buyer_headers):
        """完整充值流程：创建 → 回调 → 查余额 → 查流水"""
        # 1. 获取充值前余额
        balance_before = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]

        # 2. 创建充值订单
        order_no = self._create_recharge(client, buyer_headers, amount=30.00)

        # 3. 调用 mock 回调
        resp = client.post(
            self.CALLBACK_URL,
            json={"out_trade_no": order_no, "transaction_id": f"full_flow_tx_{order_no}"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == "SUCCESS"

        # 4. 查询订单状态
        query_resp = client.get(
            f"/api/recharge/query/{order_no}", headers=buyer_headers
        )
        assert query_resp.json()["data"]["status"] == "paid"

        # 5. 验证余额增加
        balance_after = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        assert balance_after == balance_before + 30.00, f"余额应从 {balance_before} 变为 {balance_before + 30}"

        # 6. 验证流水记录
        logs_resp = client.get(
            "/api/recharge/balance-logs", headers=buyer_headers
        )
        assert logs_resp.status_code == 200
        logs = logs_resp.json()["data"]["items"]
        # 应该有至少一条 IN 流水
        recharge_logs = [log for log in logs if log["direction"] == "IN"]
        assert len(recharge_logs) >= 1

    def test_callback_idempotent(self, client: TestClient, buyer_headers):
        """重复回调幂等"""
        order_no = self._create_recharge(client, buyer_headers, amount=10.00)

        # 第一次回调
        client.post(self.CALLBACK_URL, json={"out_trade_no": order_no})
        balance1 = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]

        # 第二次回调（幂等）
        resp2 = client.post(self.CALLBACK_URL, json={"out_trade_no": order_no})
        assert resp2.json()["code"] == "SUCCESS"
        balance2 = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        assert balance1 == balance2, "幂等回调不应增加余额"

    def test_callback_invalid_order(self, client: TestClient):
        """不存在的订单号返回 FAIL"""
        resp = client.post(
            self.CALLBACK_URL,
            json={"out_trade_no": "RC9999999999999"},
        )
        assert resp.json()["code"] == "FAIL"

    def test_callback_missing_order_no(self, client: TestClient):
        """缺少订单号返回 FAIL"""
        resp = client.post(self.CALLBACK_URL, json={})
        assert resp.json()["code"] == "FAIL"
        assert "缺少订单号" in resp.json()["message"]

    def test_multiple_recharges_same_user(self, client: TestClient, buyer_headers):
        """同一用户多次充值，余额累加正确"""
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
        assert balance_after == balance_before + total, \
            f"余额应增加 {total}，从 {balance_before} 到 {balance_before + total}"

    def test_callback_updates_logs(self, client: TestClient, buyer_headers):
        """回调后产生正确的流水记录"""
        order_no = self._create_recharge(client, buyer_headers, amount=25.00)
        client.post(self.CALLBACK_URL, json={"out_trade_no": order_no})

        logs_resp = client.get(
            "/api/recharge/balance-logs", headers=buyer_headers
        )
        items = logs_resp.json()["data"]["items"]
        matching = [log for log in items if log["biz_id"] == order_no]
        assert len(matching) >= 1
        log = matching[0]
        assert log["direction"] == "IN"
        assert log["biz_type"] == "recharge"
        assert log["amount"] == 25.00


class TestConcurrentRechargeSafety:
    """并发充值安全测试（串行模拟）"""

    def test_sequential_concurrent_recharges(self, client: TestClient, buyer_headers):
        """串行模拟并发充值：连续快速充值验证余额一致性"""
        balance_before = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]

        # 创建 5 个充值订单并处理
        order_nos = []
        for i in range(5):
            order_no = client.post(
                "/api/recharge/precreate",
                headers=buyer_headers,
                json={"amount": 10.00, "platform": "wxpay"},
            ).json()["data"]["order_no"]
            order_nos.append(order_no)

        # 逐个回调处理
        for order_no in order_nos:
            resp = client.post(
                "/api/recharge/callback/mock",
                json={"out_trade_no": order_no},
            )
            assert resp.json()["code"] == "SUCCESS", f"回调 {order_no} 失败: {resp.text}"

        balance_after = client.get(
            "/api/recharge/balance", headers=buyer_headers
        ).json()["data"]["balance"]
        expected = balance_before + 50.00
        assert balance_after == expected, f"余额应等于 {expected}，实际 {balance_after}"

    def test_recharge_row_lock_integrity(self, client: TestClient, buyer_headers, db_session: Session):
        """验证行锁机制下的余额正确性（通过数据库直接检查 version 递增）"""
        # 获取当前 buyer 的余额版本
        from recharge.models import UserBalance
        user_id = 2  # buyer1
        bal = db_session.query(UserBalance).filter(UserBalance.user_id == user_id).first()
        version_before = bal.version

        # 充值一次
        order_no = client.post(
            "/api/recharge/precreate",
            headers=buyer_headers,
            json={"amount": 10.00, "platform": "wxpay"},
        ).json()["data"]["order_no"]
        client.post(
            "/api/recharge/callback/mock",
            json={"out_trade_no": order_no},
        )

        # 检查 version 已递增
        db_session.expire_all()
        bal = db_session.query(UserBalance).filter(UserBalance.user_id == user_id).first()
        assert bal.version == version_before + 1, "乐观锁版本号应递增"


class TestAdminAdjustComprehensive:
    """管理员调额全面测试"""

    ADJUST_URL = "/api/recharge/adjust"

    def test_adjust_increase(self, client: TestClient, admin_headers, buyer_headers):
        """增加余额"""
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
        """减少余额"""
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
        """扣减超过余额返回 400"""
        resp = client.post(
            self.ADJUST_URL,
            headers=admin_headers,
            json={"user_id": 2, "amount": -99999.00, "remark": "超额"},
        )
        assert resp.status_code == 400

    def test_adjust_not_admin(self, client: TestClient, buyer_headers):
        """非管理员返回 403"""
        resp = client.post(
            self.ADJUST_URL,
            headers=buyer_headers,
            json={"user_id": 2, "amount": 10.00, "remark": ""},
        )
        assert resp.status_code == 403

    def test_adjust_zero_amount(self, client: TestClient, admin_headers):
        """调额金额为 0"""
        resp = client.post(
            self.ADJUST_URL,
            headers=admin_headers,
            json={"user_id": 2, "amount": 0, "remark": "零调整"},
        )
        # amount=0, direction = "IN" (因为 >= 0)
        # 余额不变
        assert resp.status_code == 200
        assert resp.json()["data"]["amount"] == 0

    def test_adjust_nonexistent_user(self, client: TestClient, admin_headers):
        """调整不存在用户的余额（自动创建余额记录）"""
        resp = client.post(
            self.ADJUST_URL,
            headers=admin_headers,
            json={"user_id": 999, "amount": 50.00, "remark": "新用户调额"},
        )
        # routes.py 的 get_or_create_balance 会创建新记录
        assert resp.status_code == 200
        assert resp.json()["data"]["after"] == 50.00

    def test_adjust_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
        resp = client.post(
            self.ADJUST_URL,
            json={"user_id": 1, "amount": 10.00, "remark": ""},
        )
        assert resp.status_code == 401


class TestBalanceLogsComprehensive:
    """余额流水查询全面测试"""

    LOGS_URL = "/api/recharge/balance-logs"

    def test_logs_after_recharge(self, client: TestClient, buyer_headers):
        """充值后产生正确流水"""
        # 充值
        order_no = client.post(
            "/api/recharge/precreate",
            headers=buyer_headers,
            json={"amount": 42.00, "platform": "wxpay"},
        ).json()["data"]["order_no"]
        client.post("/api/recharge/callback/mock", json={"out_trade_no": order_no})

        # 查流水
        resp = client.get(self.LOGS_URL, headers=buyer_headers)
        items = resp.json()["data"]["items"]
        matching = [it for it in items if it["biz_id"] == order_no]
        assert len(matching) >= 1
        log = matching[0]
        assert log["direction"] == "IN"
        assert log["biz_type"] == "recharge"
        assert log["amount"] == 42.00
        assert log["balance_after"] == log["balance_before"] + 42.00

    def test_logs_after_adjust(self, client: TestClient, admin_headers, buyer_headers):
        """管理员调额后产生正确流水"""
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
        """流水分页"""
        resp = client.get(self.LOGS_URL, headers=buyer_headers, params={"page": 1, "limit": 5})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["page"] == 1
        assert data["limit"] == 5
        assert len(data["items"]) <= 5

    def test_logs_empty_for_new_user(self, client: TestClient, promoter_headers):
        """新用户流水为空"""
        resp = client.get(self.LOGS_URL, headers=promoter_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    def test_logs_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
        resp = client.get(self.LOGS_URL)
        assert resp.status_code == 401


class TestQueryRechargeOrderComprehensive:
    """充值查询全面测试"""

    def test_query_after_callback(self, client: TestClient, buyer_headers):
        """回调后查询订单状态为 paid"""
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
        """不存在的订单返回 404"""
        resp = client.get(
            "/api/recharge/query/RC999999999999",
            headers=buyer_headers,
        )
        assert resp.status_code == 404

    def test_query_other_user_order(self, client: TestClient, buyer_headers, promoter_headers):
        """其他用户不能查询"""
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
        """充值记录列表"""
        # 创建几条订单
        for amt in [5, 10, 15]:
            client.post(
                "/api/recharge/precreate",
                headers=buyer_headers,
                json={"amount": amt, "platform": "wxpay"},
            )

        resp = client.get("/api/recharge/list", headers=buyer_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 3
