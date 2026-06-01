"""
管理后台API测试
=============
- 数据看板
- 用户列表 + 角色修改
- 产品审核（通过/驳回）
- 提现审核（通过/驳回）
- 权限校验
"""
import pytest
from fastapi.testclient import TestClient


class TestAdminDashboard:
    """管理后台看板测试"""

    DASHBOARD_URL = "/api/admin/dashboard"

    def test_dashboard_success(self, client: TestClient, admin_headers):
        """管理员查看看板"""
        resp = client.get(self.DASHBOARD_URL, headers=admin_headers)
        assert resp.status_code == 200, f"看板应可访问: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        d = data["data"]
        assert "total_users" in d
        assert "total_products" in d
        assert "total_orders" in d
        assert "total_revenue" in d
        assert "today_orders" in d
        assert "pending_review_products" in d
        assert "pending_withdrawals" in d
        # 种子数据
        assert d["total_users"] >= 4
        assert d["total_products"] >= 3
        assert d["total_orders"] >= 2

    def test_dashboard_forbidden_non_admin(self, client: TestClient, buyer_headers):
        """非管理员访问看板返回 403"""
        resp = client.get(self.DASHBOARD_URL, headers=buyer_headers)
        assert resp.status_code == 403

    def test_dashboard_unauthenticated(self, client: TestClient):
        """未认证访问看板返回 401"""
        resp = client.get(self.DASHBOARD_URL)
        assert resp.status_code == 401


class TestAdminUsers:
    """管理后台用户管理测试"""

    USERS_URL = "/api/admin/users"
    ROLE_URL = "/api/admin/users/{user_id}/role"

    def test_list_users(self, client: TestClient, admin_headers):
        """管理员查看用户列表"""
        resp = client.get(self.USERS_URL, headers=admin_headers)
        assert resp.status_code == 200, f"用户列表应可访问: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] >= 4
        assert len(data["data"]["items"]) >= 4
        # 检查用户字段
        user = data["data"]["items"][0]
        assert "id" in user
        assert "username" in user
        assert "role" in user
        assert "name" in user

    def test_list_users_forbidden(self, client: TestClient, buyer_headers):
        """非管理员查看用户列表返回 403"""
        resp = client.get(self.USERS_URL, headers=buyer_headers)
        assert resp.status_code == 403

    def test_list_users_unauthenticated(self, client: TestClient):
        """未认证查看用户列表返回 401"""
        resp = client.get(self.USERS_URL)
        assert resp.status_code == 401

    def test_update_user_role(self, client: TestClient, admin_headers):
        """管理员修改用户角色"""
        # 获取 buyer1 的 ID（角色是 buyer）
        login_resp = client.post("/api/auth/login", json={"username": "buyer1", "password": "Test1234"})
        buyer_user = login_resp.json()["data"]["user"]
        buyer_id = buyer_user["id"]

        resp = client.patch(
            self.ROLE_URL.format(user_id=buyer_id),
            headers=admin_headers,
            json={"role": "supplier"},
        )
        assert resp.status_code == 200, f"修改角色应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["role"] == "supplier"
        assert data["message"] == "角色更新成功"

        # 恢复角色
        client.patch(
            self.ROLE_URL.format(user_id=buyer_id),
            headers=admin_headers,
            json={"role": "buyer"},
        )

    def test_update_role_invalid(self, client: TestClient, admin_headers):
        """修改角色为无效值返回 422"""
        login_resp = client.post("/api/auth/login", json={"username": "buyer1", "password": "Test1234"})
        buyer_id = login_resp.json()["data"]["user"]["id"]

        resp = client.patch(
            self.ROLE_URL.format(user_id=buyer_id),
            headers=admin_headers,
            json={"role": "superadmin"},
        )
        assert resp.status_code == 422, f"无效角色应返回 422: {resp.text}"

    def test_update_role_not_found(self, client: TestClient, admin_headers):
        """修改不存在的用户角色返回 404"""
        resp = client.patch(
            self.ROLE_URL.format(user_id=99999),
            headers=admin_headers,
            json={"role": "buyer"},
        )
        assert resp.status_code == 404

    def test_update_own_role_forbidden(self, client: TestClient, admin_headers):
        """管理员不能修改自己的角色"""
        login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "Test1234"})
        admin_id = login_resp.json()["data"]["user"]["id"]

        resp = client.patch(
            self.ROLE_URL.format(user_id=admin_id),
            headers=admin_headers,
            json={"role": "buyer"},
        )
        assert resp.status_code == 400, "不能修改自己的角色"
        assert "不能修改自己的角色" in resp.text

    def test_update_role_forbidden_non_admin(self, client: TestClient, buyer_headers):
        """非管理员修改角色返回 403"""
        resp = client.patch(
            self.ROLE_URL.format(user_id=2),
            headers=buyer_headers,
            json={"role": "buyer"},
        )
        assert resp.status_code == 403


