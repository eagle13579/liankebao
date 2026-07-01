"""
AI数字名片 向量搜索引擎 — M3E本地模型 + API 多后端
=================================================

移植自链客宝生产级向量搜索实现，兼容现有 VectorSearchEngine 接口。

功能:
  1. 多种 embedding 后端切换:
     - "m3e"（默认，使用 sentence-transformers 本地 M3E 模型，768维）
     - "numpy"（零外部依赖，模拟 embedding，降级用）
     - "openai"  — OpenAI text-embedding-3-small API
     - "deepseek" — DeepSeek embedding API
  2. 向量搜索：embed_text(text) → embedding，search(query, index) → top-k
  3. 重排序：rerank(query, candidates) → 混合排序结果
  4. SQLite 持久化索引（VectorSearchIndex）
  5. 兼容旧版 TF-IDF 接口（VectorSearchEngine 包装类）

配置项 (config.py):
  USE_VECTOR_SEARCH: bool = True
  EMBEDDING_PROVIDER: str = "m3e"   # m3e | numpy | openai | deepseek
  EMBEDDING_DIM: int = 768
  EMBEDDING_API_KEY: str = ""
  VECTOR_TOP_K: int = 50
"""

import hashlib
import logging
import os
import re
import sqlite3
import time
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.cache import cache
from app.models.brochure import Brochure, Page
from app.models.tag import UserTag
from app.models.user import User

logger = logging.getLogger(__name__)


# ======================================================================
# 配置（从 app.config 读取，同时支持环境变量覆盖）
# ======================================================================

try:
    from app.config import settings as _settings

    USE_VECTOR_SEARCH = getattr(_settings, "USE_VECTOR_SEARCH", True)
    EMBEDDING_PROVIDER = getattr(_settings, "EMBEDDING_PROVIDER", "m3e")
    EMBEDDING_API_KEY = getattr(_settings, "EMBEDDING_API_KEY", "")
    EMBEDDING_MODEL = getattr(_settings, "EMBEDDING_MODEL", "")
    EMBEDDING_DIM = int(getattr(_settings, "EMBEDDING_DIM", 768))
    VECTOR_TOP_K = int(getattr(_settings, "VECTOR_TOP_K", 50))
except Exception:
    # 降级：从环境变量读取
    USE_VECTOR_SEARCH = os.environ.get("USE_VECTOR_SEARCH", "1") == "1"
    EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "m3e").lower()
    EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", "")
    EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "")
    EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "768"))
    VECTOR_TOP_K = int(os.environ.get("VECTOR_TOP_K", "50"))

# 持久化数据库路径
INDEX_DB_DIR = os.environ.get(
    "VECTOR_INDEX_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
)
INDEX_DB_NAME = "vector_index.db"
INDEX_DB_PATH = os.path.join(INDEX_DB_DIR, INDEX_DB_NAME)
RERANK_WEIGHT = float(os.environ.get("RERANK_WEIGHT", "0.3"))


# ======================================================================
# Embedding 后端抽象基类
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


# ======================================================================
# NumpyEmbedding — 零外部依赖降级方案
# ======================================================================


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


# ======================================================================
# M3EEmbedding — 本地 M3E 模型
# ======================================================================


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


# ======================================================================
# OpenAIEmbedding — OpenAI API 后端
# ======================================================================


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

            # L2 归一化
            norms = np.linalg.norm(result, axis=1, keepdims=True)
            norms = np.where(norms > 1e-8, norms, 1.0)
            return result / norms

        except Exception as e:
            logger.error(f"OpenAI embedding API 调用失败: {e}，回退到 numpy")
            return NumpyEmbedding(self._dim).embed(texts)


# ======================================================================
# DeepSeekEmbedding — DeepSeek API 后端
# ======================================================================


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
# 向量搜索索引 (SQLite 持久化)
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
        return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()

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
            content_type: 内容类型 ('user' | 'brochure' | 'tag')
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
        """删除单条向量数据"""
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


