"""
链客宝 - MMR 多样性重排序算法 单元测试
========================================
覆盖：基础MMR重排序、λ边界(纯多样性/纯相关性)、参数校验异常、
余弦相似度正确性、自定义similarity_fn、top_n截断、多样性评估指标、
大规模性能(100候选<1s)、批量MMR、空候选列表、单一候选、确定性等。

从 features.mmr_diversity 提取并适配为标准 pytest 测试用例。
"""

import math
import time
from typing import List, Tuple

import pytest

from features.mmr_diversity import (
    _cosine_similarity_wrapper,
    batch_mmr_rerank,
    diversity_score,
    mmr_rerank,
)

# ============================================================================
# Fixtures — 共享测试数据
# ============================================================================


@pytest.fixture
def str_candidates() -> List[str]:
    """4个字符串候选。"""
    return ["A", "B", "C", "D"]


@pytest.fixture
def str_scores() -> List[float]:
    """与 str_candidates 对应的相关性分数（降序）。"""
    return [0.9, 0.8, 0.7, 0.6]


@pytest.fixture
def simple_vectors() -> List[List[float]]:
    """
    4个候选的特征向量。
    A=[1,0]  B=[0,1]  C=[1,1]  D=[0,0]
    """
    return [[1, 0], [0, 1], [1, 1], [0, 0]]


@pytest.fixture
def three_candidates() -> Tuple[List[str], List[float], List[List[float]]]:
    """3个候选及其分数与向量。"""
    cand = ["A", "B", "C"]
    scores = [0.5, 0.9, 0.7]
    vectors = [[1, 0], [0, 1], [1, 1]]
    return cand, scores, vectors


@pytest.fixture
def identical_vector_pair() -> List[List[float]]:
    """一对完全相同的向量。"""
    return [[1, 2, 3], [1, 2, 3]]


@pytest.fixture
def orthogonal_vector_pair() -> List[List[float]]:
    """一对正交向量。"""
    return [[1, 0], [0, 1]]


@pytest.fixture
def zero_vector_pair() -> List[List[float]]:
    """包含零向量的向量对。"""
    return [[0, 0], [1, 0]]


@pytest.fixture
def repeat_candidates_for_custom_sim() -> Tuple[List[str], List[float]]:
    """
    含重复元素的候选列表，用于测试自定义相似度函数。
    值相同的元素相似度为1.0，不同的为0.0。
    """
    cand = ["A", "B", "A", "C"]
    scores = [0.9, 0.8, 0.7, 0.6]
    return cand, scores


# ============================================================================
# 基础 MMR 重排序
# ============================================================================


class TestBasicMMR:
    """基础 MMR 重排序功能测试。"""

    def test_basic_rerank_length(
        self,
        str_candidates: List[str],
        str_scores: List[float],
        simple_vectors: List[List[float]],
    ) -> None:
        """基础重排序：候选4个，验证返回4个结果。"""
        result = mmr_rerank(
            str_candidates, str_scores, lambda_=0.5, feature_vectors=simple_vectors
        )
        assert len(result) == 4

    def test_first_is_highest_relevance(
        self,
        three_candidates: Tuple[List[str], List[float], List[List[float]]],
    ) -> None:
        """第一轮应当返回相关性最高的候选。"""
        cand, scores, vectors = three_candidates
        result = mmr_rerank(cand, scores, lambda_=1.0, feature_vectors=vectors)
        assert result[0][0] == "B"  # B 相关性 0.9 最高

    def test_deterministic_output(
        self,
        str_candidates: List[str],
        str_scores: List[float],
        simple_vectors: List[List[float]],
    ) -> None:
        """相同输入应产生相同输出。"""
        result1 = mmr_rerank(
            str_candidates, str_scores, lambda_=0.5, feature_vectors=simple_vectors
        )
        result2 = mmr_rerank(
            str_candidates, str_scores, lambda_=0.5, feature_vectors=simple_vectors
        )
        assert [r[0] for r in result1] == [r[0] for r in result2]

    def test_score_values_preserved(
        self,
        str_candidates: List[str],
        str_scores: List[float],
        simple_vectors: List[List[float]],
    ) -> None:
        """返回结果中的分数应等于原始相关性分数。"""
        result = mmr_rerank(
            str_candidates, str_scores, lambda_=0.5, feature_vectors=simple_vectors
        )
        returned_scores = [r[1] for r in result]
        assert sorted(returned_scores) == sorted(str_scores)


