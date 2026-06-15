"""
联系人活动模块测试
====================
- 获取活动列表（分页、权限）
- 创建活动（合法/非法action_type）
- 边界条件和权限隔离
"""

import pytest
from fastapi.testclient import TestClient


class TestListActivities:
    """获取联系人活动列表测试"""

    def _create_contact(self, client: TestClient, headers) -> int:
        """辅助：为当前用户创建一个联系人，返回 contact_id"""
        resp = client.post(
            "/api/contacts",
            headers=headers,
            json={
                "name": "活动测试联系人",
                "phone": "13800000100",
                "company": "测试公司",
            },
        )
        assert resp.status_code == 201
        return resp.json()["data"]["id"]

    def test_list_activities_success(self, client: TestClient, buyer_headers):
        """成功获取联系人的活动列表"""
        contact_id = self._create_contact(client, buyer_headers)

        # 先创建几条活动
        for action_type in ("note", "call", "meeting"):
            resp = client.post(
                f"/api/contacts/{contact_id}/activities",
                headers=buyer_headers,
                json={"action_type": action_type, "summary": f"测试{action_type}"},
            )
            assert resp.status_code == 201

        # 获取活动列表
        resp = client.get(f"/api/contacts/{contact_id}/activities", headers=buyer_headers)
        assert resp.status_code == 200, f"获取活动列表应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] == 3
        assert len(data["data"]["items"]) == 3

    def test_list_activities_empty(self, client: TestClient, buyer_headers):
        """无活动时返回空列表"""
        contact_id = self._create_contact(client, buyer_headers)
        resp = client.get(f"/api/contacts/{contact_id}/activities", headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 0
        assert data["data"]["items"] == []

    def test_list_activities_contact_not_found(self, client: TestClient, buyer_headers):
        """不存在的联系人返回404"""
        resp = client.get("/api/contacts/99999/activities", headers=buyer_headers)
        assert resp.status_code == 404
        assert "不存在" in resp.text

    def test_list_activities_pagination(self, client: TestClient, buyer_headers):
        """分页参数测试"""
        contact_id = self._create_contact(client, buyer_headers)
        for i in range(5):
            client.post(
                f"/api/contacts/{contact_id}/activities",
                headers=buyer_headers,
                json={"action_type": "note", "summary": f"活动{i}"},
            )

        # page_size=2
        resp = client.get(
            f"/api/contacts/{contact_id}/activities",
            headers=buyer_headers,
            params={"page": 1, "page_size": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 2
        assert data["data"]["total"] == 5
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 2

    def test_list_activities_page_size_edge(self, client: TestClient, buyer_headers):
        """分页边界：page_size=1 和 page_size=100"""
        contact_id = self._create_contact(client, buyer_headers)
        client.post(
            f"/api/contacts/{contact_id}/activities",
            headers=buyer_headers,
            json={"action_type": "note", "summary": "单活动"},
        )

        # page_size=1
        resp = client.get(
            f"/api/contacts/{contact_id}/activities",
            headers=buyer_headers,
            params={"page": 1, "page_size": 1},
        )
        assert resp.status_code == 200

        # page_size=100 (上限)
        resp = client.get(
            f"/api/contacts/{contact_id}/activities",
            headers=buyer_headers,
            params={"page": 1, "page_size": 100},
        )
        assert resp.status_code == 200

    def test_list_activities_cross_user_isolation(self, client: TestClient, buyer_headers, promoter_headers):
        """跨用户隔离：promoter不能查看buyer联系人的活动"""
        contact_id = self._create_contact(client, buyer_headers)
        client.post(
            f"/api/contacts/{contact_id}/activities",
            headers=buyer_headers,
            json={"action_type": "note", "summary": "buyer的活动"},
        )
        # promoter 访问 buyer 的联系人活动应返回404
        resp = client.get(f"/api/contacts/{contact_id}/activities", headers=promoter_headers)
        assert resp.status_code == 404

    def test_list_activities_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.get("/api/contacts/1/activities")
        assert resp.status_code == 401


class TestCreateActivity:
    """创建活动测试"""

    def _create_contact(self, client: TestClient, headers) -> int:
        resp = client.post(
            "/api/contacts",
            headers=headers,
            json={"name": "活动创建测试", "phone": "13800000200"},
        )
        return resp.json()["data"]["id"]

    @pytest.mark.parametrize("action_type", ["note", "call", "meeting", "email", "wechat", "order", "import"])
    def test_create_activity_all_types(self, client: TestClient, buyer_headers, action_type):
        """所有合法的action_type都能创建成功"""
        contact_id = self._create_contact(client, buyer_headers)
        resp = client.post(
            f"/api/contacts/{contact_id}/activities",
            headers=buyer_headers,
            json={
                "action_type": action_type,
                "summary": f"测试{action_type}活动",
                "detail": f"这是{action_type}类型的详细内容",
            },
        )
        assert resp.status_code == 201, f"action_type={action_type} 创建失败: {resp.text}"
        data = resp.json()
        assert data["code"] == 201
        assert data["message"] == "添加成功"
        assert data["data"]["action_type"] == action_type
        assert data["data"]["contact_id"] == contact_id

    def test_create_activity_minimal_fields(self, client: TestClient, buyer_headers):
        """仅填写必填字段"""
        contact_id = self._create_contact(client, buyer_headers)
        resp = client.post(
            f"/api/contacts/{contact_id}/activities",
            headers=buyer_headers,
            json={"action_type": "note"},
        )
        assert resp.status_code == 201
        assert resp.json()["code"] == 201

    def test_create_activity_invalid_type(self, client: TestClient, buyer_headers):
        """无效的action_type返回400"""
        contact_id = self._create_contact(client, buyer_headers)
        resp = client.post(
            f"/api/contacts/{contact_id}/activities",
            headers=buyer_headers,
            json={"action_type": "invalid_type", "summary": "无效类型"},
        )
        assert resp.status_code == 400
        assert "无效的活动类型" in resp.text

    def test_create_activity_contact_not_found(self, client: TestClient, buyer_headers):
        """不存在的联系人返回404"""
        resp = client.post(
            "/api/contacts/99999/activities",
            headers=buyer_headers,
            json={"action_type": "note", "summary": "测试"},
        )
        assert resp.status_code == 404

    def test_create_activity_cross_user(self, client: TestClient, buyer_headers, promoter_headers):
        """promoter不能给buyer的联系人创建活动"""
        contact_id = self._create_contact(client, buyer_headers)
        resp = client.post(
            f"/api/contacts/{contact_id}/activities",
            headers=promoter_headers,
            json={"action_type": "note", "summary": "跨用户活动"},
        )
        assert resp.status_code == 404

    def test_create_activity_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.post(
            "/api/contacts/1/activities",
            json={"action_type": "note", "summary": "未认证"},
        )
        assert resp.status_code == 401

    def test_create_activity_with_detail(self, client: TestClient, buyer_headers):
        """创建含详细内容的活动"""
        contact_id = self._create_contact(client, buyer_headers)
        resp = client.post(
            f"/api/contacts/{contact_id}/activities",
            headers=buyer_headers,
            json={
                "action_type": "meeting",
                "summary": "产品需求讨论会",
                "detail": "讨论了新功能的需求和实现方案\n参会人员：张三、李四\n会议时长：2小时",
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["summary"] == "产品需求讨论会"
        assert "讨论了新功能" in data["detail"]
