"""
联系人模块测试
================
- 联系人列表（分页、标签筛选）
- 创建联系人（正常/验证/权限）
- 搜索联系人（关键词/无结果/权限）
- 标签列表
- 联系人详情（存在/不存在/跨用户隔离）
- 更新联系人（正常/部分更新/不存在/跨用户隔离）
- 删除联系人（正常/不存在/跨用户隔离）
- 批量创建联系人
"""
import pytest
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
        assert resp.status_code == 201
        return resp.json()["data"]["id"]

    def test_list_contacts_success(self, client: TestClient, buyer_headers):
        """成功获取联系人列表"""
        self._create_contact(client, buyer_headers)
        self._create_contact(client, buyer_headers, name="第二联系人", phone="13800000101")

        resp = client.get(self.LIST_URL, headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] >= 2
        assert len(data["data"]["items"]) >= 2

    def test_list_contacts_empty(self, client: TestClient, promoter_headers):
        """promoter尚未创建联系人，返回空列表"""
        resp = client.get(self.LIST_URL, headers=promoter_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 0
        assert data["data"]["items"] == []

    def test_list_contacts_pagination(self, client: TestClient, supplier_headers):
        """分页参数测试（使用全新用户）"""
        for i in range(5):
            self._create_contact(client, supplier_headers, name=f"分页联系人{i}", phone=f"13800000{i:03d}")

        resp = client.get(self.LIST_URL, headers=supplier_headers, params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 2
        assert data["data"]["total"] == 5
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 2

    def test_list_contacts_page_size_edge(self, client: TestClient, buyer_headers):
        """分页边界：page_size=1 和 page_size=100"""
        cid1 = self._create_contact(client, buyer_headers)
        cid2 = self._create_contact(client, buyer_headers, name="边界测试", phone="13800000999")

        resp = client.get(self.LIST_URL, headers=buyer_headers, params={"page": 1, "page_size": 1})
        assert resp.status_code == 200
        assert len(resp.json()["data"]["items"]) == 1

        resp = client.get(self.LIST_URL, headers=buyer_headers, params={"page": 1, "page_size": 100})
        assert resp.status_code == 200

    def test_list_contacts_filter_by_tag(self, client: TestClient, buyer_headers):
        """按标签筛选联系人"""
        self._create_contact(client, buyer_headers, name="VIP客户", tags="VIP,重要")
        self._create_contact(client, buyer_headers, name="普通客户", tags="普通")

        resp = client.get(self.LIST_URL, headers=buyer_headers, params={"tag": "VIP"})
        assert resp.status_code == 200
        data = resp.json()
        for item in data["data"]["items"]:
            assert "VIP" in (item.get("tags") or "")

    def test_list_contacts_tag_no_match(self, client: TestClient, buyer_headers):
        """标签筛选无匹配时返回空列表"""
        resp = client.get(self.LIST_URL, headers=buyer_headers, params={"tag": "不存在的标签"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 0
        assert data["data"]["items"] == []

    def test_list_contacts_cross_user_isolation(self, client: TestClient, buyer_headers, promoter_headers):
        """跨用户隔离：promoter看不到buyer的联系人"""
        self._create_contact(client, buyer_headers)
        resp = client.get(self.LIST_URL, headers=promoter_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    def test_list_contacts_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.get(self.LIST_URL)
        assert resp.status_code == 401

class TestCreateContact:
    """创建联系人测试"""

    CREATE_URL = "/api/contacts"

    def test_create_contact_full_fields(self, client: TestClient, buyer_headers):
        """完整字段创建联系人"""
        resp = client.post(
            self.CREATE_URL,
            headers=buyer_headers,
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
        assert resp.status_code == 201, f"创建联系人应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 201
        assert data["message"] == "创建成功"
        assert data["data"]["name"] == "张三"
        assert data["data"]["phone"] == "13800000123"
        assert data["data"]["tags"] == "VIP,合作伙伴"
        assert data["data"]["owner_id"] > 0

    def test_create_contact_minimal_fields(self, client: TestClient, buyer_headers):
        """仅必填字段创建联系人"""
        resp = client.post(
            self.CREATE_URL,
            headers=buyer_headers,
            json={"name": "李四"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["data"]["name"] == "李四"
        assert data["data"]["source"] == "manual"

    def test_create_contact_empty_name(self, client: TestClient, buyer_headers):
        """姓名为空字符串应返回422"""
        resp = client.post(
            self.CREATE_URL,
            headers=buyer_headers,
            json={"name": ""},
        )
        assert resp.status_code == 422

    def test_create_contact_name_too_long(self, client: TestClient, buyer_headers):
        """姓名超长应返回422"""
        resp = client.post(
            self.CREATE_URL,
            headers=buyer_headers,
            json={"name": "超长姓名" * 50},
        )
        assert resp.status_code == 422

    def test_create_contact_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.post(
            self.CREATE_URL,
            json={"name": "未认证用户"},
        )
        assert resp.status_code == 401


class TestSearchContacts:
    """搜索联系人测试"""

    SEARCH_URL = "/api/contacts/search"

    def test_search_by_name(self, client: TestClient, buyer_headers):
        """按姓名搜索"""
        client.post("/api/contacts", headers=buyer_headers, json={"name": "王晓明", "phone": "13800000111"})
        resp = client.get(self.SEARCH_URL, headers=buyer_headers, params={"q": "王晓明"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] >= 1
        assert any("王晓明" in item["name"] for item in data["data"]["items"])

    def test_search_by_phone(self, client: TestClient, buyer_headers):
        """按手机号搜索"""
        client.post("/api/contacts", headers=buyer_headers, json={"name": "赵六", "phone": "13900000666"})
        resp = client.get(self.SEARCH_URL, headers=buyer_headers, params={"q": "13900000666"})
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1

    def test_search_by_company(self, client: TestClient, buyer_headers):
        """按公司名搜索"""
        client.post("/api/contacts", headers=buyer_headers, json={"name": "钱七", "company": "量子科技"})
        resp = client.get(self.SEARCH_URL, headers=buyer_headers, params={"q": "量子科技"})
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1

    def test_search_no_results(self, client: TestClient, buyer_headers):
        """搜索不存在的关键词返回空列表"""
        resp = client.get(self.SEARCH_URL, headers=buyer_headers, params={"q": "ZZZZZZ_NOT_EXIST"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 0
        assert data["data"]["items"] == []

    def test_search_empty_query(self, client: TestClient, buyer_headers):
        """空搜索词应返回422"""
        resp = client.get(self.SEARCH_URL, headers=buyer_headers, params={"q": ""})
        assert resp.status_code == 422

    def test_search_cross_user_isolation(self, client: TestClient, buyer_headers, promoter_headers):
        """跨用户隔离：promoter搜不到buyer的联系人"""
        client.post("/api/contacts", headers=buyer_headers, json={"name": "跨用户隔离测试", "phone": "13800000999"})
        resp = client.get(self.SEARCH_URL, headers=promoter_headers, params={"q": "跨用户隔离测试"})
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    def test_search_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.get(self.SEARCH_URL, params={"q": "测试"})
        assert resp.status_code == 401


class TestListTags:
    """标签列表测试"""

    TAGS_URL = "/api/contacts/tags"

    def test_list_tags_success(self, client: TestClient, buyer_headers):
        """成功获取标签列表（去重并排序）"""
        client.post("/api/contacts", headers=buyer_headers, json={"name": "标签A", "tags": "VIP,客户"})
        client.post("/api/contacts", headers=buyer_headers, json={"name": "标签B", "tags": "VIP,供应商"})
        client.post("/api/contacts", headers=buyer_headers, json={"name": "标签C", "tags": "客户"})

        resp = client.get(self.TAGS_URL, headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        tags = data["data"]["tags"]
        assert "VIP" in tags
        assert "客户" in tags
        assert "供应商" in tags
        # 验证去重：VIP只出现一次
        assert tags.count("VIP") == 1
        # 验证排序
        assert tags == sorted(tags)

    def test_list_tags_empty(self, client: TestClient, promoter_headers):
        """promoter没有联系人时标签列表为空"""
        resp = client.get(self.TAGS_URL, headers=promoter_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["tags"] == []

    def test_list_tags_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.get(self.TAGS_URL)
        assert resp.status_code == 401


class TestGetContact:
    """联系人详情测试"""

    def _create_contact(self, client: TestClient, headers, **overrides) -> int:
        data = {"name": "详情测试", "phone": "13800000200"}
        data.update(overrides)
        resp = client.post("/api/contacts", headers=headers, json=data)
        return resp.json()["data"]["id"]

    def test_get_contact_success(self, client: TestClient, buyer_headers):
        """成功获取联系人详情"""
        contact_id = self._create_contact(client, buyer_headers, name="孙八", tags="VIP")

        resp = client.get(f"/api/contacts/{contact_id}", headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["name"] == "孙八"
        assert data["data"]["tags"] == "VIP"
        assert data["data"]["id"] == contact_id

    def test_get_contact_not_found(self, client: TestClient, buyer_headers):
        """不存在的联系人返回404"""
        resp = client.get("/api/contacts/99999", headers=buyer_headers)
        assert resp.status_code == 404
        assert "不存在" in resp.text

    def test_get_contact_cross_user(self, client: TestClient, buyer_headers, promoter_headers):
        """promoter不能查看buyer的联系人"""
        contact_id = self._create_contact(client, buyer_headers)
        resp = client.get(f"/api/contacts/{contact_id}", headers=promoter_headers)
        assert resp.status_code == 404

    def test_get_contact_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.get("/api/contacts/1")
        assert resp.status_code == 401


class TestUpdateContact:
    """更新联系人测试"""

    def _create_contact(self, client: TestClient, headers, **overrides) -> int:
        data = {"name": "更新测试", "phone": "13800000300"}
        data.update(overrides)
        resp = client.post("/api/contacts", headers=headers, json=data)
        return resp.json()["data"]["id"]

    def test_update_contact_full(self, client: TestClient, buyer_headers):
        """完整更新联系人所有字段"""
        contact_id = self._create_contact(client, buyer_headers, name="周九", company="旧公司")

        resp = client.put(
            f"/api/contacts/{contact_id}",
            headers=buyer_headers,
            json={
                "name": "周九更新",
                "phone": "13800000301",
                "company": "新公司",
                "position": "CEO",
                "tags": "重要",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "更新成功"
        assert data["data"]["name"] == "周九更新"
        assert data["data"]["company"] == "新公司"
        assert data["data"]["phone"] == "13800000301"

    def test_update_contact_partial(self, client: TestClient, buyer_headers):
        """仅更新部分字段，其他字段保持不变"""
        contact_id = self._create_contact(client, buyer_headers, name="吴十", phone="13800000310", company="原公司")

        resp = client.put(
            f"/api/contacts/{contact_id}",
            headers=buyer_headers,
            json={"company": "新公司名"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["name"] == "吴十"  # 未变
        assert data["data"]["phone"] == "13800000310"  # 未变
        assert data["data"]["company"] == "新公司名"  # 更新

    def test_update_contact_not_found(self, client: TestClient, buyer_headers):
        """不存在的联系人返回404"""
        resp = client.put(
            "/api/contacts/99999",
            headers=buyer_headers,
            json={"name": "不存在"},
        )
        assert resp.status_code == 404

    def test_update_contact_cross_user(self, client: TestClient, buyer_headers, promoter_headers):
        """promoter不能更新buyer的联系人"""
        contact_id = self._create_contact(client, buyer_headers)
        resp = client.put(
            f"/api/contacts/{contact_id}",
            headers=promoter_headers,
            json={"name": "跨用户更新"},
        )
        assert resp.status_code == 404

    def test_update_contact_empty_name(self, client: TestClient, buyer_headers):
        """name更新为空字符串应返回422"""
        contact_id = self._create_contact(client, buyer_headers)
        resp = client.put(
            f"/api/contacts/{contact_id}",
            headers=buyer_headers,
            json={"name": ""},
        )
        assert resp.status_code == 422

    def test_update_contact_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.put("/api/contacts/1", json={"name": "未认证"})
        assert resp.status_code == 401


class TestDeleteContact:
    """删除联系人测试"""

    def _create_contact(self, client: TestClient, headers, **overrides) -> int:
        data = {"name": "删除测试", "phone": "13800000400"}
        data.update(overrides)
        resp = client.post("/api/contacts", headers=headers, json=data)
        return resp.json()["data"]["id"]

    def test_delete_contact_success(self, client: TestClient, buyer_headers):
        """成功删除联系人（软删除）"""
        contact_id = self._create_contact(client, buyer_headers, name="郑十一")

        resp = client.delete(f"/api/contacts/{contact_id}", headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "删除成功"

        # 删除后再次获取应返回404
        resp = client.get(f"/api/contacts/{contact_id}", headers=buyer_headers)
        assert resp.status_code == 404

    def test_delete_contact_not_found(self, client: TestClient, buyer_headers):
        """不存在的联系人返回404"""
        resp = client.delete("/api/contacts/99999", headers=buyer_headers)
        assert resp.status_code == 404

    def test_delete_contact_cross_user(self, client: TestClient, buyer_headers, promoter_headers):
        """promoter不能删除buyer的联系人"""
        contact_id = self._create_contact(client, buyer_headers)
        resp = client.delete(f"/api/contacts/{contact_id}", headers=promoter_headers)
        assert resp.status_code == 404

    def test_delete_contact_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.delete("/api/contacts/1")
        assert resp.status_code == 401


class TestBatchCreateContacts:
    """批量创建联系人测试"""

    BATCH_URL = "/api/contacts/batch"

    def test_batch_create_success(self, client: TestClient, buyer_headers):
        """成功批量创建联系人"""
        contacts = [
            {"name": "批量A", "phone": "13800000501", "company": "公司A"},
            {"name": "批量B", "phone": "13800000502", "company": "公司B", "tags": "批量"},
            {"name": "批量C", "phone": "13800000503"},
        ]
        resp = client.post(self.BATCH_URL, headers=buyer_headers, json=contacts)
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == 201
        assert "成功创建 3 个联系人" in data["message"]
        assert data["data"]["total"] == 3
        assert len(data["data"]["items"]) == 3
        # 验证source为默认值manual（ContactBase的默认source）
        assert data["data"]["items"][0]["source"] == "manual"

    def test_batch_create_empty(self, client: TestClient, buyer_headers):
        """空列表返回201但不创建任何联系人"""
        resp = client.post(self.BATCH_URL, headers=buyer_headers, json=[])
        assert resp.status_code == 201
        data = resp.json()
        assert data["data"]["total"] == 0

    def test_batch_create_single(self, client: TestClient, buyer_headers):
        """批量创建单个联系人（边界）"""
        resp = client.post(
            self.BATCH_URL,
            headers=buyer_headers,
            json=[{"name": "单批量", "phone": "13800000600"}],
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["total"] == 1

    def test_batch_create_unauthenticated(self, client: TestClient):
        """未认证返回401"""
        resp = client.post(
            self.BATCH_URL,
            json=[{"name": "批量未认证", "phone": "13800000999"}],
        )
        assert resp.status_code == 401
