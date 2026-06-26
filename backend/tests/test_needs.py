"""
需求管理模块测试
（已适配 chainke-full）

chainke-full 需求路由：
  GET    /api/needs/                — 需求大厅列表
  POST   /api/needs/                — 发布需求
  GET    /api/needs/{id}            — 需求详情
  PUT    /api/needs/{id}            — 更新需求
  DELETE /api/needs/{id}            — 删除需求
"""

from fastapi.testclient import TestClient


class TestCreateNeed:
    """发布需求测试"""

    CREATE_URL = "/api/needs"

    NEED_DATA = {
        "title": "寻找AI技术合作伙伴",
        "description": "我们需要一家AI技术公司合作开发智能客服系统",
        "category": "科技产品",
        "budget": "50万-100万",
        "region": "深圳",
        "contact_name": "测试联系人",
        "contact_phone": "13900139000",
    }

    def test_create_need_success(self, client: TestClient, admin_headers):
        """认证用户成功发布需求"""
        resp = client.post(self.CREATE_URL, headers=admin_headers, json=self.NEED_DATA)
        assert resp.status_code in (200, 201), f"发布需求应成功: {resp.text}"

    def test_create_need_no_auth(self, client: TestClient):
        """未认证不能发布需求"""
        resp = client.post(self.CREATE_URL, json=self.NEED_DATA)
        assert resp.status_code == 401

    def test_list_needs(self, client: TestClient):
        """需求大厅列表（公开）"""
        resp = client.get(self.CREATE_URL)
        assert resp.status_code in (200, 404)
