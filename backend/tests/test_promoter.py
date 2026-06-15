"""
推广员模块测试
==============
- 推广收益查询
- 提现操作
- 提现记录查询
"""
import pytest
from fastapi.testclient import TestClient


class TestPromoterEarnings:
    """推广收益测试"""

    EARNINGS_URL = "/api/promoter/earnings"

    def test_promoter_earnings(self, client: TestClient, promoter_headers):
        """
        推广员查看收益
        种子数据中 promoter1 有：
          - 订单1（received, commission=20.00）
          - 订单2（paid, commission=5.00）
          总收益 = 20.00（仅已收货的算入）
          已提现 = 10.00（approved）
          提现中 = 5.00（pending）
          可提现 = 20.00 - 10.00 - 5.00 = 5.00
        """
        resp = client.get(self.EARNINGS_URL, headers=promoter_headers)
        assert resp.status_code == 200, f"查询收益应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200

        earnings = data["data"]
        assert earnings["total_earnings"] == 20.00, f"总收益应为 20.00，实际 {earnings['total_earnings']}"
        assert earnings["withdrawn"] == 10.00, f"已提现应为 10.00，实际 {earnings['withdrawn']}"
        assert earnings["pending"] == 5.00, f"提现中应为 5.00，实际 {earnings['pending']}"
        assert earnings["available"] == 5.00, f"可提现应为 5.00，实际 {earnings['available']}"
        assert earnings["order_count"] >= 1, "应有推广订单数"

    def test_earnings_forbidden_for_buyer(self, client: TestClient, buyer_headers):
        """非推广员角色查询收益应返回 403"""
        resp = client.get(self.EARNINGS_URL, headers=buyer_headers)
        assert resp.status_code == 403, "买家不应能查看推广收益"
        assert "仅推广员" in resp.text

    def test_earnings_unauthorized(self, client: TestClient):
        """未认证查询收益应返回 401"""
        resp = client.get(self.EARNINGS_URL)
        assert resp.status_code == 401


class TestWithdraw:
    """提现测试"""

    WITHDRAW_URL = "/api/promoter/withdraw"
    WITHDRAWALS_URL = "/api/promoter/withdrawals"

    def test_withdraw_success(self, client: TestClient, promoter_headers):
        """推广员成功发起提现（可提现 5.00，提现 3.00 应成功）"""
        # 先查当前可提现金额
        earn_resp = client.get("/api/promoter/earnings", headers=promoter_headers)
        available = earn_resp.json()["data"]["available"]

        resp = client.post(
            self.WITHDRAW_URL,
            headers=promoter_headers,
            json={
                "amount": min(3.00, available),
                "bank_info": '{"bank_name":"中国银行","card_number":"6222****5678","holder_name":"李四"}',
            },
        )
        assert resp.status_code == 200, f"提现应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "提现申请已提交，等待审核"
        assert data["data"]["status"] == "pending"
        assert data["data"]["amount"] == min(3.00, available)

    def test_withdraw_exceeds_available(self, client: TestClient, promoter_headers):
        """提现金额超过可提现金额应返回 400"""
        resp = client.post(
            self.WITHDRAW_URL,
            headers=promoter_headers,
            json={
                "amount": 99999.00,
                "bank_info": '{"bank_name":"中国银行","card_number":"6222****5678","holder_name":"李四"}',
            },
        )
        assert resp.status_code == 400, "超额提现应被拒绝"
        assert "不足" in resp.text

    def test_withdraw_zero_amount(self, client: TestClient, promoter_headers):
        """提现金额为 0 应返回 400"""
        resp = client.post(
            self.WITHDRAW_URL,
            headers=promoter_headers,
            json={
                "amount": 0,
                "bank_info": "{}",
            },
        )
        # Pydantic Field(gt=0) 会拦截为 422
        assert resp.status_code in (400, 422), "0 元提现应被拒绝"

    def test_withdraw_forbidden_for_buyer(self, client: TestClient, buyer_headers):
        """非推广员提现应返回 403"""
        resp = client.post(
            self.WITHDRAW_URL,
            headers=buyer_headers,
            json={
                "amount": 1.00,
                "bank_info": "{}",
            },
        )
        assert resp.status_code == 403

    def test_withdraw_unauthorized(self, client: TestClient):
        """未认证提现应返回 401"""
        resp = client.post(
            self.WITHDRAW_URL,
            json={"amount": 1.00},
        )
        assert resp.status_code == 401

    def test_withdrawals_history(self, client: TestClient, promoter_headers):
        """查询提现记录"""
        resp = client.get(self.WITHDRAWALS_URL, headers=promoter_headers)
        assert resp.status_code == 200, f"查询提现记录应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] >= 2, "种子数据应有 2 条提现记录"
        # 检查记录内容
        items = data["data"]["items"]
        statuses = {item["status"] for item in items}
        assert "approved" in statuses
        assert "pending" in statuses

    def test_withdrawals_forbidden_for_buyer(self, client: TestClient, buyer_headers):
        """非推广员查询提现记录应返回 403"""
        resp = client.get(self.WITHDRAWALS_URL, headers=buyer_headers)
        assert resp.status_code == 403
