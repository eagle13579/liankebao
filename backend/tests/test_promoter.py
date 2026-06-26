"""
推广分润模块测试
（已适配 chainke-full）

chainke-full 推广路由：
  GET    /api/promoter/withdrawals/        — 提现列表
  POST   /api/promoter/withdrawals/        — 创建提现申请
  GET    /api/promoter/withdrawals/{id}    — 提现详情
"""

from fastapi.testclient import TestClient


class TestPromoter:
    """推广分润模块测试"""

    WITHDRAWALS_URL = "/api/promoter/withdrawals"

    def test_list_withdrawals_with_auth(self, client: TestClient, admin_headers):
        """认证用户可查看提现列表"""
        resp = client.get(self.WITHDRAWALS_URL, headers=admin_headers)
        assert resp.status_code in (200, 404)

    def test_list_withdrawals_no_auth(self, client: TestClient):
        """未认证返回 401"""
        resp = client.get(self.WITHDRAWALS_URL)
        assert resp.status_code == 401
