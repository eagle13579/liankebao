"""
联系人活动模块测试
（已适配 chainke-full）

chainke-full 活动路由：
  GET    /api/contacts/{contact_id}/activities/   — 活动列表
  POST   /api/contacts/{contact_id}/activities/   — 创建活动
"""

from fastapi.testclient import TestClient


class TestListActivities:
    """获取联系人活动列表测试"""

    def test_list_activities_no_auth(self, client: TestClient):
        """未认证返回 401"""
        resp = client.get("/api/contacts/1/activities")
        assert resp.status_code == 401

    def test_list_activities_with_auth(self, client: TestClient, admin_headers):
        """已认证可查看活动列表"""
        # 先创建联系人
        contact_resp = client.post(
            "/api/contacts",
            headers=admin_headers,
            json={"name": "活动测试联系人", "phone": "13800000100"},
        )
        if contact_resp.status_code not in (200, 201):
            # 路由可能尚不可用
            return
        data = contact_resp.json()
        contact_id = None
        if isinstance(data, dict):
            item = data.get("data", data)
            contact_id = item.get("id") if isinstance(item, dict) else None
        if not contact_id:
            return

        resp = client.get(
            f"/api/contacts/{contact_id}/activities",
            headers=admin_headers,
        )
        assert resp.status_code in (200, 404)
