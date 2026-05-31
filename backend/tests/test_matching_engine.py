"""
链客宝 匹配引擎单元测试
========================
覆盖 GAP 3 要求的全部测试用例:
  - test_category_exact_match
  - test_category_synonym_match
  - test_keyword_match
  - test_price_match
  - test_price_out_of_range
  - test_full_pipeline
  - A/B test 策略对比
"""

import os
import sys
import time

import pytest

# 将项目根目录加入 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 必须先设定环境变量
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("PAYMENT_MODE", "mock")

from matching_engine import (
    STOP_WORDS,
    MatchEngine,
    MatchResult,
    _cache,
    clear_cache,
    get_cached,
    match_metrics,
)

# ===== Mock 模型（无需数据库） =====


class MockProduct:
    """模拟 Product ORM 对象"""

    def __init__(
        self,
        id=1,
        name="测试产品",
        description="这是一个测试产品",
        price=100.0,
        sale_price=None,
        category="电子产品",
        tags="测试,电子",
        brand="测试品牌",
        status="approved",
    ):
        self.id = id
        self.name = name
        self.description = description
        self.price = price
        self.sale_price = sale_price
        self.category = category
        self.tags = tags
        self.brand = brand
        self.status = status


class MockNeed:
    """模拟 BusinessNeed ORM 对象"""

    def __init__(
        self,
        id=1,
        title="需要电子产品",
        description="我们需要一批电子产品",
        category="电子产品",
        budget="10万-50万",
        status="open",
    ):
        self.id = id
        self.title = title
        self.description = description
        self.category = category
        self.budget = budget
        self.status = status


class MockDb:
    """模拟数据库 Session（供 MatchEngine 实例化使用）"""

    def query(self, model):
        return MockQuery()


class MockQuery:
    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None

    def all(self):
        return []

    def count(self):
        return 0


# ===== Fixtures =====


@pytest.fixture
def engine_v1():
    """v1 规则引擎实例"""
    return MatchEngine(MockDb(), strategy="v1")


@pytest.fixture
def engine_v2():
    """v2 增强引擎实例"""
    return MatchEngine(MockDb(), strategy="v2")


@pytest.fixture(autouse=True)
def reset_metrics():
    """每个测试前重置监控指标"""
    match_metrics.request_count = 0
    match_metrics.total_response_time = 0.0
    match_metrics.score_buckets.clear()
    match_metrics.daily_requests = 0
    yield


@pytest.fixture(autouse=True)
def reset_cache():
    """每个测试前清除缓存"""
    clear_cache()
    yield


# ============================================================
# GAP 3: 单元测试 - 类目匹配
# ============================================================


class TestCategoryMatching:
    """类目匹配测试 — 覆盖 exact_match + synonym_match + partial_match + no_match"""

    def test_category_exact_match(self, engine_v1, engine_v2):
        """类目完全相同 → 40分"""
        for eng in [engine_v1, engine_v2]:
            product = MockProduct(category="大健康")
            need = MockNeed(category="大健康")
            score, reasons = eng._match_category(product.category, need.category)
            assert score == 40.0, f"[{eng.strategy}] 期望40分, 实际{score}"
            assert "类目完全匹配" in "".join(reasons), f"[{eng.strategy}] 缺少类目完全匹配原因"

    def test_category_synonym_match(self, engine_v1, engine_v2):
        """类目同义词匹配 → 30分"""
        for eng in [engine_v1, engine_v2]:
            product = MockProduct(category="养生")  # 属于"大健康"同义词
            need = MockNeed(category="大健康")
            score, reasons = eng._match_category(product.category, need.category)
            assert score == 30.0, f"[{eng.strategy}] 期望30分, 实际{score}"
            assert "类目匹配" in "".join(reasons), f"[{eng.strategy}] 缺少类目匹配原因"

    def test_category_partial_match(self, engine_v1, engine_v2):
        """类目部分匹配 → 10~30分"""
        for eng in [engine_v1, engine_v2]:
            product = MockProduct(category="电子产品")
            need = MockNeed(category="科技产品")
            score, reasons = eng._match_category(product.category, need.category)
            assert score > 0, f"[{eng.strategy}] 部分匹配应有分数"
            assert score <= 30.0, f"[{eng.strategy}] 部分匹配不应超过30分"

    def test_category_no_match(self, engine_v1, engine_v2):
        """类目不匹配 → 0分"""
        for eng in [engine_v1, engine_v2]:
            product = MockProduct(category="大健康")
            need = MockNeed(category="教育培训")
            score, reasons = eng._match_category(product.category, need.category)
            assert score == 0.0, f"[{eng.strategy}] 期望0分, 实际{score}"

    def test_category_empty(self, engine_v1, engine_v2):
        """类目为空 → 0分"""
        for eng in [engine_v1, engine_v2]:
            score, reasons = eng._match_category(None, "大健康")
            assert score == 0.0, f"[{eng.strategy}] 空类目应返回0分"
            score2, _ = eng._match_category("大健康", None)
            assert score2 == 0.0
            score3, _ = eng._match_category(None, None)
            assert score3 == 0.0


