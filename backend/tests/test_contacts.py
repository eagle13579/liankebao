"""
联系人模块测试
（已适配 chainke-full）

chainke-full 联系人路由：
  GET    /api/contacts/              — 联系人列表
  POST   /api/contacts/              — 创建联系人
  GET    /api/contacts/{id}          — 联系人详情
  PUT    /api/contacts/{id}          — 更新联系人
  DELETE /api/contacts/{id}          — 删除联系人
  POST   /api/contacts/batch         — 批量创建
"""

from fastapi.testclient import TestClient


class TestListContacts:
    """联系人列表测试"""

    LIST_URL = "/api/contacts"

    def _create_contact(self, client: TestClient, headers, **overrides) -> int:
        data = {
            "name": "列表测试联系人",
            "phone": "13800000100",
            "company": "测试公司",
            "tags": "VIP,客户",
        }
        data.update(overrides)
        resp = client.post(self.LIST_URL, headers=headers, json=data)
        assert resp.status_code in (200, 201), f"创建联系人失败: {resp.text}"
        resp_data = resp.json()
        # 兼容不同响应格式
        if isinstance(resp_data, dict):
            item = resp_data.get("data", resp_data)
            if isinstance(item, dict):
                return item.get("id") or item.get("contact_id", 0)
        return 0

    def test_list_contacts_success(self, client: TestClient, admin_headers):
        """成功获取联系人列表"""
        self._create_contact(client, admin_headers)
        self._create_contact(client, admin_headers, name="第二联系人", phone="13800000101")

        resp = client.get(self.LIST_URL, headers=admin_headers)
        assert resp.status_code == 200

    def test_list_contacts_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
        resp = client.get(self.LIST_URL)
        assert resp.status_code == 401

    def test_create_contact_full_fields(self, client: TestClient, admin_headers):
        """完整字段创建联系人"""
        resp = client.post(
            self.LIST_URL,
            headers=admin_headers,
            json={
                "name": "张三",
                "phone": "13800000123",
                "wechat_id": "zhangsan123",
                "company": "测试科技有限公司",
                "position": "CTO",
                "email": "zhangsan@test.com",
                "notes": "老朋友",
                "tags": "VIP,合作伙伴",
                "source": "manual",
            },
        )
        assert resp.status_code in (200, 201), f"创建联系人应成功: {resp.text}"
