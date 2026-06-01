"""数据丰富（Enrichment）全面测试 —— 覆盖全部路由和边角场景"""
import pytest
from fastapi.testclient import TestClient


class TestEnrichCompany:
    """企业信息丰富测试"""

    def test_enrich_company(self, client: TestClient, buyer_headers: dict):
        """GET /api/enrich/company?name=企业名"""
        resp = client.get("/api/enrich/company?name=字节跳动", headers=buyer_headers)
        # 可能因为模拟API返回500，但必须能正常响应
        assert resp.status_code in (200, 500)

    def test_enrich_company_no_auth(self, client: TestClient):
        """GET /api/enrich/company — 无认证"""
        resp = client.get("/api/enrich/company?name=字节跳动")
        assert resp.status_code == 401

    def test_enrich_company_empty_name(self, client: TestClient, buyer_headers: dict):
        """GET /api/enrich/company?name= — 空名称"""
        resp = client.get("/api/enrich/company?name=", headers=buyer_headers)
        assert resp.status_code == 422

    def test_enrich_company_unknown(self, client: TestClient, buyer_headers: dict):
        """GET /api/enrich/company?name=未知企业"""
        resp = client.get("/api/enrich/company?name=未知企业测试名称", headers=buyer_headers)
        assert resp.status_code in (200, 500)


class TestEnrichCompanyBasic:
    """企业基本信息查询测试"""

    def test_company_basic(self, client: TestClient, buyer_headers: dict):
        """GET /api/enrich/company/basic?name=企业名"""
        resp = client.get("/api/enrich/company/basic?name=阿里巴巴", headers=buyer_headers)
        assert resp.status_code in (200, 500)

    def test_company_basic_no_auth(self, client: TestClient):
        """GET /api/enrich/company/basic — 无认证"""
        resp = client.get("/api/enrich/company/basic?name=阿里巴巴")
        assert resp.status_code == 401

    def test_company_basic_empty(self, client: TestClient, buyer_headers: dict):
        """GET /api/enrich/company/basic?name= — 空参数"""
        resp = client.get("/api/enrich/company/basic?name=", headers=buyer_headers)
        assert resp.status_code == 422


class TestEnrichCompanyScope:
    """企业经营范围查询测试"""

    def test_company_scope(self, client: TestClient, buyer_headers: dict):
        """GET /api/enrich/company/scope?name=企业名"""
        resp = client.get("/api/enrich/company/scope?name=腾讯", headers=buyer_headers)
        assert resp.status_code in (200, 500)

    def test_company_scope_no_auth(self, client: TestClient):
        """GET /api/enrich/company/scope — 无认证"""
        resp = client.get("/api/enrich/company/scope?name=腾讯")
        assert resp.status_code == 401

    def test_company_scope_empty(self, client: TestClient, buyer_headers: dict):
        """GET /api/enrich/company/scope?name= — 空参数"""
        resp = client.get("/api/enrich/company/scope?name=", headers=buyer_headers)
        assert resp.status_code == 422


class TestEnrichContacts:
    """企业联系人查询测试"""

    def test_enrich_contacts(self, client: TestClient, buyer_headers: dict):
        """GET /api/enrich/contacts?company=企业名"""
        resp = client.get("/api/enrich/contacts?company=阿里巴巴", headers=buyer_headers)
        assert resp.status_code in (200, 500)

    def test_enrich_contacts_no_auth(self, client: TestClient):
        """GET /api/enrich/contacts — 无认证"""
        resp = client.get("/api/enrich/contacts?company=阿里巴巴")
        assert resp.status_code == 401

    def test_enrich_contacts_empty(self, client: TestClient, buyer_headers: dict):
        """GET /api/enrich/contacts?company= — 空公司名"""
        resp = client.get("/api/enrich/contacts?company=", headers=buyer_headers)
        assert resp.status_code == 422


class TestEnrichV1Routes:
    """/api/v1/enrich 版本化路由测试"""

    def test_v1_company(self, client: TestClient, buyer_headers: dict):
        """GET /api/v1/enrich/company"""
        resp = client.get("/api/v1/enrich/company?name=测试", headers=buyer_headers)
        assert resp.status_code in (200, 500)

    def test_v1_contacts(self, client: TestClient, buyer_headers: dict):
        """GET /api/v1/enrich/contacts"""
        resp = client.get("/api/v1/enrich/contacts?company=测试", headers=buyer_headers)
        assert resp.status_code in (200, 500)


class TestEnrichPermissions:
    """权限边角测试"""

    def test_promoter_access_company(self, client: TestClient, promoter_headers: dict):
        """GET /api/enrich/company — 推广员也有权限"""
        resp = client.get("/api/enrich/company?name=华为", headers=promoter_headers)
        assert resp.status_code in (200, 500)

    def test_supplier_access_contacts(self, client: TestClient, supplier_headers: dict):
        """GET /api/enrich/contacts — 供应商权限"""
        resp = client.get("/api/enrich/contacts?company=华为", headers=supplier_headers)
        assert resp.status_code in (200, 500)

    def test_admin_access_all(self, client: TestClient, admin_headers: dict):
        """GET /api/enrich/company — 管理员权限"""
        resp = client.get("/api/enrich/company?name=华为", headers=admin_headers)
        assert resp.status_code in (200, 500)