# ============================================================================
# λ 边界情况：λ=0 (纯多样性) / λ=1 (纯相关性)
# ============================================================================


class TestLambdaBoundaries:
    """λ边界值测试。"""

    def test_lambda_one_pure_relevance(
        self,
        str_candidates: List[str],
        str_scores: List[float],
        simple_vectors: List[List[float]],
    ) -> None:
        """λ=1.0 时完全按相关性降序（忽略多样性）。"""
        result = mmr_rerank(
            str_candidates, str_scores, lambda_=1.0, feature_vectors=simple_vectors
        )
        expected = ["A", "B", "C", "D"]  # 按分数降序
        assert [r[0] for r in result] == expected

    def test_lambda_zero_pure_diversity(
        self,
    ) -> None:
        """λ=0.0 时完全按多样性排序。

        A(0.9) 独特，B(0.4) 与 C(0.3) 相似。
        第一轮选 A(最高分)，第二轮选 B 或 C (与 A 都不相似)，
        由于 B 比 C 分数高，选 B。
        """
        cand = ["A", "B", "C"]
        scores = [0.9, 0.4, 0.3]
        vectors = [[1, 0, 0], [0, 1, 0], [0, 1, 0.1]]
        result = mmr_rerank(cand, scores, lambda_=0.0, feature_vectors=vectors)
        assert result[0][0] == "A"

    def test_lambda_half_balanced(
        self,
        str_candidates: List[str],
        str_scores: List[float],
        simple_vectors: List[List[float]],
    ) -> None:
        """λ=0.5 均衡模式下结果应在相关性与多样性之间平衡。"""
        result = mmr_rerank(
            str_candidates, str_scores, lambda_=0.5, feature_vectors=simple_vectors
        )
        # 第一个必须是 A（相关性最高）
        assert result[0][0] == "A"
        # 应当有4个结果
        assert len(result) == 4


# ============================================================================
# 参数校验异常
# ============================================================================


class TestParameterValidation:
    """参数校验异常测试。"""

    def test_length_mismatch_raises(
        self, simple_vectors: List[List[float]]
    ) -> None:
        """candidates 与 relevance_scores 长度不一致应抛 ValueError。"""
        with pytest.raises(ValueError, match="长度.*不一致"):
            mmr_rerank(["A", "B"], [0.9], lambda_=0.5, feature_vectors=simple_vectors)

    def test_lambda_below_zero_raises(self) -> None:
        """λ < 0 应抛 ValueError。"""
        with pytest.raises(ValueError, match="lambda_ 必须在"):
            mmr_rerank(["A"], [0.9], lambda_=-0.1, feature_vectors=[[1]])

    def test_lambda_above_one_raises(self) -> None:
        """λ > 1 应抛 ValueError。"""
        with pytest.raises(ValueError, match="lambda_ 必须在"):
            mmr_rerank(["A"], [0.9], lambda_=1.1, feature_vectors=[[1]])

    def test_missing_similarity_source_raises(self) -> None:
        """未提供 similarity_fn 或 feature_vectors 应抛 ValueError。"""
        with pytest.raises(ValueError, match="必须提供.*之一"):
            mmr_rerank(["A"], [0.9], lambda_=0.5)

    def test_vector_dimension_mismatch_raises(self) -> None:
        """特征向量维度不一致应抛 ValueError。"""
        with pytest.raises(ValueError, match="维度不一致"):
            mmr_rerank(
                ["A", "B"],
                [0.9, 0.8],
                lambda_=0.5,
                feature_vectors=[[1, 0], [1, 0, 0]],
            )

    def test_feature_vectors_length_mismatch_raises(self) -> None:
        """feature_vectors 长度与 candidates 不一致应抛 ValueError。"""
        with pytest.raises(ValueError, match="长度.*不一致"):
            mmr_rerank(
                ["A", "B", "C"],
                [0.9, 0.8, 0.7],
                lambda_=0.5,
                feature_vectors=[[1, 0], [0, 1]],
            )