# ======================================================================
# 文档构建器（仅用于用户文档，与 AI名片 DB schema 绑定）
# ======================================================================


class DocumentBuilder:
    """从数据库构建用户文档"""

    @staticmethod
    @cache(ttl=600, prefix="user_doc_str")
    def build_user_document(db: Session, user_id: int) -> str:
        """构建单个用户的文档字符串

        拼接：简介 + 标签(带类型) + brochure标题 + ai_summary + 内容片段
        """
        parts: list[str] = []

        # 1. 用户简介
        user = db.query(User).filter(User.id == user_id).first()
        if user and user.intro:
            parts.append(user.intro)

        # 2. 用户标签（含类型前缀，使 provide/need 语义可区分）
        tags = db.query(UserTag).filter(UserTag.user_id == user_id).all()
        for t in tags:
            type_label = "提供" if t.tag_type == "provide" else "需要"
            parts.append(f"{type_label}{t.tag}")

        # 3. Brochure 内容
        brochures = (
            db.query(Brochure)
            .filter(
                Brochure.user_id == user_id,
                Brochure.status == "published",
            )
            .all()
        )
        for brochure in brochures:
            if brochure.title:
                parts.append(brochure.title)
            pages = db.query(Page).filter(Page.brochure_id == brochure.id).all()
            for page in pages:
                if page.ai_summary:
                    parts.append(page.ai_summary)
                if page.content and len(page.content) > 10:
                    parts.append(page.content[:500])

        return " ".join(parts)

    @staticmethod
    @cache(ttl=600, prefix="all_docs")
    def build_all_documents(db: Session) -> tuple[list[str], list[int]]:
        """构建所有用户的文档列表

        Returns:
            (documents, user_ids)
        """
        documents: list[str] = []
        user_ids: list[int] = []

        all_users = db.query(User).all()
        for user in all_users:
            doc = DocumentBuilder.build_user_document(db, user.id)
            documents.append(doc)
            user_ids.append(user.id)

        return documents, user_ids


# ======================================================================
# 兼容包装类：VectorSearchEngine（保留旧版接口，内部使用新引擎）
# ======================================================================


