"""
管理后台模块测试
==================
- 数据看板统计
- 用户管理（列表、修改角色）
- 产品审核
- 提现审核
- 权限边界测试
"""

import pytest
from fastapi.testclient import TestClient


class TestDashboard:
    """数据看板测试"""

    DASHBOARD_URL = "/api/admin/dashboard"

    def test_dashboard_success(self, client: TestClient, admin_headers):
        """管理员获取看板数据"""
        resp = client.get(self.DASHBOARD_URL, headers=admin_headers)
        assert resp.status_code == 200, f"看板获取失败: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "success"
        dashboard = data["data"]
        assert "total_users" in dashboard
        assert "total_products" in dashboard
        assert "total_orders" in dashboard
        assert "total_revenue" in dashboard
        assert "today_orders" in dashboard
        assert "pending_review_products" in dashboard
        assert "pending_withdrawals" in dashboard
        # 种子数据验证
        assert dashboard["total_users"] >= 4  # 4个种子用户
        assert dashboard["total_products"] >= 3  # 3个产品
        assert dashboard["total_orders"] >= 2  # 2个订单

    def test_dashboard_forbidden(self, client: TestClient, buyer_headers):
        """非管理员访问返回403"""
        resp = client.get(self.DASHBOARD_URL, headers=buyer_headers)
        assert resp.status_code == 403
        assert "管理员权限" in resp.text

    def test_dashboard_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.get(self.DASHBOARD_URL)
        assert resp.status_code == 401


class TestAdminUsers:
    """用户管理测试"""

    USERS_URL = "/api/admin/users"

    def test_list_users_success(self, client: TestClient, admin_headers):
        """管理员获取用户列表"""
        resp = client.get(self.USERS_URL, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] >= 4
        # 验证返回包含用户信息
        usernames = {u["username"] for u in data["data"]["items"]}
        assert "admin" in usernames
        assert "buyer1" in usernames
        assert "promoter1" in usernames
        assert "supplier1" in usernames

    def test_list_users_forbidden(self, client: TestClient, buyer_headers):
        """非管理员访问返回403"""
        resp = client.get(self.USERS_URL, headers=buyer_headers)
        assert resp.status_code == 403

    def test_list_users_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.get(self.USERS_URL)
        assert resp.status_code == 401


class TestUpdateUserRole:
    """修改用户角色测试"""

    def _get_user_role_url(self, user_id: int) -> str:
        return f"/api/admin/users/{user_id}/role"

    def test_update_role_success(self, client: TestClient, admin_headers, buyer_user_id):
        """管理员成功修改用户角色"""
        url = self._get_user_role_url(buyer_user_id)
        resp = client.patch(url, headers=admin_headers, json={"role": "supplier"})
        assert resp.status_code == 200, f"修改角色失败: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "角色更新成功"
        assert data["data"]["role"] == "supplier"

        # 还原角色
        client.patch(url, headers=admin_headers, json={"role": "buyer"})

    @pytest.mark.parametrize("new_role", ["buyer", "promoter", "supplier", "admin"])
    def test_update_role_all_roles(self, client: TestClient, admin_headers, buyer_user_id, new_role):
        """所有合法角色都可以设置"""
        url = self._get_user_role_url(buyer_user_id)
        resp = client.patch(url, headers=admin_headers, json={"role": new_role})
        assert resp.status_code == 200, f"设置角色 {new_role} 失败"
        # 还原
        client.patch(url, headers=admin_headers, json={"role": "buyer"})

    def test_update_role_cannot_self(self, client: TestClient, admin_headers, admin_token):
        """管理员不能修改自己的角色"""
        # 查找admin的id
        me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
        admin_id = me_resp.json()["data"]["id"]
        url = self._get_user_role_url(admin_id)
        resp = client.patch(url, headers=admin_headers, json={"role": "buyer"})
        assert resp.status_code == 400
        assert "不能修改自己的角色" in resp.text

    def test_update_role_user_not_found(self, client: TestClient, admin_headers):
        """不存在的用户返回404"""
        url = self._get_user_role_url(99999)
        resp = client.patch(url, headers=admin_headers, json={"role": "buyer"})
        assert resp.status_code == 404

    def test_update_role_invalid_role(self, client: TestClient, admin_headers, buyer_user_id):
        """无效角色值返回422"""
        url = self._get_user_role_url(buyer_user_id)
        resp = client.patch(url, headers=admin_headers, json={"role": "superadmin"})
        assert resp.status_code == 422  # Pydantic校验

    def test_update_role_forbidden(self, client: TestClient, buyer_headers, buyer_user_id):
        """非管理员返回403"""
        url = self._get_user_role_url(buyer_user_id)
        # 禁止自己修改自己
        resp = client.patch(url, headers=buyer_headers, json={"role": "admin"})
        assert resp.status_code == 403

    def test_update_role_unauthenticated(self, client: TestClient, buyer_user_id):
        """未认证返回401"""
        url = self._get_user_role_url(buyer_user_id)
        resp = client.patch(url, json={"role": "buyer"})
        assert resp.status_code == 401


