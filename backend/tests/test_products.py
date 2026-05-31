"""产品模块测试：CRUD 核心流程 + 搜索/分页/权限边界"""

from fastapi.testclient import TestClient


class TestProductCRUD:
    """产品 CRUD 核心流程测试"""

    def test_create_product(self, client: TestClient, admin_headers):
        """管理员创建新产品（admin 角色拥有 member 写权限）"""
        resp = client.post(
            "/api/products",
            headers=admin_headers,
            json={
                "name": "全新测试产品",
                "description": "由测试用例创建的产品",
                "price": 99.99,
                "earn_per_share": 19.99,
                "category": "测试分类",
                "stock": 50,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["name"] == "全新测试产品"
        assert data["data"]["status"] == "pending"  # 新建产品默认待审核
        assert data["data"]["owner_id"] is not None

    def test_get_product_detail(self, client: TestClient):
        """获取已存在产品详情"""
        resp = client.get("/api/products/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["id"] == 1
        assert "name" in data["data"]
        assert "price" in data["data"]
        assert "status" in data["data"]

    def test_update_product(self, client: TestClient, admin_headers):
        """管理员更新产品"""
        resp = client.put(
            "/api/products/1",
            headers=admin_headers,
            json={
                "price": 150.00,
                "description": "更新后的产品描述",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["price"] == 150.00
        assert data["data"]["description"] == "更新后的产品描述"

    def test_search_products(self, client: TestClient):
        """搜索产品（按名称关键词）"""
        resp = client.get("/api/products?search=测试产品 A")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] >= 1
        assert any("测试产品 A" in item["name"] for item in data["data"]["items"])

    def test_list_products_pagination(self, client: TestClient):
        """产品列表分页"""
        resp = client.get("/api/products?page=1&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 2
        assert len(data["data"]["items"]) <= 2
        assert data["data"]["total"] >= 1

    def test_viewer_cannot_create_product(self, client: TestClient):
        """未认证用户（viewer 角色）无法创建产品"""
        resp = client.post(
            "/api/products",
            json={
                "name": "匿名试图创建产品",
                "description": "不应成功",
                "price": 10.00,
                "stock": 1,
            },
        )
        # 没有认证头，返回 401/403
        assert resp.status_code in (401, 403)

    def test_list_products_filter_by_category(self, client: TestClient):
        """按分类筛选产品"""
        resp = client.get("/api/products?category=电子产品")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        for item in data["data"]["items"]:
            assert item["category"] == "电子产品"

    def test_get_nonexistent_product(self, client: TestClient):
        """获取不存在的产品返回 404"""
        resp = client.get("/api/products/99999")
        assert resp.status_code == 404

    def test_delete_product_as_admin(self, client: TestClient, admin_headers):
        """管理员可以删除产品"""
        # 先创建一个新产品（不含订单关联）
        create_resp = client.post(
            "/api/products",
            headers=admin_headers,
            json={
                "name": "待删除产品",
                "price": 1.00,
                "stock": 1,
            },
        )
        assert create_resp.status_code == 200
        product_id = create_resp.json()["data"]["id"]

        # 删除该产品
        del_resp = client.delete(f"/api/products/{product_id}", headers=admin_headers)
        assert del_resp.status_code == 200
        assert del_resp.json()["code"] == 200

    def test_non_owner_cannot_delete(self, client: TestClient, buyer_headers, admin_headers):
        """非创建者不能删除产品"""
        create_resp = client.post(
            "/api/products",
            headers=admin_headers,
            json={
                "name": "他人产品",
                "price": 50.00,
                "stock": 10,
            },
        )
        assert create_resp.status_code == 200
        product_id = create_resp.json()["data"]["id"]

        # 买家尝试删除
        del_resp = client.delete(f"/api/products/{product_id}", headers=buyer_headers)
        assert del_resp.status_code == 403
