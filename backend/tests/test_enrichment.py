"""数据丰富 API 路由测试

覆盖 /api/enrich/* 下所有端点：
- GET /api/enrich/company        — 企业信息丰富
- GET /api/enrich/company/basic  — 企业基本信息
- GET /api/enrich/company/scope  — 企业经营范围
- GET /api/enrich/contacts       — 企业联系人
"""

from fastapi.testclient import TestClient


class TestEnrichCompany:
    """GET /api/enrich/company — 企业信息丰富"""

    def test_enrich_company_success(self, client: TestClient, buyer_headers):
        """已知企业返回完整信息"""
        resp = client.get(
            "/api/enrich/company",
            headers=buyer_headers,
            params={"name": "北京字节跳动科技有限公司"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["name"] == "北京字节跳动科技有限公司"
        assert "credit_code" in data["data"]
        assert "business_scope_detail" in data["data"]
        assert "contacts" in data["data"]

    def test_enrich_company_partial_match(self, client: TestClient, buyer_headers):
        """模糊匹配企业名也能返回结果"""
        resp = client.get(
            "/api/enrich/company",
            headers=buyer_headers,
            params={"name": "字节跳动"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200

    def test_enrich_company_unknown(self, client: TestClient, buyer_headers):
        """未知企业返回降级数据（不抛错）"""
        resp = client.get(
            "/api/enrich/company",
            headers=buyer_headers,
            params={"name": "一家不存在的公司xyz"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        # 应该返回模拟默认数据
        assert "name" in data["data"]

    def test_enrich_company_empty_name(self, client: TestClient, buyer_headers):
        """空企业名返回 422"""
        resp = client.get(
            "/api/enrich/company",
            headers=buyer_headers,
            params={"name": ""},
        )
        assert resp.status_code == 422

    def test_enrich_company_unauthenticated(self, client: TestClient):
        """未认证无法调用企业信息丰富"""
        resp = client.get(
            "/api/enrich/company",
            params={"name": "北京字节跳动科技有限公司"},
        )
        assert resp.status_code == 401


class TestEnrichCompanyBasic:
    """GET /api/enrich/company/basic — 企业基本信息"""

    def test_enrich_basic_success(self, client: TestClient, buyer_headers):
        """企业基本信息查询成功"""
        resp = client.get(
            "/api/enrich/company/basic",
            headers=buyer_headers,
            params={"name": "阿里巴巴（中国）有限公司"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "credit_code" in data["data"]

    def test_enrich_basic_unknown(self, client: TestClient, buyer_headers):
        """未知企业返回降级数据"""
        resp = client.get(
            "/api/enrich/company/basic",
            headers=buyer_headers,
            params={"name": "未知企业测试"},
        )
        assert resp.status_code == 200


class TestEnrichCompanyScope:
    """GET /api/enrich/company/scope — 企业经营范围"""

    def test_enrich_scope_success(self, client: TestClient, buyer_headers):
        """企业经营范围查询成功"""
        resp = client.get(
            "/api/enrich/company/scope",
            headers=buyer_headers,
            params={"name": "腾讯科技（深圳）有限公司"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "business_scope" in data["data"]

    def test_enrich_scope_empty(self, client: TestClient, buyer_headers):
        """空企业名返回 422"""
        resp = client.get(
            "/api/enrich/company/scope",
            headers=buyer_headers,
            params={"name": ""},
        )
        assert resp.status_code == 422


class TestEnrichContacts:
    """GET /api/enrich/contacts — 企业联系人"""

    def test_enrich_contacts_success(self, client: TestClient, buyer_headers):
        """企业联系人查询成功"""
        resp = client.get(
            "/api/enrich/contacts",
            headers=buyer_headers,
            params={"company": "北京字节跳动科技有限公司"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "contacts" in data["data"]
        assert len(data["data"]["contacts"]) > 0

    def test_enrich_contacts_unknown(self, client: TestClient, buyer_headers):
        """未知企业返回空联系人列表"""
        resp = client.get(
            "/api/enrich/contacts",
            headers=buyer_headers,
            params={"company": "未知企业测试"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["contacts"] == []

    def test_enrich_contacts_empty_company(self, client: TestClient, buyer_headers):
        """空公司名返回 422"""
        resp = client.get(
            "/api/enrich/contacts",
            headers=buyer_headers,
            params={"company": ""},
        )
        assert resp.status_code == 422

    def test_enrich_contacts_unauthenticated(self, client: TestClient):
        """未认证无法查看企业联系人"""
        resp = client.get(
            "/api/enrich/contacts",
            params={"company": "北京字节跳动科技有限公司"},
        )
        assert resp.status_code == 401
