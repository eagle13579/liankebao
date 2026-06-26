"""
链客宝 - 嵌入向量缓存层 (SQLite)
====================================
基于 SQLite 的嵌入向量持久化缓存，支持批量读写和命中统计。

能力:
1. EmbeddingCache 类 — SQLite 持久化缓存
2. get / set — 单条查询和写入
3. batch_get / batch_set — 批量操作
4. stats() — 缓存命中/未命中统计
5. 自动建表、线程安全

使用方式:
    from features.embedding_cache import EmbeddingCache

    cache = EmbeddingCache()
    vec = cache.get("某文本")
    if vec is None:
        vec = [0.1, 0.2, ...]
        cache.set("某文本", vec)

    stats = cache.stats()
    print(f"命中率: {stats['hit_rate']:.1%}")

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
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 默认缓存数据库路径
DEFAULT_CACHE_DIR = os.path.join(
    str(Path.home()), ".cache", "chainke"
)
DEFAULT_DB_NAME = "embeddings_cache.db"

# SQLite 批处理最大参数数量（SQLite 限制 ~999，我们留余量）
_MAX_SQLITE_VARS = 900


# ---------------------------------------------------------------------------
# 嵌入向量缓存
# ---------------------------------------------------------------------------


class EmbeddingCache:
    """
    SQLite 持久化嵌入向量缓存。

    使用文本的 SHA-256 哈希作为键，BLOB 存储序列化向量。
    线程安全（连接级锁），支持批量读写和命中统计。

    Examples
    --------
    >>> cache = EmbeddingCache()
    >>> cache.set("hello", [0.1, 0.2, 0.3])
    >>> vec = cache.get("hello")
    >>> vec[:2]
    [0.1, 0.2]
    >>> cache.stats()["hits"]
    1
    """

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        """
        Args:
            cache_dir: 缓存目录，默认 ~/.cache/chainke/
        """
        self._cache_dir = cache_dir or DEFAULT_CACHE_DIR
        os.makedirs(self._cache_dir, exist_ok=True)
        self._db_path = os.path.join(self._cache_dir, DEFAULT_DB_NAME)

        # 统计计数器
        self._hits: int = 0
        self._misses: int = 0
        self._lock = threading.Lock()

        # 初始化数据库
        self._init_db()

        logger.info("[EmbeddingCache] 初始化完成: %s", self._db_path)

    # ------------------------------------------------------------------
    # 数据库初始化
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """创建数据库和表（如不存在）"""
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                    key_hash TEXT PRIMARY KEY,
                    vector_blob BLOB NOT NULL,
                    created_at REAL NOT NULL DEFAULT (julianday('now'))
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_embeddings_hash "
                "ON embeddings(key_hash)"
            )
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（每次调用新建，确保线程安全）"""
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    # ------------------------------------------------------------------
    # 哈希工具
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
    # 单条操作
    # ------------------------------------------------------------------

    def get(self, text: str) -> Optional[List[float]]:
        """
        查询缓存的嵌入向量。

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
                    logger.debug("[EmbeddingCache] 命中: %s...", text[:20])
                    return vec
        except Exception as e:
            logger.warning("[EmbeddingCache] 查询失败: %s", e)

        with self._lock:
            self._misses += 1
        return None

    def set(self, text: str, vector: List[float]) -> None:
        """
        写入嵌入向量到缓存。

        Args:
            text: 文本
            vector: 嵌入向量
        """
        key = self._hash(text)
        blob = self._serialize(vector)
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO embeddings (key_hash, vector_blob, created_at) "
                    "VALUES (?, ?, julianday('now'))",
                    (key, blob),
                )
                conn.commit()
        except Exception as e:
            logger.warning("[EmbeddingCache] 写入失败: %s", e)

    # ------------------------------------------------------------------
    # 批量操作
    # ------------------------------------------------------------------

    def batch_get(self, texts: Sequence[str]) -> List[Optional[List[float]]]:
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

        # 构建哈希到文本的映射
        text_list = list(texts)
        hash_to_text: Dict[str, str] = {}
        for t in text_list:
            h = self._hash(t)
            hash_to_text[h] = t

        hashes = list(hash_to_text.keys())
        results: List[Optional[List[float]]] = [None] * len(text_list)

        # 分批查询以避免 SQLite 参数限制
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
                    # 构建哈希→向量映射
                    db_map: Dict[str, List[float]] = {}
                    for h, blob in rows:
                        db_map[h] = self._deserialize(blob)
                    # 填充结果
                    for idx, t in enumerate(text_list):
                        h = self._hash(t)
                        if h in db_map:
                            results[idx] = db_map[h]
                            hit_count += 1
            except Exception as e:
                logger.warning("[EmbeddingCache] 批量查询失败: %s", e)

        with self._lock:
            self._hits += hit_count
            self._misses += len(texts) - hit_count

        logger.debug(
            "[EmbeddingCache] 批量查询: %d 条, 命中 %d 条",
            len(texts), hit_count,
        )
        return results

    def batch_set(
        self, text_pairs: Sequence[Tuple[str, List[float]]]
    ) -> None:
        """
        批量写入嵌入向量到缓存。

        Args:
            text_pairs: (文本, 向量) 元组列表
        """
        if not text_pairs:
            return

        # 分批写入
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
                    "[EmbeddingCache] 批量写入失败 (批次 %d~%d): %s",
                    i, i + len(batch) - 1, e,
                )

        logger.debug(
            "[EmbeddingCache] 批量写入: %d 条", len(text_pairs)
        )

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息。

        Returns:
            dict 包含:
            - total_entries: 缓存条目总数
            - hits: 命中次数
            - misses: 未命中次数
            - total_queries: 总查询次数
            - hit_rate: 命中率 (0.0 ~ 1.0)
            - db_size_bytes: 数据库文件大小
            - db_path: 数据库路径
        """
        with self._lock:
            hits = self._hits
            misses = self._misses

        total = hits + misses
        hit_rate = hits / total if total > 0 else 0.0

        # 获取数据库大小
        db_size = 0
        try:
            db_size = os.path.getsize(self._db_path)
        except OSError:
            pass

        # 获取条目总数
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
            "hits": hits,
            "misses": misses,
            "total_queries": total,
            "hit_rate": round(hit_rate, 4),
            "db_size_bytes": db_size,
            "db_path": self._db_path,
        }

    # ------------------------------------------------------------------
    # 管理方法
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """清空所有缓存条目和统计计数"""
        try:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM embeddings")
                conn.commit()
            with self._lock:
                self._hits = 0
                self._misses = 0
            logger.info("[EmbeddingCache] 缓存已清空")
        except Exception as e:
            logger.warning("[EmbeddingCache] 清空缓存失败: %s", e)

    def close(self) -> None:
        """关闭缓存（清理资源）"""
        try:
            # 强制 WAL checkpoint，释放所有文件句柄
            with self._get_conn() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
            # 额外尝试关闭可能残留的连接
            import gc
            gc.collect()
        except Exception:
            pass

    def __len__(self) -> int:
        """缓存条目数"""
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM embeddings"
                ).fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def __bool__(self) -> bool:
        """EmbeddingCache 实例始终为 truthy（避免 __len__=0 时被当作 falsy）"""
        return True

    def __contains__(self, text: str) -> bool:
        """检查文本是否在缓存中"""
        return self.get(text) is not None

    def __repr__(self) -> str:
        return (
            f"EmbeddingCache(db={self._db_path}, "
            f"entries={len(self)}, "
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
    print("[验证] EmbeddingCache 嵌入向量缓存层")
    print("=" * 60)

    # 1. 使用临时目录创建缓存
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = EmbeddingCache(cache_dir=tmpdir)
        assert cache is not None
        print("\n1. ✓ EmbeddingCache 创建成功")

        # 2. 单条写入和读取
        texts = [
            "链客宝企业数据平台",
            "BGE-M3 多语言嵌入模型",
            "SQLite 向量缓存测试",
        ]
        dim = 4
        # 用确定性种子生成测试向量
        rng = random.Random(42)
        vectors = [[round(rng.gauss(0, 1), 6) for _ in range(dim)]
                   for _ in texts]

        for t, v in zip(texts, vectors):
            cache.set(t, v)
        print("2. ✓ 单条写入成功")

        # 3. 单条读取
        for t, expected in zip(texts, vectors):
            got = cache.get(t)
            assert got is not None, f"读取失败: {t}"
            assert got == expected, f"向量不匹配: {t}"
        print("3. ✓ 单条读取成功")

        # 4. 未命中测试
        miss = cache.get("不存在的文本")
        assert miss is None
        print("4. ✓ 未命中返回 None")

        # 5. 批量写入和读取
        more_texts = ["批量测试A", "批量测试B", "批量测试C"]
        more_vectors = [
            [round(rng.gauss(0, 1), 6) for _ in range(dim)]
            for _ in more_texts
        ]
        cache.batch_set(list(zip(more_texts, more_vectors)))

        # 混合批量读取（部分命中、部分未命中）
        query_texts = texts + more_texts + ["不存在的D"]
        results = cache.batch_get(query_texts)
        assert len(results) == len(query_texts)
        assert results[-1] is None  # 最后一个未命中
        assert results[0] is not None  # 第一个命中
        print("5. ✓ 批量读取成功（含混合命中/未命中）")

        # 6. 统计信息
        stats = cache.stats()
        assert stats["hits"] > 0
        assert stats["misses"] > 0
        assert stats["hit_rate"] > 0
        assert stats["total_entries"] >= len(texts) + len(more_texts)
        print(f"6. ✓ 统计信息: {stats['total_entries']} 条目, "
              f"命中率 {stats['hit_rate']:.1%}")

        # 7. 空输入
        empty_get = cache.batch_get([])
        assert empty_get == []
        cache.batch_set([])
        print("7. ✓ 空输入处理正确")

        # 8. 重复写入（覆盖）
        overwrite_vec = [0.0] * dim
        cache.set(texts[0], overwrite_vec)
        got = cache.get(texts[0])
        assert got == overwrite_vec
        print("8. ✓ 重复写入覆盖正确")

        # 9. clear
        cache.clear()
        assert cache.get(texts[0]) is None
        assert len(cache) == 0
        print("9. ✓ 清空缓存成功")

        # 10. 上下文包含
        cache.set("包含测试", [1.0, 2.0])
        assert "包含测试" in cache
        assert "不存在" not in cache
        print("10. ✓ __contains__ 工作正常")

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
    else:
        _verify()
