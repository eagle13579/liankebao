"""数据丰富 Service 层测试

测试 app.services.data_enrichment 模块：
- 缓存机制（_cache_get / _cache_set）
- 降级逻辑（API 失败后返回模拟数据/过期缓存）
- QichachaEnricher 各方法（search_company / get_business_scope / get_contacts / enrich）
- 工厂函数和单例
"""

import os
import tempfile
import time

import pytest

from app.services.data_enrichment import (
    CACHE_TTL_SECONDS,
    BaseEnricher,
    QichachaEnricher,
    _cache_get,
    _cache_set,
    _get_cache_connection,
    create_enricher,
    get_enricher,
)


class TestEnrichmentCache:
    """缓存机制测试"""

    @pytest.fixture(autouse=True)
    def _isolate_cache(self):
        """每个测试使用独立的缓存数据库"""
        import app.services.data_enrichment as de_mod

        self._orig_path = de_mod.CACHE_DB_PATH
        tmpdir = tempfile.mkdtemp()
        de_mod.CACHE_DB_PATH = os.path.join(tmpdir, "test_cache.db")
        de_mod.CACHE_DB_DIR = tmpdir
        yield
        de_mod.CACHE_DB_PATH = self._orig_path
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_cache_set_and_get(self):
        """写入缓存后可以读取"""
        _cache_set("test:key", {"name": "测试", "value": 123})
        result = _cache_get("test:key")
        assert result is not None
        assert result["name"] == "测试"
        assert result["value"] == 123

    def test_cache_miss(self):
        """不存在的 key 返回 None"""
        result = _cache_get("nonexistent:key")
        assert result is None

    def test_cache_expiry(self):
        """过期缓存返回 None"""
        _cache_set("test:expire", {"data": "过期数据"})
        # 模拟时间流逝 - 通过直接修改数据库时间戳
        conn = _get_cache_connection()
        past_time = time.time() - CACHE_TTL_SECONDS - 100
        conn.execute(
            "UPDATE enrichment_cache SET created_at = ? WHERE cache_key = ?",
            (past_time, "test:expire"),
        )
        conn.commit()
        conn.close()
        result = _cache_get("test:expire")
        assert result is None

    def test_cache_overwrite(self):
        """相同 key 覆盖旧值"""
        _cache_set("test:overwrite", {"version": 1})
        _cache_set("test:overwrite", {"version": 2})
        result = _cache_get("test:overwrite")
        assert result["version"] == 2


class TestQichachaEnricher:
    """QichachaEnricher 类测试"""

    @pytest.fixture(autouse=True)
    def _setup_cache_dir(self):
        """为每个测试准备独立的缓存目录"""
        import app.services.data_enrichment as de_mod

        self._orig_path = de_mod.CACHE_DB_PATH
        self._orig_dir = de_mod.CACHE_DB_DIR
        tmpdir = tempfile.mkdtemp()
        de_mod.CACHE_DB_PATH = os.path.join(tmpdir, "test_cache.db")
        de_mod.CACHE_DB_DIR = tmpdir
        yield
        de_mod.CACHE_DB_PATH = self._orig_path
        de_mod.CACHE_DB_DIR = self._orig_dir
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_enricher_search_company_known(self):
        """已知企业返回精确匹配数据"""
        enricher = QichachaEnricher()
        result = enricher.search_company("北京字节跳动科技有限公司")
        assert result["name"] == "北京字节跳动科技有限公司"
        assert result["credit_code"] == "91110108MA01BKLE31"
        assert result["confidence"] == 0.95

    def test_enricher_search_company_fuzzy(self):
        """模糊匹配企业名"""
        enricher = QichachaEnricher()
        result = enricher.search_company("字节跳动")
        assert result is not None
        assert "credit_code" in result

    def test_enricher_search_company_unknown(self):
        """未知企业返回模拟降级数据"""
        enricher = QichachaEnricher()
        result = enricher.search_company("完全不存在的企业名称12345")
        assert result is not None
        assert result["name"] == "完全不存在的企业名称12345"

    def test_enricher_get_business_scope(self):
        """经营范围查询"""
        enricher = QichachaEnricher()
        result = enricher.get_business_scope("北京字节跳动科技有限公司")
        assert "business_scope" in result
        assert "industry" in result

    def test_enricher_get_contacts_known(self):
        """已知企业联系人查询"""
        enricher = QichachaEnricher()
        result = enricher.get_contacts("北京字节跳动科技有限公司")
        assert len(result["contacts"]) > 0
        assert "phones" in result

    def test_enricher_get_contacts_unknown(self):
        """未知企业联系人返回空列表"""
        enricher = QichachaEnricher()
        result = enricher.get_contacts("完全不存在的企业")
        assert result["contacts"] == []

    def test_enricher_enrich_integration(self):
        """enrich 聚合方法返回全部字段"""
        enricher = QichachaEnricher()
        result = enricher.enrich("北京字节跳动科技有限公司")
        assert result["name"] == "北京字节跳动科技有限公司"
        assert "business_scope_detail" in result
        assert "contacts" in result
        assert "phones" in result

    def test_enricher_cache_hit(self):
        """第二次查询命中缓存"""
        enricher = QichachaEnricher()
        # 第一次查询 — 写缓存
        result1 = enricher.search_company("北京字节跳动科技有限公司")
        # 第二次查询 — 读缓存
        result2 = enricher.search_company("北京字节跳动科技有限公司")
        assert result1 == result2


class TestCreateEnricher:
    """工厂函数测试"""

    def test_create_qichacha_enricher(self):
        """create_enricher('qichacha') 返回 QichachaEnricher 实例"""
        enricher = create_enricher("qichacha")
        assert isinstance(enricher, QichachaEnricher)

    def test_create_invalid_provider(self):
        """不支持的 provider 抛出 ValueError"""
        with pytest.raises(ValueError):
            create_enricher("invalid_provider")

    def test_get_enricher_singleton(self):
        """get_enricher 返回相同实例"""
        e1 = get_enricher()
        e2 = get_enricher()
        assert e1 is e2


class TestBaseEnricher:
    """BaseEnricher 抽象基类"""

    def test_base_enricher_cannot_instantiate(self):
        """BaseEnricher 包含抽象方法，无法直接实例化"""
        with pytest.raises(TypeError):
            BaseEnricher()