# ============================================================
# GAP 3: 单元测试 - 关键词匹配
# ============================================================


class TestKeywordMatching:
    """关键词匹配测试 — 检验 v1(set交集) 和 v2(TF-IDF)"""

    def test_keyword_match_v1(self, engine_v1):
        """v1: 关键词匹配应返回正分"""
        product = MockProduct(
            name="CRM客户管理系统",
            description="企业级SaaS软件",
            tags="CRM,企业服务",
            brand="云科技",
            category="企业服务",
        )
        need = MockNeed(
            title="寻找企业级CRM系统供应商",
            description="我们公司需要一套适合中小企业的CRM系统",
            category="企业服务",
        )
        score, reasons = engine_v1._match_keywords(product, need)
        assert score > 0, f"v1 应有正分, 实际{score}"
        assert len(reasons) > 0, "v1 应有匹配原因"

    def test_keyword_match_v2(self, engine_v2):
        """v2: TF-IDF 关键词匹配应返回正分"""
        product = MockProduct(
            name="CRM客户管理系统",
            description="企业级SaaS软件，帮助管理客户关系",
            tags="CRM,企业服务,SaaS",
            brand="云科技",
            category="企业服务",
        )
        need = MockNeed(
            title="寻找企业级CRM系统供应商",
            description="我们公司需要一套适合中小企业的CRM系统，预算10-30万",
            category="企业服务",
        )
        score, reasons = engine_v2._match_keywords(product, need)
        assert score > 0, f"v2 TF-IDF 应有正分, 实际{score}"
        assert len(reasons) > 0, "v2 应有匹配原因"

    def test_keyword_no_match(self, engine_v1, engine_v2):
        """完全不相关的内容 → 0分"""
        for eng in [engine_v1, engine_v2]:
            product = MockProduct(
                name="机械设备",
                description="工业机床配件",
                tags="机械",
                brand="重工",
                category="工业",
            )
            need = MockNeed(
                title="美妆护肤品采购",
                description="寻找化妆品代工",
                category="消费品",
            )
            score, reasons = eng._match_keywords(product, need)
            # v2 的 TF-IDF 可能会给出极低的非零分
            if eng.strategy == "v1":
                assert score == 0.0, f"v1 不相关应得0分, 实际{score}"
            else:
                # TF-IDF 可能有微弱相似度，但应 < 5分
                assert score < 5.0, f"v2 不相关得分应极低, 实际{score}"

    def test_extract_keywords_v1(self, engine_v1):
        """v1 关键词提取"""
        words = engine_v1._extract_keywords("我们需要一套CRM客户管理系统")
        assert isinstance(words, list)
        assert len(words) > 0
        # 停用词不应出现
        for w in words:
            assert w not in STOP_WORDS, f"停用词'{w}'不应出现在关键词中"

    def test_extract_keywords_v2(self, engine_v2):
        """v2 jieba 分词关键词提取"""
        words = engine_v2._extract_keywords("我们需要一套CRM客户管理系统")
        assert isinstance(words, list)
        assert len(words) > 0
        for w in words:
            assert w not in STOP_WORDS, f"停用词'{w}'不应出现在关键词中"
        # jieba 应能识别中文词汇
        assert "CRM" in words or "客户" in words or "管理" in words or "系统" in words


# ============================================================
# GAP 3: 单元测试 - 价格匹配
# ============================================================