class VectorSearchEngine:
    """向量搜索引擎 — 使用 M3E/多后端 embedding

    向后兼容旧的 VectorSearchEngine 接口（build_index, search, rerank, search_brochures）。

    用法:
        vse = VectorSearchEngine(db)
        vse.build_index()
        results = vse.search("Python全栈开发", top_k=10)
    """

    def __init__(self, db: Session):
        self.db = db
        self.user_vectors: list[np.ndarray] = []  # 改用 numpy array
        self.user_ids: list[int] = []
        self.documents: list[str] = []
        self._index_built = False
        self._backend = get_embedding_backend()
        self._vector_index = get_vector_index()

    # ── 构建索引 ──────────────────────────────────────────────────────────

    def build_index(self) -> None:
        """为所有用户构建向量索引 (使用 M3E/numpy embedding 替代 TF-IDF)"""
        self.documents, self.user_ids = DocumentBuilder.build_all_documents(self.db)

        if not self.documents:
            self._index_built = False
            return

        # 批量生成 embedding
        self.user_vectors = self._backend.embed(self.documents)
        self._index_built = True
        logger.info(f"向量索引构建完成: {len(self.user_ids)} 个用户, dim={self._backend.dimension}")

        # 同时写入持久化索引
        for i, uid in enumerate(self.user_ids):
            doc_id = hash(f"user:{uid}") & 0x7FFFFFFF
            self._vector_index.add_document(
                doc_id,
                self.documents[i],
                {"content_type": "user", "content_id": uid},
            )
        self._vector_index.save_index()

    # ── 搜索 ──────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.0,
        exclude_user_id: int | None = None,
    ) -> list[dict]:
        """语义搜索匹配的用户（使用向量 embedding）

        Args:
            query: 搜索文本（如 "Python全栈开发"）
            top_k: 返回结果数量上限
            min_score: 最低相似度阈值
            exclude_user_id: 排除的用户ID（如当前用户）

        Returns:
            [{user_id, user_name, company, title, avatar, score, ...}]
        """
        # 尝试从缓存读取
        cache_key = f"vec_search:{hash(query)}:{top_k}:{min_score}:{exclude_user_id or 0}"
        from app.cache.redis import get_redis

        _r = get_redis()
        if _r is not None:
            cached = _r.get(cache_key)
            if cached is not None:
                return cached

        if not self._index_built or not query.strip():
            return []

        # 对查询文本做向量化
        query_vec = self._backend.embed([query])[0]

        # 计算与每个用户文档的余弦相似度（向量已 L2 归一化，点积 = 余弦）
        scored: list[tuple[int, float]] = []
        for idx in range(len(self.user_ids)):
            uid = self.user_ids[idx]
            if exclude_user_id is not None and uid == exclude_user_id:
                continue
            similarity = float(np.dot(query_vec, self.user_vectors[idx]))
            # 映射到 [0, 1]
            score = max(0.0, min(1.0, (similarity + 1.0) / 2.0))
            if score >= min_score:
                scored.append((uid, score))

        # 按分数降序排序
        scored.sort(key=lambda x: x[1], reverse=True)

        # 构建结果
        results: list[dict] = []
        for uid, score in scored:
            user = self.db.query(User).filter(User.id == uid).first()
            if user is None:
                continue
            results.append(
                {
                    "user_id": user.id,
                    "user_name": user.name,
                    "user_company": user.company,
                    "user_title": user.title,
                    "user_avatar": user.avatar or "",
                    "score": round(score, 4),
                }
            )
            if len(results) >= top_k:
                break

        # 写入缓存
        if _r is not None and results:
            _r.set(cache_key, results, ttl=300)

        return results

    # ── 重排序 ────────────────────────────────────────────────────────────

    def rerank(
        self,
        candidates: list[dict],
        query: str,
        top_k: int | None = None,
    ) -> list[dict]:
        """对已有匹配结果做语义重排序（使用向量 embedding）

        Args:
            candidates: 已有的匹配结果列表（每项必须含 user_id）
            query: 查询文本
            top_k: 返回数量（默认全部）

        Returns:
            重排序后的结果列表（含原字段 + semantic_score）
        """
        if not candidates or not query.strip():
            return candidates

        # 为每个 candidate 构建文档
        temp_docs: list[str] = []
        for c in candidates:
            doc = DocumentBuilder.build_user_document(self.db, c["user_id"])
            temp_docs.append(doc)

        # 批量计算向量
        query_vec = self._backend.embed([query])[0]
        candidate_vecs = self._backend.embed(temp_docs)

        # 计算分数
        result: list[dict] = []
        for i, c in enumerate(candidates):
            similarity = float(np.dot(query_vec, candidate_vecs[i]))
            score = max(0.0, min(1.0, (similarity + 1.0) / 2.0))
            result.append(
                {
                    **c,
                    "semantic_score": round(score, 4),
                }
            )

        result.sort(key=lambda x: x["semantic_score"], reverse=True)

        if top_k is not None:
            result = result[:top_k]

        return result

    # ── Brochure 级别搜索 ─────────────────────────────────────────────────

    def search_brochures(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[dict]:
        """搜索匹配的名片（Brochure级别，使用向量 embedding）

        直接搜索 published 状态的 Brochure，返回匹配的 brochure + owner 信息。

        Args:
            query: 搜索文本
            top_k: 返回数量上限
            min_score: 最低相似度阈值

        Returns:
            [{brochure_id, title, user_id, user_name, score, matched_content, ...}]
        """
        if not query.strip():
            return []

        # 获取所有 published brochure
        brochures = self.db.query(Brochure).filter(Brochure.status == "published").all()

        if not brochures:
            return []

        # 构建每个 brochure 的文档
        brochure_docs: list[tuple[Brochure, str]] = []
        for b in brochures:
            parts: list[str] = []
            if b.title:
                parts.append(b.title)

            # 获取 owner 的信息
            user = self.db.query(User).filter(User.id == b.user_id).first()
            if user:
                if user.name:
                    parts.append(user.name)
                if user.intro:
                    parts.append(user.intro)
                if user.company:
                    parts.append(user.company)

            # 获取 pages
            pages = self.db.query(Page).filter(Page.brochure_id == b.id).all()
            for page in pages:
                if page.ai_summary:
                    parts.append(page.ai_summary)
                if page.content and len(page.content) > 10:
                    parts.append(page.content[:300])

            doc_text = " ".join(parts)
            brochure_docs.append((b, doc_text))

        # 批量计算向量
        query_vec = self._backend.embed([query])[0]

        # 先过滤掉空文档
        valid_docs = [(b, doc) for b, doc in brochure_docs if doc.strip()]
        if not valid_docs:
            return []

        valid_texts = [doc for _, doc in valid_docs]
        doc_vecs = self._backend.embed(valid_texts)

        # 计算相似度
        scored: list[tuple[Brochure, float]] = []
        for i, (b, doc) in enumerate(valid_docs):
            similarity = float(np.dot(query_vec, doc_vecs[i]))
            score = max(0.0, min(1.0, (similarity + 1.0) / 2.0))
            if score >= min_score:
                scored.append((b, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        results: list[dict] = []
        for b, score in scored:
            user = self.db.query(User).filter(User.id == b.user_id).first()
            results.append(
                {
                    "brochure_id": b.id,
                    "title": b.title,
                    "cover": b.cover or "",
                    "user_id": b.user_id,
                    "user_name": user.name if user else "",
                    "user_company": user.company if user else "",
                    "user_title": user.title if user else "",
                    "user_avatar": user.avatar if user else "",
                    "score": round(score, 4),
                }
            )
            if len(results) >= top_k:
                break

        return results

    # ── 语义相似度计算 ─────────────────────────────────────────────────────

    @staticmethod
    def compute_semantic_similarity(
        tags_a: list[str],
        tags_b: list[str],
        intro_a: str = "",
        intro_b: str = "",
    ) -> float:
        """计算两组标签/简介的语义相似度（使用向量 embedding）

        Args:
            tags_a: 用户A的标签列表
            tags_b: 用户B的标签列表
            intro_a: 用户A的简介
            intro_b: 用户B的简介

        Returns:
            余弦相似度 [0, 1]
        """
        doc_a = " ".join(tags_a) + " " + intro_a
        doc_b = " ".join(tags_b) + " " + intro_b

        if not doc_a.strip() or not doc_b.strip():
            return 0.0

        backend = get_embedding_backend()
        vecs = backend.embed([doc_a, doc_b])
        similarity = float(np.dot(vecs[0], vecs[1]))
        return max(0.0, min(1.0, (similarity + 1.0) / 2.0))

    # ── 统计信息 ──────────────────────────────────────────────────────────

    def get_index_stats(self) -> dict:
        """获取索引统计信息"""
        if not self._index_built:
            return {"status": "not_built", "user_count": 0}

        if not self.user_vectors:
            return {
                "status": "ready",
                "user_count": len(self.user_ids),
                "doc_count": len(self.documents),
                "engine": f"vector_search_{self._backend.name}",
            }

        return {
            "status": "ready",
            "user_count": len(self.user_ids),
            "doc_count": len(self.documents),
            "embedding_dim": self._backend.dimension,
            "engine": f"vector_search_{self._backend.name}",
            "provider": self._backend.name,
        }


# ======================================================================
# 重排序工具函数
# ======================================================================


def rerank(
    query: str,
    candidates: list[dict[str, Any]],
    weight: float | None = None,
) -> list[dict[str, Any]]:
    """使用向量相似度对候选结果做重排序

    混合排序公式:
        final_score = (1 - weight) * text_score_norm + weight * vector_sim

    Args:
        query: 原始搜索查询
        candidates: 候选结果列表（每项必须有 "score" 字段）
        weight: 向量权重 (0~1)，默认 RERANK_WEIGHT

    Returns:
        重排序后的结果列表（附加 "_vector_score" 和 "_final_score" 字段）
    """
    if not USE_VECTOR_SEARCH or not query or not candidates:
        return candidates

    w = weight if weight is not None else RERANK_WEIGHT
    if w <= 0:
        return candidates

    backend = get_embedding_backend()
    query_vec = backend.embed([query])[0]

    # 从候选结果中提取文本
    texts = []
    for item in candidates:
        parts = []
        for key in ("title", "description", "tags", "content", "text"):
            val = item.get(key, "")
            if val:
                parts.append(str(val))
        texts.append(" | ".join(parts))

    # 批量计算向量
    if texts:
        doc_embeddings = backend.embed(texts)
    else:
        doc_embeddings = np.zeros((0, backend.dimension), dtype=np.float32)

    # 计算向量相似度
    vector_scores = np.dot(doc_embeddings, query_vec)
    vector_scores = np.clip((vector_scores + 1.0) / 2.0, 0.0, 1.0)

    # 归一化原始分数
    orig_scores = np.array([item.get("score", 0.0) for item in candidates], dtype=np.float32)
    orig_max = orig_scores.max()
    orig_min = orig_scores.min()
    if orig_max > orig_min:
        orig_norm = (orig_scores - orig_min) / (orig_max - orig_min)
    else:
        orig_norm = np.ones_like(orig_scores)

    # 混合排序
    final_scores = (1.0 - w) * orig_norm + w * vector_scores

    # 重新排序
    enriched = []
    for i, item in enumerate(candidates):
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
# 自动同步机制：扫描所有用户，增量同步到向量索引
# ======================================================================


def sync_vector_index(db_session: Session | None = None) -> dict[str, int]:
    """扫描所有用户，增量同步到向量索引

    Args:
        db_session: SQLAlchemy 数据库会话（可选，不传则自动创建）

    Returns:
        {"users_added": int, "users_skipped": int}
    """
    if not USE_VECTOR_SEARCH:
        logger.info("向量搜索未启用，跳过同步")
        return {"users_added": 0, "users_skipped": 0}

    from app.database import SessionLocal as _SessionLocal

    close_session = False
    if db_session is None:
        db_session = _SessionLocal()
        close_session = True

    try:
        index = get_vector_index()
        result = {"users_added": 0, "users_skipped": 0}

        all_users = db_session.query(User).all()
        for user in all_users:
            doc = DocumentBuilder.build_user_document(db_session, user.id)
            if not doc.strip():
                result["users_skipped"] += 1
                continue

            if index.has_entry("user", user.id):
                # 检查 hash 是否变化
                try:
                    conn = sqlite3.connect(index._db_path)
                    existing = conn.execute(
                        "SELECT content_hash FROM vector_index WHERE content_type='user' AND content_id=?",
                        (user.id,),
                    ).fetchone()
                    conn.close()
                    if existing:
                        current_hash = hashlib.md5(doc.encode("utf-8"), usedforsecurity=False).hexdigest()
                        if existing[0] == current_hash:
                            result["users_skipped"] += 1
                            continue
                except Exception:
                    pass

            index.add_or_update("user", user.id, doc)
            result["users_added"] += 1

        logger.info(f"向量索引同步完成: added={result['users_added']}, skipped={result['users_skipped']}")
        return result

    except Exception as e:
        logger.error(f"向量索引同步失败: {e}", exc_info=True)
        return {"users_added": 0, "users_skipped": 0}
    finally:
        if close_session:
            db_session.close()


# ======================================================================
# 多轮循环收敛搜索（推荐引擎增强 — Fable5 RDT 注入点 1）
# ======================================================================


def search_with_convergence(
    query: str,
    index: VectorSearchIndex,
    top_k: int = VECTOR_TOP_K,
    max_rounds: int = 3,
    convergence_threshold: float = 0.95,
) -> dict[str, Any]:
    """多轮循环收敛的向量搜索 — 从单轮 embedding 点积升级为多轮循环收敛。

    将推荐引擎从单轮静态匹配升级为多轮动态收敛：
      - 第1轮：标准检索（余弦相似度，同原有 search 逻辑）
      - 第2轮：上下文融合 — 用第1轮 top-5 结果文本增强查询，重新检索
      - 第3轮：精化 — 用第2轮 top-3 结果文本进一步聚焦查询
      每轮之间使用 Jaccard 相似度检测结果集是否收敛，收敛则提前终止。

    Args:
        query: 搜索查询文本
        index: VectorSearchIndex 实例（必须已含文档）
        top_k: 每轮返回的结果数量
        max_rounds: 最大收敛轮数（默认 3，符合 inject_plan 建议）
        convergence_threshold: Jaccard 收敛阈值，默认 0.95（即 95% 重叠）

    Returns:
        dict 包含:
          - "results": list[dict] — 最终搜索结果（每项含 id/text/metadata/score）
          - "rounds": int — 实际执行的轮数
          - "converged": bool — 是否提前收敛
          - "round_results": dict[int, list[dict]] — 每轮的完整结果（调试用）
    """
    if not query or not query.strip() or not index._documents:
        return {
            "results": [],
            "rounds": 0,
            "converged": False,
            "round_results": {},
        }

    round_results: dict[int, list[dict[str, Any]]] = {}

    # ---- Round 1: 标准检索（同原有单轮 dot-product 逻辑） ----
    current_results = index.search(query, top_k=top_k)
    round_results[1] = current_results
    converged = False

    # ---- Round 2 ~ max_rounds: 上下文融合 + 精化 ----
    for round_num in range(2, max_rounds + 1):
        # 从上一轮结果提取文本
        prev_texts = [r["text"] for r in current_results if r.get("text")]

        if not prev_texts:
            logger.debug(f"search_with_convergence round {round_num}: no text from previous round, stopping")
            break

        # 第2轮 = 上下文融合：取 top-5 作为补充上下文
        if round_num == 2:
            context = " ".join(prev_texts[:5])
            enhanced_query = f"{query} {context}"
        # 第3轮 = 精化：取 top-3 做更聚焦的查询
        else:
            context = " ".join(prev_texts[:3])
            enhanced_query = f"{query} {context}"

        # 用增强查询重新搜索
        current_results = index.search(enhanced_query, top_k=top_k)
        round_results[round_num] = current_results

        # ---- Jaccard 收敛检测 ----
        prev_ids = {r["id"] for r in round_results.get(round_num - 1, [])}
        curr_ids = {r["id"] for r in current_results}

        union_size = len(prev_ids | curr_ids)
        if union_size > 0:
            jaccard = len(prev_ids & curr_ids) / union_size
        else:
            jaccard = 1.0  # 两者都为空视为完全收敛

        logger.debug(
            f"search_with_convergence round {round_num}: jaccard={jaccard:.4f}, threshold={convergence_threshold}"
        )

        if jaccard >= convergence_threshold:
            converged = True
            logger.info(f"search_with_convergence converged at round {round_num} (jaccard={jaccard:.4f})")
            break

    return {
        "results": current_results,
        "rounds": len(round_results),
        "converged": converged,
        "round_results": round_results,
    }


# ======================================================================
# 导出
# ======================================================================

__all__ = [
    "USE_VECTOR_SEARCH",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_DIM",
    "VECTOR_TOP_K",
    "RERANK_WEIGHT",
    "INDEX_DB_PATH",
    "EmbeddingBackend",
    "NumpyEmbedding",
    "M3EEmbedding",
    "OpenAIEmbedding",
    "DeepSeekEmbedding",
    "VectorSearchIndex",
    "VectorSearchEngine",
    "DocumentBuilder",
    "get_embedding_backend",
    "get_vector_index",
    "embed_text",
    "embed_single",
    "rerank",
    "cosine_similarity",
    "sync_vector_index",
    "search_with_convergence",
]
