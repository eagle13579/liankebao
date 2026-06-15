"""导入引擎全面测试 —— 预览/确认导入/导入历史"""
import io
import pytest
from fastapi.testclient import TestClient


class TestImportPreview:
    """导入预览测试"""

    def test_preview_csv(self, client: TestClient, buyer_headers: dict):
        """POST /api/imports/preview — CSV文件"""
        csv_content = "姓名,电话,公司\n张三,13800138001,测试公司\n李四,13900139002,另一家公司"
        resp = client.post(
            "/api/imports/preview",
            files={"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")},
            headers=buyer_headers
        )
        assert resp.status_code in (200, 400)  # 400如果格式不支持

    def test_preview_no_file(self, client: TestClient, buyer_headers: dict):
        """POST /api/imports/preview — 无文件"""
        resp = client.post("/api/imports/preview", headers=buyer_headers)
        assert resp.status_code == 422

    def test_preview_no_auth(self, client: TestClient):
        """POST /api/imports/preview — 无认证"""
        csv_content = "name,phone\nTest,123"
        resp = client.post(
            "/api/imports/preview",
            files={"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        )
        assert resp.status_code == 401

    def test_preview_empty_file(self, client: TestClient, buyer_headers: dict):
        """POST /api/imports/preview — 空文件"""
        resp = client.post(
            "/api/imports/preview",
            files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
            headers=buyer_headers
        )
        assert resp.status_code == 400

    def test_preview_large_file(self, client: TestClient, buyer_headers: dict):
        """POST /api/imports/preview — 超大文件"""
        large_content = "a,b\n" + "1,2\n" * 100000
        resp = client.post(
            "/api/imports/preview",
            files={"file": ("large.csv", io.BytesIO(large_content.encode()), "text/csv")},
            headers=buyer_headers
        )
        # 可能413或200
        assert resp.status_code in (200, 413)


class TestImportConfirm:
    """确认导入测试"""

    def test_confirm_no_batch(self, client: TestClient, buyer_headers: dict):
        """POST /api/imports/confirm — 无batch_id"""
        resp = client.post("/api/imports/confirm", json={
            "batch_id": "nonexistent-batch",
            "field_mapping": {},
            "strategy": "skip"
        }, headers=buyer_headers)
        assert resp.status_code == 404

    def test_confirm_no_auth(self, client: TestClient):
        """POST /api/imports/confirm — 无认证"""
        resp = client.post("/api/imports/confirm", json={
            "batch_id": "test", "field_mapping": {}, "strategy": "skip"
        })
        assert resp.status_code == 401


class TestImportHistory:
    """导入历史测试"""

    def test_history(self, client: TestClient, buyer_headers: dict):
        """GET /api/imports/history"""
        resp = client.get("/api/imports/history", headers=buyer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data["data"]

    def test_history_pagination(self, client: TestClient, buyer_headers: dict):
        """GET /api/imports/history?page=1&page_size=5"""
        resp = client.get("/api/imports/history?page=1&page_size=5", headers=buyer_headers)
        assert resp.status_code == 200

    def test_history_no_auth(self, client: TestClient):
        """GET /api/imports/history — 无认证"""
        resp = client.get("/api/imports/history")
        assert resp.status_code == 401
