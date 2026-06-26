"""
链客宝 - BGE-M3 嵌入服务封装
===============================
基于 FlagEmbedding 的 BGE-M3 多语言嵌入模型服务封装。

能力:
1. BgeM3Embedding 类 — 模型加载/预热/编码/降级
2. FastAPI 子应用模式 — 通过 /embed 端点提供服务
3. 批处理支持 (batch_size=32)
4. 模型缓存 (下载到本地目录，避免重复下载)
5. 错误处理 + 降级逻辑 (模型不可用时返回 None 而非崩溃)

使用方式:
    from features.embedding_service import BgeM3Embedding, get_embedding_app

    # 纯编码使用
    embedder = BgeM3Embedding()
    vectors = embedder.encode(["文本1", "文本2"])
    if vectors is not None:
        print(f"嵌入维度: {len(vectors[0])}")

    # FastAPI 子应用注册
    app.mount("/api/embed", get_embedding_app())

依赖:
    pip install FlagEmbedding fastapi

Author: P8 数据管道 Specialist
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import time
from pathlib import Path
from typing import Any, List, Optional, Sequence

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# BGE-M3 官方模型名称（HuggingFace）
DEFAULT_MODEL_NAME = "BAAI/bge-m3"

# 本地模型缓存根目录
DEFAULT_CACHE_DIR = os.path.join(
    str(Path.home()), ".cache", "chainke", "bge-m3"
)

# 批处理默认大小
DEFAULT_BATCH_SIZE = 32

# 最大重试次数（模型下载）
MAX_DOWNLOAD_RETRIES = 3

# 降级模式下的随机种子（保证确定性）
FALLBACK_SEED = 42

# 预计算缓存文件名
FALLBACK_CACHE_FILE = "fallback_embeddings_cache.pkl"

# 预热文本（用于首次推理触发模型编译）
WARMUP_TEXTS = ["链客宝数据管道预热", "warmup initialization text"]


# ---------------------------------------------------------------------------
# 降级嵌入器
# ---------------------------------------------------------------------------


class _FallbackEmbedder:
    """
    当 BGE-M3 模型不可用时的降级嵌入器。

    使用确定性哈希映射生成固定维度的虚拟嵌入向量，
    确保相同的输入始终产生相同的输出（确定性），
    但不同输入之间保持一定的区分度。
    """

    def __init__(self, dimension: int = 768, seed: int = FALLBACK_SEED) -> None:
        self.dimension = dimension
        self.seed = seed
        logger.warning(
            "[embedding] 使用降级嵌入器 (dim=%d, seed=%d) — 仅用于开发和降级场景",
            dimension, seed,
        )

    def encode(
        self,
        texts: Sequence[str],
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> Optional[List[List[float]]]:
        """生成确定性虚拟嵌入"""
        vectors: List[List[float]] = []
        for text in texts:
            # 使用文本的哈希值作为随机种子的基础
            text_hash = hashlib.md5(text.encode("utf-8")).digest()
            seed = int.from_bytes(text_hash[:4], "big")
            # 确定性伪随机向量生成
            rng = __import__("random").Random(seed)
            vec = [rng.gauss(0.0, 1.0) for _ in range(self.dimension)]
            # L2 归一化
            norm = sum(v * v for v in vec) ** 0.5
            if norm > 0:
                vec = [v / norm for v in vec]
            vectors.append(vec)
        return vectors


# ---------------------------------------------------------------------------
# 本地嵌入缓存（预计算模式）
# ---------------------------------------------------------------------------


class _LocalEmbeddingCache:
    """
    本地嵌入缓存。
    将已计算过的文本-向量对缓存到磁盘，避免重复调用模型。
    """

    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR) -> None:
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.cache_path = os.path.join(cache_dir, FALLBACK_CACHE_FILE)
        self._cache: dict[str, List[float]] = {}
        self._load()

    def _load(self) -> None:
        """从磁盘加载缓存"""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "rb") as f:
                    self._cache = pickle.load(f)
                logger.info(
                    "[embedding] 加载本地嵌入缓存: %d 条", len(self._cache)
                )
            except Exception as e:
                logger.warning("[embedding] 加载嵌入缓存失败: %s", e)
                self._cache = {}

    def _save(self) -> None:
        """持久化缓存到磁盘"""
        try:
            with open(self.cache_path, "wb") as f:
                pickle.dump(self._cache, f)
        except Exception as e:
            logger.warning("[embedding] 保存嵌入缓存失败: %s", e)

    def get(self, text: str) -> Optional[List[float]]:
        """获取缓存的嵌入"""
        return self._cache.get(self._key(text))

    def set(self, text: str, vector: List[float]) -> None:
        """设置缓存"""
        self._cache[self._key(text)] = vector

    def flush(self) -> None:
        """显式持久化"""
        self._save()

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, text: str) -> bool:
        return self._key(text) in self._cache


# ---------------------------------------------------------------------------
# BGE-M3 嵌入器
# ---------------------------------------------------------------------------


class BgeM3Embedding:
    """
    BGE-M3 多语言嵌入模型封装。

    支持:
    - 懒加载模型（首次 encode 时加载）
    - 模型预热
    - 批处理编码
    - 自动降级（模型不可用时使用确定性伪向量）
    - 本地嵌入缓存（避免重复计算）

    Examples
    --------
    >>> embedder = BgeM3Embedding()
    >>> vectors = embedder.encode(["你好", "hello world"])
    >>> vectors is not None
    True
    >>> len(vectors) == 2
    True
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        cache_dir: str = DEFAULT_CACHE_DIR,
        batch_size: int = DEFAULT_BATCH_SIZE,
        use_fp16: bool = True,
        normalize_embeddings: bool = True,
        fallback_dimension: int = 768,
        enable_cache: bool = True,
        force_fallback: bool = False,
    ) -> None:
        """
        Args:
            model_name: BGE-M3 模型名称或本地路径
            cache_dir: 模型和嵌入缓存的本地目录
            batch_size: 编码时的批处理大小
            use_fp16: 是否使用半精度（减少显存占用）
            normalize_embeddings: 是否 L2 归一化嵌入向量
            fallback_dimension: 降级模式下的向量维度
            enable_cache: 是否启用本地嵌入缓存
            force_fallback: 强制使用降级模式（用于测试）
        """
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.batch_size = batch_size
        self.use_fp16 = use_fp16
        self.normalize_embeddings = normalize_embeddings
        self.fallback_dimension = fallback_dimension
        self.enable_cache = enable_cache
        self.force_fallback = force_fallback

        # 内部状态
        self._model: Any = None  # BGEM3FlagModel 实例
        self._fallback: Optional[_FallbackEmbedder] = None
        self._cache_instance: Optional[_LocalEmbeddingCache] = None
        self._loaded: bool = False
        self._warmed_up: bool = False
        self._model_load_time: float = 0.0

        # 确保缓存目录存在
        os.makedirs(cache_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 模型加载
    # ------------------------------------------------------------------

    def load_model(self) -> bool:
        """
        加载 BGE-M3 模型。

        Returns:
            加载成功返回 True，失败（降级模式）返回 False
        """
        if self._loaded:
            return self._model is not None

        if self.force_fallback:
            logger.info("[embedding] 强制降级模式，跳过模型加载")
            self._init_fallback()
            self._loaded = True
            return False

        # 尝试加载模型
        start = time.perf_counter()
        for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
            try:
                logger.info(
                    "[embedding] 正在加载模型 %s (尝试 %d/%d)...",
                    self.model_name, attempt, MAX_DOWNLOAD_RETRIES,
                )
                self._model = self._create_model()
                self._model_load_time = time.perf_counter() - start
                self._loaded = True
                logger.info(
                    "[embedding] 模型加载成功 (%.2fs)", self._model_load_time
                )
                return True
            except Exception as e:
                logger.warning(
                    "[embedding] 模型加载失败 (尝试 %d/%d): %s",
                    attempt, MAX_DOWNLOAD_RETRIES, e,
                )
                if attempt < MAX_DOWNLOAD_RETRIES:
                    wait = 2.0 * attempt
                    logger.info("[embedding] %d 秒后重试...", wait)
                    time.sleep(wait)

        # 所有重试失败，进入降级模式
        logger.error(
            "[embedding] 模型加载失败（已重试 %d 次），进入降级模式",
            MAX_DOWNLOAD_RETRIES,
        )
        self._init_fallback()
        self._loaded = True
        return False

    def _create_model(self) -> Any:
        """创建 BGEM3FlagModel 实例（可被子类重写用于测试）"""
        from FlagEmbedding import BGEM3FlagModel

        return BGEM3FlagModel(
            model_name_or_path=self.model_name,
            normalize_embeddings=self.normalize_embeddings,
            use_fp16=self.use_fp16,
            cache_dir=self.cache_dir,
            batch_size=self.batch_size,
        )

    def _init_fallback(self) -> None:
        """初始化降级嵌入器"""
        self._model = None
        self._fallback = _FallbackEmbedder(dimension=self.fallback_dimension)
        if self.enable_cache:
            self._cache_instance = _LocalEmbeddingCache(
                cache_dir=self.cache_dir
            )

    # ------------------------------------------------------------------
    # 预热
    # ------------------------------------------------------------------

    def warmup(self) -> bool:
        """
        预热模型 — 执行一次小批量推理，触发模型编译和显存分配。

        Returns:
            预热成功返回 True
        """
        if self._warmed_up:
            return True

        if not self._loaded:
            success = self.load_model()
            if not success and self._model is None:
                # 降级模式，无需预热
                self._warmed_up = True
                return True

        if self._model is not None:
            try:
                logger.info("[embedding] 预热模型...")
                _ = self._model.encode(
                    WARMUP_TEXTS,
                    batch_size=min(len(WARMUP_TEXTS), self.batch_size),
                    return_dense=True,
                    return_sparse=False,
                    return_colbert_vecs=False,
                )
                self._warmed_up = True
                logger.info("[embedding] 预热完成")
                return True
            except Exception as e:
                logger.warning("[embedding] 预热失败: %s", e)
                # 预热失败不清除模型，仍可尝试推理
                self._warmed_up = True
                return False

        self._warmed_up = True
        return True

    # ------------------------------------------------------------------
    # 核心编码
    # ------------------------------------------------------------------

    def encode(
        self,
        texts: Sequence[str],
        batch_size: Optional[int] = None,
        **kwargs: Any,
    ) -> Optional[List[List[float]]]:
        """
        编码文本为嵌入向量。

        自动处理:
        - 模型懒加载
        - 批处理
        - 错误降级
        - 本地缓存（启用时）

        Args:
            texts: 待编码的文本列表
            batch_size: 批处理大小（覆盖默认值）
            **kwargs: 传递给底层 encode 的额外参数

        Returns:
            嵌入向量列表 (List[List[float]])，失败时返回 None。
            每个向量维度取决于模型配置（默认 1024 for bge-m3）。
        """
        if not texts:
            return []

        # 懒加载
        if not self._loaded:
            self.load_model()

        if not self._warmed_up:
            self.warmup()

        bs = batch_size or self.batch_size

        # 缓存检查
        if self.enable_cache and self._cache_instance is not None:
            cached_result = self._try_cache(texts)
            if cached_result is not None:
                return cached_result

        if self._model is not None:
            # 使用真实模型
            return self._encode_with_model(texts, bs, **kwargs)
        elif self._fallback is not None:
            # 使用降级嵌入器
            return self._fallback.encode(texts, batch_size=bs)
        else:
            # 极端情况：连降级嵌入器都没有
            logger.error("[embedding] 无可用嵌入器")
            return None

    def _encode_with_model(
        self,
        texts: Sequence[str],
        batch_size: int,
        **kwargs: Any,
    ) -> Optional[List[List[float]]]:
        """使用真实 BGE-M3 模型编码"""
        try:
            all_vectors: List[List[float]] = []
            # 分批处理
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                try:
                    output = self._model.encode(
                        list(batch),
                        batch_size=min(len(batch), batch_size),
                        return_dense=True,
                        return_sparse=False,
                        return_colbert_vecs=False,
                        **kwargs,
                    )
                    dense_vecs = output.get("dense_vecs")
                    if dense_vecs is not None:
                        batch_vectors = dense_vecs.tolist()
                        all_vectors.extend(batch_vectors)

                        # 写入缓存
                        if self.enable_cache and self._cache_instance is not None:
                            for txt, vec in zip(batch, batch_vectors):
                                self._cache_instance.set(txt, vec)
                    else:
                        logger.error(
                            "[embedding] 模型返回数据中无 dense_vecs"
                        )
                        # 部分失败，尝试降级这批
                        if self._fallback is not None:
                            fb_vectors = self._fallback.encode(
                                batch, batch_size=len(batch)
                            )
                            if fb_vectors:
                                all_vectors.extend(fb_vectors)
                        else:
                            return None
                except Exception as batch_e:
                    logger.warning(
                        "[embedding] 批次 %d~%d 编码失败: %s",
                        i, i + len(batch) - 1, batch_e,
                    )
                    # 批次降级
                    if self._fallback is not None:
                        fb_vectors = self._fallback.encode(
                            batch, batch_size=len(batch)
                        )
                        if fb_vectors:
                            all_vectors.extend(fb_vectors)
                        else:
                            return None
                    else:
                        return None

            # 刷新缓存
            if self.enable_cache and self._cache_instance is not None:
                self._cache_instance.flush()

            return all_vectors

        except Exception as e:
            logger.error("[embedding] 编码失败: %s", e)
            # 整体降级
            if self._fallback is not None:
                logger.info("[embedding] 降级到虚拟嵌入器")
                return self._fallback.encode(texts, batch_size=batch_size)
            return None

    def _try_cache(
        self, texts: Sequence[str]
    ) -> Optional[List[List[float]]]:
        """尝试从本地缓存获取全部嵌入"""
        if self._cache_instance is None:
            return None

        vectors: List[List[float]] = []
        all_cached = True
        for text in texts:
            cached = self._cache_instance.get(text)
            if cached is not None:
                vectors.append(cached)
            else:
                all_cached = False
                break

        if all_cached and len(vectors) == len(texts):
            logger.debug(
                "[embedding] 缓存命中: %d 条", len(vectors)
            )
            return vectors
        return None

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def is_fallback(self) -> bool:
        """是否处于降级模式"""
        return self._model is None

    @property
    def is_loaded(self) -> bool:
        """模型是否已加载（含降级模式）"""
        return self._loaded

    @property
    def dimension(self) -> int:
        """嵌入向量维度"""
        if self._model is not None:
            # 尝试推断维度
            try:
                test = self._model.encode(
                    ["dim"], batch_size=1, return_dense=True,
                    return_sparse=False, return_colbert_vecs=False,
                )
                dense = test.get("dense_vecs")
                if dense is not None:
                    return dense.shape[1]
            except Exception:
                pass
        return self.fallback_dimension

    @property
    def model_load_time(self) -> float:
        """模型加载耗时（秒）"""
        return self._model_load_time

    # ------------------------------------------------------------------
    # 资源管理
    # ------------------------------------------------------------------

    def flush_cache(self) -> None:
        """持久化嵌入缓存"""
        if self._cache_instance is not None:
            self._cache_instance.flush()

    def clear_cache(self) -> None:
        """清空嵌入缓存"""
        if self._cache_instance is not None:
            self._cache_instance._cache = {}
            if os.path.exists(self._cache_instance.cache_path):
                try:
                    os.remove(self._cache_instance.cache_path)
                except Exception:
                    pass

    def unload_model(self) -> None:
        """卸载模型释放资源"""
        self._model = None
        self._loaded = False
        self._warmed_up = False
        import gc
        gc.collect()
        logger.info("[embedding] 模型已卸载")

    def __repr__(self) -> str:
        return (
            f"BgeM3Embedding(model={self.model_name}, "
            f"loaded={self._loaded}, "
            f"fallback={self.is_fallback}, "
            f"cache_dir={self.cache_dir})"
        )


# ---------------------------------------------------------------------------
# FastAPI 请求/响应模型
# ---------------------------------------------------------------------------


class EmbedRequest(BaseModel):
    """嵌入请求体"""
    texts: List[str]
    batch_size: Optional[int] = None


class EmbedResponse(BaseModel):
    """嵌入响应"""
    embeddings: List[List[float]]
    dimension: int
    model: str
    fallback: bool
    elapsed_seconds: float


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    model: str
    loaded: bool
    fallback: bool
    dimension: int
    model_load_time: float


class InfoResponse(BaseModel):
    """服务信息响应"""
    model: str
    version: str = "1.0.0"
    dimension: int
    fallback_active: bool
    batch_size: int
    cache_dir: str
    cache_entries: int


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_global_embedder: Optional[BgeM3Embedding] = None


def get_embedder(
    model_name: str = DEFAULT_MODEL_NAME,
    cache_dir: str = DEFAULT_CACHE_DIR,
    batch_size: int = DEFAULT_BATCH_SIZE,
    force_fallback: bool = False,
    **kwargs: Any,
) -> BgeM3Embedding:
    """
    获取全局 BGE-M3 嵌入器单例。

    首次调用会创建并自动加载/预热模型。

    Args:
        model_name: 模型名称或路径
        cache_dir: 缓存目录
        batch_size: 批处理大小
        force_fallback: 强制降级模式
        **kwargs: 传递给 BgeM3Embedding 的其他参数

    Returns:
        BgeM3Embedding 实例
    """
    global _global_embedder
    if _global_embedder is None:
        _global_embedder = BgeM3Embedding(
            model_name=model_name,
            cache_dir=cache_dir,
            batch_size=batch_size,
            force_fallback=force_fallback,
            **kwargs,
        )
        _global_embedder.load_model()
        _global_embedder.warmup()
    return _global_embedder


# ---------------------------------------------------------------------------
# FastAPI 子应用
# ---------------------------------------------------------------------------


def get_embedding_app(
    model_name: str = DEFAULT_MODEL_NAME,
    cache_dir: str = DEFAULT_CACHE_DIR,
    batch_size: int = DEFAULT_BATCH_SIZE,
    prefix: str = "/api/embed",
    **kwargs: Any,
) -> "FastAPI":
    """
    创建 BGE-M3 嵌入服务的 FastAPI 子应用。

    端点:
        POST /embed — 编码文本为嵌入向量
        GET  /health — 服务健康检查
        GET  /info   — 模型信息

    注册方式:
        from fastapi import FastAPI
        app = FastAPI()
        app.mount("/api/embed", get_embedding_app())

    Args:
        model_name: 模型名称或路径
        cache_dir: 缓存目录
        batch_size: 批处理大小
        prefix: API 前缀（仅用于日志/文档）
        **kwargs: 传递给 BgeM3Embedding 的参数

    Returns:
        FastAPI 子应用
    """
    from fastapi import FastAPI, HTTPException

    # 获取或创建嵌入器
    embedder = get_embedder(
        model_name=model_name,
        cache_dir=cache_dir,
        batch_size=batch_size,
        **kwargs,
    )

    # ── 子应用 ─────────────────────────────────────────────────────

    sub_app = FastAPI(
        title="BGE-M3 嵌入服务",
        description="基于 BAAI/bge-m3 的多语言文本嵌入服务",
        version="1.0.0",
    )

    @sub_app.post("/embed", response_model=EmbedResponse, tags=["嵌入"])
    async def embed_texts(body: EmbedRequest):
        """
        编码文本列表为嵌入向量。

        ---
        body:
            texts: 待编码的文本列表
            batch_size: 可选的批处理大小覆盖

        response:
            embeddings: 嵌入向量列表 (List[List[float]])
            dimension:  向量维度
            model:      模型名称
            fallback:   是否处于降级模式
            elapsed:    耗时(秒)
        """
        if not body.texts:
            raise HTTPException(status_code=400, detail="texts 不能为空")

        start = time.perf_counter()
        try:
            vectors = embedder.encode(
                texts=body.texts,
                batch_size=body.batch_size,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"编码失败: {str(e)}",
            )

        if vectors is None:
            raise HTTPException(
                status_code=503,
                detail="嵌入服务不可用（模型加载失败且降级模式也失败）",
            )

        elapsed = round(time.perf_counter() - start, 4)

        return EmbedResponse(
            embeddings=vectors,
            dimension=len(vectors[0]) if vectors else 0,
            model=model_name,
            fallback=embedder.is_fallback,
            elapsed_seconds=elapsed,
        )

    @sub_app.get("/embed/health", response_model=HealthResponse, tags=["健康检查"])
    async def embedding_health():
        """嵌入服务健康检查"""
        return HealthResponse(
            status="ok" if embedder.is_loaded else "degraded",
            model=model_name,
            loaded=embedder.is_loaded,
            fallback=embedder.is_fallback,
            dimension=embedder.dimension,
            model_load_time=embedder.model_load_time,
        )

    @sub_app.get(
        "/embed/info", response_model=InfoResponse, tags=["信息"]
    )
    async def embedding_info():
        """嵌入服务信息"""
        return InfoResponse(
            model=model_name,
            dimension=embedder.dimension,
            fallback_active=embedder.is_fallback,
            batch_size=batch_size,
            cache_dir=cache_dir,
            cache_entries=0,  # 简化处理，不暴露内部缓存
        )

    # 兼容位置：同时响应 / 和 /embed
    @sub_app.get("/", include_in_schema=False)
    async def root_redirect():
        return {
            "service": "BGE-M3 嵌入服务",
            "endpoints": {
                "POST /embed": "编码文本为嵌入向量",
                "GET  /embed/health": "健康检查",
                "GET  /embed/info": "服务信息",
            },
        }

    return sub_app


# ---------------------------------------------------------------------------
# 便捷入口：直接使用
# ---------------------------------------------------------------------------


def encode_texts(
    texts: Sequence[str],
    model_name: str = DEFAULT_MODEL_NAME,
    cache_dir: str = DEFAULT_CACHE_DIR,
    batch_size: int = DEFAULT_BATCH_SIZE,
    **kwargs: Any,
) -> Optional[List[List[float]]]:
    """
    便捷函数：编码文本为嵌入向量。

    自动管理全局嵌入器生命周期。

    Args:
        texts: 待编码的文本列表
        model_name: 模型名称或路径
        cache_dir: 缓存目录
        batch_size: 批处理大小
        **kwargs: 传递给 BgeM3Embedding 的其他参数

    Returns:
        嵌入向量列表，失败返回 None
    """
    embedder = get_embedder(
        model_name=model_name,
        cache_dir=cache_dir,
        batch_size=batch_size,
        **kwargs,
    )
    return embedder.encode(texts, batch_size=batch_size)


# ---------------------------------------------------------------------------
# 内置验证 / 快速测试
# ---------------------------------------------------------------------------


def _verify() -> None:
    """快速验证服务文件语法和导入正确性"""
    import sys

    print("=" * 60)
    print("[验证] BGE-M3 嵌入服务封装")
    print("=" * 60)

    # 1. 验证 BgeM3Embedding 类
    print("\n1. 验证 BgeM3Embedding 类...")
    embedder = BgeM3Embedding(force_fallback=True)
    assert embedder is not None
    assert not embedder.is_loaded  # 尚未加载
    print("   ✓ BgeM3Embedding 类创建成功")

    # 2. 验证加载
    print("\n2. 验证模型加载（降级模式）...")
    result = embedder.load_model()
    assert result is False  # 降级模式
    assert embedder.is_fallback
    print("   ✓ 降级模式加载成功")

    # 3. 验证编码
    print("\n3. 验证编码功能...")
    vectors = embedder.encode(["你好", "hello world"], batch_size=2)
    assert vectors is not None
    assert len(vectors) == 2
    assert len(vectors[0]) == 768
    print(f"   ✓ 编码成功: {len(vectors)} 条, 维度 {len(vectors[0])}")

    # 4. 验证空输入
    print("\n4. 验证空输入...")
    empty = embedder.encode([])
    assert empty == []
    print("   ✓ 空输入处理正确")

    # 5. 验证确定性
    print("\n5. 验证降级模式的确定性...")
    vecs_a = embedder.encode(["链客宝测试"], batch_size=1)
    embedder2 = BgeM3Embedding(force_fallback=True)
    embedder2.load_model()
    vecs_b = embedder2.encode(["链客宝测试"], batch_size=1)
    assert vecs_a is not None and vecs_b is not None
    assert vecs_a[0] == vecs_b[0]
    print("   ✓ 降级嵌入确定性保持")

    # 6. 验证单例
    print("\n6. 验证全局单例...")
    global _global_embedder
    _global_embedder = None  # 重置单例以便测试
    embedder_a = get_embedder(force_fallback=True)
    embedder_b = get_embedder(force_fallback=True)
    assert embedder_a is embedder_b
    print("   ✓ 全局单例工作正常")

    # 7. 便捷函数
    print("\n7. 验证便捷函数...")
    _global_embedder = None  # 重置
    vecs = encode_texts(["测试"], force_fallback=True)
    assert vecs is not None
    assert len(vecs) == 1
    assert len(vecs[0]) == 768
    print(f"   ✓ encode_texts 工作正常")

    print("\n" + "=" * 60)
    print("✓ 所有验证通过!")
    print("=" * 60)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if "--verify" in sys.argv:
        _verify()
    elif "--serve" in sys.argv:
        # 启动 FastAPI 服务
        import uvicorn
        app = get_embedding_app(force_fallback="--fallback" in sys.argv)
        port = int(os.getenv("EMBED_PORT", "8002"))
        print(f"[Embedding Service] 启动 → http://0.0.0.0:{port}")
        print(f"[Embedding Service] POST /embed — 文本编码")
        print(f"[Embedding Service] GET  /embed/health — 健康检查")
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        _verify()
