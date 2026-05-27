"""
搜索引擎测试 — 增强版(带parametrize)
=====================================
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

import pytest
from fastapi.testclient import TestClient

# ============================================================
# MemorySearchEngine 单元测试 — 含parametrize
# ============================================================


class TestMemorySearchEngineUnit:
    """MemorySearchEngine 单元测试"""

    # ---- 分词参数化测试 ----
    @pytest.mark.parametrize(
        "text,expected_tokens",
        [
            ("测试产品", ["测试", "产品", "测试产品"]),
            ("中文搜索", ["中文", "搜索", "中文搜索"]),
            ("hello world", ["hello", "world"]),
            ("ABC-123", ["abc", "123"]),
            ("", []),
            ("a", []),  # 单字符不加入
        ],
    )
    def test_tokenize_param(self, text, expected_tokens):
        """参数化：多种文本分词结果"""
        from app.search_index import simple_tokenize

        tokens = simple_tokenize(text)
        for t in expected_tokens:
            assert t in tokens, f"'{t}' 应在分词结果 {tokens} 中"

    @pytest.mark.parametrize("query", ["测试", "产品", "描述", "搜索"])
    def test_memory_engine_add_and_search_param(self, query):
        """参数化：多个查询词的搜索"""
        from app.search_index import MemorySearchEngine

        engine = MemorySearchEngine()
        engine.add_document(
            doc_id=1,
            title="测试产品 A",
            content="这是一个很好的测试产品描述",
            category="电子产品",
            price=100.00,
            tags="测试,电子",
            brand="测试品牌",
        )
        result = engine.search(query=query, page=1, page_size=10)
        assert result["total"] >= 0
        if result["total"] > 0:
            assert result["items"][0]["score"] > 0

    @pytest.mark.parametrize(
        "page,page_size,expected_len",
        [
            (1, 5, 5),
            (2, 5, 5),
            (3, 5, 5),
            (4, 5, 5),
            (1, 10, 10),
            (1, 20, 20),
            (3, 7, 6),  # 最后一页6条
        ],
    )
    def test_memory_engine_pagination_param(self, page, page_size, expected_len):
        """参数化：分页边界测试"""
        from app.search_index import MemorySearchEngine

        engine = MemorySearchEngine()
        for i in range(1, 21):
            engine.add_document(doc_id=i, title=f"产品{i}号", content="测试产品描述")
        result = engine.search(query="产品", page=page, page_size=page_size)
        assert result["total"] == 20
        assert len(result["items"]) == expected_len
        assert result["page"] == page
        assert result["page_size"] == page_size

    @pytest.mark.parametrize(
        "sort_by,check_fn",
        [
            (
                "relevance",
                lambda items: all(items[i]["score"] >= items[i + 1]["score"] for i in range(len(items) - 1))
                if len(items) >= 2
                else True,
            ),
            (
                "price_asc",
                lambda items: all(items[i]["price"] <= items[i + 1]["price"] for i in range(len(items) - 1))
                if len(items) >= 2
                else True,
            ),
            (
                "price_desc",
                lambda items: all(items[i]["price"] >= items[i + 1]["price"] for i in range(len(items) - 1))
                if len(items) >= 2
                else True,
            ),
        ],
    )
    def test_memory_engine_sort_param(self, sort_by, check_fn):
        """参数化：多种排序方式验证"""
        from app.search_index import MemorySearchEngine

        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="便宜产品", price=10.00)
        engine.add_document(doc_id=2, title="贵产品", price=100.00)
        engine.add_document(doc_id=3, title="中等产品", price=50.00)
        result = engine.search(query="产品", sort_by=sort_by)
        assert check_fn(result["items"])

    # ---- 原始单测保留 ----
    def test_tokenize_simple(self):
        from app.search_index import simple_tokenize

        tokens = simple_tokenize("测试产品")
        assert isinstance(tokens, list)
        assert len(tokens) > 0
        assert "测试" in tokens
        assert "产品" in tokens

    def test_jieba_tokenize_available(self):
        from app.search_index import JIEBA_AVAILABLE

        assert isinstance(JIEBA_AVAILABLE, bool)

    def test_memory_engine_add_and_search(self):
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
        from app.search_index import MemorySearchEngine

        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="产品A")
        result = engine.search(query="不存在的关键词")
        assert result["total"] == 0
        assert result["items"] == []

    def test_memory_engine_empty_query(self):
        from app.search_index import MemorySearchEngine

        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="产品A")
        result = engine.search(query="")
        assert result["total"] == 0

    def test_memory_engine_pagination(self):
        from app.search_index import MemorySearchEngine

        engine = MemorySearchEngine()
        for i in range(1, 21):
            engine.add_document(doc_id=i, title=f"产品{i}号", content="测试产品描述")
        result = engine.search(query="产品", page=1, page_size=5)
        assert result["total"] == 20
        assert len(result["items"]) == 5
        assert result["page"] == 1
        assert result["page_size"] == 5
        result2 = engine.search(query="产品", page=2, page_size=5)
        assert len(result2["items"]) == 5
        result3 = engine.search(query="产品", page=10, page_size=5)
        assert len(result3["items"]) == 0

    def test_memory_engine_sort_relevance(self):
        from app.search_index import MemorySearchEngine

        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="测试产品", content="描述文本")
        engine.add_document(doc_id=2, title="其他商品", content="这里提到了测试产品")
        result = engine.search(query="测试", sort_by="relevance")
        assert len(result["items"]) >= 1
        if len(result["items"]) >= 2:
            assert result["items"][0]["score"] >= result["items"][1]["score"]

    def test_memory_engine_sort_price(self):
        from app.search_index import MemorySearchEngine

        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="便宜产品", price=10.00)
        engine.add_document(doc_id=2, title="贵产品", price=100.00)
        engine.add_document(doc_id=3, title="中等产品", price=50.00)
        asc_result = engine.search(query="产品", sort_by="price_asc")
        prices = [item["price"] for item in asc_result["items"]]
        assert prices == sorted(prices)
        desc_result = engine.search(query="产品", sort_by="price_desc")
        prices_desc = [item["price"] for item in desc_result["items"]]
        assert prices_desc == sorted(prices_desc, reverse=True)

    def test_memory_engine_filters(self):
        from app.search_index import MemorySearchEngine

        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="手机", category="电子产品", price=5000)
        engine.add_document(doc_id=2, title="苹果", category="食品", price=10)
        engine.add_document(doc_id=3, title="电脑", category="电子产品", price=8000)
        result = engine.search(query="电子产品", filters={"category": "电子产品"})
        assert result["total"] >= 1
        for item in result["items"]:
            assert item["category"] == "电子产品"
        result2 = engine.search(query="手机", filters={"min_price": 100, "max_price": 6000})
        assert result2["total"] == 1
        assert result2["items"][0]["id"] == 1

    def test_memory_engine_highlight(self):
        from app.search_index import highlight_text, highlight_title

        hl = highlight_text("这是一个测试产品的描述文本", "测试产品")
        assert "<em>" in hl
        assert "</em>" in hl
        assert "测试" in hl
        hl_title = highlight_title("测试产品名称", "测试")
        assert "<em>" in hl_title

    def test_memory_engine_suggest(self):
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
        from app.search_index import MemorySearchEngine

        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="测试产品")
        stats = engine.stats
        assert stats["engine"] == "memory"
        assert stats["documents"] == 1
        assert "unique_tokens" in stats

    def test_score_computation(self):
        from app.search_index import MemorySearchEngine

        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="测试产品", content="描述")
        engine.add_document(doc_id=2, title="其他", content="测试产品描述")
        result = engine.search(query="测试产品")
        assert result["items"][0]["id"] == 1
        assert result["items"][0]["score"] > result["items"][1]["score"]

    # ---- FTS5 引擎测试（内存模式跳过） ----
    def test_fts5_engine_init(self):
        """FTS5引擎初始化不报错"""
        from app.search_index import FTS5SearchEngine

        engine = FTS5SearchEngine()
        assert engine is not None
        assert engine.FTS_TABLE_NAME == "product_fts"

    def test_fts5_search_empty(self):
        """FTS5空搜索返回空结果"""
        from app.search_index import FTS5SearchEngine

        engine = FTS5SearchEngine()
        result = engine.search(query="")
        assert result["total"] == 0
        assert result["items"] == []

    @pytest.mark.parametrize(
        "prefix,expected_min",
        [
            ("测", 1),
            ("测试", 2),
            ("ZZZZ", 0),
        ],
    )
    def test_suggest_param(self, prefix, expected_min):
        """参数化：多种前缀建议"""
        from app.search_index import MemorySearchEngine

        engine = MemorySearchEngine()
        engine.add_document(doc_id=1, title="测试手机")
        engine.add_document(doc_id=2, title="测试电脑")
        suggestions = engine.suggest(prefix=prefix)
        assert len(suggestions) >= expected_min


# ============================================================
# /api/search 路由集成测试 — 含parametrize
# ============================================================


class TestSearchRoute:
    """搜索路由集成测试"""

    SEARCH_URL = "/api/search"

    @pytest.fixture(autouse=True)
    def _rebuild_search(self, client: TestClient):
        """每个测试前重建搜索引擎"""
        client.get(f"{self.SEARCH_URL}/rebuild")
        yield

    @pytest.mark.parametrize(
        "params,desc",
        [
            ({"q": "测试产品"}, "按产品名称搜索"),
            ({"q": "测试产品A"}, "精确名称搜索"),
            ({"category": "电子产品"}, "分类筛选"),
            ({"q": "测试", "category": "电子产品"}, "关键词+分类"),
            ({"min_price": 50, "max_price": 150}, "价格区间"),
            ({"q": "测试", "sort_by": "price_asc"}, "价格升序"),
            ({"q": "测试", "sort_by": "price_desc"}, "价格降序"),
            ({"q": "测试", "sort_by": "newest"}, "最新排序"),
            ({"q": "测试", "page": 1, "page_size": 1}, "分页"),
            ({"q": "ZZZZNOTEXISTZZZZ"}, "无结果搜索"),
            ({"q": "测试产品", "highlight": True}, "高亮搜索"),
            ({"q": ""}, "空搜索词"),
            ({"sort_by": "invalid_sort"}, "无效排序降级"),
        ],
    )
    def test_search_param(self, client, params, desc):
        """参数化：多种搜索场景"""
        resp = client.get(self.SEARCH_URL, params=params)
        assert resp.status_code == 200, f"[{desc}] 应返回200: {resp.text}"
        data = resp.json()
        assert data["code"] == 200
        assert "items" in data["data"]
        assert "total" in data["data"]

    # ---- 原始单测保留 ----
    def test_search_by_name(self, client: TestClient):
        resp = client.get(self.SEARCH_URL, params={"q": "测试产品"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["total"] >= 1
        items = data["data"]["items"]
        names = [item["name"] for item in items]
        assert any("测试产品" in n for n in names)

    def test_search_by_category(self, client: TestClient):
        resp = client.get(self.SEARCH_URL, params={"category": "电子产品"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] >= 1
        for item in data["data"]["items"]:
            assert item["category"] == "电子产品"

    def test_search_with_price_range(self, client: TestClient):
        resp = client.get(
            self.SEARCH_URL,
            params={"min_price": 50, "max_price": 150},
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["data"]["items"]:
            assert 50 <= item["price"] <= 150

    def test_search_sort_by_price_asc(self, client: TestClient):
        resp = client.get(
            self.SEARCH_URL,
            params={"q": "测试", "sort_by": "price_asc"},
        )
        assert resp.status_code == 200
        prices = [item["price"] for item in resp.json()["data"]["items"]]
        assert prices == sorted(prices)

    def test_search_sort_by_price_desc(self, client: TestClient):
        resp = client.get(
            self.SEARCH_URL,
            params={"q": "测试", "sort_by": "price_desc"},
        )
        assert resp.status_code == 200
        prices = [item["price"] for item in resp.json()["data"]["items"]]
        assert prices == sorted(prices, reverse=True)

    def test_search_sort_by_newest(self, client: TestClient):
        resp = client.get(
            self.SEARCH_URL,
            params={"q": "测试", "sort_by": "newest"},
        )
        assert resp.status_code == 200
        assert "items" in resp.json()["data"]

    def test_search_pagination(self, client: TestClient):
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
        resp = client.get(
            self.SEARCH_URL,
            params={"q": "ZZZZNOTEXISTZZZZ"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    def test_search_with_highlight(self, client: TestClient):
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
        resp = client.get(self.SEARCH_URL, params={"q": ""})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 2

    def test_search_invalid_sort(self, client: TestClient):
        resp = client.get(
            self.SEARCH_URL,
            params={"q": "测试", "sort_by": "invalid_sort"},
        )
        assert resp.status_code == 200

    def test_search_region_filter(self, client: TestClient):
        resp = client.get(
            self.SEARCH_URL,
            params={"region": "标准版"},
        )
        assert resp.status_code == 200

    def test_search_chinese_fulltext(self, client: TestClient):
        resp = client.get(
            self.SEARCH_URL,
            params={"q": "上架产品"},
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        names = [item["name"] for item in items]
        assert any("测试产品 C" in n for n in names)


class TestSearchCategories:
    """分类列表测试"""

    def test_list_categories(self, client: TestClient):
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

    @pytest.mark.parametrize("query", ["测试", "产品", "测试产品"])
    def test_suggestions_found_param(self, client, query):
        """参数化：多种查询词的建议（匹配产品标题）"""
        client.get("/api/search/rebuild")
        resp = client.get(
            "/api/search/suggestions",
            params={"q": query, "limit": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert len(data["data"]["suggestions"]) >= 1, f"query={query!r} 应返回建议"

    def test_suggestions_found(self, client: TestClient):
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
        resp = client.get(
            "/api/search/suggestions",
            params={"q": ""},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["suggestions"] == []

    def test_suggestions_no_match(self, client: TestClient):
        resp = client.get(
            "/api/search/suggestions",
            params={"q": "ZZZZNOTEXISTZZZZ"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["suggestions"] == []


class TestSearchRebuild:
    """搜索引擎重建测试"""

    def test_rebuild_success(self, client: TestClient):
        resp = client.get("/api/search/rebuild")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["indexed_count"] >= 2

    def test_search_after_rebuild(self, client: TestClient):
        client.get("/api/search/rebuild")
        resp = client.get("/api/search", params={"q": "测试产品"})
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1


class TestSearchStats:
    """搜索引擎状态统计测试"""

    def test_stats(self, client: TestClient):
        resp = client.get("/api/search/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        stats = data["data"]
        assert "engine" in stats
        assert "documents" in stats
