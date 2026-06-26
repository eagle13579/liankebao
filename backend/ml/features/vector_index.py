"""
链客宝 - FAISS 向量索引封装 (IndexFlatIP)
============================================
基于 FAISS IndexFlatIP (内积 = Cosine 相似度，对归一化向量) 的向量索引包装类。

维度: 1024 (BGE-M3 默认输出)，可通过参数配置。
线程安全: 所有写操作受锁保护。

能力:
1. add(batch) — 批量添加向量到索引
2. search(query, k) — 查询 Top-K 相似向量，返回 (indices, distances)
3. save(path) / load(path) — 持久化/加载索引
4. len() / is_trained / total() 等辅助属性

依赖:
    pip install faiss-cpu numpy

使用方式:
    from ml.features.vector_index import VectorIndex

    index = VectorIndex(dimension=1024)
    vectors = [[0.1] * 1024, [0.2] * 1024]
    index.add(vectors)
    scores, ids = index.search([0.15] * 1024, k=5)
    index.save("/path/to/index.faiss")

Author: 贤宇 (P6, 数据分析部, 缓存/检索专家)
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# BGE-M3 默认维度
DEFAULT_DIMENSION = 1024

# ---------------------------------------------------------------------------
# FAISS 向量索引包装
# ---------------------------------------------------------------------------


class VectorIndex:
    """
    FAISS IndexFlatIP 包装类，提供 add/search/save/load 接口。

    IndexFlatIP 使用内积距离。对于 L2 归一化向量，内积等价于余弦相似度。

    Parameters
    ----------
    dimension : int
        向量维度，默认为 1024 (BGE-M3)。
    index_path : str or None
        若提供路径且文件存在，自动从该路径加载索引。

    Attributes
    ----------
    dimension : int
        向量维度。
    ntotal : int
        索引中的向量总数。

    Examples
    --------
    >>> index = VectorIndex(dimension=4)
    >>> index.add([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    >>> scores, ids = index.search([0.9, 0.1, 0.0, 0.0], k=2)
    >>> len(scores)
    2
    >>> ids[0]
    0
    >>> index.save('/tmp/test_index.faiss')
    >>> index2 = VectorIndex(dimension=4, index_path='/tmp/test_index.faiss')
    >>> index2.ntotal
    2
    """

    def __init__(
        self,
        dimension: int = DEFAULT_DIMENSION,
        index_path: Optional[str] = None,
    ) -> None:
        self.dimension = dimension
        self._lock = threading.Lock()
        self._index: Optional["faiss.Index"] = None  # type: ignore
        self._ntotal: int = 0

        # 延迟导入 faiss（允许模块级 import 即使 faiss 未安装）
        self._faiss = _lazy_import_faiss()

        if index_path is not None and os.path.exists(index_path):
            self.load(index_path)
            logger.info("[VectorIndex] 从文件加载索引: %s (%d 条)", index_path, self._ntotal)
        else:
            self._create_index()
            logger.info("[VectorIndex] 新建索引 (dim=%d)", self.dimension)

    # ------------------------------------------------------------------
    # 索引创建
    # ------------------------------------------------------------------

    def _create_index(self) -> None:
        """创建 IndexFlatIP 索引"""
        self._index = self._faiss.IndexFlatIP(self.dimension)
        self._ntotal = 0

    def reset(self) -> None:
        """重置索引（清空所有向量）"""
        with self._lock:
            self._create_index()

    # ------------------------------------------------------------------
    # 添加向量
    # ------------------------------------------------------------------

    def add(self, vectors: Union[List[List[float]], np.ndarray]) -> int:
        """
        批量添加向量到索引。

        Args:
            vectors: 形状为 (N, dimension) 的向量列表或 numpy 数组。

        Returns:
            添加前索引中的向量总数（可视为这批向量的起始 ID）。
        """
        if isinstance(vectors, list):
            if len(vectors) == 0:
                return self._ntotal
            vectors_np = np.asarray(vectors, dtype=np.float32)
        else:
            vectors_np = vectors.astype(np.float32)

        # 验证维度
        if vectors_np.shape[1] != self.dimension:
            raise ValueError(
                f"向量维度 {vectors_np.shape[1]} 与索引维度 {self.dimension} 不匹配"
            )

        with self._lock:
            start_id = self._ntotal
            self._index.add(vectors_np)  # type: ignore[union-attr]
            self._ntotal = self._index.ntotal  # type: ignore[union-attr]

        logger.debug("[VectorIndex] add: %d 条 (起始 ID=%d)", vectors_np.shape[0], start_id)
        return start_id

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    def search(
        self,
        query: Union[List[float], List[List[float]], np.ndarray],
        k: int = 10,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        搜索 Top-K 相似向量。

        Args:
            query: 单个查询向量 (dim,) 或批量查询向量 (N, dim)。
            k: 返回的最近邻数量。

        Returns:
            (distances, indices) 二元组:
            - distances: 形状为 (N, k) 或 (k,) 的距离数组（内积值）。
            - indices:   形状为 (N, k) 或 (k,) 的索引数组。
                        对于未命中/不足的情况，距离为 -inf，索引为 -1。
        """
        if isinstance(query, list) and len(query) > 0:
            # 判断是单个向量还是批量
            if isinstance(query[0], (int, float)):
                # 单个向量 [dim]
                query_np = np.asarray([query], dtype=np.float32)
                single = True
            else:
                # 批量向量 [N, dim]
                query_np = np.asarray(query, dtype=np.float32)
                single = False
        elif isinstance(query, np.ndarray):
            if query.ndim == 1:
                query_np = query[np.newaxis, :].astype(np.float32)
                single = True
            else:
                query_np = query.astype(np.float32)
                single = False
        else:
            raise TypeError(f"不支持的 query 类型: {type(query)}")

        # 验证维度
        if query_np.shape[1] != self.dimension:
            raise ValueError(
                f"查询向量维度 {query_np.shape[1]} 与索引维度 {self.dimension} 不匹配"
            )

        n_queries = query_np.shape[0]
        effective_k = min(k, self._ntotal) if self._ntotal > 0 else 0

        with self._lock:
            if self._ntotal == 0:
                distances = np.full((n_queries, k), -np.inf, dtype=np.float32)
                indices = np.full((n_queries, k), -1, dtype=np.int64)
            else:
                distances, indices = self._index.search(query_np, effective_k)  # type: ignore[union-attr]
                # 如果 effective_k < k，填充剩余列
                if effective_k < k:
                    pad_d = np.full((n_queries, k), -np.inf, dtype=np.float32)
                    pad_i = np.full((n_queries, k), -1, dtype=np.int64)
                    pad_d[:, :effective_k] = distances
                    pad_i[:, :effective_k] = indices
                    distances, indices = pad_d, pad_i

        if single:
            return distances[0], indices[0]
        return distances, indices

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """
        将索引持久化到磁盘。

        Args:
            path: 保存路径（建议使用 .faiss 扩展名）。
        """
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._faiss.write_index(self._index, str(path_obj))
        logger.info("[VectorIndex] 索引已保存: %s (%d 条)", path, self._ntotal)

    def load(self, path: str) -> None:
        """
        从磁盘加载索引。

        Args:
            path: 索引文件路径。
        """
        path_obj = Path(path)
        if not path_obj.exists():
            raise FileNotFoundError(f"索引文件不存在: {path}")
        with self._lock:
            self._index = self._faiss.read_index(str(path_obj))
            self._ntotal = self._index.ntotal
        logger.info("[VectorIndex] 索引已加载: %s (%d 条)", path, self._ntotal)

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def ntotal(self) -> int:
        """索引中的向量总数"""
        return self._ntotal

    @property
    def is_trained(self) -> bool:
        """IndexFlatIP 始终已训练"""
        return True

    # ------------------------------------------------------------------
    # Dunder 方法
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return self._ntotal

    def __bool__(self) -> bool:
        return True

    def __repr__(self) -> str:
        return (
            f"VectorIndex(dim={self.dimension}, ntotal={self._ntotal})"
        )


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _lazy_import_faiss():
    """延迟导入 faiss，允许模块级加载时 faiss 未安装。"""
    try:
        import faiss
        return faiss
    except ImportError:
        raise ImportError(
            "faiss 未安装。请执行: pip install faiss-cpu"
        )


def normalize_vectors(
    vectors: Union[List[List[float]], np.ndarray],
) -> np.ndarray:
    """
    L2 归一化向量（原地修改并返回）。

    Args:
        vectors: 形状为 (N, dim) 的向量。

    Returns:
        L2 归一化后的 numpy 数组 (float32)。
    """
    if isinstance(vectors, list):
        vectors_np = np.asarray(vectors, dtype=np.float32)
    else:
        vectors_np = vectors.astype(np.float32)

    norms = np.linalg.norm(vectors_np, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)  # 避免除零
    return vectors_np / norms


# ---------------------------------------------------------------------------
# 内置验证 / 快速测试
# ---------------------------------------------------------------------------


def _verify() -> None:
    """快速验证模块语法和基本功能"""
    import tempfile

    print("=" * 60)
    print("[验证] VectorIndex FAISS 向量索引包装")
    print("=" * 60)

    # 1. 创建索引
    dim = 4
    index = VectorIndex(dimension=dim)
    assert index is not None
    assert index.ntotal == 0
    print("\n1. ✓ VectorIndex 创建成功 (dim=%d)" % dim)

    # 2. 添加向量
    np.random.seed(42)
    vecs = np.random.randn(10, dim).astype(np.float32)
    vecs = normalize_vectors(vecs)
    start_id = index.add(vecs)
    assert start_id == 0
    assert index.ntotal == 10
    print("2. ✓ 添加 10 条向量成功")

    # 3. 搜索
    scores, ids = index.search(vecs[0], k=5)
    assert len(scores) == 5
    assert len(ids) == 5
    assert ids[0] == 0  # 与自身最相似
    print("3. ✓ 搜索 Top-5 成功 (最相似为自身)")

    # 4. 批量搜索
    scores_batch, ids_batch = index.search(vecs[:3], k=3)
    assert scores_batch.shape == (3, 3)
    assert ids_batch.shape == (3, 3)
    print("4. ✓ 批量搜索 3 条成功")

    # 5. 空索引搜索
    empty_index = VectorIndex(dimension=dim)
    scores_e, ids_e = empty_index.search([0.0] * dim, k=5)
    assert np.all(scores_e == -np.inf)
    assert np.all(ids_e == -1)
    print("5. ✓ 空索引搜索返回填充值")

    # 6. 持久化
    with tempfile.NamedTemporaryFile(suffix=".faiss", delete=False) as f:
        tmp_path = f.name
    try:
        index.save(tmp_path)

        # 加载
        index2 = VectorIndex(dimension=dim, index_path=tmp_path)
        assert index2.ntotal == 10
        print("6. ✓ 索引持久化 + 加载成功")

        # 搜索结果一致
        scores2, ids2 = index2.search(vecs[0], k=5)
        assert np.allclose(scores, scores2)
        assert np.all(ids == ids2)
        print("   ✓ 加载后搜索结果一致")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    # 7. reset
    index.reset()
    assert index.ntotal == 0
    print("7. ✓ reset 重置成功")

    # 8. 多维搜索
    scores_multi, ids_multi = index.search([[0.0] * dim, [1.0] * dim], k=2)
    assert scores_multi.shape == (2, 2)
    print("8. ✓ 多维搜索成功")

    print("\n" + "=" * 60)
    print("所有验证通过 ✓")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _verify()
