"""
联系人活动模块测试
==============
- 为联系人添加活动
- 查看联系人活动列表
- 活动类型校验
- 权限校验
"""
import pytest
from fastapi.testclient import TestClient


class TestCreateActivity:
    """创建活动测试"""

    def _create_contact(self, client, headers):
        """辅助：创建联系人并返回ID"""
        resp = client.post("/api/contacts", headers=headers, json={"name": "活动测试联系人"})
        return resp.json()["data"]["id"]

    def test_create_activity_success(self, client: TestClient, buyer_headers):
        """为联系人成功添加活动"""
        contact_id = self._create_contact(client, buyer_headers)

        activity_data = {
            "action_type": "call",
            "summary": "初次电话沟通",
            "detail": "讨论了合作意向，对方表示有兴趣深入了解",
        }
        resp = client.post(
            f"/api/contacts/{contact_id}/activities",
            headers=buyer_headers,
            json=activity_data,
        )
        assert resp.status_code == 201, f"添加活动应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 201
        assert data["message"] == "添加成功"
        assert data["data"]["action_type"] == "call"
        assert data["data"]["summary"] == "初次电话沟通"
        assert data["data"]["detail"] == "讨论了合作意向，对方表示有兴趣深入了解"
        assert data["data"]["contact_id"] == contact_id
        assert "id" in data["data"]
        assert "created_at" in data["data"]

    @pytest.mark.parametrize("action_type", ["note", "call", "meeting", "email", "wechat", "order", "import"])
    def test_create_activity_all_types(self, client: TestClient, buyer_headers, action_type):
        """支持所有活动类型"""
        contact_id = self._create_contact(client, buyer_headers)
        resp = client.post(
            f"/api/contacts/{contact_id}/activities",
            headers=buyer_headers,
            json={"action_type": action_type, "summary": f"{action_type}活动"},
        )
        assert resp.status_code == 201, f"活动类型 {action_type} 应成功: {resp.text}"
        assert resp.json()["data"]["action_type"] == action_type

    def test_create_activity_minimal(self, client: TestClient, buyer_headers):
        """仅必填字段创建活动"""
        contact_id = self._create_contact(client, buyer_headers)
        resp = client.post(
            f"/api/contacts/{contact_id}/activities",
            headers=buyer_headers,
            json={"action_type": "note"},
        )
        assert resp.status_code == 201, f"最小化创建应成功: {resp.text}"
        assert resp.json()["data"]["action_type"] == "note"

    def test_create_activity_invalid_type(self, client: TestClient, buyer_headers):
        """无效活动类型返回 400"""
        contact_id = self._create_contact(client, buyer_headers)
        resp = client.post(
            f"/api/contacts/{contact_id}/activities",
            headers=buyer_headers,
            json={"action_type": "invalid_type", "summary": "测试"},
        )
        assert resp.status_code == 400, f"无效类型应返回 400: {resp.text}"

    def test_create_activity_contact_not_found(self, client: TestClient, buyer_headers):
        """不存在的联系人返回 404"""
        resp = client.post(
            "/api/contacts/99999/activities",
            headers=buyer_headers,
            json={"action_type": "note", "summary": "测试"},
        )
        assert resp.status_code == 404

    def test_create_activity_other_user(self, client: TestClient, buyer_headers, promoter_headers):
        """不能给其他用户的联系人添加活动"""
        contact_id = self._create_contact(client, buyer_headers)
        resp = client.post(
            f"/api/contacts/{contact_id}/activities",
            headers=promoter_headers,
            json={"action_type": "note", "summary": "无权添加"},
        )
        assert resp.status_code == 404

    def test_create_activity_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
        resp = client.post(
            "/api/contacts/1/activities",
            json={"action_type": "note"},
        )
        assert resp.status_code == 401


class TestListActivities:
    """活动列表测试"""

    def _create_contact_with_activities(self, client, headers, count=3):
        """辅助：创建联系人并添加多条活动，返回contact_id"""
        create_resp = client.post("/api/contacts", headers=headers, json={"name": "活动列表测试"})
        contact_id = create_resp.json()["data"]["id"]

        for i in range(count):
            client.post(
                f"/api/contacts/{contact_id}/activities",
                headers=headers,
                json={"action_type": "note", "summary": f"活动{i+1}"},
            )
        return contact_id

    def test_list_activities(self, client: TestClient, buyer_headers):
        """查看联系人的活动列表"""
        contact_id = self._create_contact_with_activities(client, buyer_headers, 3)

        resp = client.get(f"/api/contacts/{contact_id}/activities", headers=buyer_headers)
        assert resp.status_code == 200, f"活动列表应可访问: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] == 3
        assert len(data["data"]["items"]) == 3

        # 检查按时间倒序
        items = data["data"]["items"]
        assert items[0]["summary"] == "活动3"  # 最新的在前

    def test_list_activities_pagination(self, client: TestClient, buyer_headers):
        """分页"""
        contact_id = self._create_contact_with_activities(client, buyer_headers, 5)

        resp = client.get(
            f"/api/contacts/{contact_id}/activities",
            headers=buyer_headers,
            params={"page": 1, "page_size": 2},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) == 2
        assert data["total"] == 5

    def test_list_activities_empty(self, client: TestClient, buyer_headers):
        """没有活动的联系人返回空列表"""
        create_resp = client.post("/api/contacts", headers=buyer_headers, json={"name": "无活动联系人"})
        contact_id = create_resp.json()["data"]["id"]

        resp = client.get(f"/api/contacts/{contact_id}/activities", headers=buyer_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0
        assert resp.json()["data"]["items"] == []

    def test_list_activities_contact_not_found(self, client: TestClient, buyer_headers):
        """不存在的联系人返回 404"""
        resp = client.get("/api/contacts/99999/activities", headers=buyer_headers)
        assert resp.status_code == 404

    def test_list_activities_other_user(self, client: TestClient, buyer_headers, promoter_headers):
        """不能查看其他用户的联系人活动"""
        contact_id = self._create_contact_with_activities(client, buyer_headers, 1)
        resp = client.get(f"/api/contacts/{contact_id}/activities", headers=promoter_headers)
        assert resp.status_code == 404

    def test_list_activities_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
        resp = client.get("/api/contacts/1/activities")
        assert resp.status_code == 401
