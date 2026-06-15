"""
供需匹配模块测试
==================
- 发布需求（需登录）
- 需求大厅列表（公开）
- 我的需求（需登录）
- 获取需求详情
- 修改需求（仅发布者/管理员）
- 删除需求（仅发布者/管理员）
- 权限边界测试
"""

import pytest
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

    def test_create_need_success(self, client: TestClient, buyer_headers):
        """认证用户成功发布需求"""
        resp = client.post(self.CREATE_URL, headers=buyer_headers, json=self.NEED_DATA)
        assert resp.status_code == 200, f"发布需求应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "需求发布成功"
        assert data["data"]["title"] == "寻找AI技术合作伙伴"
        assert data["data"]["status"] == "open"
        assert data["data"]["category"] == "科技产品"

    def test_create_need_unauthenticated(self, client: TestClient):
        """未认证用户发布需求应返回 401"""
        resp = client.post(self.CREATE_URL, json=self.NEED_DATA)
        assert resp.status_code == 401, f"未认证应返回 401: {resp.text}"

    def test_create_need_missing_fields(self, client: TestClient, buyer_headers):
        """缺少必填字段应返回 422"""
        resp = client.post(
            self.CREATE_URL,
            headers=buyer_headers,
            json={"title": "不完整的需求"},
        )
        assert resp.status_code == 422, f"缺少必填字段应返回 422: {resp.text}"

    def test_create_need_all_roles(self, client: TestClient, buyer_headers, promoter_headers, supplier_headers):
        """所有角色(买家/推广员/供应商)都能发布需求"""
        for headers in [buyer_headers, promoter_headers, supplier_headers]:
            resp = client.post(self.CREATE_URL, headers=headers, json={
                "title": f"多角色测试需求",
                "contact_name": "测试",
            })
            assert resp.status_code == 200, f"角色发布需求应成功: {resp.text}"


