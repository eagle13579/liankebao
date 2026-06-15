"""企业知识图谱全面测试 —— 企业库 CRUD、搜索、关系图谱"""

from fastapi.testclient import TestClient


class TestEnterpriseSearch:
    """企业搜索测试"""

    def test_search_empty(self, client: TestClient):
        """GET /api/enterprise/search — 无关键词"""
        resp = client.get("/api/enterprise/search")
        assert resp.status_code == 200
        assert "items" in resp.json()["data"]

    def test_search_with_keyword(self, client: TestClient):
        """GET /api/enterprise/search?q=关键词"""
        resp = client.get("/api/enterprise/search?q=科技")
        assert resp.status_code == 200

    def test_search_with_pagination(self, client: TestClient):
        """GET /api/enterprise/search?page=1&page_size=5"""
        resp = client.get("/api/enterprise/search?page=1&page_size=5")
        assert resp.status_code == 200

    def test_search_with_filters(self, client: TestClient):
        """GET /api/enterprise/search?industry=互联网&region=北京"""
        resp = client.get("/api/enterprise/search?industry=互联网&region=北京")
        assert resp.status_code == 200


class TestEnterpriseCRUD:
    """企业 CRUD 测试"""

    def test_create_enterprise_as_admin(self, client: TestClient, admin_headers: dict):
        """POST /api/enterprise — 管理员创建"""
        resp = client.post(
            "/api/enterprise",
            json={"name": "测试企业科技", "industry": "互联网", "region": "北京"},
            headers=admin_headers,
        )
        # 路由器返回200 HTTP状态码（即使内容中有code=201）
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] in (200, 201)
        assert data["data"]["name"] == "测试企业科技"
        return data["data"]["id"]

    def test_create_enterprise_no_admin(self, client: TestClient, buyer_headers: dict):
        """POST /api/enterprise — 非管理员被拒"""
        resp = client.post("/api/enterprise", json={"name": "普通用户创建", "industry": "科技"}, headers=buyer_headers)
        assert resp.status_code == 403

    def test_create_duplicate_name(self, client: TestClient, admin_headers: dict):
        """POST /api/enterprise — 重复名称"""
        client.post("/api/enterprise", json={"name": "唯一企业名称"}, headers=admin_headers)
        resp = client.post("/api/enterprise", json={"name": "唯一企业名称"}, headers=admin_headers)
        assert resp.status_code == 409

    def test_get_enterprise(self, client: TestClient, admin_headers: dict):
        """GET /api/enterprise/{id} — 企业详情"""
        create_resp = client.post(
            "/api/enterprise", json={"name": "详情测试企业", "industry": "金融"}, headers=admin_headers
        )
        ent_id = create_resp.json()["data"]["id"]
        resp = client.get(f"/api/enterprise/{ent_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "详情测试企业"

    def test_get_enterprise_not_found(self, client: TestClient):
        """GET /api/enterprise/{id} — 不存在"""
        resp = client.get("/api/enterprise/99999")
        assert resp.status_code == 404

    def test_update_enterprise(self, client: TestClient, admin_headers: dict):
        """PUT /api/enterprise/{id} — 管理员更新"""
        create_resp = client.post(
            "/api/enterprise", json={"name": "更新前名称", "industry": "教育"}, headers=admin_headers
        )
        ent_id = create_resp.json()["data"]["id"]
        resp = client.put(f"/api/enterprise/{ent_id}", json={"name": "更新后名称"}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "更新后名称"

    def test_update_not_admin(self, client: TestClient, buyer_headers: dict, admin_headers: dict):
        """PUT /api/enterprise/{id} — 非管理员"""
        create_resp = client.post("/api/enterprise", json={"name": "权限测试企业"}, headers=admin_headers)
        ent_id = create_resp.json()["data"]["id"]
        resp = client.put(f"/api/enterprise/{ent_id}", json={"name": "尝试修改"}, headers=buyer_headers)
        assert resp.status_code == 403

    def test_delete_enterprise(self, client: TestClient, admin_headers: dict):
        """DELETE /api/enterprise/{id} — 管理员删除"""
        create_resp = client.post("/api/enterprise", json={"name": "待删除企业"}, headers=admin_headers)
        ent_id = create_resp.json()["data"]["id"]
        resp = client.delete(f"/api/enterprise/{ent_id}", headers=admin_headers)
        assert resp.status_code == 200

    def test_delete_not_found(self, client: TestClient, admin_headers: dict):
        """DELETE /api/enterprise/{id} — 不存在"""
        resp = client.delete("/api/enterprise/99999", headers=admin_headers)
        assert resp.status_code == 404


class TestEnterpriseRelations:
    """企业关系图谱测试"""

    def test_add_relation(self, client: TestClient, admin_headers: dict):
        """POST /api/enterprise/{id}/relation — 添加关系"""
        # 创建两个企业
        resp1 = client.post("/api/enterprise", json={"name": "源企业A"}, headers=admin_headers)
        resp2 = client.post("/api/enterprise", json={"name": "目标企业B"}, headers=admin_headers)
        src_id = resp1.json()["data"]["id"]
        tgt_id = resp2.json()["data"]["id"]
        resp = client.post(
            f"/api/enterprise/{src_id}/relation",
            json={"target_id": tgt_id, "relation_type": "investment", "relation_label": "投资"},
            headers=admin_headers,
        )
        assert resp.status_code == 201

    def test_get_relations(self, client: TestClient, admin_headers: dict):
        """GET /api/enterprise/{id}/relations — 获取关系图谱"""
        resp1 = client.post("/api/enterprise", json={"name": "关系源企业"}, headers=admin_headers)
        ent_id = resp1.json()["data"]["id"]
        resp = client.get(f"/api/enterprise/{ent_id}/relations")
        assert resp.status_code == 200
        assert "outgoing" in resp.json()["data"]
        assert "incoming" in resp.json()["data"]

    def test_delete_relation(self, client: TestClient, admin_headers: dict):
        """DELETE /api/enterprise/{id}/relation/{relation_id}"""
        resp1 = client.post("/api/enterprise", json={"name": "关系删除源"}, headers=admin_headers)
        resp2 = client.post("/api/enterprise", json={"name": "关系删除目标"}, headers=admin_headers)
        src_id = resp1.json()["data"]["id"]
        tgt_id = resp2.json()["data"]["id"]
        rel_resp = client.post(
            f"/api/enterprise/{src_id}/relation",
            json={"target_id": tgt_id, "relation_type": "cooperation"},
            headers=admin_headers,
        )
        rel_id = rel_resp.json()["data"]["id"]
        resp = client.delete(f"/api/enterprise/{src_id}/relation/{rel_id}", headers=admin_headers)
        assert resp.status_code == 200


class TestEnterpriseEnrich:
    """企业信息补全测试"""

    def test_enrich(self, client: TestClient, buyer_headers: dict):
        """POST /api/enterprise/enrich — 补全企业信息"""
        resp = client.post("/api/enterprise/enrich", json={"name": "字节跳动"}, headers=buyer_headers)
        # 可能因为爬虫不可用返回404
        assert resp.status_code in (200, 201, 404)

    def test_enrich_empty_name(self, client: TestClient, buyer_headers: dict):
        """POST /api/enterprise/enrich — 空名称"""
        resp = client.post("/api/enterprise/enrich", json={"name": ""}, headers=buyer_headers)
        assert resp.status_code == 422
