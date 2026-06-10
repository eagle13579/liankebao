"""
链客宝AI向量搜索引擎 — M3E本地模型 + API 多模式
==============================================

功能:
  1. 向量搜索：embed_text(text) → embedding，search(query, index) → top-k
  2. 重排序：rerank(query, bm25_results) → 混合排序结果
  3. 多种 embedding 后端切换:
     - "m3e"（默认，使用 sentence-transformers 本地 M3E 模型，768维）
     - "numpy"（零外部依赖，模拟 embedding，降级用）
     - "openai"  — OpenAI text-embedding-3-small API
     - "deepseek" — DeepSeek embedding API

环境变量:
  USE_VECTOR_SEARCH=0|1           (默认: 0，关闭)
  EMBEDDING_PROVIDER=m3e|numpy|openai|deepseek  (默认: m3e)
  EMBEDDING_API_KEY=xxx           (OpenAI / DeepSeek API Key)
  EMBEDDING_MODEL=xxx             (模型名，默认根据 provider 自动选择)
  EMBEDDING_DIM=768               (向量维度，m3e 默认 768)
  VECTOR_TOP_K=50                 (向量搜索返回数量，默认 50)
  RERANK_WEIGHT=0.3              (向量重排序权重 0~1，默认 0.3，BM25=0.7)
"""

import hashlib
import logging
import os
import re
import sqlite3
import time
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ======================================================================
# 持久化数据库路径
# ======================================================================
INDEX_DB_DIR = os.environ.get(
    "VECTOR_INDEX_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
)
INDEX_DB_NAME = "vector_index.db"
INDEX_DB_PATH = os.path.join(INDEX_DB_DIR, INDEX_DB_NAME)

# ======================================================================
# 环境变量配置
# ======================================================================
USE_VECTOR_SEARCH = os.environ.get("USE_VECTOR_SEARCH", "0") == "1"
EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "m3e").lower()
EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "768"))
VECTOR_TOP_K = int(os.environ.get("VECTOR_TOP_K", "50"))
RERANK_WEIGHT = float(os.environ.get("RERANK_WEIGHT", "0.3"))


# ======================================================================
# Embedding 后端工厂
# ======================================================================


class EmbeddingBackend:
    """Embedding 后端抽象基类"""

    def embed(self, texts: list[str]) -> np.ndarray:
        """将文本列表转为 embedding 矩阵 (n_texts, dim)"""
        raise NotImplementedError

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIM

    @property
    def name(self) -> str:
        return "base"


class NumpyEmbedding(EmbeddingBackend):
    """numpy 模拟 embedding — 零外部依赖

    使用 TF-IDF 风格的词频直方图 + 随机投影，确保:
    - 相同文本得到一致向量
    - 语义相近文本向量相近（通过词重叠）
    - 无需任何外部依赖
    """

    def __init__(self, dim: int = EMBEDDING_DIM):
        self._dim = dim
        # 伪随机但固定的投影矩阵（用 hash 保证确定性）
        rng = np.random.RandomState(42)
        self._projection = rng.randn(5000, dim).astype(np.float32)
        self._projection /= np.linalg.norm(self._projection, axis=1, keepdims=True) + 1e-8

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def name(self) -> str:
        return "numpy"

    def _tokenize(self, text: str) -> dict[str, float]:
        """简单分词并计算词频（TF）"""
        if not text:
            return {}
        text = text.lower().strip()
        # 中文按字 + 双字组合
        tokens = {}
        # 单字
        for ch in re.findall(r"[\u4e00-\u9fff]", text):
            tokens[ch] = tokens.get(ch, 0) + 1
        # 双字
        chars = re.findall(r"[\u4e00-\u9fff]", text)
        for i in range(len(chars) - 1):
            bigram = chars[i] + chars[i + 1]
            tokens[bigram] = tokens.get(bigram, 0) + 1
        # 英文/数字词
        for word in re.findall(r"[a-zA-Z0-9]{2,}", text):
            tokens[word] = tokens.get(word, 0) + 1
        # 归一化 TF
        total = sum(tokens.values()) or 1
        return {k: v / total for k, v in tokens.items()}

    def _hash_feature(self, token: str) -> int:
        """将 token 哈希到 [0, 5000) 空间"""
        return abs(hash(token)) % 5000

    def embed(self, texts: list[str]) -> np.ndarray:
        """生成模拟 embedding

        策略: 将文本的 TF 向量通过随机投影映射到低维空间。
        相同文本 → 相同向量；词重叠多 → 向量夹角小。
        """
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)

        embeddings = []
        for text in texts:
            tf = self._tokenize(text)
            if not tf:
                embeddings.append(np.zeros(self._dim, dtype=np.float32))
                continue

            # 构建稀疏 TF 向量 (5000 维)
            sparse = np.zeros(5000, dtype=np.float32)
            for token, weight in tf.items():
                idx = self._hash_feature(token)
                sparse[idx] += weight

            # 随机投影降维
            vec = sparse @ self._projection  # (dim,)
            # L2 归一化
            norm = np.linalg.norm(vec)
            if norm > 1e-8:
                vec = vec / norm
            embeddings.append(vec)

        return np.array(embeddings, dtype=np.float32)


