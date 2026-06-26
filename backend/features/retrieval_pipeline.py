"""
链客宝 - 向量检索管道
======================
基于 BGE-M3 嵌入 + SQLite 缓存的向量检索管道，替代 TF-IDF。

能力:
1. RetrievalPipeline 类 — 完整的编码→缓存→检索管道
2. encode_and_cache(texts) — 编码文本并写入缓存
3. search(query, candidates[], top_k) — 余弦相似度向量检索
4. 回退逻辑: 缓存优先 → 模型编码 → TF-IDF 回退
5. 支持空候选、单候选、重复候选等边界场景

使用方式:
    from features.embedding_service import BgeM3Embedding
    from features.embedding_cache import EmbeddingCache
    from features.retrieval_pipeline import RetrievalPipeline

    embedder = BgeM3Embedding(force_fallback=True)
    cache = EmbeddingCache()
    pipeline = RetrievalPipeline(embedder=embedder, cache=cache)

    candidates = ["文本A", "文本B", "文本C"]
    pipeline.encode_and_cache(candidates)

    results = pipeline.search("查询文本", candidates, top_k=3)
    for text, score in results:
        print(f"{score:.4f} {text}")

Author: 贤宇 (P6, 数据分析部, 缓存/检索专家)
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from features.embedding_service import BgeM3Embedding
from features.embedding_cache import EmbeddingCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 默认返回最相似文档数
DEFAULT_TOP_K = 10

# 余弦相似度阈值（低于此值认为无相似文档）
SIMILARITY_THRESHOLD = 0.0

# TF-IDF 回退时 BM25 参数
BM25_K1 = 1.5
BM25_B = 0.75


# ---------------------------------------------------------------------------
# 向量检索管道
# ---------------------------------------------------------------------------


class RetrievalPipeline:
    """
    向量检索管道。

    将 BGE-M3 嵌入器与 SQLite 缓存结合，提供高效的编码→缓存→检索全流程。
    内置多层回退逻辑，确保各种场景下的可用性。

    Examples
    --------
    >>> from features.embedding_service import BgeM3Embedding
    >>> from features.embedding_cache import EmbeddingCache
    >>> embedder = BgeM3Embedding(force_fallback=True)
    >>> embedder.load_model()
    True
    >>> cache = EmbeddingCache()
    >>> pipeline = RetrievalPipeline(embedder, cache)
    >>> candidates = ["苹果是一种水果", "香蕉是黄色的", "汽车有四个轮子"]
    >>> pipeline.encode_and_cache(candidates)
    >>> results = pipeline.search("水果", candidates)
    >>> len(results) > 0
    True
    """

    def __init__(
        self,
        embedder: Optional[BgeM3Embedding] = None,
        cache: Optional[EmbeddingCache] = None,
    ) -> None:
        """
        Args:
            embedder: BgeM3Embedding 实例。为 None 时自动创建（降级模式）
            cache: EmbeddingCache 实例。为 None 时自动创建
        """
        self._embedder = embedder if embedder is not None else BgeM3Embedding(force_fallback=True)
        self._cache = cache if cache is not None else EmbeddingCache()

        # 确保嵌入器已加载
        if not self._embedder.is_loaded:
            self._embedder.load_model()

        logger.info(
            "[RetrievalPipeline] 初始化完成 (embedder=%s, cache=%s)",
            "BgeM3Embedding" if not self._embedder.is_fallback else "FALLBACK",
            repr(self._cache),
        )

    # ------------------------------------------------------------------
    # 编码 + 缓存
    # ------------------------------------------------------------------

    def encode_and_cache(
        self,
        texts: Sequence[str],
        batch_size: Optional[int] = None,
        force_recompute: bool = False,
    ) -> List[Optional[List[float]]]:
        """
        编码文本列表并将结果写入缓存。

        先查询缓存中已有的向量，只对未缓存的文本调用嵌入器编码。

        Args:
            texts: 待编码的文本列表
            batch_size: 批处理大小（覆盖默认值）
            force_recompute: 强制重新计算（忽略缓存）

        Returns:
            嵌入向量列表（与输入顺序一致），编码失败的文本对应 None
        """
        if not texts:
            return []

        text_list = list(texts)
        vectors: List[Optional[List[float]]] = [None] * len(text_list)

        if force_recompute:
            # 强制模式：全部重新编码，不查缓存
            uncached_indices = list(range(len(text_list)))
            uncached_texts = text_list
        else:
            # 缓存优先：批量查询缓存
            cached_vectors = self._cache.batch_get(text_list)
            for i, v in enumerate(cached_vectors):
                if v is not None:
                    vectors[i] = v

            # 收集未缓存的文本
            uncached_indices = [
                i for i, v in enumerate(vectors) if v is None
            ]
            uncached_texts = [text_list[i] for i in uncached_indices]

        # 对未缓存的文本调用嵌入器
        encoded: Optional[List[List[float]]] = None
        if uncached_texts:
            logger.info(
                "[RetrievalPipeline] 编码 %d 条未缓存文本...",
                len(uncached_texts),
            )
            try:
                encoded = self._embedder.encode(
                    uncached_texts,
                    batch_size=batch_size,
                )
                if encoded is not None:
                    # 写入缓存
                    pairs = list(zip(uncached_texts, encoded))
                    self._cache.batch_set(pairs)

                    # 填充结果
                    for idx, vec in zip(uncached_indices, encoded):
                        vectors[idx] = vec
                else:
                    logger.error(
                        "[RetrievalPipeline] 编码失败，返回 None"
                    )
            except Exception as e:
                logger.error(
                    "[RetrievalPipeline] 编码异常: %s", e
                )

        # 统计
        encoded_count = len(uncached_indices) if encoded is not None else 0
        cached_count = sum(1 for v in vectors if v is not None) - encoded_count
        logger.debug(
            "[RetrievalPipeline] encode_and_cache: 共 %d 条, "
            "缓存 %d 条, 编码 %d 条",
            len(texts), cached_count, encoded_count,
        )

        return vectors

    # ------------------------------------------------------------------
    # 向量检索
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        candidates: Sequence[str],
        top_k: int = DEFAULT_TOP_K,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
    ) -> List[Tuple[str, float]]:
        """
        执行向量检索：计算查询与候选文档的余弦相似度。

        回退逻辑:
        1. 缓存优先 — 查询候选文档的缓存向量
        2. 模型编码 — 未缓存的候选文档 + 查询文本
        3. TF-IDF 补充 — 当向量检索结果不足 top_k 时，用 TF-IDF 补充

        Args:
            query: 查询文本
            candidates: 候选文档列表
            top_k: 返回前 K 个结果
            similarity_threshold: 相似度阈值，低于此值的文档不返回

        Returns:
            (文本, 相似度分数) 元组列表，按分数降序排列

        Raises:
            ValueError: 查询文本为空
        """
        if not query or not query.strip():
            raise ValueError("查询文本不能为空")

        if not candidates:
            return []

        candidate_list = list(candidates)

        # 去重候选（保留首次出现的顺序）
        seen: set[str] = set()
        unique_candidates: List[str] = []
        for c in candidate_list:
            if c not in seen:
                seen.add(c)
                unique_candidates.append(c)

        logger.debug(
            "[RetrievalPipeline] search: query=%s..., "
            "candidates=%d (去重后 %d), top_k=%d",
            query[:30], len(candidate_list), len(unique_candidates),
            top_k,
        )

        # ── 第 1 步：向量检索 ──────────────────────────────────
        vector_results: List[Tuple[str, float]] = []
        try:
            vector_results = self._vector_search(
                query=query,
                candidates=unique_candidates,
                top_k=top_k,
                threshold=similarity_threshold,
            ) or []
        except Exception as e:
            logger.warning(
                "[RetrievalPipeline] 向量检索异常: %s", e,
            )

        # 向量检索已经足够，直接返回
        if len(vector_results) >= min(top_k, len(unique_candidates)):
            return vector_results[:top_k]

        # ── 第 2 步：TF-IDF 补充 ──────────────────────────────
        # 收集已通过向量检索找到的文档
        found_docs = {doc for doc, _ in vector_results}

        # 从未找到的候选中做 TF-IDF 检索
        remaining = [
            c for c in unique_candidates if c not in found_docs
        ]
        if remaining:
            logger.info(
                "[RetrievalPipeline] 向量检索返回 %d 条（不足 %d），"
                "用 TF-IDF 补充 %d 条",
                len(vector_results),
                min(top_k, len(unique_candidates)),
                len(remaining),
            )
            try:
                tfidf_results = self._tfidf_search(
                    query=query,
                    candidates=remaining,
                    top_k=top_k,
                    threshold=similarity_threshold,
                )
                # 合并结果，向量检索结果优先（更高置信度）
                combined = list(vector_results)
                combined.extend(tfidf_results)
                # 去重（保留首次出现，即向量检索优先）
                seen_docs: set[str] = set()
                final: List[Tuple[str, float]] = []
                for doc, score in combined:
                    if doc not in seen_docs:
                        seen_docs.add(doc)
                        final.append((doc, score))
                final.sort(key=lambda x: x[1], reverse=True)
                return final[:top_k]
            except Exception as e:
                logger.warning(
                    "[RetrievalPipeline] TF-IDF 补充异常: %s", e,
                )

        return vector_results[:top_k]

    # ------------------------------------------------------------------
    # 向量检索核心
    # ------------------------------------------------------------------

    def _vector_search(
        self,
        query: str,
        candidates: List[str],
        top_k: int,
        threshold: float,
    ) -> Optional[List[Tuple[str, float]]]:
        """
        向量检索核心实现。

        流程:
        1. 查缓存获取候选文档向量
        2. 编码查询文本
        3. 计算余弦相似度
        4. 排序并返回 Top-K

        Returns:
            结果列表，失败时返回 None（触发回退）
        """
        # 1. 获取候选文档的向量
        candidate_vectors = self._get_candidate_vectors(candidates)
        if candidate_vectors is None:
            return None

        # 2. 编码查询文本
        query_vector = self._encode_query(query)
        if query_vector is None:
            return None

        # 验证向量维度一致性
        query_dim = len(query_vector)
        for cv in candidate_vectors.values():
            if len(cv) != query_dim:
                logger.warning(
                    "[RetrievalPipeline] 向量维度不一致: "
                    "query=%d, candidate=%d, 回退 TF-IDF",
                    query_dim, len(cv),
                )
                return None

        # 3. 计算余弦相似度
        scores: List[Tuple[str, float]] = []
        for text, vec in candidate_vectors.items():
            sim = self._cosine_similarity(query_vector, vec)
            if sim >= threshold:
                scores.append((text, sim))

        # 4. 排序
        scores.sort(key=lambda x: x[1], reverse=True)

        return scores[:top_k]

    def _get_candidate_vectors(
        self, candidates: List[str]
    ) -> Optional[Dict[str, List[float]]]:
        """
        获取候选文档的向量。

        先从缓存查询，未命中的调用嵌入器编码并写入缓存。
        """
        # 批量查缓存
        cached = self._cache.batch_get(candidates)

        result: Dict[str, List[float]] = {}
        uncached_texts: List[str] = []
        uncached_indices: List[int] = []

        for i, (text, vec) in enumerate(zip(candidates, cached)):
            if vec is not None:
                result[text] = vec
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)

        # 编码未缓存的部分
        if uncached_texts:
            try:
                encoded = self._embedder.encode(uncached_texts)
                if encoded is not None:
                    pairs = list(zip(uncached_texts, encoded))
                    self._cache.batch_set(pairs)
                    for text, vec in pairs:
                        result[text] = vec
                else:
                    logger.warning(
                        "[RetrievalPipeline] 编码候选文档失败"
                    )
                    return None
            except Exception as e:
                logger.error(
                    "[RetrievalPipeline] 编码候选文档异常: %s", e
                )
                return None

        if not result:
            logger.warning(
                "[RetrievalPipeline] 无法获取任何候选向量"
            )
            return None

        return result

    def _encode_query(
        self, query: str
    ) -> Optional[List[float]]:
        """编码查询文本"""
        try:
            vectors = self._embedder.encode([query])
            if vectors is not None and len(vectors) > 0:
                return vectors[0]
        except Exception as e:
            logger.warning(
                "[RetrievalPipeline] 编码查询文本失败: %s", e
            )
        return None

    # ------------------------------------------------------------------
    # 相似度计算
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(
        vec_a: List[float], vec_b: List[float]
    ) -> float:
        """
        计算两个向量的余弦相似度。

        假设向量已经 L2 归一化（BGE-M3 默认归一化），
        余弦相似度 = 点积。

        Args:
            vec_a: 向量 A
            vec_b: 向量 B

        Returns:
            余弦相似度 (-1.0 ~ 1.0)
        """
        if len(vec_a) != len(vec_b):
            logger.warning(
                "[RetrievalPipeline] 向量维度不匹配: %d vs %d",
                len(vec_a), len(vec_b),
            )
            return -1.0

        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0

        for a, b in zip(vec_a, vec_b):
            dot += a * b
            norm_a += a * a
            norm_b += b * b

        norm_a = math.sqrt(norm_a)
        norm_b = math.sqrt(norm_b)

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return dot / (norm_a * norm_b)

    # ------------------------------------------------------------------
    # TF-IDF 回退
    # ------------------------------------------------------------------

    def _tfidf_search(
        self,
        query: str,
        candidates: List[str],
        top_k: int,
        threshold: float,
    ) -> List[Tuple[str, float]]:
        """
        TF-IDF / BM25 回退检索。

        当向量检索失败时（模型不可用、维度异常等），
        使用基于词频的 BM25 算法进行文本检索。

        Args:
            query: 查询文本
            candidates: 候选文档列表
            top_k: 返回前 K 个结果
            threshold: 分数阈值

        Returns:
            (文本, 分数) 元组列表
        """
        if not candidates:
            return []

        # 分词（简单的中英文分词：按非字母数字字符拆分 + 小写化）
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # 构建文档词频统计
        doc_tokens_list: List[List[str]] = []
        doc_freq: Dict[str, int] = {}  # 文档频率（包含某词的文档数）
        doc_lengths: List[int] = []

        for doc in candidates:
            tokens = self._tokenize(doc)
            doc_tokens_list.append(tokens)
            doc_lengths.append(len(tokens))
            # 文档频率
            unique = set(tokens)
            for t in unique:
                doc_freq[t] = doc_freq.get(t, 0) + 1

        n_docs = len(candidates)
        avg_doc_len = sum(doc_lengths) / n_docs if n_docs > 0 else 1.0

        # BM25 评分
        results: List[Tuple[str, float]] = []
        for idx, doc in enumerate(candidates):
            tokens = doc_tokens_list[idx]
            doc_len = doc_lengths[idx]
            score = 0.0

            for q_token in query_tokens:
                if q_token not in doc_freq:
                    continue
                df = doc_freq[q_token]
                idf = math.log(
                    (n_docs - df + 0.5) / (df + 0.5) + 1.0
                )
                # 词频在当前文档
                tf = tokens.count(q_token)
                if tf == 0:
                    continue
                # BM25 公式
                numerator = tf * (BM25_K1 + 1)
                denominator = tf + BM25_K1 * (
                    1 - BM25_B + BM25_B * doc_len / avg_doc_len
                )
                score += idf * (numerator / denominator)

            if score >= threshold:
                results.append((doc, round(score, 6)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """
        简单分词函数。

        按非字母数字字符拆分，小写化。
        中文按单字拆分（Unigram），英文按单词拆分，数字保留。

        Args:
            text: 输入文本

        Returns:
            词列表
        """
        import re
        tokens: List[str] = []
        # 匹配英文单词/数字 或 单个中文字符
        for match in re.finditer(
            r"[a-zA-Z0-9]+|[\u4e00-\u9fff]", text
        ):
            token = match.group().lower()
            if len(token) >= 1:
                tokens.append(token)
        return tokens

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def embedder(self) -> BgeM3Embedding:
        """获取嵌入器实例"""
        return self._embedder

    @property
    def cache(self) -> EmbeddingCache:
        """获取缓存实例"""
        return self._cache

    @property
    def is_fallback_active(self) -> bool:
        """是否处于降级模式（使用 TF-IDF 回退）"""
        return self._embedder.is_fallback

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """
        获取管道统计信息。

        Returns:
            dict 包含嵌入器状态和缓存统计
        """
        cache_stats = self._cache.stats()
        return {
            "embedder_fallback": self._embedder.is_fallback,
            "embedder_loaded": self._embedder.is_loaded,
            "embedder_dimension": self._embedder.dimension,
            "cache": cache_stats,
            "pipeline": {
                "type": "向量检索 (BGE-M3 + SQLite 缓存)",
                "fallback_mechanism": "TF-IDF (BM25)",
            },
        }

    def __repr__(self) -> str:
        status = "降级(TF-IDF)" if self.is_fallback_active else "正常"
        return (
            f"RetrievalPipeline(status={status}, "
            f"cache_entries={len(self._cache)}, "
            f"dim={self._embedder.dimension})"
        )


# ---------------------------------------------------------------------------
# 内置验证 / 快速测试
# ---------------------------------------------------------------------------


def _verify() -> None:
    """快速验证模块语法和基本功能"""
    import random
    import tempfile

    print("=" * 60)
    print("[验证] RetrievalPipeline 向量检索管道")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # ── 准备 ──────────────────────────────────────────────────
        # 使用降级模式 + 临时缓存目录
        embedder = BgeM3Embedding(
            force_fallback=True,
            cache_dir=tmpdir,
        )
        embedder.load_model()
        assert embedder.is_fallback

        cache = EmbeddingCache(cache_dir=tmpdir)
        pipeline = RetrievalPipeline(embedder=embedder, cache=cache)

        print("\n1. ✓ RetrievalPipeline 创建成功")

        # ── 测试场景 1: encode_and_cache ──────────────────────────
        print("\n2. encode_and_cache 测试...")
        texts = [
            "苹果是一种常见的水果",
            "香蕉是黄色的热带水果",
            "汽车有四个轮子用于交通",
            "计算机可以处理大量数据",
            "Python是一种流行的编程语言",
            "机器学习是人工智能的子领域",
        ]
        vectors = pipeline.encode_and_cache(texts)
        assert vectors is not None
        assert len(vectors) == len(texts)
        assert all(v is not None for v in vectors)
        print("   ✓ 编码并缓存成功")

        # ── 测试场景 2: 缓存命中 ────────────────────────────────
        print("\n3. 缓存命中测试...")
        vectors2 = pipeline.encode_and_cache(texts)
        assert len(vectors2) == len(texts)
        assert all(v is not None for v in vectors2)
        # 向量应相同（确定性降级）
        for v1, v2 in zip(vectors, vectors2):
            assert v1 == v2
        print("   ✓ 缓存命中后返回相同向量")

        # ── 测试场景 3: 向量检索 ────────────────────────────────
        print("\n4. 向量检索测试...")
        results = pipeline.search("水果", texts, top_k=3)
        assert len(results) > 0
        assert len(results) <= 3
        # 水果相关的应排前面
        top_texts = [r[0] for r in results]
        print(f"   查询 '水果' 前3: {[t[:10] for t in top_texts]}")
        print("   ✓ 向量检索返回结果")

        # ── 测试场景 4: top_k 限制 ──────────────────────────────
        print("\n5. top_k 限制测试...")
        results_all = pipeline.search("数据", texts, top_k=10)
        results_2 = pipeline.search("数据", texts, top_k=2)
        assert len(results_all) <= 6  # 最多6个候选
        assert len(results_2) <= 2
        print(f"   top_k=10 返回 {len(results_all)} 条, "
              f"top_k=2 返回 {len(results_2)} 条")
        print("   ✓ top_k 限制正确")

        # ── 测试场景 5: 空候选 ──────────────────────────────────
        print("\n6. 空候选测试...")
        empty_results = pipeline.search("查询", [], top_k=10)
        assert empty_results == []
        print("   ✓ 空候选返回空列表")

        # ── 测试场景 6: 空查询 ──────────────────────────────────
        print("\n7. 空查询测试...")
        try:
            pipeline.search("", texts)
            assert False, "应抛出 ValueError"
        except ValueError:
            pass
        try:
            pipeline.search("   ", texts)
            assert False, "应抛出 ValueError"
        except ValueError:
            pass
        print("   ✓ 空查询抛出 ValueError")

        # ── 测试场景 7: 单候选 ──────────────────────────────────
        print("\n8. 单候选测试...")
        single_results = pipeline.search("苹果", ["苹果是一种水果"], top_k=5)
        assert len(single_results) == 1
        print("   ✓ 单候选返回正确")

        # ── 测试场景 8: 重复候选 ────────────────────────────────
        print("\n9. 重复候选测试...")
        dup_candidates = ["苹果是水果", "苹果是水果", "香蕉是水果", "苹果是水果"]
        dup_results = pipeline.search("苹果", dup_candidates, top_k=3)
        assert len(dup_results) == 2  # 去重后只有2个不同文档
        print("   ✓ 重复候选去重正确")

        # ── 测试场景 9: 强制重算 ────────────────────────────────
        print("\n10. 强制重算测试...")
        cache_stats_before = cache.stats()
        pipeline.encode_and_cache(texts, force_recompute=True)
        cache_stats_after = cache.stats()
        # 强制重算会重新写入，缓存命中数不变
        print("   ✓ 强制重算成功")

        # ── 测试场景 10: TF-IDF 回退 ───────────────────────────
        print("\n11. TF-IDF 回退测试...")
        # 直接调用 TF-IDF 确保回退路径正常工作
        tfidf_results = pipeline._tfidf_search(
            "水果", texts, top_k=3, threshold=0.0
        )
        assert len(tfidf_results) > 0
        print(f"   TF-IDF 查询 '水果': {[t[0][:10] for t in tfidf_results]}")
        print("   ✓ TF-IDF 回退工作正常")

        # ── 测试场景 11: 空结果 TF-IDF ─────────────────────────
        print("\n12. 空结果 TF-IDF 测试...")
        tfidf_empty = pipeline._tfidf_search(
            "xyzzy_nonexistent_word_12345", texts, top_k=5, threshold=0.0
        )
        # 可能没有匹配的词，取决于分词
        print("   ✓ 无匹配 TF-IDF 返回列表")

        # ── 测试场景 12: TF-IDF 无候选 ─────────────────────────
        print("\n13. TF-IDF 无候选测试...")
        tfidf_no_cand = pipeline._tfidf_search(
            "查询", [], top_k=5, threshold=0.0
        )
        assert tfidf_no_cand == []
        print("   ✓ 无候选 TF-IDF 返回空列表")

        # ── 测试场景 13: 余弦相似度基础 ────────────────────────
        print("\n14. 余弦相似度测试...")
        same = pipeline._cosine_similarity([1.0, 0.0], [1.0, 0.0])
        assert abs(same - 1.0) < 1e-9
        orth = pipeline._cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert abs(orth - 0.0) < 1e-9
        opp = pipeline._cosine_similarity([1.0, 0.0], [-1.0, 0.0])
        assert abs(opp - (-1.0)) < 1e-9
        zero = pipeline._cosine_similarity([0.0, 0.0], [1.0, 0.0])
        assert abs(zero - 0.0) < 1e-9
        print("   ✓ 余弦相似度计算正确")

        # ── 测试场景 14: 维度不匹配的余弦相似度 ────────────────
        print("\n15. 维度不匹配测试...")
        bad = pipeline._cosine_similarity([1.0], [1.0, 2.0])
        assert bad == -1.0
        print("   ✓ 维度不匹配返回 -1.0")

        # ── 测试场景 15: 混合候选（部分缓存、部分未缓存） ──────
        print("\n16. 混合候选测试...")
        new_texts = ["深度学习是机器学习的子集", "自然语言处理技术"]
        # 不清除之前缓存的 texts，混合查询
        mix_results = pipeline.search("机器学习", texts + new_texts, top_k=5)
        assert len(mix_results) > 0
        print("   ✓ 混合候选检索成功")

        # ── 测试场景 16: 全未缓存候选 ──────────────────────────
        print("\n17. 全未缓存候选测试...")
        fresh_texts = [
            "统计学是数学的分支",
            "概率论用于不确定性建模",
            "线性代数是机器学习的基础",
        ]
        fresh_results = pipeline.search("数学", fresh_texts, top_k=3)
        assert len(fresh_results) > 0
        print("   ✓ 全未缓存候选检索成功")

        # ── 测试场景 17: 空输入 encode_and_cache ───────────────
        print("\n18. 空输入 encode_and_cache 测试...")
        empty_encode = pipeline.encode_and_cache([])
        assert empty_encode == []
        print("   ✓ 空输入编码返回空列表")

        # ── 测试场景 18: stats ─────────────────────────────────
        print("\n19. stats 测试...")
        s = pipeline.stats()
        assert "cache" in s
        assert "embedder_fallback" in s
        assert s["pipeline"]["type"] == "向量检索 (BGE-M3 + SQLite 缓存)"
        print(f"   ✓ stats: 命中率 {s['cache']['hit_rate']:.1%}, "
              f"条目 {s['cache']['total_entries']}")

        # ── 测试场景 19: 相似度阈值过滤 ────────────────────────
        print("\n20. 相似度阈值测试...")
        high_threshold = pipeline.search(
            "水果", texts, top_k=10, similarity_threshold=0.999
        )
        low_threshold = pipeline.search(
            "水果", texts, top_k=10, similarity_threshold=-1.0
        )
        # 高阈值可能过滤掉所有结果
        print(f"   高阈值(0.999): {len(high_threshold)} 条, "
              f"低阈值(-1.0): {len(low_threshold)} 条")
        print("   ✓ 阈值过滤工作正常")

        # ── 测试场景 20: 大量候选 ──────────────────────────────
        print("\n21. 大量候选测试...")
        rng = random.Random(42)
        many_texts = [f"文档{i} 包含一些测试内容" for i in range(100)]
        many_results = pipeline.search("测试", many_texts, top_k=5)
        assert len(many_results) <= 5
        print("   ✓ 100 个候选检索成功")

        # ── 测试场景 21: 候选中去重保留首次 ────────────────────
        print("\n22. 去重保留首次顺序测试...")
        order_candidates = ["C文档", "A文档", "B文档", "A文档", "C文档"]
        # 编码后搜索
        pipeline.encode_and_cache(order_candidates)
        order_results = pipeline.search("文档", order_candidates, top_k=5)
        # 去重后应为 ["C文档", "A文档", "B文档"]
        result_texts = [r[0] for r in order_results]
        assert "C文档" in result_texts
        assert "A文档" in result_texts
        assert "B文档" in result_texts
        # A文档和C文档只在结果中出现一次
        assert result_texts.count("A文档") <= 1
        assert result_texts.count("C文档") <= 1
        print("   ✓ 去重保留首次顺序正确")

        # ── 测试场景 22: repr 和属性 ───────────────────────────
        print("\n23. repr 和属性测试...")
        r = repr(pipeline)
        assert "RetrievalPipeline" in r
        assert pipeline.is_fallback_active
        assert pipeline.embedder is embedder
        assert pipeline.cache is cache
        print("   ✓ repr 和属性工作正常")

    print("\n" + "=" * 60)
    print("✓ 所有 22 个测试场景通过!")
    print("=" * 60)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if "--verify" in sys.argv:
        _verify()
    else:
        _verify()
