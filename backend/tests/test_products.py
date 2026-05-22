"""
产品模块测试
============
- 获取产品列表（未登录 / 已登录）
- 创建产品（需认证）
- 搜索产品
"""
import pytest
from fastapi.testclient import TestClient


class TestListProducts:
    """产品列表测试"""

    LIST_URL = "/api/products"

    def test_list_products_unauthenticated(self, client: TestClient):
        """未登录用户：只看到已上架(approved)的产品"""
        resp = client.get(self.LIST_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        items = data["data"]["items"]
        # 种子数据中有 2 个 approved + 1 个 pending
        for item in items:
            assert item["status"] == "approved", f"未登录用户不应看到 {item['status']} 状态的产品"
        assert len(items) == 2, f"应返回 2 个已上架产品，实际 {len(items)}"

    def test_list_products_as_admin(self, client: TestClient, admin_headers):
        """管理员：可查看所有状态的产品"""
        resp = client.get(self.LIST_URL, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        items = data["data"]["items"]
        statuses = {item["status"] for item in items}
        assert "approved" in statuses
        assert "pending" in statuses, "管理员应能看到 pending 状态的产品"
        assert len(items) == 3, f"管理员应看到全部 3 个产品，实际 {len(items)}"

    def test_list_products_pagination(self, client: TestClient):
        """分页参数测试"""
        resp = client.get(self.LIST_URL, params={"page": 1, "page_size": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 1
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 1
        assert data["data"]["total"] >= 1

    def test_list_products_filter_category(self, client: TestClient):
        """按分类筛选"""
        resp = client.get(self.LIST_URL, params={"category": "电子产品"})
        assert resp.status_code == 200
        data = resp.json()
        for item in data["data"]["items"]:
            assert item["category"] == "电子产品"


class TestCreateProduct:
    """创建产品测试"""

    CREATE_URL = "/api/products"

    def test_create_product_authenticated(self, client: TestClient, supplier_headers):
        """已认证用户可创建产品"""
        resp = client.post(
            self.CREATE_URL,
            headers=supplier_headers,
            json={
                "name": "新测试产品",
                "description": "通过 API 创建的产品",
                "price": 99.99,
                "earn_per_share": 15.00,
                "category": "测试分类",
                "stock": 50,
                "brand": "测试品牌",
                "tags": "测试,新品",
            },
        )
        assert resp.status_code == 200, f"创建产品应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "产品创建成功，等待审核"
        assert data["data"]["status"] == "pending"
        assert data["data"]["name"] == "新测试产品"

    def test_create_product_unauthenticated(self, client: TestClient):
        """未认证用户创建产品应返回 401"""
        resp = client.post(
            self.CREATE_URL,
            json={
                "name": "未登录产品",
                "price": 10.0,
            },
        )
        assert resp.status_code == 401, f"未认证应返回 401: {resp.text}"


class TestSearchProducts:
    """产品搜索测试"""

    SEARCH_URL = "/api/products"

    def test_search_products_by_name(self, client: TestClient):
        """按产品名称搜索"""
        resp = client.get(self.SEARCH_URL, params={"search": "测试产品 A"})
        assert resp.status_code == 200
        data = resp.json()
        items = data["data"]["items"]
        assert any("测试产品 A" in item["name"] for item in items), "应搜到 测试产品 A"

    def test_search_products_by_description(self, client: TestClient):
        """按产品描述搜索"""
        resp = client.get(self.SEARCH_URL, params={"search": "另一个已上架"})
        assert resp.status_code == 200
        data = resp.json()
        items = data["data"]["items"]
        assert len(items) >= 1
        assert any("另一个已上架" in item.get("description", "") or "C" in item.get("name", "")
                   for item in items), "应搜到匹配描述的产品"

    def test_search_no_results(self, client: TestClient):
        """搜索不存在的内容返回空列表"""
        resp = client.get(self.SEARCH_URL, params={"search": "ZZZZZZZZZZ_NOT_EXIST"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 0
        assert data["data"]["items"] == []