class M3EEmbedding(EmbeddingBackend):
    """M3E 本地模型 embedding — 使用 sentence-transformers

    方案B：M3E (moka-ai/m3e-base) 本地模型，768维。
    零API成本，纯本地运行。
    """

    def __init__(self):
        self._dim = 768
        self._model = None
        self._model_name = EMBEDDING_MODEL or "moka-ai/m3e-base"

    def _load_model(self):
        """惰性加载 M3E 模型（仅在首次 embed 时加载）"""
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"正在加载 M3E 模型: {self._model_name}")
            self._model = SentenceTransformer(self._model_name)
            logger.info(f"M3E 模型加载完成: {self._model_name}")
        except Exception as e:
            logger.error(f"M3E 模型加载失败: {e}，将使用 numpy 回退")
            self._model = None

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def name(self) -> str:
        return "m3e"

    def embed(self, texts: list[str]) -> np.ndarray:
        """使用 M3E 模型生成 embedding"""
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)

        self._load_model()
        if self._model is None:
            logger.warning("M3E 模型不可用，使用 numpy 回退")
            return NumpyEmbedding(self._dim).embed(texts)

        try:
            # 过滤空文本
            valid_texts = [t.strip() for t in texts]
            valid_indices = [i for i, t in enumerate(valid_texts) if t]
            if not valid_indices:
                return np.zeros((len(texts), self._dim), dtype=np.float32)

            # 批量 encode
            embeddings = self._model.encode(
                [valid_texts[i] for i in valid_indices],
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            # 确保是 float32
            if hasattr(embeddings, "numpy"):
                embeddings = embeddings.numpy()
            embeddings = np.asarray(embeddings, dtype=np.float32)

            # 对空文本补零向量
            all_embeddings = np.zeros((len(texts), self._dim), dtype=np.float32)
            for idx, emb in zip(valid_indices, embeddings):
                all_embeddings[idx] = emb

            return all_embeddings

        except Exception as e:
            logger.error(f"M3E embedding 调用失败: {e}，回退到 numpy")
            return NumpyEmbedding(self._dim).embed(texts)


class OpenAIEmbedding(EmbeddingBackend):
    """OpenAI embedding API 后端"""

    def __init__(self):
        self._api_key = EMBEDDING_API_KEY or os.environ.get("OPENAI_API_KEY", "")
        self._model = EMBEDDING_MODEL or "text-embedding-3-small"
        self._dim = 1536 if "3-small" in self._model else 3072
        self._client = None
        self._init_client()

    def _init_client(self):
        """惰性初始化 OpenAI 客户端"""
        if self._client is not None:
            return
        try:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key)
            logger.info(f"OpenAI embedding 客户端已初始化 (model={self._model})")
        except ImportError:
            logger.warning("openai 库未安装，回退到 numpy embedding。安装: pip install openai")
        except Exception as e:
            logger.warning(f"OpenAI 客户端初始化失败: {e}")

    @property
    def name(self) -> str:
        return "openai"

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> np.ndarray:
        """调用 OpenAI Embedding API"""
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        if self._client is None:
            logger.warning("OpenAI 客户端不可用，使用 numpy 回退")
            return NumpyEmbedding(self._dim).embed(texts)

        try:
            # 过滤空文本
            valid_texts = [t.strip() for t in texts]
            valid_indices = [i for i, t in enumerate(valid_texts) if t]
            if not valid_indices:
                return np.zeros((len(texts), self._dim), dtype=np.float32)

            response = self._client.embeddings.create(
                model=self._model,
                input=[valid_texts[i] for i in valid_indices],
            )
            # 解析响应
            all_embeddings = [None] * len(texts)
            for idx, data in zip(valid_indices, response.data):
                all_embeddings[idx] = data.embedding

            # 空文本用零向量
            result = np.array(
                [emb if emb is not None else [0.0] * self._dim for emb in all_embeddings], dtype=np.float32
            )

            # L2 归一化
            norms = np.linalg.norm(result, axis=1, keepdims=True)
            norms = np.where(norms > 1e-8, norms, 1.0)
            return result / norms

        except Exception as e:
            logger.error(f"OpenAI embedding API 调用失败: {e}，回退到 numpy")
            return NumpyEmbedding(self._dim).embed(texts)