# ============================================================================
# 余弦相似度正确性
# ============================================================================


class TestCosineSimilarity:
    """余弦相似度计算正确性测试。"""

    def test_identical_vectors(
        self, identical_vector_pair: List[List[float]]
    ) -> None:
        """相同向量的余弦相似度应为 1.0。"""
        sim_fn = _cosine_similarity_wrapper(identical_vector_pair)
        assert sim_fn(0, 1) == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors(
        self, orthogonal_vector_pair: List[List[float]]
    ) -> None:
        """正交向量的余弦相似度应为 0.0。"""
        sim_fn = _cosine_similarity_wrapper(orthogonal_vector_pair)
        assert sim_fn(0, 1) == pytest.approx(0.0, abs=1e-6)

    def test_zero_vector(self, zero_vector_pair: List[List[float]]) -> None:
        """包含零向量的余弦相似度应为 0.0。"""
        sim_fn = _cosine_similarity_wrapper(zero_vector_pair)
        assert sim_fn(0, 1) == 0.0

    def test_self_similarity(self) -> None:
        """非零向量与自身的余弦相似度应为 1.0。"""
        vectors = [[1, 2, 3], [0.5, -0.5, 1.0]]
        sim_fn = _cosine_similarity_wrapper(vectors)
        for i in range(len(vectors)):
            assert sim_fn(i, i) == pytest.approx(1.0, abs=1e-6)

    def test_zero_vector_self_similarity(self) -> None:
        """零向量与自身的余弦相似度应为 0.0（norm为0）。"""
        vectors = [[0, 0], [0, 0, 0]]
        sim_fn = _cosine_similarity_wrapper(vectors)
        for i in range(len(vectors)):
            assert sim_fn(i, i) == 0.0

    def test_symmetric(
        self, simple_vectors: List[List[float]]
    ) -> None:
        """余弦相似度应对称：sim(i,j) == sim(j,i)。"""
        sim_fn = _cosine_similarity_wrapper(simple_vectors)
        for i in range(len(simple_vectors)):
            for j in range(len(simple_vectors)):
                assert sim_fn(i, j) == pytest.approx(sim_fn(j, i), abs=1e-6)

    def test_partial_similarity(self) -> None:
        """[1,0] 与 [0.5, 0.5] 的部分相似度应为 ~0.707。"""
        vectors = [[1, 0], [0.5, 0.5]]
        sim_fn = _cosine_similarity_wrapper(vectors)
        expected = (1 * 0.5 + 0 * 0.5) / (1.0 * math.sqrt(0.5))
        assert sim_fn(0, 1) == pytest.approx(expected, abs=1e-6)


# ============================================================================
# 自定义 similarity_fn
# ============================================================================


