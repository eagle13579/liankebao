"""
搜索引擎测试
=============
- MemorySearchEngine 单元测试（分词、倒排索引、评分、排序、分页、建议）
- FTS5 搜索引擎测试（需 SQLite 支持）
- /api/search 路由全功能测试
- 中文分词 + 高亮
- 排序（相关性/价格/时间）
- 分页
- 搜索建议
- 分类列表
- 搜索引擎重建 + 状态
"""
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


# ============================================================
# MemorySearchEngine 单元测试
# ============================================================

class TestMemorySearchEngineUnit:
    """MemorySearchEngine 单元测试"""

    def test_tokenize_simple(self):
        """简单分词测试"""
        from app.search_index import simple_tokenize
        tokens = simple_tokenize("测试产品")
        assert isinstance(tokens, list)
        assert len(tokens) > 0
        # 中文双字组合
        assert "测试" in tokens
        assert "产品" in tokens

    def test_jieba_tokenize_available(self):
        """jieba 分词可用性"""
        from app.search_index import JIEBA_AVAILABLE
        # jieba 可能未安装，但不报错
        assert isinstance(JIEBA_AVAILABLE, bool)

    def test_memory_engine_add_and_search(self):
        """添加文档并搜索"""
        from app.search_index import MemorySearchEngine
        engine = MemorySearchEngine()
        engine.add_document(
            doc_id=1,
            title="测试产品 A",
            content="这是一个很好的测试产品",
            category="电子产品",
            price=100.00,
            tags="测试,电子",
            brand="测试品牌",
        )
        result = engine.search(query="测试", page=1, page_size=10)
        assert result["total"] == 1
        assert result["items"][0]["id"] == 1
        assert result["items"][0]["score"] > 0

    def test_memory_engine_no_results(self):
        """无匹配结果"""
        from app.search_index import MemorySearchEngine
        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="产品A")
        result = engine.search(query="不存在的关键词")
        assert result["total"] == 0
        assert result["items"] == []

    def test_memory_engine_empty_query(self):
        """空查询返回空结果"""
        from app.search_index import MemorySearchEngine
        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="产品A")
        result = engine.search(query="")
        assert result["total"] == 0

    def test_memory_engine_pagination(self):
        """分页测试"""
        from app.search_index import MemorySearchEngine
        engine = MemorySearchEngine()
        for i in range(1, 21):
            engine.add_document(doc_id=i, title=f"产品{i}号", content="测试产品描述")
        # 第 1 页，每页 5 条
        result = engine.search(query="产品", page=1, page_size=5)
        assert result["total"] == 20
        assert len(result["items"]) == 5
        assert result["page"] == 1
        assert result["page_size"] == 5

        # 第 2 页
        result2 = engine.search(query="产品", page=2, page_size=5)
        assert len(result2["items"]) == 5

        # 超出范围
        result3 = engine.search(query="产品", page=10, page_size=5)
        assert len(result3["items"]) == 0

    def test_memory_engine_sort_relevance(self):
        """相关性排序"""
        from app.search_index import MemorySearchEngine
        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="精确匹配产品名称", content="描述")
        engine.add_document(doc_id=2, title="其他", content="描述中提到了产品")
        result = engine.search(query="产品", sort_by="relevance")
        assert len(result["items"]) == 2
        # 标题匹配的分数应高于内容匹配
        assert result["items"][0]["score"] >= result["items"][1]["score"]

    def test_memory_engine_sort_price(self):
        """价格排序"""
        from app.search_index import MemorySearchEngine
        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="便宜产品", price=10.00)
        engine.add_document(doc_id=2, title="贵产品", price=100.00)
        engine.add_document(doc_id=3, title="中等产品", price=50.00)

        # 价格升序
        asc_result = engine.search(query="产品", sort_by="price_asc")
        prices = [item["price"] for item in asc_result["items"]]
        assert prices == sorted(prices)

        # 价格降序
        desc_result = engine.search(query="产品", sort_by="price_desc")
        prices_desc = [item["price"] for item in desc_result["items"]]
        assert prices_desc == sorted(prices_desc, reverse=True)

    def test_memory_engine_filters(self):
        """过滤器测试"""
        from app.search_index import MemorySearchEngine
        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="手机", category="电子产品", price=5000)
        engine.add_document(doc_id=2, title="苹果", category="食品", price=10)
        engine.add_document(doc_id=3, title="电脑", category="电子产品", price=8000)

        # 按分类过滤
        result = engine.search(query="产品", filters={"category": "电子产品"})
        assert result["total"] == 2
        assert all(item["category"] == "电子产品" for item in result["items"])

        # 价格区间
        result2 = engine.search(query="产品", filters={"min_price": 100, "max_price": 6000})
        assert result2["total"] == 1
        assert result2["items"][0]["id"] == 1

    def test_memory_engine_highlight(self):
        """高亮功能"""
        from app.search_index import highlight_text, highlight_title
        hl = highlight_text("这是一个测试产品的描述文本", "测试产品")
        assert "<em>" in hl
        assert "</em>" in hl
        assert "测试" in hl

        hl_title = highlight_title("测试产品名称", "测试")
        assert "<em>" in hl_title

    def test_memory_engine_suggest(self):
        """搜索建议"""
        from app.search_index import MemorySearchEngine
        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="测试手机")
        engine.add_document(doc_id=2, title="测试电脑")
        engine.add_document(doc_id=3, title="其他产品")

        suggestions = engine.suggest(prefix="测试")
        assert len(suggestions) >= 2
        assert "测试手机" in suggestions
        assert "测试电脑" in suggestions

    def test_memory_engine_remove_and_clear(self):
        """删除和清空文档"""
        from app.search_index import MemorySearchEngine
        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="测试产品")
        assert engine.size == 1

        engine.remove_document(1)
        assert engine.size == 0

        engine.add_document(doc_id=2, title="产品B")
        engine.clear()
        assert engine.size == 0

    def test_memory_engine_stats(self):
        """统计信息"""
        from app.search_index import MemorySearchEngine
        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="测试产品")
        stats = engine.stats
        assert stats["engine"] == "memory"
        assert stats["documents"] == 1
        assert "unique_tokens" in stats

    def test_score_computation(self):
        """验证评分计算逻辑"""
        from app.search_index import MemorySearchEngine, SearchDocument
        engine = MemorySearchEngine()
        # 标题精确匹配应得分最高
        engine.add_document(doc_id=1, title="测试产品", content="描述")
        engine.add_document(doc_id=2, title="其他", content="测试产品描述")
        result = engine.search(query="测试产品")
        assert result["items"][0]["id"] == 1  # 标题精确匹配优先
        assert result["items"][0]["score"] > result["items"][1]["score"]