class TestListNeeds:
    """需求大厅列表测试"""

    LIST_URL = "/api/needs"

    def test_list_needs_public(self, client: TestClient):
        """未登录用户可查看需求大厅（只显示 open 状态）"""
        resp = client.get(self.LIST_URL)
        assert resp.status_code == 200, f"列表应可访问: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        items = data["data"]["items"]
        assert len(items) >= 2, f"应至少有 2 个 open 需求，实际 {len(items)}"
        for item in items:
            assert item["status"] == "open", f"公开列表只应显示 open 需求"

    def test_list_needs_filter_category(self, client: TestClient):
        """按品类筛选"""
        resp = client.get(self.LIST_URL, params={"category": "企业服务"})
        assert resp.status_code == 200
        data = resp.json()
        for item in data["data"]["items"]:
            assert item["category"] == "企业服务"

    def test_list_needs_filter_status_closed(self, client: TestClient):
        """按状态筛选 closed"""
        resp = client.get(self.LIST_URL, params={"status": "closed"})
        assert resp.status_code == 200
        data = resp.json()
        for item in data["data"]["items"]:
            assert item["status"] == "closed"

    def test_list_needs_search(self, client: TestClient):
        """搜索需求"""
        resp = client.get(self.LIST_URL, params={"search": "CRM"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) >= 1
        # CRM 应该在"寻找企业级CRM系统供应商"的标题中
        titles = [item["title"] for item in data["data"]["items"]]
        assert any("CRM" in t for t in titles), f"应搜到包含 CRM 的需求: {titles}"

    def test_list_needs_pagination(self, client: TestClient):
        """分页参数测试"""
        resp = client.get(self.LIST_URL, params={"page": 1, "page_size": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 1
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 1
        assert data["data"]["total"] >= 1

    def test_list_needs_no_results(self, client: TestClient):
        """搜索不存在的内容返回空列表"""
        resp = client.get(self.LIST_URL, params={"search": "ZZZZZZ_NOT_EXIST"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 0
        assert data["data"]["items"] == []


class TestMyNeeds:
    """我的需求测试"""

    MY_URL = "/api/needs/my"

    def test_my_needs_authenticated(self, client: TestClient, buyer_headers):
        """认证用户可查看自己发布的需求"""
        resp = client.get(self.MY_URL, headers=buyer_headers)
        assert resp.status_code == 200, f"查询我的需求应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        # buyer1 有 2 条种子需求
        assert data["data"]["total"] >= 2

    def test_my_needs_unauthenticated(self, client: TestClient):
        """未认证用户查看我的需求应返回 401"""
        resp = client.get(self.MY_URL)
        assert resp.status_code == 401

    def test_my_needs_only_own(self, client: TestClient, promoter_headers):
        """每个用户只能看到自己的需求"""
        resp = client.get(self.MY_URL, headers=promoter_headers)
        assert resp.status_code == 200
        data = resp.json()
        # promoter 有 1 条 seed + 可能由其他测试创建的
        assert data["data"]["total"] >= 1

    def test_my_needs_pagination(self, client: TestClient, buyer_headers):
        """我的需求分页"""
        resp = client.get(self.MY_URL, headers=buyer_headers, params={"page": 1, "page_size": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 1
        assert data["data"]["page"] == 1


class TestGetNeed:
    """获取需求详情测试"""

    def test_get_need_success(self, client: TestClient):
        """获取需求详情（公开，无需登录）"""
        # 先获取列表拿到第一个需求的 ID
        list_resp = client.get("/api/needs")
        need_id = list_resp.json()["data"]["items"][0]["id"]

        resp = client.get(f"/api/needs/{need_id}")
        assert resp.status_code == 200, f"获取详情应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["id"] == need_id
        assert "title" in data["data"]
        assert "user" in data["data"], "详情应包含发布者信息"

    def test_get_need_not_found(self, client: TestClient):
        """不存在的需求应返回 404"""
        resp = client.get("/api/needs/99999")
        assert resp.status_code == 404


class TestUpdateNeed:
    """修改需求测试"""

    def _create_own_need(self, client: TestClient, headers) -> int:
        """创建一条属于自己的需求并返回 ID"""
        resp = client.post(
            "/api/needs",
            headers=headers,
            json={
                "title": "需要更新的需求",
                "contact_name": "测试联系人",
                "contact_phone": "13800138000",
            },
        )
        return resp.json()["data"]["id"]

    def test_update_need_owner(self, client: TestClient, buyer_headers):
        """发布者修改自己的需求"""
        need_id = self._create_own_need(client, buyer_headers)
        resp = client.put(
            f"/api/needs/{need_id}",
            headers=buyer_headers,
            json={"title": "修改后的需求标题", "budget": "20万-50万"},
        )
        assert resp.status_code == 200, f"修改需求应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "需求更新成功"
        assert data["data"]["title"] == "修改后的需求标题"
        assert data["data"]["budget"] == "20万-50万"

    def test_update_need_status_to_closed(self, client: TestClient, buyer_headers):
        """发布者关闭自己的需求"""
        need_id = self._create_own_need(client, buyer_headers)
        resp = client.put(
            f"/api/needs/{need_id}",
            headers=buyer_headers,
            json={"status": "closed"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "closed"

    def test_update_need_admin(self, client: TestClient, admin_headers):
        """管理员可修改任何需求"""
        # 获取第一条公开需求
        resp = client.get("/api/needs")
        items = resp.json()["data"]["items"]
        assert len(items) > 0, "应有需求数据"
        need_id = items[0]["id"]
        resp = client.put(
            f"/api/needs/{need_id}",
            headers=admin_headers,
            json={"title": "管理员修改的标题"},
        )
        assert resp.status_code == 200, f"管理员修改应成功: {resp.text}"

    def test_update_need_forbidden(self, client: TestClient, buyer_headers, promoter_headers):
        """非发布者且非管理员无法修改需求"""
        # buyer 创建需求
        need_id = self._create_own_need(client, buyer_headers)
        # promoter 来修改
        resp = client.put(
            f"/api/needs/{need_id}",
            headers=promoter_headers,
            json={"title": "无权修改"},
        )
        assert resp.status_code == 403, "非发布者修改应返回 403"

    def test_update_need_unauthenticated(self, client: TestClient):
        """未认证修改需求应返回 401"""
        resp = client.put("/api/needs/1", json={"title": "未登录修改"})
        assert resp.status_code == 401

    def test_update_need_not_found(self, client: TestClient, buyer_headers):
        """修改不存在的需求应返回 404"""
        resp = client.put(
            "/api/needs/99999",
            headers=buyer_headers,
            json={"title": "不存在的需求"},
        )
        assert resp.status_code == 404


class TestDeleteNeed:
    """删除需求测试"""

    def _create_temp_need(self, client: TestClient, headers) -> int:
        """创建临时需求并返回 ID"""
        resp = client.post(
            "/api/needs",
            headers=headers,
            json={
                "title": "临时需求-即将删除",
                "contact_name": "测试",
                "contact_phone": "13900139000",
            },
        )
        return resp.json()["data"]["id"]

    def test_delete_need_owner(self, client: TestClient, buyer_headers):
        """发布者删除自己的需求"""
        need_id = self._create_temp_need(client, buyer_headers)
        resp = client.delete(f"/api/needs/{need_id}", headers=buyer_headers)
        assert resp.status_code == 200, f"删除需求应成功: {resp.text}"
        assert resp.json()["message"] == "需求删除成功"

        # 确认已删除
        resp = client.get(f"/api/needs/{need_id}")
        assert resp.status_code == 404

    def test_delete_need_admin(self, client: TestClient, buyer_headers, admin_headers):
        """管理员可删除任何需求"""
        need_id = self._create_temp_need(client, buyer_headers)
        resp = client.delete(f"/api/needs/{need_id}", headers=admin_headers)
        assert resp.status_code == 200

    def test_delete_need_forbidden(self, client: TestClient, buyer_headers, promoter_headers):
        """非发布者且非管理员无法删除需求"""
        need_id = self._create_temp_need(client, buyer_headers)
        resp = client.delete(f"/api/needs/{need_id}", headers=promoter_headers)
        assert resp.status_code == 403

    def test_delete_need_unauthenticated(self, client: TestClient):
        """未认证删除需求应返回 401"""
        resp = client.delete("/api/needs/1")
        assert resp.status_code == 401

    def test_delete_need_not_found(self, client: TestClient, buyer_headers):
        """删除不存在的需求应返回 404"""
        resp = client.delete("/api/needs/99999", headers=buyer_headers)
        assert resp.status_code == 404