class TestPriceMatching:
    """价格区间匹配测试"""

    def test_price_in_range(self, engine_v1, engine_v2):
        """价格在预算范围内 → 正分"""
        for eng in [engine_v1, engine_v2]:
            product = MockProduct(price=200000)  # 20万
            need = MockNeed(budget="10万-50万")
            score, reasons = eng._match_price_range(product, need)
            assert score > 0.0, f"[{eng.strategy}] 价格在预算内应有分数"
            assert "价格匹配" in "".join(reasons)

    def test_price_out_of_range(self, engine_v1, engine_v2):
        """价格超出预算 → 0分或极低"""
        for eng in [engine_v1, engine_v2]:
            product = MockProduct(price=1000000)  # 100万
            need = MockNeed(budget="10万-50万")
            score, reasons = eng._match_price_range(product, need)
            assert score <= 5.0, f"[{eng.strategy}] 价格超出预算得分应<=5.0, 实际{score}"

    def test_price_exact_budget(self, engine_v1, engine_v2):
        """价格恰好等于预算边界"""
        for eng in [engine_v1, engine_v2]:
            product = MockProduct(price=100000)  # 10万
            need = MockNeed(budget="10万-50万")
            score, reasons = eng._match_price_range(product, need)
            assert score > 0.0, f"[{eng.strategy}] 边界价格应有分数"

    def test_price_no_budget(self, engine_v1, engine_v2):
        """需求无预算信息 → 0分"""
        for eng in [engine_v1, engine_v2]:
            product = MockProduct(price=100)
            need = MockNeed(budget=None)
            score, reasons = eng._match_price_range(product, need)
            assert score == 0.0

    def test_price_below_range(self, engine_v1, engine_v2):
        """价格低于预算范围（差距不大时可有部分分）"""
        for eng in [engine_v1, engine_v2]:
            product = MockProduct(price=50000)  # 5万
            need = MockNeed(budget="10万-50万")
            score, reasons = eng._match_price_range(product, need)
            # 5万/10万=0.5 → 0.5*10=5分
            assert 0 <= score <= 10, f"[{eng.strategy}] 价格低于预算得分应在0~10之间, 实际{score}"

    def test_parse_budget_range(self, engine_v1, engine_v2):
        """解析预算范围"""
        for eng in [engine_v1, engine_v2]:
            result = eng._parse_budget("10万-50万")
            assert result == (100000, 500000), f"解析失败: {result}"
            result2 = eng._parse_budget("10万~50万")
            assert result2 == (100000, 500000)
            result3 = eng._parse_budget("10-50万")
            assert result3 == (100000, 500000)

    def test_parse_budget_open_ended(self, engine_v1, engine_v2):
        """解析开放式预算"""
        for eng in [engine_v1, engine_v2]:
            result = eng._parse_budget("10万以上")
            assert result[0] == 100000
            assert result[1] == float("inf")
            result2 = eng._parse_budget("5万以内")
            assert result2[0] == 0
            assert result2[1] == 50000


# ============================================================
# GAP 3: 单元测试 - 全链路端到端
# ============================================================


class TestFullPipeline:
    """全链路端到端匹配测试"""

    def _make_result(self, engine, product, need):
        """用 _calculate_match 模拟全链路"""
        return engine._calculate_match(product, need)

    def test_full_match_v1(self, engine_v1):
        """v1 全链路: 产品与需求匹配"""
        product = MockProduct(
            name="企业CRM系统",
            description="专为中小企业设计的CRM管理软件",
            price=200000,
            category="企业服务",
        )
        need = MockNeed(
            title="寻找CRM供应商",
            description="需要适合中小企业的CRM系统",
            category="企业服务",
            budget="10万-50万",
        )
        result = self._make_result(engine_v1, product, need)
        assert isinstance(result, MatchResult)
        assert 0 <= result.match_score <= 1.0
        assert result.match_score > 0.3, f"v1 全链路匹配分数应 > 0.3, 实际{result.match_score}"
        assert len(result.match_reasons) > 0
        assert result.strategy == "v1"

    def test_full_match_v2(self, engine_v2):
        """v2 全链路: 产品与需求匹配（jieba+TF-IDF）"""
        product = MockProduct(
            name="企业CRM系统",
            description="专为中小企业设计的CRM管理软件，SaaS云部署",
            price=200000,
            category="企业服务",
            tags="CRM,SaaS,企业服务",
        )
        need = MockNeed(
            title="寻找CRM供应商",
            description="需要适合中小企业的CRM系统，预算10-30万",
            category="企业服务",
            budget="10万-50万",
        )
        result = self._make_result(engine_v2, product, need)
        assert isinstance(result, MatchResult)
        assert 0 <= result.match_score <= 1.0
        assert result.match_score > 0.3, f"v2 全链路匹配分数应 > 0.3, 实际{result.match_score}"
        assert len(result.match_reasons) > 0
        assert result.strategy == "v2"

    def test_full_pipeline_no_match(self, engine_v1, engine_v2):
        """完全不匹配的场景"""
        for eng in [engine_v1, engine_v2]:
            product = MockProduct(
                name="工业机床",
                description="CNC数控机床加工设备",
                price=5000000,
                category="工业",
                tags="机械,工业",
            )
            need = MockNeed(
                title="美妆护肤品采购",
                description="寻找化妆品OEM代加工",
                category="消费品",
                budget="10万-30万",
            )
            result = self._make_result(eng, product, need)
            # 可以得一个极低分（部分匹配），但不应>0.5
            assert result.match_score < 0.5, f"[{eng.strategy}] 不匹配得分应<0.5, 实际{result.match_score}"


