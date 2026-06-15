"""多租户+RBAC权限隔离测试"""

from fastapi.testclient import TestClient


class TestRBAC:
    """RBAC权限隔离核心流程测试"""

    def test_admin_access_dashboard(self, client: TestClient, admin_headers):
        """管理员可以访问管理后台仪表盘"""
        resp = client.get("/api/admin/dashboard", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "total_users" in data["data"]
        assert "total_products" in data["data"]
        assert "total_orders" in data["data"]
        assert data["data"]["total_users"] >= 4  # 种子数据4个用户

    def test_non_admin_denied_dashboard(self, client: TestClient, buyer_headers):
        """非管理员（买家）无法访问管理后台"""
        resp = client.get("/api/admin/dashboard", headers=buyer_headers)
        assert resp.status_code == 403
        assert "权限不足" in resp.text

    def test_product_owner_isolation(self, client: TestClient, admin_headers, buyer_headers):
        """产品创建者可以更新，非创建者（且无写角色）被拒绝"""
        # 管理员创建新产品
        create_resp = client.post(
            "/api/products",
            headers=admin_headers,
            json={
                "name": "管理员专属产品",
                "price": 200.00,
                "stock": 10,
            },
        )
        assert create_resp.status_code == 200
        product_id = create_resp.json()["data"]["id"]

        # 买家 buyer1 尝试更新该产品（buyer 角色无写权限）应被拒绝
        update_resp = client.put(
            f"/api/products/{product_id}",
            headers=buyer_headers,
            json={
                "name": "被篡改的产品名",
            },
        )
        assert update_resp.status_code == 403
        assert "权限不足" in update_resp.text

    def test_member_cannot_access_admin_dashboard(self, client: TestClient, buyer_headers):
        """member 角色（买家/供应商）无法访问管理后台"""
        resp = client.get("/api/admin/dashboard", headers=buyer_headers)
        assert resp.status_code == 403
        assert "权限不足" in resp.text

    def test_viewer_cannot_create_order(self, client: TestClient):
        """未登录（viewer 角色）无法下单"""
        resp = client.post(
            "/api/orders",
            json={
                "product_id": 1,
                "quantity": 1,
            },
        )
        assert resp.status_code in (401, 403)

    def test_unauthenticated_denied(self, client: TestClient):
        """未认证用户访问受保护接口返回 401"""
        resp = client.get("/api/auth/me")
        assert resp.status_code in (401, 403)