class TestAdminProductReview:
    """管理后台产品审核测试"""

    ADMIN_PRODUCTS_URL = "/api/admin/products"
    REVIEW_URL = "/api/admin/products/{product_id}/review"

    def test_list_all_products(self, client: TestClient, admin_headers):
        """管理员查看所有产品（含待审核）"""
        resp = client.get(self.ADMIN_PRODUCTS_URL, headers=admin_headers)
        assert resp.status_code == 200, f"产品列表应可访问: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] >= 3
        items = data["data"]["items"]
        statuses = {item["status"] for item in items}
        assert "approved" in statuses
        assert "pending" in statuses

    def test_list_products_filter_by_status(self, client: TestClient, admin_headers):
        """按状态筛选产品"""
        resp = client.get(
            self.ADMIN_PRODUCTS_URL,
            headers=admin_headers,
            params={"status": "pending"},
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["data"]["items"]:
            assert item["status"] == "pending"

    def test_list_all_products_forbidden(self, client: TestClient, buyer_headers):
        """非管理员查看所有产品返回 403"""
        resp = client.get(self.ADMIN_PRODUCTS_URL, headers=buyer_headers)
        assert resp.status_code == 403

    def test_approve_product(self, client: TestClient, supplier_headers, admin_headers):
        """管理员通过产品审核"""
        # 供应商先创建一个待审核产品
        create_resp = client.post(
            "/api/products",
            headers=supplier_headers,
            json={"name": "待审核产品-审批测试", "price": 88.00, "category": "测试"},
        )
        product_id = create_resp.json()["data"]["id"]
        assert create_resp.json()["data"]["status"] == "pending"

        # 管理员审核通过
        resp = client.put(
            self.REVIEW_URL.format(product_id=product_id),
            headers=admin_headers,
            json={"action": "approve"},
        )
        assert resp.status_code == 200, f"审核通过应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["status"] == "approved"
        assert data["message"] == "产品审核通过"

    def test_reject_product(self, client: TestClient, supplier_headers, admin_headers):
        """管理员驳回产品"""
        create_resp = client.post(
            "/api/products",
            headers=supplier_headers,
            json={"name": "待审核产品-驳回测试", "price": 66.00, "category": "测试"},
        )
        product_id = create_resp.json()["data"]["id"]

        resp = client.put(
            self.REVIEW_URL.format(product_id=product_id),
            headers=admin_headers,
            json={"action": "reject"},
        )
        assert resp.status_code == 200, f"驳回应成功: {resp.text}"
        assert resp.json()["data"]["status"] == "rejected"
        assert resp.json()["message"] == "产品审核驳回"

    def test_review_invalid_action(self, client: TestClient, admin_headers):
        """无效的审核操作返回 400"""
        resp = client.put(
            self.REVIEW_URL.format(product_id=1),
            headers=admin_headers,
            json={"action": "invalid_action"},
        )
        assert resp.status_code == 400

    def test_review_nonexistent_product(self, client: TestClient, admin_headers):
        """审核不存在的产品返回 404"""
        resp = client.put(
            self.REVIEW_URL.format(product_id=99999),
            headers=admin_headers,
            json={"action": "approve"},
        )
        assert resp.status_code == 404

    def test_review_forbidden_non_admin(self, client: TestClient, buyer_headers):
        """非管理员审核产品返回 403"""
        resp = client.put(
            self.REVIEW_URL.format(product_id=1),
            headers=buyer_headers,
            json={"action": "approve"},
        )
        assert resp.status_code == 403


class TestAdminWithdrawalReview:
    """管理后台提现审核测试"""

    ADMIN_WITHDRAWALS_URL = "/api/admin/withdrawals"
    REVIEW_URL = "/api/admin/withdrawals/{withdrawal_id}/review"

    def test_list_withdrawals(self, client: TestClient, admin_headers):
        """管理员查看提现申请列表"""
        resp = client.get(self.ADMIN_WITHDRAWALS_URL, headers=admin_headers)
        assert resp.status_code == 200, f"提现列表应可访问: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] >= 2

    def test_list_withdrawals_filter_status(self, client: TestClient, admin_headers):
        """按状态筛选提现记录"""
        resp = client.get(
            self.ADMIN_WITHDRAWALS_URL,
            headers=admin_headers,
            params={"status": "pending"},
        )
        assert resp.status_code == 200
        for item in resp.json()["data"]["items"]:
            assert item["status"] == "pending"

    def test_list_withdrawals_forbidden(self, client: TestClient, buyer_headers):
        """非管理员查看提现列表返回 403"""
        resp = client.get(self.ADMIN_WITHDRAWALS_URL, headers=buyer_headers)
        assert resp.status_code == 403

    def test_approve_withdrawal(self, client: TestClient, admin_headers):
        """管理员通过提现申请"""
        # 查找一个 pending 的提现记录
        list_resp = client.get(
            self.ADMIN_WITHDRAWALS_URL,
            headers=admin_headers,
            params={"status": "pending"},
        )
        items = list_resp.json()["data"]["items"]
        if not items:
            pytest.skip("没有待审核的提现记录")
        withdrawal_id = items[0]["id"]

        resp = client.put(
            self.REVIEW_URL.format(withdrawal_id=withdrawal_id),
            headers=admin_headers,
            json={"action": "approve"},
        )
        assert resp.status_code == 200, f"提现审核通过应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["status"] == "approved"
        assert data["message"] == "提现审核通过"

    def test_reject_withdrawal(self, client: TestClient, promoter_headers, admin_headers):
        """管理员驳回提现申请"""
        # 先创建一个 pending 提现
        earn_resp = client.get("/api/promoter/earnings", headers=promoter_headers)
        available = earn_resp.json()["data"]["available"]
        if available < 1:
            pytest.skip("可提现金额不足")

        withdraw_resp = client.post(
            "/api/promoter/withdraw",
            headers=promoter_headers,
            json={"amount": min(1, available), "bank_info": "{}"},
        )
        withdrawal_id = withdraw_resp.json()["data"]["id"]

        resp = client.put(
            self.REVIEW_URL.format(withdrawal_id=withdrawal_id),
            headers=admin_headers,
            json={"action": "reject"},
        )
        assert resp.status_code == 200, f"提现驳回应成功: {resp.text}"
        assert resp.json()["data"]["status"] == "rejected"
        assert resp.json()["message"] == "提现审核驳回"

    def test_review_withdrawal_invalid_action(self, client: TestClient, admin_headers):
        """无效的审核操作返回 400"""
        resp = client.put(
            self.REVIEW_URL.format(withdrawal_id=1),
            headers=admin_headers,
            json={"action": "invalid"},
        )
        assert resp.status_code == 400

    def test_review_withdrawal_not_found(self, client: TestClient, admin_headers):
        """审核不存在的提现记录返回 404"""
        resp = client.put(
            self.REVIEW_URL.format(withdrawal_id=99999),
            headers=admin_headers,
            json={"action": "approve"},
        )
        assert resp.status_code == 404

    def test_review_withdrawal_forbidden(self, client: TestClient, buyer_headers):
        """非管理员审核提现返回 403"""
        resp = client.put(
            self.REVIEW_URL.format(withdrawal_id=1),
            headers=buyer_headers,
            json={"action": "approve"},
        )
        assert resp.status_code == 403
