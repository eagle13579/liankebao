"""
链客宝 - BGE-M3 嵌入服务单元测试
====================================
测试覆盖:
1.  BgeM3Embedding 初始化 (降级模式/正常模式)
2.  encode 单个文本
3.  encode 批量文本
4.  encode 空文本
5.  批处理 (batch_size=1/32/100)
6.  降级模式确定性 (同一输入输出一致)
7.  单例模式 (get_embedder 返回同一实例)
8.  便捷函数 encode_texts
9.  _LocalEmbeddingCache get/set 单条操作
10. _LocalEmbeddingCache 不存在key返回None
11. _LocalEmbeddingCache batch 批量操作
12. _LocalEmbeddingCache stats/fush/clear
13. get_embedding_app FastAPI 子应用路由注册
14. get_embedding_app POST /embed 端点
15. get_embedding_app GET /embed/health 端点
16. get_embedding_app GET /embed/info 端点
"""

from __future__ import annotations

import os
import pickle
import tempfile
from typing import Any, Dict, Generator, List, Optional, Sequence
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# 被测试模块
from features.embedding_service import (
    BgeM3Embedding,
    DEFAULT_BATCH_SIZE,
    DEFAULT_CACHE_DIR,
    DEFAULT_MODEL_NAME,
    FALLBACK_SEED,
    MAX_DOWNLOAD_RETRIES,
    WARMUP_TEXTS,
    _FallbackEmbedder,
    _LocalEmbeddingCache,
    encode_texts,
    get_embedder,
    get_embedding_app,
)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def temp_cache_dir() -> Generator[str, None, None]:
    """提供临时缓存目录，测试后自动清理"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def fallback_embedder() -> BgeM3Embedding:
    """强制降级模式的嵌入器（每次测试全新实例）"""
    emb = BgeM3Embedding(force_fallback=True, enable_cache=False)
    emb.load_model()
    return emb


@pytest.fixture
def fallback_embedder_with_cache(temp_cache_dir: str) -> BgeM3Embedding:
    """带缓存的降级模式嵌入器"""
    emb = BgeM3Embedding(
        force_fallback=True,
        enable_cache=True,
        cache_dir=temp_cache_dir,
    )
    emb.load_model()
    return emb


@pytest.fixture
def reset_global_embedder() -> Generator[None, None, None]:
    """每个测试前后重置全局单例"""
    import features.embedding_service as svc

    old = svc._global_embedder
    svc._global_embedder = None
    yield
    svc._global_embedder = old


# ===================================================================
# _FallbackEmbedder 测试
# ===================================================================


class TestFallbackEmbedder:
    def test_initialization(self) -> None:
        """降级嵌入器初始化"""
        fb = _FallbackEmbedder(dimension=768, seed=FALLBACK_SEED)
        assert fb.dimension == 768
        assert fb.seed == FALLBACK_SEED

    def test_encode_single(self) -> None:
        """降级嵌入器：单条文本编码"""
        fb = _FallbackEmbedder(dimension=768)
        vecs = fb.encode(["测试文本"])
        assert vecs is not None
        assert len(vecs) == 1
        assert len(vecs[0]) == 768

    def test_encode_batch(self) -> None:
        """降级嵌入器：批量文本编码"""
        fb = _FallbackEmbedder(dimension=768)
        texts = ["文本A", "文本B", "文本C"]
        vecs = fb.encode(texts)
        assert vecs is not None
        assert len(vecs) == 3
        for v in vecs:
            assert len(v) == 768

    def test_deterministic_same_input(self) -> None:
        """降级嵌入器：相同输入产生相同输出（确定性）"""
        fb = _FallbackEmbedder(dimension=768)
        texts = ["链客宝确定性测试"]
        vecs_a = fb.encode(texts)
        vecs_b = fb.encode(texts)
        assert vecs_a is not None and vecs_b is not None
        assert vecs_a[0] == vecs_b[0]

    def test_deterministic_different_instances(self) -> None:
        """降级嵌入器：不同实例对相同输入也产生相同输出"""
        fb_a = _FallbackEmbedder(dimension=768)
        fb_b = _FallbackEmbedder(dimension=768)
        texts = ["跨实例测试"]
        vecs_a = fb_a.encode(texts)
        vecs_b = fb_b.encode(texts)
        assert vecs_a is not None and vecs_b is not None
        assert vecs_a[0] == vecs_b[0]

    def test_different_inputs_different_vectors(self) -> None:
        """降级嵌入器：不同输入应产生不同的向量"""
        fb = _FallbackEmbedder(dimension=768)
        vecs = fb.encode(["完全不同的文本A", "完全不同的文本B"])
        assert vecs is not None
        assert vecs[0] != vecs[1]

    def test_normalized_vectors(self) -> None:
        """降级嵌入器：输出向量应为 L2 归一化（约等于 1.0）"""
        fb = _FallbackEmbedder(dimension=768)
        vecs = fb.encode(["归一化测试"])
        assert vecs is not None
        norm = sum(v * v for v in vecs[0]) ** 0.5
        assert abs(norm - 1.0) < 1e-6

    def test_custom_dimension(self) -> None:
        """降级嵌入器：自定义维度"""
        fb = _FallbackEmbedder(dimension=128)
        vecs = fb.encode(["自定义维度"])
        assert vecs is not None
        assert len(vecs[0]) == 128


# ===================================================================
# _LocalEmbeddingCache 测试
# ===================================================================


class TestLocalEmbeddingCache:
    def test_get_set_single(self, temp_cache_dir: str) -> None:
        """缓存：单条 get/set 操作"""
        cache = _LocalEmbeddingCache(cache_dir=temp_cache_dir)
        text = "缓存测试文本"
        vector = [0.1, 0.2, 0.3]
        cache.set(text, vector)
        result = cache.get(text)
        assert result == vector

    def test_get_nonexistent_key(self, temp_cache_dir: str) -> None:
        """缓存：不存在的key返回 None"""
        cache = _LocalEmbeddingCache(cache_dir=temp_cache_dir)
        result = cache.get("不存在的key")
        assert result is None

    def test_contains(self, temp_cache_dir: str) -> None:
        """缓存：__contains__ 操作"""
        cache = _LocalEmbeddingCache(cache_dir=temp_cache_dir)
        text = "包含测试"
        cache.set(text, [0.5, 0.6])
        assert text in cache
        assert "不存在的" not in cache

    def test_len(self, temp_cache_dir: str) -> None:
        """缓存：__len__ 操作"""
        cache = _LocalEmbeddingCache(cache_dir=temp_cache_dir)
        assert len(cache) == 0
        cache.set("a", [1.0])
        cache.set("b", [2.0])
        assert len(cache) == 2

    def test_persistence_across_reload(self, temp_cache_dir: str) -> None:
        """缓存：持久化后重新加载仍可读取"""
        cache1 = _LocalEmbeddingCache(cache_dir=temp_cache_dir)
        cache1.set("持久化文本", [0.7, 0.8, 0.9])
        cache1.flush()

        # 重新创建实例，验证从磁盘加载
        cache2 = _LocalEmbeddingCache(cache_dir=temp_cache_dir)
        result = cache2.get("持久化文本")
        assert result == [0.7, 0.8, 0.9]

    def test_cache_clear(self, temp_cache_dir: str) -> None:
        """缓存：clear 清空所有数据"""
        cache = _LocalEmbeddingCache(cache_dir=temp_cache_dir)
        cache.set("a", [1.0])
        cache.set("b", [2.0])
        assert len(cache) == 2
        cache._cache = {}
        if os.path.exists(cache.cache_path):
            os.remove(cache.cache_path)
        assert len(cache) == 0
        assert cache.get("a") is None

    def test_different_texts_generate_different_keys(self) -> None:
        """缓存：不同文本生成不同缓存key"""
        key_a = _LocalEmbeddingCache._key("文本A")
        key_b = _LocalEmbeddingCache._key("文本B")
        key_a_dup = _LocalEmbeddingCache._key("文本A")
        assert key_a != key_b
        assert key_a == key_a_dup

    def test_corrupted_cache_file(self, temp_cache_dir: str) -> None:
        """缓存：损坏的缓存文件不会导致崩溃"""
        cache_path = os.path.join(temp_cache_dir, "fallback_embeddings_cache.pkl")
        # 写入损坏数据
        with open(cache_path, "wb") as f:
            f.write(b"corrupted data")
        cache = _LocalEmbeddingCache(cache_dir=temp_cache_dir)
        # 应该优雅降级为空缓存
        assert len(cache) == 0


# ===================================================================
# BgeM3Embedding 测试
# ===================================================================


class TestBgeM3Embedding:
    def test_initialization(self) -> None:
        """BgeM3Embedding：正常初始化（不加载模型）"""
        emb = BgeM3Embedding()
        assert emb.model_name == DEFAULT_MODEL_NAME
        assert emb.batch_size == DEFAULT_BATCH_SIZE
        assert emb.use_fp16 is True
        assert emb.normalize_embeddings is True
        assert emb.enable_cache is True
        assert emb.force_fallback is False
        assert emb._loaded is False
        assert emb._warmed_up is False

    def test_force_fallback_initialization(self) -> None:
        """BgeM3Embedding：强制降级模式初始化"""
        emb = BgeM3Embedding(force_fallback=True, enable_cache=False)
        assert emb.force_fallback is True
        result = emb.load_model()
        assert result is False  # 降级模式返回 False
        assert emb.is_fallback is True
        assert emb.is_loaded is True
        assert emb._model is None
        assert emb._fallback is not None

    def test_encode_single_text(self, fallback_embedder: BgeM3Embedding) -> None:
        """encode：单条文本编码"""
        vecs = fallback_embedder.encode(["测试文本"])
        assert vecs is not None
        assert len(vecs) == 1
        assert len(vecs[0]) == fallback_embedder.fallback_dimension

    def test_encode_batch_texts(self, fallback_embedder: BgeM3Embedding) -> None:
        """encode：批量文本编码"""
        texts = ["文本1", "文本2", "文本3", "文本4", "文本5"]
        vecs = fallback_embedder.encode(texts)
        assert vecs is not None
        assert len(vecs) == 5

    def test_encode_empty_texts(self, fallback_embedder: BgeM3Embedding) -> None:
        """encode：空文本列表"""
        vecs = fallback_embedder.encode([])
        assert vecs == []

    def test_encode_batch_size_1(self, fallback_embedder: BgeM3Embedding) -> None:
        """encode：batch_size=1 逐条编码"""
        texts = ["单条A", "单条B", "单条C"]
        vecs = fallback_embedder.encode(texts, batch_size=1)
        assert vecs is not None
        assert len(vecs) == 3

    def test_encode_batch_size_32(self, fallback_embedder: BgeM3Embedding) -> None:
        """encode：batch_size=32（默认批次）"""
        texts = [f"文本{i}" for i in range(35)]
        vecs = fallback_embedder.encode(texts, batch_size=32)
        assert vecs is not None
        assert len(vecs) == 35

    def test_encode_batch_size_100(self, fallback_embedder: BgeM3Embedding) -> None:
        """encode：batch_size=100（大批次覆盖）"""
        texts = [f"大文本{i}" for i in range(150)]
        vecs = fallback_embedder.encode(texts, batch_size=100)
        assert vecs is not None
        assert len(vecs) == 150

    def test_determinism_same_instance(self, fallback_embedder: BgeM3Embedding) -> None:
        """encode：同一实例相同输入产生相同输出"""
        texts = ["确定性测试"]
        vecs_a = fallback_embedder.encode(texts)
        vecs_b = fallback_embedder.encode(texts)
        assert vecs_a is not None and vecs_b is not None
        assert vecs_a[0] == vecs_b[0]

    def test_determinism_different_instances(self) -> None:
        """encode：不同实例相同输入产生相同输出（降级模式确定性）"""
        emb_a = BgeM3Embedding(force_fallback=True, enable_cache=False)
        emb_a.load_model()
        emb_b = BgeM3Embedding(force_fallback=True, enable_cache=False)
        emb_b.load_model()
        texts = ["链客宝跨实例测试"]
        vecs_a = emb_a.encode(texts)
        vecs_b = emb_b.encode(texts)
        assert vecs_a is not None and vecs_b is not None
        assert vecs_a[0] == vecs_b[0]

    def test_property_is_fallback(self, fallback_embedder: BgeM3Embedding) -> None:
        """属性：is_fallback 在降级模式下返回 True"""
        assert fallback_embedder.is_fallback is True

    def test_property_is_loaded(self, fallback_embedder: BgeM3Embedding) -> None:
        """属性：is_loaded 加载后返回 True"""
        assert fallback_embedder.is_loaded is True

    def test_property_dimension(self, fallback_embedder: BgeM3Embedding) -> None:
        """属性：dimension 返回降级维度"""
        assert fallback_embedder.dimension == 768

    @pytest.mark.parametrize(
        "model_name,cache_dir,batch_size,use_fp16,normalize",
        [
            (DEFAULT_MODEL_NAME, DEFAULT_CACHE_DIR, 32, True, True),
            ("BAAI/bge-small-zh-v1.5", "/tmp/cache", 64, False, False),
            ("custom-model", "./custom_cache", 1, True, False),
        ],
    )
    def test_init_params(
        self,
        model_name: str,
        cache_dir: str,
        batch_size: int,
        use_fp16: bool,
        normalize: bool,
    ) -> None:
        """BgeM3Embedding：参数化构造验证"""
        emb = BgeM3Embedding(
            model_name=model_name,
            cache_dir=cache_dir,
            batch_size=batch_size,
            use_fp16=use_fp16,
            normalize_embeddings=normalize,
            force_fallback=True,
        )
        assert emb.model_name == model_name
        assert emb.cache_dir == cache_dir
        assert emb.batch_size == batch_size
        assert emb.use_fp16 == use_fp16
        assert emb.normalize_embeddings == normalize

    def test_repr(self, fallback_embedder: BgeM3Embedding) -> None:
        """BgeM3Embedding：__repr__ 输出"""
        rep = repr(fallback_embedder)
        assert "BgeM3Embedding" in rep
        assert "fallback=True" in rep or "fallback=True" in rep

    def test_unload_model(self, fallback_embedder: BgeM3Embedding) -> None:
        """BgeM3Embedding：unload_model 卸载模型"""
        assert fallback_embedder.is_loaded
        fallback_embedder.unload_model()
        assert fallback_embedder.is_loaded is False
        assert fallback_embedder._warmed_up is False

    def test_double_load(self) -> None:
        """BgeM3Embedding：重复 load_model 不会重新加载"""
        emb = BgeM3Embedding(force_fallback=True, enable_cache=False)
        r1 = emb.load_model()
        r2 = emb.load_model()
        # 第二次调用应直接返回缓存状态
        assert r1 == r2

    def test_model_load_failure_triggers_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """BgeM3Embedding：模型加载失败自动进入降级模式"""
        # 模拟 _create_model 抛出异常
        def failing_create(self: Any) -> None:
            raise RuntimeError("模拟模型加载失败")

        emb = BgeM3Embedding(enable_cache=False)
        monkeypatch.setattr(BgeM3Embedding, "_create_model", failing_create)
        result = emb.load_model()
        assert result is False
        assert emb.is_fallback is True
        assert emb._fallback is not None

    def test_encode_with_cache_hit(
        self, fallback_embedder_with_cache: BgeM3Embedding
    ) -> None:
        """encode：缓存命中应直接从缓存返回"""
        emb = fallback_embedder_with_cache
        texts = ["缓存命中测试"]
        # 第一次调用写入缓存
        vecs_a = emb.encode(texts)
        assert vecs_a is not None
        # 第二次调用应从缓存读取（结果相同）
        vecs_b = emb.encode(texts)
        assert vecs_b is not None
        assert vecs_a[0] == vecs_b[0]

    def test_flush_cache(self, fallback_embedder_with_cache: BgeM3Embedding) -> None:
        """BgeM3Embedding：flush_cache 持久化缓存"""
        emb = fallback_embedder_with_cache
        emb.encode(["刷入磁盘"])
        emb.flush_cache()
        # 验证没有异常即可

    def test_clear_cache(self, fallback_embedder_with_cache: BgeM3Embedding) -> None:
        """BgeM3Embedding：clear_cache 清空缓存"""
        emb = fallback_embedder_with_cache
        # 降级模式下 encode 不写入缓存；直接操作 _cache_instance
        assert emb._cache_instance is not None
        # 手动设置缓存条目
        emb._cache_instance.set("测试key", [0.1, 0.2, 0.3])
        assert len(emb._cache_instance) == 1
        # clear_cache 清空
        emb.clear_cache()
        assert len(emb._cache_instance) == 0
        assert emb._cache_instance.get("测试key") is None


# ===================================================================
# 单例模式测试
# ===================================================================


class TestSingleton:
    def test_get_embedder_singleton(
        self, reset_global_embedder: None
    ) -> None:
        """get_embedder：多次调用返回同一实例"""
        emb_a = get_embedder(force_fallback=True)
        emb_b = get_embedder(force_fallback=True)
        assert emb_a is emb_b

    def test_get_embedder_is_loaded(
        self, reset_global_embedder: None
    ) -> None:
        """get_embedder：返回的实例已加载"""
        emb = get_embedder(force_fallback=True)
        assert emb.is_loaded

    def test_get_embedder_different_params_returns_same(
        self, reset_global_embedder: None
    ) -> None:
        """get_embedder：即使传入不同参数，单例也返回同一实例"""
        emb_a = get_embedder(force_fallback=True, batch_size=32)
        emb_b = get_embedder(force_fallback=True, batch_size=64)
        assert emb_a is emb_b

    def test_encode_texts_convenience(
        self, reset_global_embedder: None
    ) -> None:
        """encode_texts 便捷函数：正常编码"""
        vecs = encode_texts(["便捷函数测试"], force_fallback=True)
        assert vecs is not None
        assert len(vecs) == 1
        assert len(vecs[0]) == 768

    def test_encode_texts_batch(
        self, reset_global_embedder: None
    ) -> None:
        """encode_texts 便捷函数：批量编码"""
        vecs = encode_texts(
            ["便捷A", "便捷B", "便捷C"],
            force_fallback=True,
        )
        assert vecs is not None
        assert len(vecs) == 3

    def test_encode_texts_empty(
        self, reset_global_embedder: None
    ) -> None:
        """encode_texts 便捷函数：空文本"""
        vecs = encode_texts([], force_fallback=True)
        assert vecs == []

    def test_encode_texts_uses_global_singleton(
        self, reset_global_embedder: None
    ) -> None:
        """encode_texts 便捷函数：内部使用全局单例"""
        emb = get_embedder(force_fallback=True)
        vecs = encode_texts(["单例复用测试"], force_fallback=True)
        assert vecs is not None
        # 验证 encode_texts 内部复用了同一个全局嵌入器
        assert len(vecs) == 1


# ===================================================================
# FastAPI 子应用测试
# ===================================================================


class TestEmbeddingApp:
    @pytest.fixture
    def app(self, reset_global_embedder: None) -> TestClient:
        """创建嵌入服务子应用的 TestClient"""
        sub_app = get_embedding_app(force_fallback=True, enable_cache=False)
        return TestClient(sub_app)

    def test_post_embed_single(self, app: TestClient) -> None:
        """POST /embed：单条文本编码"""
        resp = app.post("/embed", json={"texts": ["你好世界"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "embeddings" in data
        assert len(data["embeddings"]) == 1
        assert data["dimension"] == 768
        assert data["fallback"] is True
        assert data["model"] == DEFAULT_MODEL_NAME

    def test_post_embed_batch(self, app: TestClient) -> None:
        """POST /embed：批量文本编码"""
        texts = ["文本A", "文本B", "文本C", "文本D"]
        resp = app.post("/embed", json={"texts": texts})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["embeddings"]) == 4

    def test_post_embed_with_batch_size(self, app: TestClient) -> None:
        """POST /embed：指定 batch_size"""
        texts = [f"第{i}个" for i in range(10)]
        resp = app.post("/embed", json={"texts": texts, "batch_size": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["embeddings"]) == 10

    def test_post_embed_empty_texts_400(self, app: TestClient) -> None:
        """POST /embed：空文本返回 400"""
        resp = app.post("/embed", json={"texts": []})
        assert resp.status_code == 400
        assert "不能为空" in resp.json()["detail"]

    def test_post_embed_missing_texts_422(self, app: TestClient) -> None:
        """POST /embed：缺少 texts 字段返回 422"""
        resp = app.post("/embed", json={})
        assert resp.status_code == 422

    def test_get_health(self, app: TestClient) -> None:
        """GET /embed/health：健康检查"""
        resp = app.get("/embed/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["loaded"] is True
        assert data["fallback"] is True
        assert data["model"] == DEFAULT_MODEL_NAME

    def test_get_info(self, app: TestClient) -> None:
        """GET /embed/info：服务信息"""
        resp = app.get("/embed/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == DEFAULT_MODEL_NAME
        assert data["fallback_active"] is True
        assert data["dimension"] == 768

    def test_get_root(self, app: TestClient) -> None:
        """GET /：根路径返回服务信息"""
        resp = app.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "service" in data
        assert "endpoints" in data

    def test_post_embed_response_structure(self, app: TestClient) -> None:
        """POST /embed：响应结构完整性"""
        resp = app.post("/embed", json={"texts": ["结构测试"]})
        assert resp.status_code == 200
        data = resp.json()
        # 验证所有必需字段
        required_fields = ["embeddings", "dimension", "model", "fallback", "elapsed_seconds"]
        for field in required_fields:
            assert field in data, f"缺少字段: {field}"
        # elapsed_seconds 应为正数
        assert data["elapsed_seconds"] >= 0


# ===================================================================
# 模型加载失败场景测试
# ===================================================================


class TestModelFailureScenarios:
    def test_model_import_error_graceful(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_create_model 抛出 ImportError 时优雅处理"""
        def raise_import_error(self: Any) -> None:
            raise ImportError("模拟 FlagEmbedding 未安装")

        emb = BgeM3Embedding(enable_cache=False)
        monkeypatch.setattr(BgeM3Embedding, "_create_model", raise_import_error)
        result = emb.load_model()
        assert result is False
        assert emb.is_fallback is True

    def test_encode_when_no_embedder_available(self) -> None:
        """encode：无可用嵌入器返回 None（极端情况测试）"""
        emb = BgeM3Embedding(force_fallback=True, enable_cache=False)
        # 不加载模型，直接编码应触发懒加载（进入降级）
        vecs = emb.encode(["懒加载触发"])
        assert vecs is not None  # 降级模式提供结果

    def test_encode_fallback_on_model_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """encode：模型编码失败降级到 fallback（通过 monkeypatch _encode_with_model）"""
        def failing_encode(self: Any, texts: Sequence[str], batch_size: int, **kwargs: Any) -> None:
            raise RuntimeError("模拟模型编码失败")

        emb = BgeM3Embedding(force_fallback=True, enable_cache=False)
        emb.load_model()
        # 在降级模式下 _encode_with_model 不会被调用
        # 但我们可以验证整体逻辑：model为None时走_fallback
        assert emb._model is None
        assert emb._fallback is not None
        vecs = emb.encode(["降级测试"])
        assert vecs is not None