# ============================================================
# /api/search 路由集成测试
# ============================================================

class TestSearchRoute:
    """搜索路由集成测试"""

    SEARCH_URL = "/api/search"

    @pytest.fixture(autouse=True)
    def _rebuild_search(self, client: TestClient):
        """每个测试前重建搜索引擎"""
        client.get(f"{self.SEARCH_URL}/rebuild")
        yield

    def test_search_by_name(self, client: TestClient):
        """按产品名称搜索"""
        resp = client.get(self.SEARCH_URL, params={"q": "测试产品"})
        assert resp.status_code == 200, f"搜索应成功: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] >= 1
        items = data["data"]["items"]
        # 至少有一个匹配项
        names = [item["name"] for item in items]
        assert any("测试产品" in n for n in names)

    def test_search_by_category(self, client: TestClient):
        """按分类搜索"""
        resp = client.get(self.SEARCH_URL, params={"category": "电子产品"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] >= 1
        for item in data["data"]["items"]:
            assert item["category"] == "电子产品"

    def test_search_with_price_range(self, client: TestClient):
        """价格区间筛选"""
        resp = client.get(
            self.SEARCH_URL,
            params={"min_price": 50, "max_price": 150},
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["data"]["items"]:
            assert 50 <= item["price"] <= 150

    def test_search_sort_by_price_asc(self, client: TestClient):
        """价格升序排序"""
        resp = client.get(
            self.SEARCH_URL,
            params={"q": "测试", "sort_by": "price_asc"},
        )
        assert resp.status_code == 200
        prices = [item["price"] for item in resp.json()["data"]["items"]]
        assert prices == sorted(prices)

    def test_search_sort_by_price_desc(self, client: TestClient):
        """价格降序排序"""
        resp = client.get(
            self.SEARCH_URL,
            params={"q": "测试", "sort_by": "price_desc"},
        )
        assert resp.status_code == 200
        prices = [item["price"] for item in resp.json()["data"]["items"]]
        assert prices == sorted(prices, reverse=True)

    def test_search_sort_by_newest(self, client: TestClient):
        """最新排序"""
        resp = client.get(
            self.SEARCH_URL,
            params={"q": "测试", "sort_by": "newest"},
        )
        assert resp.status_code == 200
        # 至少返回结果不报错
        assert "items" in resp.json()["data"]

    def test_search_pagination(self, client: TestClient):
        """分页"""
        resp = client.get(
            self.SEARCH_URL,
            params={"q": "测试", "page": 1, "page_size": 1},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 1
        assert len(data["items"]) <= 1

    def test_search_no_results(self, client: TestClient):
        """无结果搜索"""
        resp = client.get(
            self.SEARCH_URL,
            params={"q": "ZZZZNOTEXISTZZZZ"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    def test_search_with_highlight(self, client: TestClient):
        """搜索结果高亮"""
        resp = client.get(
            self.SEARCH_URL,
            params={"q": "测试产品", "highlight": True},
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        if items:
            item = items[0]
            assert "highlight_title" in item
            assert "highlight_content" in item

    def test_search_empty_query(self, client: TestClient):
        """空搜索词返回所有已上架产品"""
        resp = client.get(self.SEARCH_URL, params={"q": ""})
        assert resp.status_code == 200
        data = resp.json()["data"]
        # 应该返回所有 approved 产品
        assert data["total"] >= 2  # seed 中有 2 个 approved 产品

    def test_search_invalid_sort(self, client: TestClient):
        """无效排序参数自动降级为 relevance"""
        resp = client.get(
            self.SEARCH_URL,
            params={"q": "测试", "sort_by": "invalid_sort"},
        )
        assert resp.status_code == 200  # 不报错，降级处理

    def test_search_region_filter(self, client: TestClient):
        """地区筛选（通过 specs 中的产地匹配）"""
        resp = client.get(
            self.SEARCH_URL,
            params={"region": "标准版"},  # seed 中 specs 包含 "标准版"
        )
        assert resp.status_code == 200
        # 只要不报错就行

    def test_search_chinese_fulltext(self, client: TestClient):
        """中文全文搜索"""
        resp = client.get(
            self.SEARCH_URL,
            params={"q": "上架产品"},
        )
        assert resp.status_code == 200
        # 应匹配 "测试产品 C"（描述中包含 "上架产品"）
        items = resp.json()["data"]["items"]
        names = [item["name"] for item in items]
        assert any("测试产品 C" in n for n in names)


class TestSearchCategories:
    """分类列表测试"""

    def test_list_categories(self, client: TestClient):
        """获取分类列表"""
        resp = client.get("/api/search/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        categories = data["data"]["categories"]
        assert len(categories) >= 2
        assert "电子产品" in categories
        assert "日用品" in categories


class TestSearchSuggestions:
    """搜索建议测试"""

    def test_suggestions_found(self, client: TestClient):
        """搜索建议返回结果"""
        # 先重建索引
        client.get("/api/search/rebuild")
        resp = client.get(
            "/api/search/suggestions",
            params={"q": "测试", "limit": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        suggestions = data["data"]["suggestions"]
        assert len(suggestions) >= 1

    def test_suggestions_empty_query(self, client: TestClient):
        """空查询返回空建议"""
        resp = client.get(
            "/api/search/suggestions",
            params={"q": ""},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["suggestions"] == []

    def test_suggestions_no_match(self, client: TestClient):
        """无匹配建议返回空列表"""
        resp = client.get(
            "/api/search/suggestions",
            params={"q": "ZZZZNOTEXISTZZZZ"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["suggestions"] == []


class TestSearchRebuild:
    """搜索引擎重建测试"""

    def test_rebuild_success(self, client: TestClient):
        """重建索引成功"""
        resp = client.get("/api/search/rebuild")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["indexed_count"] >= 2

    def test_search_after_rebuild(self, client: TestClient):
        """重建后搜索正常"""
        client.get("/api/search/rebuild")
        resp = client.get("/api/search", params={"q": "测试产品"})
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1


class TestSearchStats:
    """搜索引擎状态统计测试"""

    def test_stats(self, client: TestClient):
        """获取搜索引擎统计"""
        resp = client.get("/api/search/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        stats = data["data"]
        assert "engine" in stats
        assert "documents" in stats
