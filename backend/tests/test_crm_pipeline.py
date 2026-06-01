"""CRM管道工作流测试

覆盖 /api/crm/* 下所有端点：
- GET  /api/crm/pipeline       — 管道概览
- GET  /api/crm/leads           — 线索列表
- POST /api/crm/leads           — 新建线索
- GET  /api/crm/leads/{id}      — 线索详情
- PUT  /api/crm/leads/{id}/stage — 更新阶段
- POST /api/crm/leads/{id}/note  — 添加跟进记录
- GET  /api/crm/leads/stale      — 待跟进线索
- GET  /api/crm/leads/my         — 我的线索

使用独立的 CRM_SQLite 数据库，通过 CRM_PIPELINE_DATA_DIR 环境变量隔离。
"""

import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _crm_isolated_db(monkeypatch):
    """每个测试使用独立的临时目录存放 crm.db，避免交叉污染"""
    tmpdir = tempfile.mkdtemp()
    monkeypatch.setenv("CRM_PIPELINE_DATA_DIR", tmpdir)
    yield
    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)


class TestCrmPipeline:
    """CRM 管道概览"""

    def test_get_pipeline_success(self, client: TestClient, buyer_headers):
        """GET /api/crm/pipeline 返回管道概览（含 stages、total、total_value）"""
        resp = client.get("/api/crm/pipeline", headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "stages" in data["data"]
        # 实际响应使用 total 而非 total_count
        assert "total" in data["data"]
        assert len(data["data"]["stages"]) > 0

    def test_get_pipeline_unauthenticated(self, client: TestClient):
        """未认证无法访问管道概览"""
        resp = client.get("/api/crm/pipeline")
        assert resp.status_code == 401


class TestCrmLeads:
    """线索列表"""

    def test_list_leads_success(self, client: TestClient, buyer_headers):
        """GET /api/crm/leads 返回线索列表"""
        resp = client.get("/api/crm/leads", headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "items" in data["data"]

    def test_list_leads_unauthenticated(self, client: TestClient):
        """未认证无法查看线索列表"""
        resp = client.get("/api/crm/leads")
        assert resp.status_code == 401


class TestCrmCreateLead:
    """新建线索"""

    def test_create_lead_success(self, client: TestClient, buyer_headers):
        """POST /api/crm/leads 成功创建新线索"""
        resp = client.post(
            "/api/crm/leads",
            headers=buyer_headers,
            params={
                "name": "测试客户",
                "company": "测试公司",
                "phone": "13800138000",
                "source": "manual",
                "value": 50000.0,
                "notes": "初始备注",
            },
        )
        assert resp.status_code == 201, f"创建失败: {resp.text}"
        data = resp.json()
        assert data["code"] == 201
        assert data["data"]["name"] == "测试客户"
        assert "id" in data["data"]

    def test_create_lead_minimal(self, client: TestClient, buyer_headers):
        """仅传必填参数 name 即可创建线索"""
        resp = client.post(
            "/api/crm/leads",
            headers=buyer_headers,
            params={"name": "最小客户"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["data"]["name"] == "最小客户"

    def test_create_lead_empty_name(self, client: TestClient, buyer_headers):
        """name 为空时返回 422"""
        resp = client.post(
            "/api/crm/leads",
            headers=buyer_headers,
            params={"name": ""},
        )
        assert resp.status_code == 422

    def test_create_lead_unauthenticated(self, client: TestClient):
        """未认证无法创建线索"""
        resp = client.post(
            "/api/crm/leads",
            params={"name": "黑客客户"},
        )
        assert resp.status_code == 401


class TestCrmLeadDetail:
    """线索详情"""

    def _create_test_lead(self, client, headers, name="测试客户"):
        resp = client.post(
            "/api/crm/leads",
            headers=headers,
            params={"name": name, "company": "测试公司", "phone": "13800138000"},
        )
        assert resp.status_code == 201
        return resp.json()["data"]["id"]

    def test_get_lead_detail(self, client: TestClient, buyer_headers):
        """GET /api/crm/leads/{id} 返回线索详情"""
        lead_id = self._create_test_lead(client, buyer_headers)
        resp = client.get(f"/api/crm/leads/{lead_id}", headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["id"] == lead_id
        assert data["data"]["name"] == "测试客户"

    def test_get_lead_not_found(self, client: TestClient, buyer_headers):
        """不存在的线索返回 404"""
        resp = client.get("/api/crm/leads/99999", headers=buyer_headers)
        assert resp.status_code == 404


class TestCrmStageUpdate:
    """更新线索阶段"""

    def _create_test_lead(self, client, headers):
        resp = client.post(
            "/api/crm/leads",
            headers=headers,
            params={"name": "阶段测试客户"},
        )
        return resp.json()["data"]["id"]

    def test_update_stage_forward(self, client: TestClient, buyer_headers):
        """推进阶段到 'contacted' 成功"""
        lead_id = self._create_test_lead(client, buyer_headers)
        resp = client.put(
            f"/api/crm/leads/{lead_id}/stage",
            headers=buyer_headers,
            params={"stage": "contacted"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200

    def test_update_stage_invalid_stage(self, client: TestClient, buyer_headers):
        """无效阶段名返回 400"""
        lead_id = self._create_test_lead(client, buyer_headers)
        resp = client.put(
            f"/api/crm/leads/{lead_id}/stage",
            headers=buyer_headers,
            params={"stage": "invalid_stage"},
        )
        assert resp.status_code == 400

    def test_update_stage_not_found(self, client: TestClient, buyer_headers):
        """不存在的线索更新阶段返回 404"""
        resp = client.put(
            "/api/crm/leads/99999/stage",
            headers=buyer_headers,
            params={"stage": "contacted"},
        )
        assert resp.status_code == 404


class TestCrmAddNote:
    """添加跟进记录"""

    def _create_test_lead(self, client, headers):
        resp = client.post(
            "/api/crm/leads",
            headers=headers,
            params={"name": "备注测试客户"},
        )
        return resp.json()["data"]["id"]

    def test_add_note_success(self, client: TestClient, buyer_headers):
        """POST /api/crm/leads/{id}/note 成功添加跟进记录"""
        lead_id = self._create_test_lead(client, buyer_headers)
        resp = client.post(
            f"/api/crm/leads/{lead_id}/note",
            headers=buyer_headers,
            params={"content": "第一次跟进：电话沟通"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == 201

    def test_add_note_empty_content(self, client: TestClient, buyer_headers):
        """content 为空时返回 422"""
        lead_id = self._create_test_lead(client, buyer_headers)
        resp = client.post(
            f"/api/crm/leads/{lead_id}/note",
            headers=buyer_headers,
            params={"content": ""},
        )
        assert resp.status_code == 422

    def test_add_note_lead_not_found(self, client: TestClient, buyer_headers):
        """不存在的线索添加备注返回 404"""
        resp = client.post(
            "/api/crm/leads/99999/note",
            headers=buyer_headers,
            params={"content": "测试备注"},
        )
        assert resp.status_code == 404


class TestCrmStaleLeads:
    """待跟进线索"""

    def _create_test_lead(self, client, headers):
        resp = client.post(
            "/api/crm/leads",
            headers=headers,
            params={"name": "待跟进客户"},
        )
        return resp.json()["data"]["id"]

    def test_stale_leads_success(self, client: TestClient, buyer_headers):
        """GET /api/crm/leads/stale 返回待跟进线索列表"""
        self._create_test_lead(client, buyer_headers)
        resp = client.get(
            "/api/crm/leads/stale",
            headers=buyer_headers,
            params={"days": 30},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "items" in data["data"]

    def test_stale_leads_unauthenticated(self, client: TestClient):
        """未认证无法访问待跟进线索"""
        resp = client.get("/api/crm/leads/stale")
        assert resp.status_code == 401


class TestCrmMyLeads:
    """我的线索"""

    def _create_test_lead(self, client, headers):
        resp = client.post(
            "/api/crm/leads",
            headers=headers,
            params={"name": "我的客户"},
        )
        return resp.json()["data"]["id"]

    def test_my_leads_success(self, client: TestClient, buyer_headers):
        """GET /api/crm/leads/my 返回当前用户分配的线索"""
        self._create_test_lead(client, buyer_headers)
        resp = client.get("/api/crm/leads/my", headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "items" in data["data"]

    def test_my_leads_filter_by_stage(self, client: TestClient, buyer_headers):
        """支持按 stage 筛选我的线索"""
        self._create_test_lead(client, buyer_headers)
        resp = client.get(
            "/api/crm/leads/my",
            headers=buyer_headers,
            params={"stage": "new_lead"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200

    def test_my_leads_unauthenticated(self, client: TestClient):
        """未认证无法访问我的线索"""
        resp = client.get("/api/crm/leads/my")
        assert resp.status_code == 401
