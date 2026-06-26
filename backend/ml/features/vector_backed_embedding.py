"""
链客宝 - FAISS + SQLite 双存嵌入向量缓存
============================================
兼容现有 embedding_cache.py 接口，但后端替换为 FAISS 索引 + SQLite 双重存储。

设计目标:
1. 兼容性 — 与 EmbeddingCache 的 store/retrieve/batch_query 接口一致
2. 双存 — SQLite 负责文本→向量精确查询，FAISS 负责近似最近邻(ANN)搜索
3. 零侵入 — 不修改任何现有源码，可独立 import 使用

接口速览:
    from ml.features.vector_backed_embedding import VectorBackedEmbedding

    vbe = VectorBackedEmbedding()
    vbe.store("某文本", [0.1, 0.2, ...])       # 写入
    vec = vbe.retrieve("某文本")                # 单条查询
    vecs = vbe.batch_query(["文本1", "文本2"])   # 批量查询
    ids, scores = vbe.search(query_vec, k=10)   # ANN 搜索
    vbe.clear()
    vbe.close()

依赖:
    pip install faiss-cpu numpy

Author: 贤宇 (P6, 数据分析部, 缓存/检索专家)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from ml.features.vector_index import VectorIndex, normalize_vectors

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 默认缓存目录
DEFAULT_CACHE_DIR = os.path.join(
    str(Path.home()), ".cache", "chainke"
)
DEFAULT_DB_NAME = "vector_backed_cache.db"
DEFAULT_INDEX_NAME = "vector_index.faiss"

# BGE-M3 默认维度
DEFAULT_EMBEDDING_DIM = 1024

# SQLite 批处理参数限制 (留余量)
_MAX_SQLITE_VARS = 900

# ---------------------------------------------------------------------------
# FAISS + SQLite 双存嵌入向量缓存
# ---------------------------------------------------------------------------


class VectorBackedEmbedding:
    """
    FAISS + SQLite 双重存储的嵌入向量缓存。

    核心设计:
    - SQLite: key_hash → vector_blob 映射，支持精确文本→向量查询
    - FAISS: 向量索引，支持近似最近邻(ANN)搜索
    - 写入时同步更新两者，读取时优先查 SQLite

    接口兼容现有 EmbeddingCache:
        store(text, vec)   ↔  set(text, vec)
        retrieve(text)     ↔  get(text)
        batch_query(texts) ↔  batch_get(texts)

    新增接口:
        search(query_vec, k) — ANN 近似最近邻搜索

    Parameters
    ----------
    cache_dir : str or None
        缓存目录，默认为 ~/.cache/chainke/。
    dimension : int
        向量维度，默认为 1024 (BGE-M3)。
    index_path : str or None
        FAISS 索引文件路径；若文件已存在则自动加载。
    db_path : str or None
        SQLite 数据库文件路径。

    Examples
    --------
    >>> vbe = VectorBackedEmbedding(cache_dir='/tmp/test_vbe')
    >>> vbe.store("hello", [0.1, 0.2, 0.3, 0.4])
    >>> vec = vbe.retrieve("hello")
    >>> vec[:2]
    [0.1, 0.2]
    >>> vbe.batch_query(["hello", "nope"])
    [[0.1, 0.2, 0.3, 0.4], None]
    >>> scores, ids = vbe.search([0.1, 0.2, 0.3, 0.4], k=5)
    >>> ids[0]
    0
    """

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        dimension: int = DEFAULT_EMBEDDING_DIM,
        index_path: Optional[str] = None,
        db_path: Optional[str] = None,
    ) -> None:
        self._cache_dir = cache_dir or DEFAULT_CACHE_DIR
        os.makedirs(self._cache_dir, exist_ok=True)

        self._dimension = dimension

        # 文件路径
        self._db_path = db_path or os.path.join(self._cache_dir, DEFAULT_DB_NAME)
        self._index_path = index_path or os.path.join(self._cache_dir, DEFAULT_INDEX_NAME)

        # 统计计数器
        self._hits: int = 0
        self._misses: int = 0
        self._lock = threading.Lock()

        # 初始化 FAISS 索引
        self._vector_index = VectorIndex(
            dimension=self._dimension,
            index_path=self._index_path if os.path.exists(self._index_path) else None,
        )

        # 初始化 SQLite
        self._init_db()

        logger.info(
            "[VectorBackedEmbedding] 初始化完成: db=%s, index=%s, dim=%d, ntotal=%d",
            self._db_path, self._index_path, self._dimension, self._vector_index.ntotal,
        )

    # ------------------------------------------------------------------
    # SQLite 数据库初始化
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """创建数据库和表（如不存在）"""
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                    key_hash TEXT PRIMARY KEY,
                    vector_blob BLOB NOT NULL,
                    created_at REAL NOT NULL DEFAULT (julianday('now')),
                    faiss_id INTEGER DEFAULT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_embeddings_hash "
                "ON embeddings(key_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_embeddings_faiss_id "
                "ON embeddings(faiss_id)"
            )
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（每次调用新建，确保线程安全）"""
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    # ------------------------------------------------------------------
    # 哈希与序列化工具
    # ------------------------------------------------------------------

    @staticmethod
    def _hash(text: str) -> str:
        """计算文本的 SHA-256 哈希作为键"""
        import hashlib
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _serialize(vector: List[float]) -> bytes:
        """将向量序列化为 BLOB（JSON 二进制编码）"""
        return json.dumps(vector, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _deserialize(blob: bytes) -> List[float]:
        """从 BLOB 反序列化向量"""
        return json.loads(blob.decode("utf-8"))

    # ------------------------------------------------------------------
    # 接口: store / retrieve (别名：set / get)
    # ------------------------------------------------------------------

    # --- store / set ---

    def store(self, text: str, vector: List[float]) -> None:
        """
        写入嵌入向量到缓存（同时更新 SQLite 和 FAISS 索引）。

        Args:
            text: 文本
            vector: 嵌入向量列表
        """
        self.set(text, vector)

    def set(self, text: str, vector: List[float]) -> None:
        """
        写入嵌入向量到缓存（store 的等效别名）。

        Args:
            text: 文本
            vector: 嵌入向量列表
        """
        key = self._hash(text)
        blob = self._serialize(vector)
        vec_np = np.asarray(vector, dtype=np.float32).reshape(1, -1)

        try:
            # 检查是否已存在（用于更新场景）
            existing_faiss_id = self._get_faiss_id(key)

            # 写入 SQLite
            with self._get_conn() as conn:
                if existing_faiss_id is not None:
                    # 更新已有记录（SQLite 中向量替换，FAISS 中新增并标记旧 ID 无效）
                    conn.execute(
                        "UPDATE embeddings SET vector_blob = ?, created_at = julianday('now') "
                        "WHERE key_hash = ?",
                        (blob, key),
                    )
                else:
                    conn.execute(
                        "INSERT INTO embeddings (key_hash, vector_blob, created_at) "
                        "VALUES (?, ?, julianday('now'))",
                        (key, blob),
                    )
                conn.commit()

            # 写入 FAISS（始终新增；不支持删除，因此更新时旧向量可能残留）
            with self._lock:
                faiss_id = self._vector_index.add(normalize_vectors(vec_np))

            # 更新 SQLite 中的 faiss_id
            with self._get_conn() as conn:
                conn.execute(
                    "UPDATE embeddings SET faiss_id = ? WHERE key_hash = ?",
                    (faiss_id, key),
                )
                conn.commit()

        except Exception as e:
            logger.warning("[VectorBackedEmbedding] 写入失败: %s", e)

    def _get_faiss_id(self, key_hash: str) -> Optional[int]:
        """查询 key_hash 对应的 FAISS ID（若存在）"""
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT faiss_id FROM embeddings WHERE key_hash = ?",
                    (key_hash,),
                ).fetchone()
                if row and row[0] is not None:
                    return int(row[0])
        except Exception:
            pass
        return None

    # --- retrieve / get ---

    def retrieve(self, text: str) -> Optional[List[float]]:
        """
        查询缓存的嵌入向量。

        Args:
            text: 查询文本

        Returns:
            嵌入向量列表，未命中返回 None
        """
        return self.get(text)

    def get(self, text: str) -> Optional[List[float]]:
        """
        查询缓存的嵌入向量（retrieve 的等效别名）。

        Args:
            text: 查询文本

        Returns:
            嵌入向量列表，未命中返回 None
        """
        key = self._hash(text)
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT vector_blob FROM embeddings WHERE key_hash = ?",
                    (key,),
                ).fetchone()
                if row is not None:
                    with self._lock:
                        self._hits += 1
                    vec = self._deserialize(row[0])
                    logger.debug("[VectorBackedEmbedding] 命中: %s...", text[:20])
                    return vec
        except Exception as e:
            logger.warning("[VectorBackedEmbedding] 查询失败: %s", e)

        with self._lock:
            self._misses += 1
        return None

    # ------------------------------------------------------------------
    # 接口: batch_query / batch_get
    # ------------------------------------------------------------------

    def batch_query(
        self, texts: Sequence[str]
    ) -> List[Optional[List[float]]]:
        """
        批量查询嵌入向量（batch_get 的等效别名）。

        Args:
            texts: 文本列表

        Returns:
            嵌入向量列表（与输入顺序一致，未命中的位置为 None）
        """
        return self.batch_get(texts)

    def batch_get(
        self, texts: Sequence[str]
    ) -> List[Optional[List[float]]]:
        """
        批量查询嵌入向量。

        结果顺序与输入 texts 顺序一致，未命中的位置为 None。

        Args:
            texts: 文本列表

        Returns:
            嵌入向量列表（与输入顺序一致）
        """
        if not texts:
            return []

        text_list = list(texts)
        hash_to_text: Dict[str, str] = {}
        for t in text_list:
            h = self._hash(t)
            hash_to_text[h] = t

        hashes = list(hash_to_text.keys())
        results: List[Optional[List[float]]] = [None] * len(text_list)

        hit_count = 0
        for i in range(0, len(hashes), _MAX_SQLITE_VARS):
            batch_hashes = hashes[i : i + _MAX_SQLITE_VARS]
            placeholders = ",".join(["?"] * len(batch_hashes))
            try:
                with self._get_conn() as conn:
                    rows = conn.execute(
                        f"SELECT key_hash, vector_blob FROM embeddings "
                        f"WHERE key_hash IN ({placeholders})",
                        batch_hashes,
                    ).fetchall()
                    db_map: Dict[str, List[float]] = {}
                    for h, blob in rows:
                        db_map[h] = self._deserialize(blob)
                    for idx, t in enumerate(text_list):
                        h = self._hash(t)
                        if h in db_map:
                            results[idx] = db_map[h]
                            hit_count += 1
            except Exception as e:
                logger.warning(
                    "[VectorBackedEmbedding] 批量查询失败: %s", e
                )

        with self._lock:
            self._hits += hit_count
            self._misses += len(texts) - hit_count

        logger.debug(
            "[VectorBackedEmbedding] 批量查询: %d 条, 命中 %d 条",
            len(texts), hit_count,
        )
        return results

    def batch_set(
        self, text_pairs: Sequence[Tuple[str, List[float]]]
    ) -> None:
        """
        批量写入嵌入向量到缓存（同时更新 SQLite 和 FAISS）。

        Args:
            text_pairs: (文本, 向量) 元组列表
        """
        if not text_pairs:
            return

        # 分批写入 SQLite
        for i in range(0, len(text_pairs), _MAX_SQLITE_VARS // 3):
            batch = text_pairs[i : i + _MAX_SQLITE_VARS // 3]
            try:
                with self._get_conn() as conn:
                    conn.executemany(
                        "INSERT OR REPLACE INTO embeddings "
                        "(key_hash, vector_blob, created_at) "
                        "VALUES (?, ?, julianday('now'))",
                        [
                            (self._hash(t), self._serialize(v))
                            for t, v in batch
                        ],
                    )
                    conn.commit()
            except Exception as e:
                logger.warning(
                    "[VectorBackedEmbedding] 批量写入失败 (批次 %d~%d): %s",
                    i, i + len(batch) - 1, e,
                )

        # 批量写入 FAISS
        vectors_np_list = []
        keys_list = []
        for t, v in text_pairs:
            keys_list.append(self._hash(t))
            vectors_np_list.append(v)

        if vectors_np_list:
            vecs_np = np.asarray(vectors_np_list, dtype=np.float32)
            with self._lock:
                start_id = self._vector_index.add(normalize_vectors(vecs_np))

            # 更新 SQLite 中的 faiss_id
            try:
                with self._get_conn() as conn:
                    for idx, key in enumerate(keys_list):
                        fid = start_id + idx
                        conn.execute(
                            "UPDATE embeddings SET faiss_id = ? WHERE key_hash = ?",
                            (fid, key),
                        )
                    conn.commit()
            except Exception as e:
                logger.warning(
                    "[VectorBackedEmbedding] 批量更新 faiss_id 失败: %s", e
                )

        logger.debug(
            "[VectorBackedEmbedding] 批量写入: %d 条 (SQLite + FAISS)",
            len(text_pairs),
        )

    # ------------------------------------------------------------------
    # 新增: 向量搜索 (ANN, 基于 FAISS)
    # ------------------------------------------------------------------

    def search(
        self,
        query: Union[List[float], List[List[float]], np.ndarray],
        k: int = 10,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        近似最近邻搜索 — 在 FAISS 索引中搜索相似向量。

        Args:
            query: 查询向量（单个或批量）。
            k: 返回的最近邻数量。

        Returns:
            (distances, indices) 二元组，形状取决于输入。
        """
        # 确保查询向量已归一化
        if isinstance(query, list):
            query_np = np.asarray(query, dtype=np.float32)
        else:
            query_np = query.astype(np.float32)

        single = query_np.ndim == 1
        if single:
            query_np = query_np.reshape(1, -1)

        query_normalized = normalize_vectors(query_np)

        # 委托给 VectorIndex
        distances, indices = self._vector_index.search(query_normalized, k=k)

        # 如果是单向量输入，展平输出
        if single:
            return distances[0], indices[0]
        return distances, indices

    def search_with_text(
        self,
        query: Union[List[float], List[List[float]], np.ndarray],
        k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        近似最近邻搜索 — 返回包含文本和相关度的结果。

        Args:
            query: 查询向量。
            k: 返回的最近邻数量。

        Returns:
            [{"text": str, "score": float, "faiss_id": int}, ...]
            按相似度降序排列。
        """
        distances, indices = self.search(query, k=k)

        # 展平处理
        if indices.ndim == 1:
            indices = indices.reshape(1, -1)
            distances = distances.reshape(1, -1)

        results: List[Dict[str, Any]] = []
        faiss_ids = []

        # 收集有效的 faiss_id
        for batch_idx in range(indices.shape[0]):
            for j in range(indices.shape[1]):
                fid = indices[batch_idx, j]
                if fid >= 0:
                    faiss_ids.append(int(fid))

        # 从 SQLite 批量回查文本
        text_map: Dict[int, str] = {}
        if faiss_ids:
            try:
                unique_ids = list(set(faiss_ids))
                for i in range(0, len(unique_ids), _MAX_SQLITE_VARS // 2):
                    batch_ids = unique_ids[i : i + _MAX_SQLITE_VARS // 2]
                    placeholders = ",".join(["?"] * len(batch_ids))
                    with self._get_conn() as conn:
                        rows = conn.execute(
                            f"SELECT key_hash, faiss_id FROM embeddings "
                            f"WHERE faiss_id IN ({placeholders})",
                            batch_ids,
                        ).fetchall()
                        # key_hash 是文本的哈希，无法直接还原文本
                        # 此处只记录 faiss_id 到 key_hash 的映射
                        for row in rows:
                            text_map[int(row[1])] = row[0]
            except Exception as e:
                logger.warning(
                    "[VectorBackedEmbedding] 回查文本失败: %s", e
                )

        # 组装结果（按顺序）
        for batch_idx in range(indices.shape[0]):
            for j in range(indices.shape[1]):
                fid = indices[batch_idx, j]
                score = distances[batch_idx, j]
                if fid >= 0:
                    results.append({
                        "faiss_id": int(fid),
                        "key_hash": text_map.get(int(fid), ""),
                        "score": float(score),
                    })

        return results

    # ------------------------------------------------------------------
    # 统计信息
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息。

        Returns:
            dict 包含:
            - total_entries: 缓存条目总数 (SQLite)
            - faiss_entries: FAISS 索引中的向量数
            - hits: 命中次数
            - misses: 未命中次数
            - total_queries: 总查询次数
            - hit_rate: 命中率 (0.0 ~ 1.0)
            - db_size_bytes: 数据库文件大小
            - index_size_bytes: FAISS 索引文件大小
            - cache_dir: 缓存目录
        """
        with self._lock:
            hits = self._hits
            misses = self._misses

        total = hits + misses
        hit_rate = hits / total if total > 0 else 0.0

        # 文件大小
        db_size = 0
        index_size = 0
        try:
            if os.path.exists(self._db_path):
                db_size = os.path.getsize(self._db_path)
            if os.path.exists(self._index_path):
                index_size = os.path.getsize(self._index_path)
        except OSError:
            pass

        # SQLite 条目数
        entry_count = 0
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM embeddings"
                ).fetchone()
                if row:
                    entry_count = row[0]
        except Exception:
            pass

        return {
            "total_entries": entry_count,
            "faiss_entries": self._vector_index.ntotal,
            "hits": hits,
            "misses": misses,
            "total_queries": total,
            "hit_rate": round(hit_rate, 4),
            "db_size_bytes": db_size,
            "index_size_bytes": index_size,
            "db_path": self._db_path,
            "index_path": self._index_path,
            "cache_dir": self._cache_dir,
        }

    # ------------------------------------------------------------------
    # 管理方法
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """清空所有缓存条目、FAISS 索引和统计计数"""
        try:
            # 清空 SQLite
            with self._get_conn() as conn:
                conn.execute("DELETE FROM embeddings")
                conn.commit()

            # 重置 FAISS
            self._vector_index.reset()

            # 重置统计
            with self._lock:
                self._hits = 0
                self._misses = 0

            logger.info("[VectorBackedEmbedding] 缓存已清空")
        except Exception as e:
            logger.warning("[VectorBackedEmbedding] 清空缓存失败: %s", e)

    def close(self) -> None:
        """关闭缓存（持久化 FAISS 索引并清理资源）"""
        try:
            # 保存 FAISS 索引
            self._vector_index.save(self._index_path)

            # SQLite WAL checkpoint (使用独立连接)
            conn = sqlite3.connect(self._db_path, timeout=10)
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                conn.close()

            import gc
            gc.collect()

            logger.info("[VectorBackedEmbedding] 已关闭并持久化")
        except Exception as e:
            logger.warning("[VectorBackedEmbedding] 关闭失败: %s", e)

    def save_index(self, path: Optional[str] = None) -> None:
        """
        显式保存 FAISS 索引到磁盘。

        Args:
            path: 保存路径（默认使用初始化时的路径）
        """
        save_path = path or self._index_path
        self._vector_index.save(save_path)
        logger.info(
            "[VectorBackedEmbedding] FAISS 索引已保存: %s", save_path
        )

    # ------------------------------------------------------------------
    # Dunder 方法
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """缓存条目数 (SQLite)"""
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM embeddings"
                ).fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def __bool__(self) -> bool:
        """VectorBackedEmbedding 实例始终为 truthy"""
        return True

    def __contains__(self, text: str) -> bool:
        """检查文本是否在缓存中"""
        return self.get(text) is not None

    def __repr__(self) -> str:
        return (
            f"VectorBackedEmbedding(db={self._db_path}, "
            f"index={self._index_path}, "
            f"entries={len(self)}, "
            f"faiss_ntotal={self._vector_index.ntotal}, "
            f"dim={self._dimension}, "
            f"hits={self._hits}, misses={self._misses})"
        )


# ---------------------------------------------------------------------------
# 内置验证 / 快速测试
# ---------------------------------------------------------------------------


def _verify() -> None:
    """快速验证模块语法和基本功能"""
    import random
    import tempfile

    print("=" * 60)
    print("[验证] VectorBackedEmbedding FAISS+SQLite 双存缓存")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. 创建实例
        dim = 4
        vbe = VectorBackedEmbedding(cache_dir=tmpdir, dimension=dim)
        assert vbe is not None
        print("\n1. ✓ VectorBackedEmbedding 创建成功 (dim=%d)" % dim)

        # 2. 单条 store/retrieve
        texts = [
            "链客宝企业数据平台",
            "BGE-M3 多语言嵌入模型",
            "FAISS 向量索引测试",
        ]
        rng = random.Random(42)
        vectors = [
            [round(rng.gauss(0, 1), 6) for _ in range(dim)]
            for _ in texts
        ]

        for t, v in zip(texts, vectors):
            vbe.store(t, v)
        print("2. ✓ 单条 store (set) 写入成功")

        for t, expected in zip(texts, vectors):
            got = vbe.retrieve(t)
            assert got is not None, f"读取失败: {t}"
            assert got == expected, f"向量不匹配: {t}"
        print("3. ✓ 单条 retrieve (get) 读取成功")

        # 4. 未命中
        miss = vbe.retrieve("不存在的文本")
        assert miss is None
        print("4. ✓ 未命中返回 None")

        # 5. 批量写入和读取
        more_texts = ["批量测试A", "批量测试B", "批量测试C"]
        more_vectors = [
            [round(rng.gauss(0, 1), 6) for _ in range(dim)]
            for _ in more_texts
        ]
        vbe.batch_set(list(zip(more_texts, more_vectors)))

        query_texts = texts + more_texts + ["不存在的D"]
        results = vbe.batch_query(query_texts)
        assert len(results) == len(query_texts)
        assert results[-1] is None
        assert results[0] is not None
        print("5. ✓ 批量 batch_query (batch_get) 成功")

        # 6. 统计
        stats = vbe.stats()
        assert stats["hits"] > 0
        assert stats["misses"] > 0
        assert stats["hit_rate"] > 0
        assert stats["total_entries"] >= len(texts) + len(more_texts)
        assert stats["faiss_entries"] >= len(texts) + len(more_texts)
        print("6. ✓ 统计信息: %d 条目, FAISS %d 条, 命中率 %.1f%%" % (
            stats["total_entries"], stats["faiss_entries"],
            stats["hit_rate"] * 100,
        ))

        # 7. 向量搜索 (ANN)
        # 使用原始（未归一化）向量搜索；search() 内部会归一化
        query_vec = vectors[0]

        distances, indices = vbe.search(query_vec, k=3)
        # 单向量搜索时返回形状为 (k,) 或 (1, k)
        assert len(distances) == 3 or distances.shape[1] == 3
        print("7. ✓ ANN 搜索 Top-3 成功")

        # 8. search_with_text
        results_with_text = vbe.search_with_text(query_vec, k=3)
        assert len(results_with_text) == 3
        assert "faiss_id" in results_with_text[0]
        assert "score" in results_with_text[0]
        assert "key_hash" in results_with_text[0]
        print("8. ✓ search_with_text 返回结构化结果成功")

        # 9. 空输入
        assert vbe.batch_query([]) == []
        vbe.batch_set([])
        print("9. ✓ 空输入处理正确")

        # 10. 覆盖写入
        overwrite_vec = [0.0] * dim
        vbe.store(texts[0], overwrite_vec)
        got = vbe.retrieve(texts[0])
        assert got == overwrite_vec
        print("10. ✓ 覆盖写入正确")

        # 11. persisted_size 和 close/save
        vbe.save_index()
        assert os.path.exists(vbe._index_path)
        print("11. ✓ save_index 持久化成功")

        # 12. clear
        vbe.clear()
        assert len(vbe) == 0
        assert vbe.retrieve(texts[0]) is None
        print("12. ✓ clear 清空成功")

    print("\n" + "=" * 60)
    print("所有验证通过 ✓")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _verify()