class TestCustomSimilarityFn:
    """自定义相似度函数测试。"""

    def test_custom_similarity_fn(
        self,
        repeat_candidates_for_custom_sim: Tuple[List[str], List[float]],
    ) -> None:
        """自定义相似度函数（相同元素相似度为1，不同为0）应正常工作。"""
        cand, scores = repeat_candidates_for_custom_sim

        def sim(a: str, b: str) -> float:
            return 1.0 if a == b else 0.0

        # λ=0: 只看多样性 → 选所有不同元素
        result = mmr_rerank(cand, scores, lambda_=0.0, similarity_fn=sim)
        assert result[0][0] == "A"  # 第一轮选分数最高的 A
        # 第二轮选 B (不同元素中分数最高)
        assert result[1][0] == "B"
        # 第三轮选 C (下一个不同元素)
        assert result[2][0] == "C"

    def test_custom_similarity_with_lambda_one(self) -> None:
        """λ=1 时自定义相似度函数不应影响排序（纯按相关性）。"""
        cand = ["X", "Y", "Z"]
        scores = [0.3, 0.9, 0.6]

        def sim(a: str, b: str) -> float:
            return 1.0  # 全部认为相同

        result = mmr_rerank(cand, scores, lambda_=1.0, similarity_fn=sim)
        assert [r[0] for r in result] == ["Y", "Z", "X"]  # 按分数降序

    def test_custom_similarity_no_feature_vectors_needed(self) -> None:
        """提供 similarity_fn 时不需要 feature_vectors。"""
        cand = ["A", "B"]
        scores = [0.9, 0.8]

        def sim(a: str, b: str) -> float:
            return 0.5

        # 不应抛出 ValueError
        result = mmr_rerank(cand, scores, lambda_=0.5, similarity_fn=sim)
        assert len(result) == 2


# ============================================================================
# top_n 截断
# ============================================================================


class TestTopN:
    """top_n 截断参数测试。"""

    def test_top_n_truncation(
        self,
        str_candidates: List[str],
        str_scores: List[float],
        simple_vectors: List[List[float]],
    ) -> None:
        """top_n 应只返回前 N 个结果。"""
        result = mmr_rerank(
            str_candidates,
            str_scores,
            lambda_=0.5,
            top_n=2,
            feature_vectors=simple_vectors,
        )
        assert len(result) == 2

    def test_top_n_larger_than_list(
        self,
        str_candidates: List[str],
        str_scores: List[float],
        simple_vectors: List[List[float]],
    ) -> None:
        """top_n 大于列表长度应全部返回。"""
        result = mmr_rerank(
            str_candidates,
            str_scores,
            lambda_=0.5,
            top_n=10,
            feature_vectors=simple_vectors,
        )
        assert len(result) == 4

    def test_top_n_equals_one(self) -> None:
        """top_n=1 应只返回一个结果。"""
        cand = ["A", "B", "C"]
        scores = [0.9, 0.5, 0.7]
        vectors = [[1, 0], [0, 1], [1, 1]]
        result = mmr_rerank(
            cand, scores, lambda_=0.5, top_n=1, feature_vectors=vectors
        )
        assert len(result) == 1
        # 第一个应是最相关的
        assert result[0][0] == "A"


# ============================================================================
# 边界情况：空候选列表 / 单一候选
# ============================================================================


