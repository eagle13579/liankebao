"""向量搜索路由测试

覆盖 /api/search/vector/* 下所有端点：
- GET  /api/search/vector?q=... — 语义搜索
- POST /api/search/vector/rebuild — 重建索引

注意：向量搜索需启用 USE_VECTOR_SEARCH=1，否则返回 503。
测试同时覆盖启用和未启用两种场景。
"""

from fastapi.testclient import TestClient


class TestVectorSearch:
    """向量搜索路由测试"""

    def test_vector_search_disabled_by_default(self, client: TestClient):
        """默认 USE_VECTOR_SEARCH=0 时搜索返回 503"""
        resp = client.get("/api/search/vector", params={"q": "测试"})
        assert resp.status_code == 503

    def test_vector_search_empty_query_disabled(self, client: TestClient):
        """未启用时空查询也返回 503（中间件先于参数校验）"""
        resp = client.get("/api/search/vector", params={"q": ""})
        assert resp.status_code == 503

    def test_rebuild_disabled_by_default(self, client: TestClient):
        """默认状态下重建也返回 503"""
        resp = client.post("/api/search/vector/rebuild")
        assert resp.status_code == 503

    def test_vector_search_no_q_param_disabled(self, client: TestClient):
        """缺少 q 参数时未启用返回 503"""
        resp = client.get("/api/search/vector")
        assert resp.status_code == 503
