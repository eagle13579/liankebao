"""
联系人模块测试
============
- 创建联系人
- 列表 + 分页
- 搜索
- 详情
- 更新
- 删除
- 标签列表
- 批量创建
- 权限校验
"""
import pytest
from fastapi.testclient import TestClient


class TestCreateContact:
    """创建联系人测试"""

    CREATE_URL = "/api/contacts"

    CONTACT_DATA = {
        "name": "测试联系人张三",
        "phone": "13912345678",
        "wechat_id": "zhangsan_wechat",
        "company": "测试科技有限公司",
        "position": "产品经理",
        "email": "zhangsan@test.com",
        "notes": "这是备注信息",
        "tags": "VIP,核心客户,技术",
    }

    def test_create_contact_success(self, client: TestClient, buyer_headers):
        """认证用户成功创建联系人"""
        resp = client.post(self.CREATE_URL, headers=buyer_headers, json=self.CONTACT_DATA)
        assert resp.status_code == 201, f"创建联系人应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 201
        assert data["message"] == "创建成功"
        assert data["data"]["name"] == "测试联系人张三"
        assert data["data"]["phone"] == "13912345678"
        assert data["data"]["wechat_id"] == "zhangsan_wechat"
        assert data["data"]["company"] == "测试科技有限公司"
        assert data["data"]["tags"] == "VIP,核心客户,技术"
        assert data["data"]["owner_id"] > 0
        assert "id" in data["data"]
        assert "created_at" in data["data"]

    def test_create_contact_minimal(self, client: TestClient, buyer_headers):
        """仅必填字段创建联系人"""
        resp = client.post(self.CREATE_URL, headers=buyer_headers, json={"name": "仅姓名"})
        assert resp.status_code == 201, f"最小化创建应成功: {resp.text}"
        assert resp.json()["data"]["name"] == "仅姓名"

    def test_create_contact_unauthenticated(self, client: TestClient):
        """未认证创建联系人返回 401"""
        resp = client.post(self.CREATE_URL, json=self.CONTACT_DATA)
        assert resp.status_code == 401

    def test_create_contact_empty_name(self, client: TestClient, buyer_headers):
        """姓名为空返回 422"""
        resp = client.post(self.CREATE_URL, headers=buyer_headers, json={"name": ""})
        assert resp.status_code == 422

    def test_create_contact_all_roles(self, client: TestClient, buyer_headers, supplier_headers, promoter_headers):
        """所有角色都能创建联系人"""
        for role, headers in [("buyer", buyer_headers), ("supplier", supplier_headers), ("promoter", promoter_headers)]:
            resp = client.post(
                self.CREATE_URL,
                headers=headers,
                json={"name": f"{role}_联系人"},
            )
            assert resp.status_code == 201, f"{role} 创建联系人应成功: {resp.text}"