class DeepSeekEmbedding(EmbeddingBackend):
    """DeepSeek embedding API 后端 (兼容 OpenAI 接口)"""

    def __init__(self):
        self._api_key = EMBEDDING_API_KEY or os.environ.get("DEEPSEEK_API_KEY", "")
        self._model = EMBEDDING_MODEL or "text-embedding-v2"
        self._dim = 1024
        self._base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self._client = None
        self._init_client()

    def _init_client(self):
        if self._client is not None:
            return
        try:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
            logger.info(f"DeepSeek embedding 客户端已初始化 (model={self._model}, base_url={self._base_url})")
        except ImportError:
            logger.warning("openai 库未安装，回退到 numpy embedding")
        except Exception as e:
            logger.warning(f"DeepSeek 客户端初始化失败: {e}")

    @property
    def name(self) -> str:
        return "deepseek"

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> np.ndarray:
        """调用 DeepSeek Embedding API"""
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        if self._client is None:
            logger.warning("DeepSeek 客户端不可用，使用 numpy 回退")
            return NumpyEmbedding(self._dim).embed(texts)

        try:
            valid_texts = [t.strip() for t in texts]
            valid_indices = [i for i, t in enumerate(valid_texts) if t]
            if not valid_indices:
                return np.zeros((len(texts), self._dim), dtype=np.float32)

            response = self._client.embeddings.create(
                model=self._model,
                input=[valid_texts[i] for i in valid_indices],
            )
            all_embeddings = [None] * len(texts)
            for idx, data in zip(valid_indices, response.data):
                all_embeddings[idx] = data.embedding

            result = np.array(
                [emb if emb is not None else [0.0] * self._dim for emb in all_embeddings], dtype=np.float32
            )

            norms = np.linalg.norm(result, axis=1, keepdims=True)
            norms = np.where(norms > 1e-8, norms, 1.0)
            return result / norms

        except Exception as e:
            logger.error(f"DeepSeek embedding API 调用失败: {e}，回退到 numpy")
            return NumpyEmbedding(self._dim).embed(texts)


# ======================================================================
# Embedding 引擎工厂
# ======================================================================

_embedding_backend: EmbeddingBackend | None = None


