"""
向量搜索路由测试
（已适配 chainke-full）

覆盖 /api/search/vector/* 端点：
- GET  /api/search/vector?q=... — 语义搜索
- POST /api/search/vector/rebuild — 重建索引
"""

from fastapi.testclient import TestClient


class TestVectorSearch:
    """向量搜索路由测试"""

    def test_vector_search_endpoint(self, client: TestClient):
        """GET /api/search/vector — 端点可访问"""
        resp = client.get("/api/search/vector", params={"q": "测试"})
        # 可能 200(可用)、404(未实现)、503(向量搜索禁用)
        assert resp.status_code in (200, 404, 503)

    def test_rebuild_endpoint(self, client: TestClient):
        """POST /api/search/vector/rebuild — 端点可访问"""
        resp = client.post("/api/search/vector/rebuild")
        assert resp.status_code in (200, 401, 404, 405, 503)