# ============================================================
# GAP 8: A/B 测试策略对比
# ============================================================


class TestABTesting:
    """A/B 测试策略对比"""

    def test_v1_v2_different_strategies(self, engine_v1, engine_v2):
        """v1 和 v2 策略不同，结果应有差异"""
        product = MockProduct(
            name="健康保健品",
            description="高品质保健品，增强免疫力",
            price=50000,
            category="大健康",
            tags="健康,保健品,养生",
        )
        need = MockNeed(
            title="寻找保健品供应商",
            description="需要保健品渠道合作推广",
            category="大健康",
            budget="5万-20万",
        )
        r1 = engine_v1._calculate_match(product, need)
        r2 = engine_v2._calculate_match(product, need)
        assert r1.strategy == "v1"
        assert r2.strategy == "v2"
        # 两者分数可能不同（但都是正分）
        assert r1.match_score > 0
        assert r2.match_score > 0

    def test_v1_v2_strategy_propagation(self):
        """策略信息传递到结果"""
        engine = MatchEngine(MockDb(), strategy="v1")
        assert engine.strategy == "v1"
        engine2 = MatchEngine(MockDb(), strategy="v2")
        assert engine2.strategy == "v2"

    def test_invalid_strategy(self):
        """非法策略参数应报错"""
        with pytest.raises(ValueError):
            MatchEngine(MockDb(), strategy="v3")


# ============================================================
# GAP 2: 缓存测试
# ============================================================


class TestCaching:
    """LRU 缓存层测试"""

    def test_cache_hit(self):
        """缓存命中"""
        call_count = [0]

        def fetch():
            call_count[0] += 1
            return [1, 2, 3]

        result1 = get_cached("test_key", fetch)
        assert result1 == [1, 2, 3]
        assert call_count[0] == 1

        result2 = get_cached("test_key", fetch)
        assert result2 == [1, 2, 3]
        assert call_count[0] == 1  # 没有再次调用 fetch

    def test_cache_expiry(self):
        """缓存过期后重新获取"""
        call_count = [0]

        def fetch():
            call_count[0] += 1
            return ["data"]

        # 短 TTL
        get_cached("expiry_key", fetch, ttl=0.01)
        assert call_count[0] == 1

        time.sleep(0.02)
        get_cached("expiry_key", fetch, ttl=0.01)
        assert call_count[0] == 2  # 过期后重新获取

    def test_clear_cache(self):
        """清除缓存"""
        get_cached("key_a", lambda: "A", ttl=60)
        get_cached("key_b", lambda: "B", ttl=60)
        assert "key_a" in _cache
        clear_cache("key_a")
        assert "key_a" not in _cache
        assert "key_b" in _cache
        clear_cache()
        assert len(_cache) == 0

    def test_cache_update_on_refresh(self):
        """缓存刷新后内容更新"""
        get_cached("refresh_key", lambda: "old", ttl=60)
        get_cached("refresh_key", lambda: "new", ttl=60)
        # 应该还是 old（缓存未过期）
        assert _cache["refresh_key"].data == "old"


# ============================================================
# GAP 6: 监控测试
# ============================================================


class TestMetrics:
    """匹配质量监控测试"""

    def test_metrics_record(self):
        """记录匹配指标"""
        match_metrics.record(0.8, 0.05)
        match_metrics.record(0.5, 0.03)
        match_metrics.record(0.2, 0.02)
        stats = match_metrics.get_stats()
        assert stats["total_requests"] == 3
        assert stats["avg_response_time_ms"] > 0
        assert "0.2-0.4" in stats["score_distribution"]
        assert "0.4-0.6" in stats["score_distribution"]
        assert "0.8-1.0" in stats["score_distribution"]

    def test_metrics_in_match(self, engine_v2):
        """匹配过程自动记录指标"""
        before = match_metrics.request_count
        product = MockProduct(
            name="CRM系统",
            description="SaaS软件",
            price=100000,
            category="企业服务",
        )
        need = MockNeed(
            title="找CRM",
            description="需要CRM",
            category="企业服务",
            budget="10万-50万",
        )
        engine_v2._calculate_match(product, need)
        assert match_metrics.request_count == before + 1