def get_embedding_backend() -> EmbeddingBackend:
    """获取 embedding 后端实例（单例）"""
    global _embedding_backend

    if _embedding_backend is not None:
        return _embedding_backend

    provider = EMBEDDING_PROVIDER
    logger.info(f"向量搜索: embedding_provider={provider}")

    if provider == "openai":
        _embedding_backend = OpenAIEmbedding()
    elif provider == "deepseek":
        _embedding_backend = DeepSeekEmbedding()
    elif provider == "m3e":
        _embedding_backend = M3EEmbedding()
    else:  # numpy (fallback)
        _embedding_backend = NumpyEmbedding(EMBEDDING_DIM)

    logger.info(f"Embedding 后端已初始化: {_embedding_backend.name}, dim={_embedding_backend.dimension}")
    return _embedding_backend


def embed_text(text: str | list[str]) -> np.ndarray:
    """对外接口：embed 文本

    Args:
        text: 单个字符串或字符串列表

    Returns:
        numpy array, shape (n, dim)
    """
    backend = get_embedding_backend()
    texts = [text] if isinstance(text, str) else text
    return backend.embed(texts)


# ======================================================================
# 向量搜索索引
# ======================================================================


class VectorSearchIndex:
    """向量搜索索引

    管理文档及其 embedding，支持向量相似度搜索。
    支持 SQLite 持久化存储 + 增量更新。
    """

    def __init__(self, db_path: str | None = None):
        self._documents: dict[int, dict[str, Any]] = {}  # id -> doc
        self._embeddings: dict[int, np.ndarray] = {}  # id -> embedding vector
        self._backend: EmbeddingBackend | None = None
        self._dirty = False
        self._db_path = db_path or INDEX_DB_PATH
        # 自动加载持久化数据
        self._init_db_table()
        self._auto_load()

    def _init_db_table(self) -> None:
        """初始化 SQLite 表结构（如果不存在）"""
        try:
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vector_index (
                    id INTEGER PRIMARY KEY,
                    content_hash TEXT UNIQUE NOT NULL,
                    content_type TEXT NOT NULL,
                    content_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vi_type_id
                ON vector_index(content_type, content_id)
            """)
            conn.commit()
            conn.close()
            logger.info(f"向量索引表已就绪: {self._db_path}")
        except Exception as e:
            logger.warning(f"向量索引表初始化失败: {e}")

    def _auto_load(self) -> bool:
        """从 SQLite 自动加载持久化数据，跳过重建"""
        try:
            count = self.load_index(self._db_path)
            if count > 0:
                logger.info(f"向量索引从持久化存储加载完成: {count} 条记录")
                return True
            logger.info("向量索引持久化存储为空，需要重建")
            return False
        except Exception as e:
            logger.warning(f"向量索引自动加载失败: {e}，将重建")
            return False

    @property
    def size(self) -> int:
        return len(self._documents)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "engine": "vector_search",
            "provider": get_embedding_backend().name,
            "dimension": get_embedding_backend().dimension,
            "documents": self.size,
            "enabled": USE_VECTOR_SEARCH,
            "rerank_weight": RERANK_WEIGHT,
            "db_path": self._db_path,
            "persisted": True,
        }

    def _compute_content_hash(self, text: str) -> str:
        """计算文本的 MD5 哈希"""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def add_document(self, doc_id: int, text: str, metadata: dict[str, Any] | None = None) -> None:
        """添加文档及其 embedding"""
        backend = get_embedding_backend()

        self._documents[doc_id] = {
            "id": doc_id,
            "text": text,
            "metadata": metadata or {},
        }

        # 生成 embedding
        vec = backend.embed([text])[0]
        self._embeddings[doc_id] = vec
        self._dirty = True

    def remove_document(self, doc_id: int) -> None:
        """删除文档"""
        self._documents.pop(doc_id, None)
        self._embeddings.pop(doc_id, None)
        self._dirty = True

    def clear(self) -> None:
        """清空索引"""
        self._documents.clear()
        self._embeddings.clear()
        self._dirty = True

    def save_index(self, db_path: str | None = None) -> int:
        """将向量数据写入 SQLite 持久化存储

        Args:
            db_path: SQLite 数据库路径，默认使用 INDEX_DB_PATH

        Returns:
            写入的记录数
        """
        path = db_path or self._db_path
        count = 0
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            conn = sqlite3.connect(path)
            # 确保表存在
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vector_index (
                    id INTEGER PRIMARY KEY,
                    content_hash TEXT UNIQUE NOT NULL,
                    content_type TEXT NOT NULL,
                    content_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vi_type_id
                ON vector_index(content_type, content_id)
            """)

            now = time.strftime("%Y-%m-%d %H:%M:%S")
            for doc_id, doc in self._documents.items():
                metadata = doc.get("metadata", {})
                content_type = metadata.get("content_type", "unknown")
                content_id = metadata.get("content_id", doc_id)
                content = doc.get("text", "")
                content_hash = self._compute_content_hash(content)
                vec = self._embeddings.get(doc_id)
                if vec is None:
                    continue
                embedding_blob = vec.astype(np.float32).tobytes()

                # 先按 content_type+content_id 删除旧记录，再插入新记录
                conn.execute(
                    "DELETE FROM vector_index WHERE content_type=? AND content_id=?",
                    (content_type, content_id),
                )
                conn.execute(
                    """
                    INSERT INTO vector_index
                        (content_hash, content_type, content_id, content, embedding, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (content_hash, content_type, content_id, content, embedding_blob, now),
                )
                count += 1

            conn.commit()
            conn.close()
            self._dirty = False
            logger.info(f"向量索引持久化完成: {count} 条记录写入 {path}")
        except Exception as e:
            logger.error(f"向量索引持久化失败: {e}")
        return count

    def load_index(self, db_path: str | None = None) -> int:
        """从 SQLite 加载向量数据到内存

        Args:
            db_path: SQLite 数据库路径，默认使用 INDEX_DB_PATH

        Returns:
            加载的记录数
        """
        path = db_path or self._db_path
        count = 0
        try:
            if not os.path.isfile(path):
                logger.info(f"向量索引数据库不存在: {path}")
                return 0

            conn = sqlite3.connect(path)
            rows = conn.execute("""
                SELECT id, content_hash, content_type, content_id, content, embedding
                FROM vector_index
                ORDER BY id
            """).fetchall()

            self._documents.clear()
            self._embeddings.clear()

            for row in rows:
                row_id, content_hash, content_type, content_id, content, embedding_blob = row
                # 反序列化 embedding
                vec = np.frombuffer(embedding_blob, dtype=np.float32)
                # 使用与 add_or_update 一致的 doc_id 生成逻辑
                doc_id = hash(f"{content_type}:{content_id}") & 0x7FFFFFFF

                self._documents[doc_id] = {
                    "id": doc_id,
                    "text": content,
                    "metadata": {
                        "content_type": content_type,
                        "content_id": content_id,
                        "content_hash": content_hash,
                    },
                }
                self._embeddings[doc_id] = vec
                count += 1

            conn.close()
            logger.info(f"向量索引从持久化存储加载: {count} 条记录")
        except Exception as e:
            logger.error(f"向量索引加载失败: {e}")
        return count

    def add_or_update(
        self,
        content_type: str,
        content_id: int,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """增量添加或更新单条向量数据

        检查 content_hash，如果内容未变化则跳过计算。

        Args:
            content_type: 内容类型 ('product' | 'need')
            content_id: 内容 ID
            content: 文本内容
            metadata: 额外元数据

        Returns:
            True 表示已新增/更新，False 表示已存在且未变化
        """
        content_hash = self._compute_content_hash(content)

        # 检查数据库中是否已有且 hash 相同（内容未变化）
        try:
            conn = sqlite3.connect(self._db_path)
            existing = conn.execute(
                "SELECT id, content_hash FROM vector_index WHERE content_type=? AND content_id=?",
                (content_type, content_id),
            ).fetchone()
            if existing:
                if existing[1] == content_hash:
                    conn.close()
                    logger.debug(f"向量索引跳过（内容未变化）: {content_type}#{content_id}")
                    return False
                # 内容已变化，先删除旧记录
                conn.execute(
                    "DELETE FROM vector_index WHERE content_type=? AND content_id=?",
                    (content_type, content_id),
                )
            conn.commit()
            conn.close()
        except Exception:
            pass

        # 生成 embedding
        meta = {
            "content_type": content_type,
            "content_id": content_id,
            "content_hash": content_hash,
            **(metadata or {}),
        }
        # 使用组合 ID 避免冲突
        doc_id = hash(f"{content_type}:{content_id}") & 0x7FFFFFFF

        # 如果内存中已存在，先移除旧的
        if doc_id in self._documents:
            self._documents.pop(doc_id, None)
            self._embeddings.pop(doc_id, None)

        self.add_document(doc_id, content, meta)

        # 立即持久化
        self.save_index()
        logger.info(f"向量索引已更新: {content_type}#{content_id}")
        return True

    def delete(self, content_type: str, content_id: int) -> bool:
        """删除单条向量数据

        Args:
            content_type: 内容类型 ('product' | 'need')
            content_id: 内容 ID

        Returns:
            True 表示已删除
        """
        # 从内存中删除
        doc_id = hash(f"{content_type}:{content_id}") & 0x7FFFFFFF
        removed = False
        if doc_id in self._documents:
            self._documents.pop(doc_id, None)
            self._embeddings.pop(doc_id, None)
            removed = True

        # 从 SQLite 中删除
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "DELETE FROM vector_index WHERE content_type=? AND content_id=?",
                (content_type, content_id),
            )
            conn.commit()
            conn.close()
            removed = True
            logger.info(f"向量索引已删除: {content_type}#{content_id}")
        except Exception as e:
            logger.warning(f"向量索引删除失败: {e}")

        return removed

    def has_entry(self, content_type: str, content_id: int) -> bool:
        """检查是否存在向量索引条目"""
        # 先检查 SQLite（权威数据源）
        try:
            conn = sqlite3.connect(self._db_path)
            existing = conn.execute(
                "SELECT 1 FROM vector_index WHERE content_type=? AND content_id=?",
                (content_type, content_id),
            ).fetchone()
            conn.close()
            if existing is not None:
                return True
        except Exception:
            pass
        # 再检查内存
        doc_id = hash(f"{content_type}:{content_id}") & 0x7FFFFFFF
        return doc_id in self._documents

    def search(self, query: str, top_k: int = VECTOR_TOP_K) -> list[dict[str, Any]]:
        """向量搜索：按余弦相似度返回 top-k 文档

        Args:
            query: 搜索查询
            top_k: 返回结果数量

        Returns:
            [{"id": int, "text": str, "metadata": dict, "score": float}, ...]
        """
        if not query or not query.strip() or not self._documents:
            return []

        backend = get_embedding_backend()
        query_vec = backend.embed([query])[0]

        # 计算所有余弦相似度
        results = []
        for doc_id, doc_vec in self._embeddings.items():
            # 余弦相似度（向量已 L2 归一化）
            similarity = float(np.dot(query_vec, doc_vec))
            results.append(
                {
                    "id": doc_id,
                    "text": self._documents[doc_id]["text"],
                    "metadata": self._documents[doc_id]["metadata"],
                    "score": round(max(0.0, min(1.0, (similarity + 1.0) / 2.0)), 4),
                }
            )

        # 按分数降序排列
        results.sort(key=lambda r: -r["score"])
        return results[:top_k]


# ======================================================================
# 全局向量搜索索引单例
# ======================================================================

_vector_index: VectorSearchIndex | None = None


def get_vector_index() -> VectorSearchIndex:
    """获取向量搜索索引实例"""
    global _vector_index
    if _vector_index is None:
        _vector_index = VectorSearchIndex()
    return _vector_index


def build_document_text(
    title: str = "",
    content: str = "",
    category: str = "",
    tags: str = "",
    brand: str = "",
) -> str:
    """构建用于 embedding 的文档文本（多字段拼接）"""
    parts = []
    if title:
        parts.append(f"标题: {title}")
    if content:
        parts.append(f"描述: {content}")
    if category:
        parts.append(f"分类: {category}")
    if tags:
        parts.append(f"标签: {tags}")
    if brand:
        parts.append(f"品牌: {brand}")
    return " | ".join(parts)


# ======================================================================
# 重排序 (Rerank)
# ======================================================================


def rerank(
    query: str,
    bm25_results: list[dict[str, Any]],
    weight: float | None = None,
) -> list[dict[str, Any]]:
    """使用向量相似度对 BM25 搜索结果做重排序

    混合排序公式:
        final_score = (1 - weight) * bm25_norm + weight * vector_sim

    其中 bm25_norm 是 BM25 分数在 top-k 内的归一化值。

    Args:
        query: 原始搜索查询
        bm25_results: BM25 搜索结果列表（每项必须有 "id" 和 "score"）
        weight: 向量权重 (0~1)，默认 RERANK_WEIGHT

    Returns:
        重排序后的结果列表（附加 "_vector_score" 和 "_final_score" 字段）
    """
    if not USE_VECTOR_SEARCH or not query or not bm25_results:
        return bm25_results

    w = weight if weight is not None else RERANK_WEIGHT
    if w <= 0:
        return bm25_results

    backend = get_embedding_backend()
    query_vec = backend.embed([query])[0]

    # --- 1. 构建查询文本列表 ---
    # 从 BM25 结果中提取文本用于向量匹配
    texts = []
    for item in bm25_results:
        title = item.get("title", "")
        desc = item.get("description", "")
        tags = item.get("tags", "")
        category = item.get("category", "")
        brand = item.get("brand", "")
        texts.append(build_document_text(title, desc, category, tags, brand))

    # --- 2. 批量计算向量 ---
    if texts:
        doc_embeddings = backend.embed(texts)
    else:
        doc_embeddings = np.zeros((0, backend.dimension), dtype=np.float32)

    # --- 3. 计算向量相似度 ---
    vector_scores = np.dot(doc_embeddings, query_vec)  # 余弦相似度 (已 L2 归一化)
    # 映射到 [0, 1]
    vector_scores = np.clip((vector_scores + 1.0) / 2.0, 0.0, 1.0)

    # --- 4. 归一化 BM25 分数 ---
    bm25_scores = np.array([item.get("score", 0.0) for item in bm25_results], dtype=np.float32)
    bm25_max = bm25_scores.max()
    bm25_min = bm25_scores.min()
    if bm25_max > bm25_min:
        bm25_norm = (bm25_scores - bm25_min) / (bm25_max - bm25_min)
    else:
        bm25_norm = np.ones_like(bm25_scores)

    # --- 5. 混合排序 ---
    final_scores = (1.0 - w) * bm25_norm + w * vector_scores

    # --- 6. 重新排序 ---
    enriched = []
    for i, item in enumerate(bm25_results):
        enriched.append(
            {
                **item,
                "_vector_score": round(float(vector_scores[i]), 4),
                "_final_score": round(float(final_scores[i]), 4),
            }
        )

    enriched.sort(key=lambda r: -r["_final_score"])
    return enriched


# ======================================================================
# 兼容接口: 单条文本 embedding
# ======================================================================


def embed_single(text: str) -> list[float]:
    """单条文本 embedding（返回 Python list 便于序列化）"""
    backend = get_embedding_backend()
    vec = backend.embed([text])[0]
    return vec.tolist()


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """计算两条向量的余弦相似度"""
    a = np.array(vec1, dtype=np.float32)
    b = np.array(vec2, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-8 or norm_b < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ======================================================================
# 自动同步机制
# ======================================================================


def sync_vector_index(db_session=None) -> dict[str, int]:
    """扫描所有 products 和 needs，增量同步到向量索引

    检查 vector_index 中是否已有 → 只计算缺失的或内容变化的条目。

    Args:
        db_session: SQLAlchemy 数据库会话（可选）

    Returns:
        {"products_added": int, "needs_added": int, "products_skipped": int, "needs_skipped": int}
    """
    if not USE_VECTOR_SEARCH:
        logger.info("向量搜索未启用（USE_VECTOR_SEARCH=0），跳过同步")
        return {"products_added": 0, "needs_added": 0, "products_skipped": 0, "needs_skipped": 0}

    from app.database import SessionLocal as _SessionLocal

    close_session = False
    if db_session is None:
        db_session = _SessionLocal()
        close_session = True

    try:
        from app.models import BusinessNeed, Product

        index = get_vector_index()
        result = {"products_added": 0, "needs_added": 0, "products_skipped": 0, "needs_skipped": 0}

        # --- 同步 Products ---
        products = db_session.query(Product).filter(Product.status == "approved", Product.is_deleted == False).all()
        for p in products:
            content = build_document_text(
                title=p.name or "",
                content=p.description or "",
                category=p.category or "",
                tags=p.tags or "",
                brand=p.brand or "",
            )
            if not content:
                result["products_skipped"] += 1
                continue

            if index.has_entry("product", p.id):
                # 检查是否需要更新
                try:
                    import sqlite3

                    conn = sqlite3.connect(index._db_path)
                    existing = conn.execute(
                        "SELECT content_hash FROM vector_index WHERE content_type='product' AND content_id=?",
                        (p.id,),
                    ).fetchone()
                    conn.close()
                    if existing:
                        current_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
                        if existing[0] == current_hash:
                            result["products_skipped"] += 1
                            continue
                except Exception:
                    pass

            index.add_or_update("product", p.id, content)
            result["products_added"] += 1

        # --- 同步 Needs ---
        needs = db_session.query(BusinessNeed).filter(BusinessNeed.is_deleted == False).all()
        for n in needs:
            content = build_document_text(
                title=n.title or "",
                content=n.description or "",
                category=n.category or "",
            )
            if not content:
                result["needs_skipped"] += 1
                continue

            if index.has_entry("need", n.id):
                result["needs_skipped"] += 1
                continue

            index.add_or_update("need", n.id, content)
            result["needs_added"] += 1

        logger.info(
            f"向量索引同步完成: "
            f"products_added={result['products_added']}, "
            f"products_skipped={result['products_skipped']}, "
            f"needs_added={result['needs_added']}, "
            f"needs_skipped={result['needs_skipped']}"
        )
        return result

    except Exception as e:
        logger.error(f"向量索引同步失败: {e}", exc_info=True)
        return {"products_added": 0, "needs_added": 0, "products_skipped": 0, "needs_skipped": 0}
    finally:
        if close_session:
            db_session.close()


# ======================================================================
# 导出
# ======================================================================

__all__ = [
    "USE_VECTOR_SEARCH",
    "EMBEDDING_PROVIDER",
    "RERANK_WEIGHT",
    "INDEX_DB_PATH",
    "EmbeddingBackend",
    "NumpyEmbedding",
    "M3EEmbedding",
    "OpenAIEmbedding",
    "DeepSeekEmbedding",
    "VectorSearchIndex",
    "get_embedding_backend",
    "get_vector_index",
    "embed_text",
    "embed_single",
    "rerank",
    "build_document_text",
    "cosine_similarity",
    "sync_vector_index",
]
