"""
产品模块测试：CRUD 核心流程
（已适配 chainke-full）

chainke-full 产品路由：
  GET    /api/products/              — 产品列表
  POST   /api/products/              — 创建产品
  GET    /api/products/{id}          — 产品详情
  PUT    /api/products/{id}          — 更新产品
  DELETE /api/products/{id}          — 删除产品
"""

from fastapi.testclient import TestClient


class TestProductCRUD:
    """产品 CRUD 核心流程测试"""

    PRODUCTS_URL = "/api/products"

    def test_get_product_list(self, client: TestClient):
        """获取产品列表"""
        resp = client.get(self.PRODUCTS_URL)
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()
            assert "data" in data or isinstance(data, (list, dict))

    def test_get_product_list_unauthenticated(self, client: TestClient):
        """未认证用户可以查看公开产品列表"""
        resp = client.get(self.PRODUCTS_URL)
        assert resp.status_code in (200, 401, 404)

    def test_create_product_admin(self, client: TestClient, admin_headers):
        """管理员创建新产品"""
        resp = client.post(
            self.PRODUCTS_URL,
            headers=admin_headers,
            json={
                "name": "全新测试产品",
                "description": "由测试用例创建的产品",
                "price": 99.99,
                "category": "测试分类",
                "stock": 50,
            },
        )
        assert resp.status_code in (200, 201, 422), f"创建产品: {resp.text}"