class TestEdgeCases:
    """边界情况测试。"""

    def test_empty_candidates(self) -> None:
        """空候选列表应返回空列表。"""
        result = mmr_rerank([], [], lambda_=0.5, feature_vectors=[])
        assert result == []

    def test_empty_candidates_custom_sim(self) -> None:
        """空候选列表（使用自定义相似度函数）应返回空列表。"""
        result = mmr_rerank([], [], lambda_=0.5, similarity_fn=lambda a, b: 0.0)
        assert result == []

    def test_single_candidate(self) -> None:
        """单一候选应直接返回。"""
        result = mmr_rerank(
            ["X"], [0.8], lambda_=0.5, feature_vectors=[[1, 0]]
        )
        assert len(result) == 1
        assert result[0][0] == "X"
        assert result[0][1] == pytest.approx(0.8)

    def test_single_candidate_custom_sim(self) -> None:
        """单一候选（使用自定义相似度函数）应直接返回。"""
        result = mmr_rerank(
            ["X"], [0.8], lambda_=0.5, similarity_fn=lambda a, b: 0.0
        )
        assert len(result) == 1
        assert result[0][0] == "X"

    def test_all_zero_scores(self) -> None:
        """所有候选分数为0时应能正常排序。"""
        cand = ["A", "B", "C"]
        scores = [0.0, 0.0, 0.0]
        vectors = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        result = mmr_rerank(cand, scores, lambda_=0.5, feature_vectors=vectors)
        assert len(result) == 3
        # 所有分数为0，排序结果仅由多样性决定
        assert result[0][1] == 0.0

    def test_identical_scores_and_vectors(self) -> None:
        """所有候选分数和向量都相同时应稳定排序。"""
        cand = ["A", "B", "C"]
        scores = [0.5, 0.5, 0.5]
        vectors = [[1, 0], [1, 0], [1, 0]]
        result = mmr_rerank(cand, scores, lambda_=0.5, feature_vectors=vectors)
        assert len(result) == 3
        # 所有都相同，结果应为确定性顺序
        items = [r[0] for r in result]
        assert items == ["A", "B", "C"]  # 原始顺序（第一轮选第一个）


# ============================================================================
# 多样性评估指标
# ============================================================================


class TestDiversityScore:
    """diversity_score 评估指标测试。"""

    def test_identical_items_score_zero(self) -> None:
        """完全相同的结果多样性分数应为 0.0。"""
        score = diversity_score(["A", "A", "A"], lambda a, b: 1.0)
        assert score == pytest.approx(0.0)

    def test_all_different_items_score_one(self) -> None:
        """完全不同结果多样性分数应为 1.0。"""
        score = diversity_score(["A", "B", "C"], lambda a, b: 0.0)
        assert score == pytest.approx(1.0)

    def test_single_item_score_one(self) -> None:
        """单元素列表多样性分数应为 1.0。"""
        score = diversity_score(["A"], lambda a, b: 1.0)
        assert score == pytest.approx(1.0)

    def test_empty_list_score_one(self) -> None:
        """空列表多样性分数应为 1.0。"""
        score = diversity_score([], lambda a, b: 1.0)
        assert score == pytest.approx(1.0)

    def test_mixed_similarity_score(self) -> None:
        """混合相似度值应计算出正确的平均多样性分数。"""
        # A与B相似0.3, A与C相似0.7, B与C相似0.5
        # 平均相似度 = (0.3 + 0.7 + 0.5) / 3 = 0.5
        # 多样性 = 1 - 0.5 = 0.5
        sim_map = {
            ("A", "B"): 0.3,
            ("A", "C"): 0.7,
            ("B", "C"): 0.5,
        }

        def sim_fn(a: str, b: str) -> float:
            return sim_map.get((a, b), sim_map.get((b, a), 0.0))

        score = diversity_score(["A", "B", "C"], sim_fn)
        assert score == pytest.approx(0.5)

    def test_mmr_with_diversity_evaluation(
        self,
        str_candidates: List[str],
        str_scores: List[float],
        simple_vectors: List[List[float]],
    ) -> None:
        """MMR 重排序后应具有比纯相关性排序更高的多样性分数。"""
        # 纯相关性排序
        relevance_ordered = sorted(
            zip(str_candidates, str_scores), key=lambda x: -x[1]
        )

        # MMR 排序
        mmr_result = mmr_rerank(
            str_candidates, str_scores, lambda_=0.3, feature_vectors=simple_vectors
        )
        mmr_ordered = [r[0] for r in mmr_result]

        # 构建余弦相似度函数用于评估
        def vec_sim(a: str, b: str) -> float:
            idx_map = {c: i for i, c in enumerate(str_candidates)}
            sim_fn = _cosine_similarity_wrapper(simple_vectors)
            return sim_fn(idx_map[a], idx_map[b])

        relevance_div = diversity_score(
            [r[0] for r in relevance_ordered], vec_sim
        )
        mmr_div = diversity_score(mmr_ordered, vec_sim)

        # MMR 的多样性应不低于纯相关性排序
        assert mmr_div >= relevance_div


