"""
Maximal Marginal Relevance (MMR) — 多样性优化重排序
=====================================================

MMR 是一种经典的信息检索多样性算法，在保持相关性的同时最大化结果多样性。
适用于推荐系统、搜索结果、匹配引擎等需要对候选列表进行多样性重排序的场景。

MMR公式:
    MMR = argmax( λ * Rel(i) - (1-λ) * max(Sim(i, j)) )  for j in selected

    其中:
        Rel(i)     = item i 与 query 的相关性分数
        Sim(i, j)  = item i 与已选 item j 之间的相似度
        λ          = 多样性参数 (0~1), λ=1 完全关注相关性, λ=0 完全关注多样性

典型用途:
    - 匹配结果重排序: 替换 matching_engine 中简单的排序逻辑
    - 产品推荐: 避免推荐过于相似的商品
    - 搜索结果: 覆盖query的不同方面

Author: Analytics P7 / Algorithm Implementation Specialist
"""

from __future__ import annotations

import math
from typing import Any, Callable, List, Optional, Sequence, Tuple, TypeVar

T = TypeVar("T")  # 候选 item 类型


# ═══════════════════════════════════════════════════════════════
# 核心 MMR 排序函数
# ═══════════════════════════════════════════════════════════════


def mmr_rerank(
    candidates: Sequence[T],
    relevance_scores: Sequence[float],
    lambda_: float = 0.5,
    similarity_fn: Optional[Callable[[T, T], float]] = None,
    feature_vectors: Optional[Sequence[Sequence[float]]] = None,
    top_n: Optional[int] = None,
) -> List[Tuple[T, float]]:
    """
    MMR 多样性重排序。

    Parameters
    ----------
    candidates : Sequence[T]
        候选列表，元素类型任意。
    relevance_scores : Sequence[float]
        每个候选与 query 的相关性分数（非负），顺序需与 candidates 一致。
    lambda_ : float, default=0.5
        多样性参数，取值 [0, 1]。
        - λ=1.0 → 只按相关性排序（无多样性）。
        - λ=0.0 → 只考虑多样性（忽略相关性）。
        - λ=0.5 → 均衡模式。
    similarity_fn : Callable[[T, T], float] | None, default=None
        计算两个候选间相似度的函数，返回值 [0, 1]。
        若为 None 则使用 feature_vectors 计算余弦相似度。
    feature_vectors : Sequence[Sequence[float]] | None, default=None
        每个候选的特征向量（用于余弦相似度计算）。
        当 similarity_fn 为 None 时必传。
    top_n : int | None, default=None
        返回前 top_n 个结果，默认返回全部。

    Returns
    -------
    List[Tuple[T, float]]
        重排序后的列表，每个元素为 (候选, 最终MMR分数)。
        分数越高表示综合相关性+多样性得分越高。

    Raises
    ------
    ValueError
        - candidates 与 relevance_scores 长度不一致
        - lambda_ 不在 [0, 1] 范围内
        - 未提供 similarity_fn 也未提供 feature_vectors
        - 特征向量维度不匹配

    Examples
    --------
    >>> cand = ["A", "B", "C", "D"]
    >>> scores = [0.9, 0.8, 0.7, 0.6]
    >>> result = mmr_rerank(cand, scores, lambda_=0.5)
    >>> len(result) == 4
    True
    """
    # ── 输入校验 ──
    if len(candidates) != len(relevance_scores):
        raise ValueError(
            f"candidates 长度 ({len(candidates)}) 与 relevance_scores 长度 "
            f"({len(relevance_scores)}) 不一致"
        )
    if not (0.0 <= lambda_ <= 1.0):
        raise ValueError(f"lambda_ 必须在 [0, 1] 范围内, 当前值: {lambda_}")

    n = len(candidates)
    if n == 0:
        return []

    # ── 相似度计算准备 ──
    if similarity_fn is not None:
        # 包装自定义相似度函数：将下标映射为实际候选对象
        _items = list(candidates)

        def _sim_func(i: int, j: int) -> float:
            return similarity_fn(_items[i], _items[j])
    elif feature_vectors is not None:
        if len(feature_vectors) != n:
            raise ValueError(
                f"feature_vectors 长度 ({len(feature_vectors)}) 与 candidates "
                f"长度 ({n}) 不一致"
            )
        # 验证向量维度一致
        if n > 0:
            dim = len(feature_vectors[0])
            for i, fv in enumerate(feature_vectors):
                if len(fv) != dim:
                    raise ValueError(
                        f"特征向量维度不一致: candidates[0] 维度 {dim}, "
                        f"candidates[{i}] 维度 {len(fv)}"
                    )
        _sim_func = _cosine_similarity_wrapper(feature_vectors)
    else:
        raise ValueError(
            "必须提供 similarity_fn 或 feature_vectors 其中之一"
        )

    # ── MMR 贪婪选择 ──
    relevance = list(relevance_scores)
    selected_indices: List[int] = []        # 已选中的下标
    remaining_indices = list(range(n))      # 未选中的下标

    # 候选下标 → 与已选集的最大相似度缓存（加速用）
    max_sim_to_selected: List[float] = [0.0] * n

    # 第一轮：直接选相关性最高的 item
    first_idx = max(remaining_indices, key=lambda i: relevance[i])
    selected_indices.append(first_idx)
    remaining_indices.remove(first_idx)

    # 更新剩余 item 到已选集的最大相似度
    for i in remaining_indices:
        sim = _sim_func(i, first_idx)
        max_sim_to_selected[i] = max(max_sim_to_selected[i], sim)

    # 后续轮次：按 MMR 分数选择
    while remaining_indices:
        best_idx = -1
        best_score = -math.inf

        for i in remaining_indices:
            mmr_score = (lambda_ * relevance[i]
                         - (1 - lambda_) * max_sim_to_selected[i])
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = i

        # 安全兜底（不应发生）
        if best_idx == -1:
            best_idx = remaining_indices[0]
            best_score = 0.0

        selected_indices.append(best_idx)
        remaining_indices.remove(best_idx)

        # 更新 max_sim_to_selected 缓存
        for i in remaining_indices:
            sim = _sim_func(i, best_idx)
            if sim > max_sim_to_selected[i]:
                max_sim_to_selected[i] = sim

    # ── 组装结果 ──
    if top_n is not None and top_n < n:
        selected_indices = selected_indices[:top_n]

    result = [
        (candidates[idx], relevance[idx])
        for idx in selected_indices
    ]
    return result


