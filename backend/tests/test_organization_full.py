"""组织管理（多租户）全面测试 —— 覆盖全部路由和边角场景"""
import pytest
from fastapi.testclient import TestClient


class TestOrgCRUD:
    """组织 CRUD 测试"""

    def test_create_org(self, client: TestClient, buyer_headers: dict):
        """POST /api/orgs — 创建组织"""
        resp = client.post("/api/orgs", json={"name": "测试组织"}, headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "id" in data["data"]
        return data["data"]["id"]

    def test_create_org_empty_name(self, client: TestClient, buyer_headers: dict):
        """POST /api/orgs — 空名称"""
        resp = client.post("/api/orgs", json={"name": ""}, headers=buyer_headers)
        assert resp.status_code == 422

    def test_create_org_no_auth(self, client: TestClient):
        """POST /api/orgs — 无认证"""
        resp = client.post("/api/orgs", json={"name": "测试组织"})
        assert resp.status_code == 401

    def test_list_orgs(self, client: TestClient, buyer_headers: dict):
        """GET /api/orgs — 组织列表"""
        # 先创建一个
        client.post("/api/orgs", json={"name": "列表测试"}, headers=buyer_headers)
        resp = client.get("/api/orgs", headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["data"], list)

    def test_list_orgs_no_auth(self, client: TestClient):
        """GET /api/orgs — 无认证"""
        resp = client.get("/api/orgs")
        assert resp.status_code == 401

    def test_get_org_detail(self, client: TestClient, buyer_headers: dict):
        """GET /api/orgs/{id} — 组织详情"""
        create_resp = client.post("/api/orgs", json={"name": "详情组织"}, headers=buyer_headers)
        org_id = create_resp.json()["data"]["id"]
        resp = client.get(f"/api/orgs/{org_id}", headers=buyer_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "详情组织"

    def test_get_org_not_found(self, client: TestClient, buyer_headers: dict):
        """GET /api/orgs/{id} — 不存在"""
        resp = client.get("/api/orgs/99999", headers=buyer_headers)
        assert resp.status_code == 403  # Not a member

    def test_get_org_no_auth(self, client: TestClient):
        """GET /api/orgs/{id} — 无认证"""
        resp = client.get("/api/orgs/1")
        assert resp.status_code == 401

    def test_update_org(self, client: TestClient, buyer_headers: dict):
        """PUT /api/orgs/{id} — 更新组织"""
        create_resp = client.post("/api/orgs", json={"name": "旧名称"}, headers=buyer_headers)
        org_id = create_resp.json()["data"]["id"]
        resp = client.put(f"/api/orgs/{org_id}", json={"name": "新名称"}, headers=buyer_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "新名称"

    def test_update_org_not_admin(self, client: TestClient, promoter_headers: dict, buyer_headers: dict):
        """PUT /api/orgs/{id} — 非管理员更新"""
        create_resp = client.post("/api/orgs", json={"name": "权限测试组织"}, headers=buyer_headers)
        org_id = create_resp.json()["data"]["id"]
        resp = client.put(f"/api/orgs/{org_id}", json={"name": "新名称"}, headers=promoter_headers)
        assert resp.status_code == 403  # Not admin

    def test_delete_org(self, client: TestClient, buyer_headers: dict):
        """DELETE /api/orgs/{id} — 删除组织"""
        create_resp = client.post("/api/orgs", json={"name": "待删除"}, headers=buyer_headers)
        org_id = create_resp.json()["data"]["id"]
        resp = client.delete(f"/api/orgs/{org_id}", headers=buyer_headers)
        assert resp.status_code == 200
        assert resp.json()["message"] == "组织已删除"

    def test_delete_org_not_found(self, client: TestClient, buyer_headers: dict):
        """DELETE /api/orgs/{id} — 不存在"""
        resp = client.delete("/api/orgs/99999", headers=buyer_headers)
        assert resp.status_code == 403

    def test_delete_org_no_auth(self, client: TestClient):
        """DELETE /api/orgs/{id} — 无认证"""
        resp = client.delete("/api/orgs/1")
        assert resp.status_code == 401


class TestOrgMembers:
    """成员管理测试"""

    @pytest.fixture
    def org_id(self, client: TestClient, buyer_headers: dict) -> int:
        resp = client.post("/api/orgs", json={"name": "成员测试组织"}, headers=buyer_headers)
        return resp.json()["data"]["id"]

    def test_list_members(self, client: TestClient, buyer_headers: dict, org_id: int):
        """GET /api/orgs/{id}/members"""
        resp = client.get(f"/api/orgs/{org_id}/members", headers=buyer_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    def test_list_members_no_member(self, client: TestClient, promoter_headers: dict, org_id: int):
        """GET /api/orgs/{id}/members — 非成员"""
        resp = client.get(f"/api/orgs/{org_id}/members", headers=promoter_headers)
        assert resp.status_code == 403

    def test_add_member(self, client: TestClient, buyer_headers: dict, org_id: int):
        """POST /api/orgs/{id}/members — 添加成员"""
        resp = client.post(
            f"/api/orgs/{org_id}/members",
            json={"user_id": 3, "role": "member"},  # promoter1 is user 3
            headers=buyer_headers
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 200

    def test_add_member_not_admin(self, client: TestClient, promoter_headers: dict, org_id: int):
        """POST /api/orgs/{id}/members — 非管理员"""
        resp = client.post(
            f"/api/orgs/{org_id}/members",
            json={"user_id": 3, "role": "member"},
            headers=promoter_headers
        )
        assert resp.status_code == 403

    def test_add_member_nonexistent_user(self, client: TestClient, buyer_headers: dict, org_id: int):
        """POST /api/orgs/{id}/members — 不存在的用户"""
        resp = client.post(
            f"/api/orgs/{org_id}/members",
            json={"user_id": 99999, "role": "member"},
            headers=buyer_headers
        )
        assert resp.status_code == 404

    def test_add_duplicate_member(self, client: TestClient, buyer_headers: dict, org_id: int):
        """POST /api/orgs/{id}/members — 重复添加"""
        client.post(f"/api/orgs/{org_id}/members", json={"user_id": 3, "role": "member"}, headers=buyer_headers)
        resp = client.post(f"/api/orgs/{org_id}/members", json={"user_id": 3, "role": "member"}, headers=buyer_headers)
        assert resp.status_code in (200, 400)  # 可能已存在

    def test_update_member_role(self, client: TestClient, buyer_headers: dict, org_id: int):
        """PUT /api/orgs/{id}/members/{user_id}/role"""
        # 先添加成员
        client.post(f"/api/orgs/{org_id}/members", json={"user_id": 3, "role": "member"}, headers=buyer_headers)
        resp = client.put(f"/api/orgs/{org_id}/members/3/role?role=admin", headers=buyer_headers)
        assert resp.status_code == 200

    def test_update_member_role_not_admin(self, client: TestClient, promoter_headers: dict, org_id: int):
        """PUT /api/orgs/{id}/members/role — 非管理员"""
        resp = client.put(f"/api/orgs/{org_id}/members/3/role?role=admin", headers=promoter_headers)
        assert resp.status_code == 403

    def test_remove_member(self, client: TestClient, buyer_headers: dict, org_id: int):
        """DELETE /api/orgs/{id}/members/{user_id}"""
        client.post(f"/api/orgs/{org_id}/members", json={"user_id": 3, "role": "member"}, headers=buyer_headers)
        resp = client.delete(f"/api/orgs/{org_id}/members/3", headers=buyer_headers)
        assert resp.status_code == 200

    def test_remove_member_not_found(self, client: TestClient, buyer_headers: dict, org_id: int):
        """DELETE /api/orgs/{id}/members/{user_id} — 不存在"""
        resp = client.delete(f"/api/orgs/{org_id}/members/99999", headers=buyer_headers)
        assert resp.status_code == 404


class TestOrgInvites:
    """邀请管理测试"""

    @pytest.fixture
    def org_id(self, client: TestClient, buyer_headers: dict) -> int:
        resp = client.post("/api/orgs", json={"name": "邀请测试组织"}, headers=buyer_headers)
        return resp.json()["data"]["id"]

    def test_create_invite(self, client: TestClient, buyer_headers: dict, org_id: int):
        """POST /api/orgs/{id}/invites"""
        resp = client.post(
            f"/api/orgs/{org_id}/invites",
            json={"email": "test@example.com"},
            headers=buyer_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data["data"]
        return data["data"]["token"]

    def test_create_invite_not_admin(self, client: TestClient, promoter_headers: dict, org_id: int):
        """POST /api/orgs/{id}/invites — 非管理员"""
        resp = client.post(
            f"/api/orgs/{org_id}/invites",
            json={"email": "test@example.com"},
            headers=promoter_headers
        )
        assert resp.status_code == 403

    def test_list_invites(self, client: TestClient, buyer_headers: dict, org_id: int):
        """GET /api/orgs/{id}/invites"""
        resp = client.get(f"/api/orgs/{org_id}/invites", headers=buyer_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    def test_accept_invite(self, client: TestClient, buyer_headers: dict, promoter_headers: dict, org_id: int):
        """POST /api/orgs/invites/accept — 接受邀请"""
        # 创建邀请
        inv_resp = client.post(
            f"/api/orgs/{org_id}/invites",
            json={"email": "promoter@test.com"},
            headers=buyer_headers
        )
        token = inv_resp.json()["data"]["token"]
        # promoter 接受邀请
        resp = client.post(
            "/api/orgs/invites/accept",
            json={"token": token},
            headers=promoter_headers
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 200

    def test_accept_invite_invalid_token(self, client: TestClient, buyer_headers: dict):
        """POST /api/orgs/invites/accept — 无效token"""
        resp = client.post(
            "/api/orgs/invites/accept",
            json={"token": "invalid-token"},
            headers=buyer_headers
        )
        assert resp.status_code == 400

    def test_cancel_invite(self, client: TestClient, buyer_headers: dict, org_id: int):
        """DELETE /api/orgs/{id}/invites/{invite_id}"""
        inv_resp = client.post(
            f"/api/orgs/{org_id}/invites",
            json={"email": "cancel@test.com"},
            headers=buyer_headers
        )
        invite_id = inv_resp.json()["data"]["id"]
        resp = client.delete(f"/api/orgs/{org_id}/invites/{invite_id}", headers=buyer_headers)
        assert resp.status_code == 200

    def test_cancel_invite_not_found(self, client: TestClient, buyer_headers: dict, org_id: int):
        """DELETE /api/orgs/{id}/invites/{invite_id} — 不存在"""
        resp = client.delete(f"/api/orgs/{org_id}/invites/99999", headers=buyer_headers)
        assert resp.status_code == 404


class TestOrgStats:
    """组织统计测试"""

    def test_org_stats(self, client: TestClient, buyer_headers: dict):
        """GET /api/orgs/{id}/stats"""
        create_resp = client.post("/api/orgs", json={"name": "统计测试"}, headers=buyer_headers)
        org_id = create_resp.json()["data"]["id"]
        resp = client.get(f"/api/orgs/{org_id}/stats", headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "member_count" in data

    def test_org_stats_no_member(self, client: TestClient, promoter_headers: dict):
        """GET /api/orgs/{id}/stats — 非成员"""
        resp = client.get("/api/orgs/99999/stats", headers=promoter_headers)
        assert resp.status_code == 403