# ============================================================================
# 大规模性能测试
# ============================================================================


class TestPerformance:
    """大规模候选集性能测试。"""

    def test_one_hundred_candidates_under_one_second(self) -> None:
        """100个候选应在 1 秒内完成排序。"""
        n = 100
        cand = [f"item_{i}" for i in range(n)]
        scores = [0.5 + 0.5 * (i / n) for i in range(n)]
        vectors = [[1 if i == j else 0 for j in range(10)] for i in range(n)]

        start = time.time()
        result = mmr_rerank(cand, scores, lambda_=0.5, feature_vectors=vectors)
        elapsed = time.time() - start

        assert len(result) == n
        assert elapsed < 1.0, f"100候选排序耗时 {elapsed:.3f}s > 1s"

    def test_two_hundred_candidates(self) -> None:
        """200个候选应在合理时间内完成（<2s）。"""
        n = 200
        cand = [f"idx_{i}" for i in range(n)]
        scores = [0.9 - 0.4 * (i / n) for i in range(n)]
        vectors = [[1 if i == j else 0 for j in range(8)] for i in range(n)]

        start = time.time()
        result = mmr_rerank(cand, scores, lambda_=0.5, feature_vectors=vectors)
        elapsed = time.time() - start

        assert len(result) == n
        assert elapsed < 2.0, f"200候选排序耗时 {elapsed:.3f}s > 2s"


# ============================================================================
# 批量 MMR
# ============================================================================


class TestBatchMMR:
    """批量 MMR 重排序测试。"""

    def test_batch_two_groups(self) -> None:
        """批量 MMR 应正确处理多个 group。"""
        groups = [
            (["A", "B"], [0.9, 0.8], [[1, 0], [0, 1]]),
            (["C", "D"], [0.7, 0.6], [[1, 0], [0, 1]]),
        ]
        results = batch_mmr_rerank(groups, lambda_=0.5)
        assert len(results) == 2
        assert len(results[0]) == 2
        assert len(results[1]) == 2

    def test_batch_empty_group(self) -> None:
        """批量 MMR 中某个 group 为空应返回空列表。"""
        groups = [
            ([], [], []),
            (["A", "B"], [0.9, 0.8], [[1, 0], [0, 1]]),
        ]
        results = batch_mmr_rerank(groups, lambda_=0.5)
        assert len(results) == 2
        assert results[0] == []
        assert len(results[1]) == 2

    def test_batch_no_feature_vectors(self) -> None:
        """批量 MMR 中 feature_vectors 为 None 应抛 ValueError。"""
        groups = [
            (["A", "B"], [0.9, 0.8], None),
        ]
        with pytest.raises(ValueError, match="必须提供"):
            batch_mmr_rerank(groups, lambda_=0.5)

    def test_batch_with_top_n(self) -> None:
        """批量 MMR 支持 top_n 参数。"""
        groups = [
            (["A", "B", "C"], [0.9, 0.8, 0.7], [[1, 0], [0, 1], [1, 1]]),
            (["D", "E", "F"], [0.6, 0.5, 0.4], [[1, 0], [0, 1], [1, 1]]),
        ]
        results = batch_mmr_rerank(groups, lambda_=0.5, top_n=2)
        assert len(results) == 2
        assert len(results[0]) == 2
        assert len(results[1]) == 2

    def test_batch_varied_lambda(self) -> None:
        """批量 MMR 支持不同 λ 参数。"""
        groups = [
            (["A", "B"], [0.9, 0.8], [[1, 0], [0, 1]]),
        ]
        # λ=1.0: 纯相关性排序
        results = batch_mmr_rerank(groups, lambda_=1.0)
        assert [r[0] for r in results[0]] == ["A", "B"]  # 0.9 > 0.8