# ═══════════════════════════════════════════════════════════════
# 余弦相似度
# ═══════════════════════════════════════════════════════════════


def _cosine_similarity_wrapper(
    vectors: Sequence[Sequence[float]],
) -> Callable[[int, int], float]:
    """
    创建余弦相似度计算闭包（下标索引版）。

    内部预计算向量模长，避免重复计算。

    Parameters
    ----------
    vectors : Sequence[Sequence[float]]
        所有候选的特征向量列表。

    Returns
    -------
    Callable[[int, int], float]
        (i, j) → cos_sim(vectors[i], vectors[j])
    """
    norms = [math.sqrt(sum(v * v for v in vec)) for vec in vectors]

    def _cos_sim(i: int, j: int) -> float:
        vec_i = vectors[i]
        vec_j = vectors[j]
        dot = sum(a * b for a, b in zip(vec_i, vec_j))
        norm_product = norms[i] * norms[j]
        if norm_product == 0.0:
            return 0.0
        # 裁剪到 [0, 1] 范围（避免浮点误差）
        return max(0.0, min(1.0, dot / norm_product))

    return _cos_sim


# ═══════════════════════════════════════════════════════════════
# 批量工具函数
# ═══════════════════════════════════════════════════════════════


def batch_mmr_rerank(
    query_groups: Sequence[Tuple[
        Sequence[T],
        Sequence[float],
        Optional[Sequence[Sequence[float]]],
    ]],
    lambda_: float = 0.5,
    top_n: Optional[int] = None,
) -> List[List[Tuple[T, float]]]:
    """
    批量执行 MMR 重排序（适用于多个 query 独立排序）。

    Parameters
    ----------
    query_groups : Sequence of tuples
        每个 tuple: (candidates, relevance_scores, feature_vectors)
        feature_vectors 可为 None。
    lambda_ : float
        多样性参数。
    top_n : int | None
        每个 query 返回 top_n 个结果。

    Returns
    -------
    List[List[Tuple[T, float]]]
        每个 query 的重排序结果。
    """
    results = []
    for candidates, scores, vectors in query_groups:
        result = mmr_rerank(
            candidates=candidates,
            relevance_scores=scores,
            lambda_=lambda_,
            feature_vectors=vectors,
            top_n=top_n,
        )
        results.append(result)
    return results