class TestAdminProducts:
    """产品审核测试"""

    PRODUCTS_URL = "/api/admin/products"

    def test_list_all_products(self, client: TestClient, admin_headers):
        """管理员查看所有产品（含待审核）"""
        resp = client.get(self.PRODUCTS_URL, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        statuses = {p["status"] for p in data["data"]["items"]}
        assert "approved" in statuses
        assert "pending" in statuses
        assert data["data"]["total"] >= 3

    def test_list_products_filter_by_status(self, client: TestClient, admin_headers):
        """按状态筛选产品"""
        resp = client.get(self.PRODUCTS_URL, headers=admin_headers, params={"status": "pending"})
        assert resp.status_code == 200
        data = resp.json()
        for item in data["data"]["items"]:
            assert item["status"] == "pending"

    def test_list_products_forbidden(self, client: TestClient, buyer_headers):
        """非管理员返回403"""
        resp = client.get(self.PRODUCTS_URL, headers=buyer_headers)
        assert resp.status_code == 403


class TestReviewProduct:
    """产品审核测试"""

    def test_review_approve(self, client: TestClient, admin_headers):
        """审核通过产品"""
        # 找到待审核产品
        list_resp = client.get("/api/admin/products", headers=admin_headers, params={"status": "pending"})
        items = list_resp.json()["data"]["items"]
        if not items:
            pytest.skip("没有待审核产品")
        product_id = items[0]["id"]

        resp = client.put(
            f"/api/admin/products/{product_id}/review",
            headers=admin_headers,
            json={"action": "approve", "reason": "审核通过"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "产品审核通过"
        assert data["data"]["status"] == "approved"

    def test_review_reject(self, client: TestClient, admin_headers):
        """审核驳回产品"""
        list_resp = client.get("/api/admin/products", headers=admin_headers, params={"status": "pending"})
        items = list_resp.json()["data"]["items"]
        if not items:
            pytest.skip("没有待审核产品")
        product_id = items[0]["id"]

        resp = client.put(
            f"/api/admin/products/{product_id}/review",
            headers=admin_headers,
            json={"action": "reject", "reason": "不符合上架标准"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "产品审核驳回"
        assert data["data"]["status"] == "rejected"

    def test_review_invalid_action(self, client: TestClient, admin_headers):
        """无效审核操作返回400"""
        list_resp = client.get("/api/admin/products", headers=admin_headers)
        items = list_resp.json()["data"]["items"]
        if not items:
            pytest.skip("没有产品")
        product_id = items[0]["id"]

        resp = client.put(
            f"/api/admin/products/{product_id}/review",
            headers=admin_headers,
            json={"action": "invalid"},
        )
        assert resp.status_code == 400
        assert "操作无效" in resp.text

    def test_review_product_not_found(self, client: TestClient, admin_headers):
        """不存在的产品返回404"""
        resp = client.put(
            "/api/admin/products/99999/review",
            headers=admin_headers,
            json={"action": "approve"},
        )
        assert resp.status_code == 404

    def test_review_forbidden(self, client: TestClient, buyer_headers):
        """非管理员返回403"""
        resp = client.put(
            "/api/admin/products/1/review",
            headers=buyer_headers,
            json={"action": "approve"},
        )
        assert resp.status_code == 403


class TestAdminWithdrawals:
    """提现管理测试"""

    WITHDRAWALS_URL = "/api/admin/withdrawals"

    def test_list_withdrawals(self, client: TestClient, admin_headers):
        """管理员查看提现列表"""
        resp = client.get(self.WITHDRAWALS_URL, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] >= 2  # 种子数据2条
        statuses = {w["status"] for w in data["data"]["items"]}
        assert "approved" in statuses
        assert "pending" in statuses

    def test_list_withdrawals_filter_by_status(self, client: TestClient, admin_headers):
        """按状态筛选提现"""
        resp = client.get(self.WITHDRAWALS_URL, headers=admin_headers, params={"status": "pending"})
        assert resp.status_code == 200
        for item in resp.json()["data"]["items"]:
            assert item["status"] == "pending"

    def test_list_withdrawals_forbidden(self, client: TestClient, buyer_headers):
        """非管理员返回403"""
        resp = client.get(self.WITHDRAWALS_URL, headers=buyer_headers)
        assert resp.status_code == 403


class TestReviewWithdrawal:
    """提现审核测试"""

    def test_review_withdrawal_approve(self, client: TestClient, admin_headers):
        """审核通过提现申请"""
        list_resp = client.get("/api/admin/withdrawals", headers=admin_headers, params={"status": "pending"})
        items = list_resp.json()["data"]["items"]
        if not items:
            pytest.skip("没有待审核提现")
        withdrawal_id = items[0]["id"]

        resp = client.put(
            f"/api/admin/withdrawals/{withdrawal_id}/review",
            headers=admin_headers,
            json={"action": "approve"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "提现审核通过"
        assert data["data"]["status"] == "approved"

    def test_review_withdrawal_reject(self, client: TestClient, admin_headers):
        """审核驳回提现申请"""
        list_resp = client.get("/api/admin/withdrawals", headers=admin_headers, params={"status": "pending"})
        items = list_resp.json()["data"]["items"]
        if not items:
            pytest.skip("没有待审核提现")
        withdrawal_id = items[0]["id"]

        resp = client.put(
            f"/api/admin/withdrawals/{withdrawal_id}/review",
            headers=admin_headers,
            json={"action": "reject", "reason": "信息不符"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "提现审核驳回"

    def test_review_withdrawal_not_found(self, client: TestClient, admin_headers):
        """不存在的提现返回404"""
        resp = client.put(
            "/api/admin/withdrawals/99999/review",
            headers=admin_headers,
            json={"action": "approve"},
        )
        assert resp.status_code == 404

    def test_review_withdrawal_invalid_action(self, client: TestClient, admin_headers):
        """无效操作返回400"""
        list_resp = client.get("/api/admin/withdrawals", headers=admin_headers)
        items = list_resp.json()["data"]["items"]
        if not items:
            pytest.skip("没有提现记录")
        withdrawal_id = items[0]["id"]

        resp = client.put(
            f"/api/admin/withdrawals/{withdrawal_id}/review",
            headers=admin_headers,
            json={"action": "invalid"},
        )
        assert resp.status_code == 400

    def test_review_withdrawal_forbidden(self, client: TestClient, buyer_headers):
        """非管理员返回403"""
        resp = client.put(
            "/api/admin/withdrawals/1/review",
            headers=buyer_headers,
            json={"action": "approve"},
        )
        assert resp.status_code == 403