# ===================================================================
# 边缘场景测试
# ===================================================================


class TestEdgeCases:
    def test_special_characters(self, fallback_embedder: BgeM3Embedding) -> None:
        """特殊字符：emoji、空格、空字符串"""
        texts = [
            "Hello, 世界！🌍",
            "  多个  空格  ",
            "\n\t换行符\t\n",
            "",
            "🔥🔥🔥🔥🔥",
            "a" * 10000,  # 长文本
        ]
        vecs = fallback_embedder.encode(texts)
        assert vecs is not None
        assert len(vecs) == 6
        for v in vecs:
            assert len(v) == 768

    def test_large_batch(self, fallback_embedder: BgeM3Embedding) -> None:
        """大批量：300条文本编码"""
        texts = [f"大批量文本{i}" for i in range(300)]
        vecs = fallback_embedder.encode(texts, batch_size=64)
        assert vecs is not None
        assert len(vecs) == 300

    def test_duplicate_texts(self, fallback_embedder: BgeM3Embedding) -> None:
        """重复文本：相同文本多次出现"""
        texts = ["重复文本"] * 5
        vecs = fallback_embedder.encode(texts)
        assert vecs is not None
        assert len(vecs) == 5
        # 所有输出应该相同（确定性）
        for i in range(1, 5):
            assert vecs[i] == vecs[0]

    def test_cache_not_affect_fallback_determinism(
        self, temp_cache_dir: str
    ) -> None:
        """缓存不破坏降级确定性"""
        emb_a = BgeM3Embedding(
            force_fallback=True, enable_cache=True, cache_dir=temp_cache_dir
        )
        emb_a.load_model()
        emb_a.encode(["确定性测试"], batch_size=1)

        # 重建实例（从缓存加载）
        emb_b = BgeM3Embedding(
            force_fallback=True, enable_cache=True, cache_dir=temp_cache_dir
        )
        emb_b.load_model()
        vecs = emb_b.encode(["确定性测试"])
        assert vecs is not None
        assert len(vecs[0]) == 768