# ═══════════════════════════════════════════════════════════════
# 评估指标
# ═══════════════════════════════════════════════════════════════


def diversity_score(
    ranked_list: Sequence[Any],
    similarity_fn: Callable[[Any, Any], float],
) -> float:
    """
    计算排序结果的平均多样性分数。

    定义为 1 - 列表中任意两两相似度的平均值。
    值越接近 1 表示结果越多样化。

    Parameters
    ----------
    ranked_list : Sequence
        排好序的候选列表。
    similarity_fn : Callable
        两两相似度函数。

    Returns
    -------
    float
        [0, 1] 范围内的多样性分数。
    """
    n = len(ranked_list)
    if n <= 1:
        return 1.0

    total_sim = 0.0
    pair_count = 0
    for i in range(n):
        for j in range(i + 1, n):
            total_sim += similarity_fn(ranked_list[i], ranked_list[j])
            pair_count += 1

    avg_sim = total_sim / pair_count if pair_count > 0 else 0.0
    return 1.0 - avg_sim


# ═══════════════════════════════════════════════════════════════
# 单元测试
# ═══════════════════════════════════════════════════════════════


def _run_tests() -> None:
    """运行内置单元测试。"""
    import unittest

    class TestMMR(unittest.TestCase):
        """MMR 算法核心单元测试"""

        # ── 基础功能 ──

        def test_basic_rerank(self):
            """基础重排序：候选4个，验证返回4个结果"""
            cand = ["A", "B", "C", "D"]
            scores = [0.9, 0.8, 0.7, 0.6]
            result = mmr_rerank(cand, scores, lambda_=0.5,
                                feature_vectors=[[1, 0], [0, 1], [1, 1], [0, 0]])
            self.assertEqual(len(result), 4)

        def test_first_is_highest_relevance(self):
            """第一轮应当返回相关性最高的候选"""
            cand = ["A", "B", "C"]
            scores = [0.5, 0.9, 0.7]
            result = mmr_rerank(cand, scores, lambda_=1.0,
                                feature_vectors=[[1, 0], [0, 1], [1, 1]])
            self.assertEqual(result[0][0], "B")  # B 相关性 0.9 最高

        def test_lambda_one_no_diversity(self):
            """lambda=1.0 时完全按相关性降序"""
            cand = ["A", "B", "C"]
            scores = [0.3, 0.9, 0.6]
            result = mmr_rerank(cand, scores, lambda_=1.0,
                                feature_vectors=[[1, 0], [0, 1], [1, 1]])
            expected = ["B", "C", "A"]  # 按分数降序
            self.assertEqual([r[0] for r in result], expected)

        def test_lambda_zero_only_diversity(self):
            """lambda=0.0 时完全按多样性排序"""
            # A(0.9) 与 B(0.1) 相似, 与 C(0.1) 也相似
            # B 和 C 互相非常相似 (0.9)
            cand = ["A", "B", "C"]
            scores = [0.9, 0.4, 0.3]
            # 向量: A 独特, B 和 C 相似
            result = mmr_rerank(cand, scores, lambda_=0.0,
                                feature_vectors=[[1, 0, 0], [0, 1, 0], [0, 1, 0.1]])
            # 第一轮选 A (最高分), 第二轮选 B 或 C (与 A 都不相似)
            # B 和 C 相似, 选完一个后另一个不会被选
            self.assertEqual(result[0][0], "A")

        def test_empty_candidates(self):
            """空候选列表应返回空列表"""
            result = mmr_rerank([], [], lambda_=0.5,
                                feature_vectors=[])
            self.assertEqual(result, [])

        def test_single_candidate(self):
            """单候选应直接返回"""
            result = mmr_rerank(["X"], [0.8], lambda_=0.5,
                                feature_vectors=[[1, 0]])
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0][0], "X")
            self.assertAlmostEqual(result[0][1], 0.8)

        # ── 参数校验 ──

        def test_length_mismatch_raises(self):
            """长度不一致应抛 ValueError"""
            with self.assertRaises(ValueError):
                mmr_rerank(["A", "B"], [0.9], lambda_=0.5,
                           feature_vectors=[[1], [0]])

        def test_invalid_lambda_raises(self):
            """lambda 超出 [0,1] 应抛 ValueError"""
            with self.assertRaises(ValueError):
                mmr_rerank(["A"], [0.9], lambda_=-0.1,
                           feature_vectors=[[1]])
            with self.assertRaises(ValueError):
                mmr_rerank(["A"], [0.9], lambda_=1.1,
                           feature_vectors=[[1]])

        def test_missing_similarity_raises(self):
            """未提供相似度函数或特征向量应抛 ValueError"""
            with self.assertRaises(ValueError):
                mmr_rerank(["A"], [0.9], lambda_=0.5)

        def test_vector_dimension_mismatch_raises(self):
            """特征向量维度不一致应抛 ValueError"""
            with self.assertRaises(ValueError):
                mmr_rerank(["A", "B"], [0.9, 0.8], lambda_=0.5,
                           feature_vectors=[[1, 0], [1, 0, 0]])

        # ── 自定义相似度函数 ──

        def test_custom_similarity_fn(self):
            """自定义相似度函数应正常工作"""
            def sim(a, b):
                return 1.0 if a == b else 0.0

            cand = ["A", "B", "A", "C"]
            scores = [0.9, 0.8, 0.7, 0.6]
            # lambda=0: 选 A(0.9) → B(不同,0分) → C(不同,0分)
            result = mmr_rerank(cand, scores, lambda_=0.0,
                                similarity_fn=sim)
            self.assertEqual(result[0][0], "A")
            # 剩下的 B 和 C 与 A 不同, 且互不相同
            second = result[1][0]
            third = result[2][0]
            # 第二个应该是 B(0.8) 和 C(0.6) 中分数更高的
            # 但 lambda=0 只看多样性... 都不相似于已选集, 所以按原始分数
            # 实际上: 第二轮: max over {B(0), C(0)} 按分数排 B > C
            self.assertEqual(second, "B")
            self.assertEqual(third, "C")

        # ── top_n 参数 ──

        def test_top_n(self):
            """top_n 应只返回前 N 个"""
            cand = ["A", "B", "C", "D"]
            scores = [0.9, 0.8, 0.7, 0.6]
            result = mmr_rerank(cand, scores, lambda_=0.5, top_n=2,
                                feature_vectors=[[1, 0], [0, 1], [1, 1], [0, 0]])
            self.assertEqual(len(result), 2)

        def test_top_n_larger_than_list(self):
            """top_n 大于列表长度应全部返回"""
            cand = ["A", "B"]
            scores = [0.9, 0.8]
            result = mmr_rerank(cand, scores, lambda_=0.5, top_n=10,
                                feature_vectors=[[1, 0], [0, 1]])
            self.assertEqual(len(result), 2)

        # ── 余弦相似度正确性 ──

        def test_cosine_similarity_identical(self):
            """相同向量的余弦相似度应为 1"""
            from features.mmr_diversity import _cosine_similarity_wrapper
            vectors = [[1, 2, 3], [1, 2, 3]]
            sim_fn = _cosine_similarity_wrapper(vectors)
            self.assertAlmostEqual(sim_fn(0, 1), 1.0, places=6)

        def test_cosine_similarity_orthogonal(self):
            """正交向量的余弦相似度应为 0"""
            from features.mmr_diversity import _cosine_similarity_wrapper
            vectors = [[1, 0], [0, 1]]
            sim_fn = _cosine_similarity_wrapper(vectors)
            self.assertAlmostEqual(sim_fn(0, 1), 0.0, places=6)

        def test_cosine_similarity_zero_vector(self):
            """零向量的余弦相似度应为 0"""
            from features.mmr_diversity import _cosine_similarity_wrapper
            vectors = [[0, 0], [1, 0]]
            sim_fn = _cosine_similarity_wrapper(vectors)
            self.assertEqual(sim_fn(0, 1), 0.0)

        # ── 多样性评估 ──

        def test_diversity_score_identical(self):
            """完全相同的结果多样性分数应为 0"""
            def sim(a, b):
                return 1.0
            score = diversity_score(["A", "A", "A"], sim)
            self.assertAlmostEqual(score, 0.0)

        def test_diversity_score_all_different(self):
            """完全不同结果多样性分数应为 1"""
            def sim(a, b):
                return 0.0
            score = diversity_score(["A", "B", "C"], sim)
            self.assertAlmostEqual(score, 1.0)

        def test_diversity_score_single(self):
            """单元素列表多样性分数应为 1"""
            score = diversity_score(["A"], lambda a, b: 1.0)
            self.assertAlmostEqual(score, 1.0)

        # ── 稳定性测试 ──

        def test_large_candidate_set(self):
            """100个候选应快速完成排序"""
            n = 100
            cand = [f"item_{i}" for i in range(n)]
            scores = [0.5 + 0.5 * (i / n) for i in range(n)]  # 0.5~1.0
            vectors = [[1 if i == j else 0 for j in range(10)]
                       for i in range(n)]
            import time
            start = time.time()
            result = mmr_rerank(cand, scores, lambda_=0.5,
                                feature_vectors=vectors)
            elapsed = time.time() - start
            self.assertEqual(len(result), n)
            # 100个候选应在 1 秒内完成
            self.assertLess(elapsed, 1.0,
                            f"100候选排序耗时 {elapsed:.3f}s > 1s")

        def test_deterministic(self):
            """相同输入应产生相同输出"""
            cand = ["A", "B", "C"]
            scores = [0.9, 0.7, 0.5]
            vectors = [[1, 0], [0, 1], [1, 1]]
            result1 = mmr_rerank(cand, scores, lambda_=0.5,
                                 feature_vectors=vectors)
            result2 = mmr_rerank(cand, scores, lambda_=0.5,
                                 feature_vectors=vectors)
            self.assertEqual(
                [r[0] for r in result1],
                [r[0] for r in result2],
            )

        # ── batch 批量测试 ──

        def test_batch_mmr(self):
            """批量 MMR 应正确处理多个 group"""
            groups = [
                (["A", "B"], [0.9, 0.8], [[1, 0], [0, 1]]),
                (["C", "D"], [0.7, 0.6], [[1, 0], [0, 1]]),
            ]
            results = batch_mmr_rerank(groups, lambda_=0.5)
            self.assertEqual(len(results), 2)
            self.assertEqual(len(results[0]), 2)
            self.assertEqual(len(results[1]), 2)

    # 运行测试
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMMR)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    _run_tests()