# ============================================================
# GAP 4: 配置化同义词测试
# ============================================================


class TestSynonymConfig:
    """配置化类目同义词测试"""

    def test_load_from_config_file(self, engine_v1, engine_v2):
        """从配置文件加载类目同义词"""
        for eng in [engine_v1, engine_v2]:
            synonyms = eng.CATEGORY_SYNONYMS
            assert isinstance(synonyms, dict)
            assert len(synonyms) >= 10  # 配置文件中有15大类
            assert "大健康" in synonyms
            assert "企业服务" in synonyms

    def test_synonym_from_config_works(self, engine_v2):
        """配置中的同义词匹配生效"""
        # "保健" 是大健康的同义词（来自配置文件）
        product = MockProduct(category="保健")
        need = MockNeed(category="大健康")
        score, reasons = engine_v2._match_category(product.category, need.category)
        assert score == 30.0, f"配置同义词匹配应得30分, 实际{score}"

    def test_fallback_to_default(self):
        """配置文件不存在时回退到默认同义词"""
        engine = MatchEngine(MockDb(), strategy="v2")
        engine._synonyms_config_path = "/nonexistent/path/synonyms.json"
        engine._synonyms = None  # 强制重新加载
        synonyms = engine._load_synonyms_from_file()
        assert synonyms is None  # 文件不存在返回 None
        # 自动使用默认值
        default_syns = engine.CATEGORY_SYNONYMS
        assert len(default_syns) >= 5  # 默认至少有5个


# ============================================================
# GAP 5+7: TF-IDF 关键词加权测试
# ============================================================


class TestTFIDFMatching:
    """TF-IDF 关键词加权测试"""

    def test_tfidf_similarity(self, engine_v2):
        """TF-IDF 计算正分"""
        product = MockProduct(
            name="AI智能客服系统",
            description="基于人工智能的在线客服机器人",
            tags="AI,客服,SaaS",
            category="科技产品",
        )
        need = MockNeed(
            title="寻找AI智能客服供应商",
            description="需要智能客服机器人系统",
            category="科技产品",
        )
        prod_text, need_text = engine_v2._build_tfidf_corpus(product, need)
        sim = engine_v2._compute_tfidf_similarity(prod_text, need_text)
        assert sim > 0, f"TF-IDF 相似度应为正数, 实际{sim}"

    def test_tfidf_dissimilar(self, engine_v2):
        """TF-IDF 不相关内容得分极低"""
        product = MockProduct(
            name="工业机床",
            description="CNC数控机床",
            tags="机械",
            category="工业",
        )
        need = MockNeed(
            title="护肤品采购",
            description="化妆品代工",
            category="消费品",
        )
        prod_text, need_text = engine_v2._build_tfidf_corpus(product, need)
        sim = engine_v2._compute_tfidf_similarity(prod_text, need_text)
        assert sim < 0.5, f"不相关内容 TF-IDF 相似度应 < 0.5, 实际{sim}"


# ============================================================
# 通用行为测试
# ============================================================


class TestNormalization:
    """文本规范化测试"""

    def test_normalize_text(self, engine_v1, engine_v2):
        """规范化处理"""
        for eng in [engine_v1, engine_v2]:
            assert eng._normalize_text("  Hello World! ") == "hello world"
            assert eng._normalize_text("") == ""
            assert eng._normalize_text(None) == ""
            assert eng._normalize_text("大健康/医疗") == "大健康 医疗"

    def test_score_normalization(self, engine_v1, engine_v2):
        """分数归一化到0-1"""
        for eng in [engine_v1, engine_v2]:
            # 假设三个维度都满分
            orig_cat = eng._match_category
            orig_kw = eng._match_keywords
            orig_price = eng._match_price_range

            def mock_cat(*args):
                return 40.0, ["mock"]

            def mock_kw(*args):
                return 40.0, ["mock"]

            def mock_price(*args):
                return 20.0, ["mock"]

            eng._match_category = mock_cat
            eng._match_keywords = mock_kw
            eng._match_price_range = mock_price

            product = MockProduct()
            need = MockNeed()
            result = eng._calculate_match(product, need)

            eng._match_category = orig_cat
            eng._match_keywords = orig_kw
            eng._match_price_range = orig_price

            assert result.match_score == 1.0, f"满分应归一化为1.0, 实际{result.match_score}"