class TestListContacts:
    """联系人列表测试"""

    LIST_URL = "/api/contacts"

    def _create_contacts(self, client: TestClient, headers, count=3):
        """辅助：创建多条联系人"""
        ids = []
        for i in range(count):
            resp = client.post(
                "/api/contacts",
                headers=headers,
                json={"name": f"联系人{i}", "phone": f"1380000000{i}", "tags": "测试"},
            )
            ids.append(resp.json()["data"]["id"])
        return ids

    def test_list_contacts(self, client: TestClient, buyer_headers):
        """获取联系人列表"""
        self._create_contacts(client, buyer_headers, 2)
        resp = client.get(self.LIST_URL, headers=buyer_headers)
        assert resp.status_code == 200, f"列表应可访问: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] >= 2
        assert len(data["data"]["items"]) >= 2
        contact = data["data"]["items"][0]
        assert "name" in contact
        assert "phone" in contact
        assert "id" in contact

    def test_list_contacts_pagination(self, client: TestClient, buyer_headers):
        """分页"""
        self._create_contacts(client, buyer_headers, 5)
        resp = client.get(self.LIST_URL, headers=buyer_headers, params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) <= 2
        assert data["total"] >= 5

    def test_list_contacts_tag_filter(self, client: TestClient, buyer_headers):
        """按标签筛选"""
        client.post("/api/contacts", headers=buyer_headers, json={"name": "标签测试-张三", "tags": "VIP客户"})
        client.post("/api/contacts", headers=buyer_headers, json={"name": "标签测试-李四", "tags": "普通客户"})

        resp = client.get(self.LIST_URL, headers=buyer_headers, params={"tag": "VIP客户"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1
        for item in data["items"]:
            assert "VIP客户" in (item.get("tags") or "")

    def test_list_contacts_isolation(self, client: TestClient, buyer_headers, promoter_headers):
        """不同用户联系人隔离"""
        # buyer 创建 2 个联系人
        self._create_contacts(client, buyer_headers, 2)
        # promoter 创建 1 个联系人
        self._create_contacts(client, promoter_headers, 1)

        # buyer 只能看到自己的
        buyer_resp = client.get(self.LIST_URL, headers=buyer_headers)
        total_buyer = buyer_resp.json()["data"]["total"]

        # promoter 只能看到自己的
        promoter_resp = client.get(self.LIST_URL, headers=promoter_headers)
        total_promoter = promoter_resp.json()["data"]["total"]

        # 两个总数不同（不能断言精确值因为其他测试也创建了联系人）
        # 至少每个用户能看到自己创建的联系人
        assert total_buyer >= 2
        assert total_promoter >= 1

    def test_list_contacts_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
        resp = client.get(self.LIST_URL)
        assert resp.status_code == 401


class TestSearchContacts:
    """联系人搜索测试"""

    SEARCH_URL = "/api/contacts/search"

    def test_search_by_name(self, client: TestClient, buyer_headers):
        """按姓名搜索"""
        client.post("/api/contacts", headers=buyer_headers, json={"name": "搜索姓名测试", "phone": "13900001111"})
        resp = client.get(self.SEARCH_URL, headers=buyer_headers, params={"q": "搜索姓名"})
        assert resp.status_code == 200, f"搜索应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] >= 1
        names = [item["name"] for item in data["data"]["items"]]
        assert any("搜索姓名测试" in n for n in names)

    def test_search_by_phone(self, client: TestClient, buyer_headers):
        """按电话搜索"""
        client.post("/api/contacts", headers=buyer_headers, json={"name": "电话搜索测试", "phone": "13700002222"})
        resp = client.get(self.SEARCH_URL, headers=buyer_headers, params={"q": "13700002222"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1
        assert any(item["phone"] == "13700002222" for item in data["items"])

    def test_search_no_results(self, client: TestClient, buyer_headers):
        """搜索无结果"""
        resp = client.get(self.SEARCH_URL, headers=buyer_headers, params={"q": "ZZZZ_NOT_EXIST_ZZZZ"})
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0
        assert resp.json()["data"]["items"] == []

    def test_search_pagination(self, client: TestClient, buyer_headers):
        """搜索分页"""
        for i in range(3):
            client.post("/api/contacts", headers=buyer_headers, json={"name": f"分页搜索{i}"})
        resp = client.get(self.SEARCH_URL, headers=buyer_headers, params={"q": "分页搜索", "page": 1, "page_size": 1})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 1
        assert len(data["items"]) == 1

    def test_search_unauthenticated(self, client: TestClient):
        """未认证搜索返回 401"""
        resp = client.get(self.SEARCH_URL, params={"q": "test"})
        assert resp.status_code == 401

    def test_search_empty_query(self, client: TestClient, buyer_headers):
        """空搜索词返回 422"""
        resp = client.get(self.SEARCH_URL, headers=buyer_headers, params={"q": ""})
        assert resp.status_code == 422


class TestGetContact:
    """联系人详情测试"""

    def test_get_contact_success(self, client: TestClient, buyer_headers):
        """获取联系人详情"""
        create_resp = client.post(
            "/api/contacts",
            headers=buyer_headers,
            json={"name": "详情测试", "phone": "13600001111", "company": "详情公司"},
        )
        contact_id = create_resp.json()["data"]["id"]

        resp = client.get(f"/api/contacts/{contact_id}", headers=buyer_headers)
        assert resp.status_code == 200, f"获取详情应成功: {resp.text}"
        data = resp.json()["data"]
        assert data["name"] == "详情测试"
        assert data["phone"] == "13600001111"
        assert data["company"] == "详情公司"
        assert data["id"] == contact_id

    def test_get_contact_not_found(self, client: TestClient, buyer_headers):
        """不存在的联系人返回 404"""
        resp = client.get("/api/contacts/99999", headers=buyer_headers)
        assert resp.status_code == 404

    def test_get_contact_other_user(self, client: TestClient, buyer_headers, promoter_headers):
        """不能查看其他用户的联系人"""
        create_resp = client.post(
            "/api/contacts",
            headers=buyer_headers,
            json={"name": "买家私密联系人"},
        )
        contact_id = create_resp.json()["data"]["id"]

        resp = client.get(f"/api/contacts/{contact_id}", headers=promoter_headers)
        assert resp.status_code == 404, "其他用户不应看到此联系人"

    def test_get_contact_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
        resp = client.get("/api/contacts/1")
        assert resp.status_code == 401


class TestUpdateContact:
    """更新联系人测试"""

    def test_update_contact_success(self, client: TestClient, buyer_headers):
        """更新联系人信息"""
        create_resp = client.post(
            "/api/contacts",
            headers=buyer_headers,
            json={"name": "更新前", "company": "旧公司", "tags": "旧标签"},
        )
        contact_id = create_resp.json()["data"]["id"]

        resp = client.put(
            f"/api/contacts/{contact_id}",
            headers=buyer_headers,
            json={"name": "更新后", "company": "新公司", "tags": "新标签"},
        )
        assert resp.status_code == 200, f"更新应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "更新成功"
        assert data["data"]["name"] == "更新后"
        assert data["data"]["company"] == "新公司"
        assert data["data"]["tags"] == "新标签"

    def test_update_contact_partial(self, client: TestClient, buyer_headers):
        """部分更新，只修改一个字段"""
        create_resp = client.post(
            "/api/contacts",
            headers=buyer_headers,
            json={"name": "部分更新测试", "phone": "13500001111"},
        )
        contact_id = create_resp.json()["data"]["id"]

        resp = client.put(
            f"/api/contacts/{contact_id}",
            headers=buyer_headers,
            json={"phone": "13500009999"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "部分更新测试"  # 不应改变
        assert data["phone"] == "13500009999"  # 应更新

    def test_update_contact_not_found(self, client: TestClient, buyer_headers):
        """更新不存在的联系人返回 404"""
        resp = client.put(
            "/api/contacts/99999",
            headers=buyer_headers,
            json={"name": "不存在"},
        )
        assert resp.status_code == 404

    def test_update_contact_other_user(self, client: TestClient, buyer_headers, promoter_headers):
        """不能更新其他用户的联系人"""
        create_resp = client.post(
            "/api/contacts",
            headers=buyer_headers,
            json={"name": "买家联系人"},
        )
        contact_id = create_resp.json()["data"]["id"]

        resp = client.put(
            f"/api/contacts/{contact_id}",
            headers=promoter_headers,
            json={"name": "被篡改"},
        )
        assert resp.status_code == 404

    def test_update_contact_unauthenticated(self, client: TestClient):
        """未认证更新返回 401"""
        resp = client.put("/api/contacts/1", json={"name": "未认证"})
        assert resp.status_code == 401


class TestDeleteContact:
    """删除联系人测试"""

    def test_delete_contact_success(self, client: TestClient, buyer_headers):
        """删除自己的联系人"""
        create_resp = client.post(
            "/api/contacts",
            headers=buyer_headers,
            json={"name": "待删除联系人"},
        )
        contact_id = create_resp.json()["data"]["id"]

        resp = client.delete(f"/api/contacts/{contact_id}", headers=buyer_headers)
        assert resp.status_code == 200, f"删除应成功: {resp.text}"
        assert resp.json()["message"] == "删除成功"

        # 确认已删除
        get_resp = client.get(f"/api/contacts/{contact_id}", headers=buyer_headers)
        assert get_resp.status_code == 404

    def test_delete_contact_not_found(self, client: TestClient, buyer_headers):
        """删除不存在的联系人返回 404"""
        resp = client.delete("/api/contacts/99999", headers=buyer_headers)
        assert resp.status_code == 404

    def test_delete_contact_other_user(self, client: TestClient, buyer_headers, promoter_headers):
        """不能删除其他用户的联系人"""
        create_resp = client.post(
            "/api/contacts",
            headers=buyer_headers,
            json={"name": "买家联系人"},
        )
        contact_id = create_resp.json()["data"]["id"]

        resp = client.delete(f"/api/contacts/{contact_id}", headers=promoter_headers)
        assert resp.status_code == 404

    def test_delete_contact_unauthenticated(self, client: TestClient):
        """未认证删除返回 401"""
        resp = client.delete("/api/contacts/1")
        assert resp.status_code == 401


class TestContactTags:
    """联系人标签测试"""

    TAGS_URL = "/api/contacts/tags"

    def test_list_tags(self, client: TestClient, buyer_headers):
        """获取当前用户的标签列表"""
        client.post("/api/contacts", headers=buyer_headers, json={"name": "标签A", "tags": "VIP,大客户"})
        client.post("/api/contacts", headers=buyer_headers, json={"name": "标签B", "tags": "VIP,普通"})

        resp = client.get(self.TAGS_URL, headers=buyer_headers)
        assert resp.status_code == 200, f"标签列表应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        tags = data["data"]["tags"]
        assert "VIP" in tags
        assert "大客户" in tags or "普通" in tags

    def test_list_tags_empty(self, client: TestClient, buyer_headers):
        """无标签时返回空列表"""
        # 创建一个没有标签的联系人
        client.post("/api/contacts", headers=buyer_headers, json={"name": "无标签"})
        resp = client.get(self.TAGS_URL, headers=buyer_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"]["tags"], list)

    def test_list_tags_unauthenticated(self, client: TestClient):
        """未认证返回 401"""
        resp = client.get(self.TAGS_URL)
        assert resp.status_code == 401


class TestBatchCreateContacts:
    """批量创建联系人测试"""

    BATCH_URL = "/api/contacts/batch"

    def test_batch_create_success(self, client: TestClient, buyer_headers):
        """批量创建联系人成功"""
        contacts = [
            {"name": "批量A", "phone": "13100000001", "tags": "批量导入"},
            {"name": "批量B", "phone": "13100000002", "tags": "批量导入"},
            {"name": "批量C", "phone": "13100000003", "tags": "批量导入"},
        ]
        resp = client.post(self.BATCH_URL, headers=buyer_headers, json=contacts)
        assert resp.status_code == 201, f"批量创建应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 201
        assert data["data"]["total"] == 3
        assert len(data["data"]["items"]) == 3
        assert "成功创建 3 个联系人" in data["message"]

    def test_batch_create_single(self, client: TestClient, buyer_headers):
        """批量创建单个联系人"""
        resp = client.post(
            self.BATCH_URL,
            headers=buyer_headers,
            json=[{"name": "单个批量导入"}],
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["total"] == 1

    def test_batch_create_empty(self, client: TestClient, buyer_headers):
        """空数组返回 422"""
        resp = client.post(self.BATCH_URL, headers=buyer_headers, json=[])
        assert resp.status_code == 422

    def test_batch_create_unauthenticated(self, client: TestClient):
        """未认证批量创建返回 401"""
        resp = client.post(self.BATCH_URL, json=[{"name": "未认证导入"}])
        assert resp.status_code == 401
