"""
链客宝AI搜索引擎 — 增强版

支持三种引擎（可配置切换）:
  1. memory  — 内存倒排索引 + jieba 中文分词（默认，通用）
  2. fts5    — SQLite FTS5 全文搜索（仅 SQLite，性能最佳）
  3. auto    — 自动检测：SQLite 用 fts5，否则用 memory

环境变量:
  SEARCH_BACKEND=auto|memory|fts5   (默认: auto)
  USE_JIEBA=1|0                      (默认: 1，memory 引擎使用 jieba 分词)
  USE_VECTOR_SEARCH=0|1             (默认: 0，启用向量重排序)
  EMBEDDING_PROVIDER=numpy|openai|deepseek  (默认: numpy)
  RERANK_WEIGHT=0.3                 (向量重排序权重 0~1)

功能:
  - 多字段搜索（产品名+描述+标签+品牌+分类）
  - jieba 中文分词（memory 引擎）
  - FTS5 全文索引（SQLite 引擎）
  - 排序（相关性/价格升序/价格降序/最新）
  - 分页
  - 搜索结果高亮
  - 搜索建议/补全
  - 向量重排序（USE_VECTOR_SEARCH=1 时启用，BM25+向量混合排序）
"""

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ======================================================================
# 配置
# ======================================================================
SEARCH_BACKEND = os.environ.get("SEARCH_BACKEND", "auto").lower()
USE_JIEBA = os.environ.get("USE_JIEBA", "1") == "1"
USE_VECTOR_SEARCH = os.environ.get("USE_VECTOR_SEARCH", "0") == "1"

# ======================================================================
# 中文分词
# ======================================================================
try:
    import jieba

    JIEBA_AVAILABLE = True
    # 加载自定义词典（如果存在）
    _dict_path = os.path.join(os.path.dirname(__file__), "dict.txt")
    if os.path.isfile(_dict_path):
        jieba.load_userdict(_dict_path)
        logger.info(f"已加载自定义分词词典: {_dict_path}")
except ImportError:
    JIEBA_AVAILABLE = False
    if USE_JIEBA:
        logger.warning("jieba 未安装，回退到简单分词器。安装: pip install jieba")


def simple_tokenize(text: str) -> list[str]:
    """简化中文分词（向后兼容）

    策略:
    - 英文/数字按空白和标点拆分
    - 中文逐字符（单字索引）
    - 中文双字组合（二元语法）
    - 保留原始短字符串用于完全匹配
    """
    if not text:
        return []
    tokens = set()
    # 提取中文单字
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    for c in chinese_chars:
        tokens.add(c)
    # 提取双字组合（中文二元语法）
    for i in range(len(chinese_chars) - 1):
        bigram = chinese_chars[i] + chinese_chars[i + 1]
        tokens.add(bigram)
    # 提取纯英文/数字单词（从混合文本中提取）
    for word in re.findall(r"[a-zA-Z0-9]{2,}", text):
        tokens.add(word.lower())
    # 也按空白/标点拆分的完整部分
    for part in re.split(r"[,\s;:、，。；：\s]+", text):
        part = part.strip()
        if part and len(part) >= 2:
            tokens.add(part.lower())
    # 提取完整原文（用于相关性加分）
    if len(text) <= 100:
        tokens.add(text.lower().strip())
    return list(tokens)


def jieba_tokenize(text: str) -> list[str]:
    """jieba 中文分词"""
    if not text:
        return []
    tokens = set()
    # jieba 精确模式分词
    words = jieba.lcut(text)
    for w in words:
        w = w.strip().lower()
        if w:
            tokens.add(w)
    # 补充英文/数字 token
    for w in re.findall(r"[a-zA-Z0-9]{2,}", text):
        tokens.add(w.lower())
    # 补充完整原文（短文本时）
    if len(text) <= 100:
        tokens.add(text.lower().strip())
    return list(tokens)


def tokenize(text: str) -> list[str]:
    """智能分词：优先 jieba，回退 simple"""
    if USE_JIEBA and JIEBA_AVAILABLE:
        return jieba_tokenize(text)
    return simple_tokenize(text)


def tokenize_query(text: str) -> list[str]:
    """查询分词（与索引分词一致）"""
    return tokenize(text)


# ======================================================================
# 搜索结果高亮
# ======================================================================


def highlight_text(
    text: str,
    query: str,
    max_length: int = 200,
    tag: str = "em",
) -> str:
    """高亮搜索结果中的匹配词

    截取包含匹配词的上下文区间，用 <em> 标签包裹匹配词。

    Args:
        text: 原始文本
        query: 搜索关键词
        max_length: 截取最大长度（含高亮标签后）
        tag: 高亮 HTML 标签名

    Returns:
        含 <em> 标签的高亮片段
    """
    if not text or not query:
        return (text or "")[:max_length]

    # 获取查询词的 tokens
    query_tokens = tokenize_query(query)
    if not query_tokens:
        return text[:max_length]

    text_lower = text.lower()

    # 找到第一个匹配位置
    first_pos = len(text)
    matched_token = ""
    for token in query_tokens:
        pos = text_lower.find(token)
        if pos != -1 and pos < first_pos:
            first_pos = pos
            matched_token = token

    if not matched_token:
        return text[:max_length]

    # 截取上下文
    context_start = max(0, first_pos - 30)
    context_end = min(len(text), first_pos + max_length - 30)

    prefix = "..." if context_start > 0 else ""
    suffix = "..." if context_end < len(text) else ""
    snippet = text[context_start:context_end]

    # 高亮所有匹配词（不区分大小写）
    # 按 token 长度降序排序，避免短 token 嵌套在高亮中
    sorted_tokens = sorted(
        [t for t in query_tokens if t],
        key=lambda t: -len(t),
    )
    # 先将被高亮区域用占位符保护
    placeholders = {}
    for i, token in enumerate(sorted_tokens):
        if not token:
            continue
        placeholder = f"\x00HL{i}\x00"
        snippet = re.sub(
            re.escape(token),
            placeholder,
            snippet,
            flags=re.IGNORECASE,
        )
        placeholders[placeholder] = f"<{tag}>{token}</{tag}>"

    # 还原占位符
    for placeholder, replacement in placeholders.items():
        snippet = snippet.replace(placeholder, replacement)

    return f"{prefix}{snippet}{suffix}"


def highlight_title(title: str, query: str) -> str:
    """高亮标题"""
    return highlight_text(title, query, max_length=100)


# ======================================================================
# 引擎接口
# ======================================================================


class SearchEngine(ABC):
    """搜索引擎抽象接口"""

    @abstractmethod
    def search(
        self,
        query: str,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "relevance",
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """搜索

        Args:
            query: 搜索关键词
            page: 页码（从1开始）
            page_size: 每页条数
            sort_by: 排序方式 (relevance|price_asc|price_desc|newest)
            filters: 过滤条件 {category, region, min_price, max_price}

        Returns:
            {
                "items": [{"id", "title", "description", "highlight_title", "highlight_content", ...}, ...],
                "total": int,
                "page": int,
                "page_size": int,
                "query": str,
            }
        """
        ...

    @abstractmethod
    def suggest(self, prefix: str, limit: int = 10) -> list[str]:
        """搜索建议"""
        ...

    @abstractmethod
    def add_document(
        self,
        doc_id: int,
        title: str,
        content: str = "",
        category: str = "",
        price: float = 0.0,
        region: str = "",
        tags: str = "",
        brand: str = "",
    ) -> None:
        """添加/更新文档"""
        ...

    @abstractmethod
    def remove_document(self, doc_id: int) -> None:
        """删除文档"""
        ...

    @abstractmethod
    def clear(self) -> None:
        """清空索引"""
        ...

    @abstractmethod
    def rebuild(self, db_session=None) -> int:
        """从数据库重建索引"""
        ...

    @property
    @abstractmethod
    def size(self) -> int:
        """索引文档数"""
        ...

    @property
    @abstractmethod
    def stats(self) -> dict[str, Any]:
        """索引统计"""
        ...


# ======================================================================
# MemorySearchEngine — 内存倒排索引 + jieba 分词
# ======================================================================


@dataclass
class SearchDocument:
    """搜索文档"""

    doc_id: int
    title: str = ""
    content: str = ""
    category: str = ""
    price: float = 0.0
    region: str = ""
    tags: str = ""
    brand: str = ""
    created_at: str | None = None


class MemorySearchEngine(SearchEngine):
    """内存搜索引擎（增强版）

    使用倒排索引结构 + jieba 中文分词。
    支持任意数据库后端。
    """

    def __init__(self):
        self._documents: dict[int, SearchDocument] = {}
        self._inverted_index: dict[str, list[int]] = {}  # token -> [doc_id, ...]
        self._dirty = False

    # ---- 文档管理 ----

    def add_document(
        self,
        doc_id: int,
        title: str = "",
        content: str = "",
        category: str = "",
        price: float = 0.0,
        region: str = "",
        tags: str = "",
        brand: str = "",
    ) -> None:
        doc = SearchDocument(
            doc_id=doc_id,
            title=title or "",
            content=content or "",
            category=category or "",
            price=price,
            region=region or "",
            tags=tags or "",
            brand=brand or "",
        )

        # 如果已存在，先移除旧的 token
        if doc_id in self._documents:
            self._remove_document_tokens(doc_id)

        self._documents[doc_id] = doc
        self._index_document(doc)
        self._dirty = True

    def _remove_document_tokens(self, doc_id: int) -> None:
        doc = self._documents.get(doc_id)
        if not doc:
            return

        all_tokens = set()
        for text in [doc.title, doc.content, doc.category, doc.region, doc.tags, doc.brand]:
            all_tokens.update(tokenize(text))

        for token in all_tokens:
            if token in self._inverted_index:
                try:
                    self._inverted_index[token].remove(doc_id)
                    if not self._inverted_index[token]:
                        del self._inverted_index[token]
                except ValueError:
                    pass

    def _index_document(self, doc: SearchDocument) -> None:
        fields = {
            "title": doc.title,
            "content": doc.content,
            "category": doc.category,
            "region": doc.region,
            "tags": doc.tags,
            "brand": doc.brand,
        }

        for field, text in fields.items():
            if not text:
                continue
            tokens = tokenize(text)
            for t in tokens:
                if t not in self._inverted_index:
                    self._inverted_index[t] = []
                if doc.doc_id not in self._inverted_index[t]:
                    self._inverted_index[t].append(doc.doc_id)

    def remove_document(self, doc_id: int) -> None:
        if doc_id in self._documents:
            self._remove_document_tokens(doc_id)
            del self._documents[doc_id]
            self._dirty = True

    def clear(self) -> None:
        self._documents.clear()
        self._inverted_index.clear()
        self._dirty = True

    # ---- 搜索 ----

    def _compute_score(
        self,
        doc: SearchDocument,
        query: str,
        query_tokens: list[str],
    ) -> float:
        """计算相关性分数

        评分规则:
        - 标题精确匹配: +20.0
        - 标题包含查询: +15.0
        - 标题 token 匹配: +8.0/token
        - 描述精确匹配: +8.0
        - 描述包含查询: +5.0
        - 描述 token 匹配: +2.0/token
        - 标签精确匹配: +10.0
        - 标签 token 匹配: +3.0/token
        - 品牌精确匹配: +8.0
        - 品牌 token 匹配: +2.0/token
        - 分类匹配: +2.0
        - Region 匹配: +1.0
        """
        score = 0.0
        ql = query.lower().strip()

        # === 标题匹配 ===
        title_lower = doc.title.lower()
        if ql and ql == title_lower:
            score += 20.0
        elif ql and ql in title_lower:
            score += 15.0
        else:
            for token in query_tokens:
                if token in title_lower:
                    score += 8.0

        # === 描述匹配 ===
        content_lower = doc.content.lower()
        if ql and ql == content_lower:
            score += 8.0
        elif ql and ql in content_lower:
            score += 5.0
        else:
            for token in query_tokens:
                if token in content_lower:
                    score += 2.0

        # === 标签匹配 ===
        tags_lower = doc.tags.lower()
        if ql and ql in tags_lower:
            score += 10.0
        else:
            for token in query_tokens:
                if token in tags_lower:
                    score += 3.0

        # === 品牌匹配 ===
        brand_lower = doc.brand.lower()
        if ql and ql == brand_lower:
            score += 8.0
        elif ql and ql in brand_lower:
            score += 5.0
        else:
            for token in query_tokens:
                if token in brand_lower:
                    score += 2.0

        # === 分类匹配 ===
        cat_lower = doc.category.lower()
        for token in query_tokens:
            if token in cat_lower:
                score += 2.0

        # === Region 匹配 ===
        region_lower = doc.region.lower()
        for token in query_tokens:
            if token in region_lower:
                score += 1.0

        return score

    def search(
        self,
        query: str,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "relevance",
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """搜索"""
        result = {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "query": query,
        }

        if not query or not query.strip():
            return result

        query_tokens = tokenize_query(query)
        if not query_tokens:
            return result

        filters = filters or {}

        # 收集匹配文档并计算分数
        matched: dict[int, float] = {}

        for token in query_tokens:
            doc_ids = self._inverted_index.get(token, [])
            for doc_id in doc_ids:
                doc = self._documents.get(doc_id)
                if doc:
                    score = self._compute_score(doc, query, query_tokens)
                    if doc_id in matched:
                        matched[doc_id] = max(matched[doc_id], score)
                    else:
                        matched[doc_id] = score

        if not matched:
            return result

        # 应用过滤器
        filtered = {}
        for doc_id, score in matched.items():
            doc = self._documents[doc_id]
            if not self._match_filters(doc, filters):
                continue
            filtered[doc_id] = score

        if not filtered:
            return result

        # 排序
        sorted_items = self._sort_results(filtered, sort_by)

        # 分页
        total = len(sorted_items)
        offset = (page - 1) * page_size
        page_items = sorted_items[offset : offset + page_size]

        # 构造结果
        items = []
        for doc_id, score in page_items:
            doc = self._documents[doc_id]
            items.append(self._format_result(doc, score, query))

        # 向量重排序（可配置，通过 USE_VECTOR_SEARCH 环境变量开启）
        if USE_VECTOR_SEARCH:
            try:
                from app.vector_search import rerank as vector_rerank

                items = vector_rerank(query, items)
            except Exception as e:
                logger.debug(f"向量重排序跳过: {e}")

        result["items"] = items
        result["total"] = total
        return result

    def _match_filters(self, doc: SearchDocument, filters: dict[str, Any]) -> bool:
        """过滤器匹配"""
        if "category" in filters and filters["category"]:
            cat = filters["category"].strip()
            if doc.category.lower() != cat.lower():
                return False

        if "region" in filters and filters["region"]:
            region = filters["region"].strip().lower()
            if region not in doc.region.lower():
                return False

        if "min_price" in filters and filters["min_price"] is not None:
            if doc.price < filters["min_price"]:
                return False

        if "max_price" in filters and filters["max_price"] is not None:
            if doc.price > filters["max_price"]:
                return False

        return True

    def _sort_results(
        self,
        matched: dict[int, float],
        sort_by: str,
    ) -> list[tuple[int, float]]:
        """排序"""
        items = list(matched.items())

        if sort_by == "price_asc":
            items.sort(key=lambda x: (self._documents[x[0]].price, -x[1]))
        elif sort_by == "price_desc":
            items.sort(key=lambda x: (-self._documents[x[0]].price, -x[1]))
        elif sort_by == "newest":
            items.sort(
                key=lambda x: (
                    self._documents[x[0]].created_at or "",
                    -x[1],
                ),
                reverse=True,
            )
        else:  # relevance (default)
            items.sort(key=lambda x: -x[1])

        return items

    def _format_result(self, doc: SearchDocument, score: float, query: str) -> dict[str, Any]:
        """格式化搜索结果"""
        # 生成高亮标题和描述
        hl_title = highlight_title(doc.title, query)
        hl_content = highlight_text(doc.content, query, max_length=200)

        return {
            "id": doc.doc_id,
            "title": doc.title,
            "description": doc.content[:300] if doc.content else "",
            "category": doc.category,
            "price": doc.price,
            "region": doc.region,
            "tags": doc.tags,
            "brand": doc.brand,
            "score": round(score, 2),
            "highlight_title": hl_title,
            "highlight_content": hl_content,
        }

    # ---- 搜索建议 ----

    def suggest(self, prefix: str, limit: int = 10) -> list[str]:
        if not prefix or not prefix.strip():
            return []

        prefix_lower = prefix.lower().strip()
        suggestions = []

        for doc in self._documents.values():
            title = doc.title
            if prefix_lower in title.lower():
                suggestions.append(title)

        # 去重并限制
        seen = set()
        unique = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique.append(s)
                if len(unique) >= limit:
                    break

        return unique

    # ---- 重建 ----

    def rebuild(self, db_session=None) -> int:
        """从数据库重建索引"""
        if db_session is None:
            return 0

        from app.models import Product

        self.clear()

        products = (
            db_session.query(Product)
            .filter(
                Product.status == "approved",
                Product.is_deleted == False,
            )
            .all()
        )

        for p in products:
            # 从 specs JSON 中提取产地
            region = ""
            if p.specs:
                try:
                    specs = json.loads(p.specs)
                    region = specs.get("产地", specs.get("产地/发货地", ""))
                except (json.JSONDecodeError, TypeError):
                    pass

            self.add_document(
                doc_id=p.id,
                title=p.name or "",
                content=p.description or "",
                category=p.category or "",
                price=p.price or 0.0,
                region=region,
                tags=p.tags or "",
                brand=p.brand or "",
            )

        logger.info(f"MemorySearchEngine 重建完成，共 {len(products)} 个文档")
        return len(products)

    @property
    def size(self) -> int:
        return len(self._documents)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "engine": "memory",
            "documents": len(self._documents),
            "unique_tokens": len(self._inverted_index),
            "jieba_enabled": USE_JIEBA and JIEBA_AVAILABLE,
            "dirty": self._dirty,
        }


# ======================================================================
# FTS5SearchEngine — SQLite FTS5 全文搜索
# ======================================================================


class FTS5SearchEngine(SearchEngine):
    """SQLite FTS5 全文搜索引擎

    仅支持 SQLite 数据库。利用 SQLite 内置的 FTS5 扩展进行全文搜索。
    需要 SQLite 版本 >= 3.9.0（FTS5 在 3.9.0 引入）。
    """

    FTS_TABLE_NAME = "product_fts"

    def __init__(self):
        self._engine = None
        self._initialized = False

    def _get_sqlite_engine(self, db_session) -> Any:
        """从 SQLAlchemy session 获取底层 SQLite 引擎"""
        return db_session.bind

    def _ensure_fts_table(self, db_session) -> None:
        """确保 FTS5 虚拟表存在"""
        if self._initialized:
            return

        raw_conn = db_session.connection().connection
        # 启用 FTS5 扩展
        raw_conn.execute("PRAGMA journal_mode=WAL")

        # 创建 FTS5 虚拟表（如果不存在）
        # 使用 content= 外部内容表以减少数据冗余
        sql = f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {self.FTS_TABLE_NAME} USING fts5(
            name,
            description,
            tags,
            brand,
            category,
            content='products',
            content_rowid='id',
            tokenize='unicode61 tokenchars'
        )
        """
        try:
            raw_conn.execute(sql)
        except Exception as e:
            # 如果 products 表不在同一个数据库，退化到内部存储
            logger.warning(f"FTS5 外部内容表创建失败: {e}，尝试内部存储")
            sql = f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {self.FTS_TABLE_NAME} USING fts5(
                name,
                description,
                tags,
                brand,
                category,
                tokenize='unicode61 tokenchars'
            )
            """
            raw_conn.execute(sql)

        self._initialized = True

    def _sync_fts_data(self, db_session) -> None:
        """从 products 表同步数据到 FTS5 索引"""
        from app.models import Product

        products = (
            db_session.query(Product)
            .filter(
                Product.status == "approved",
                Product.is_deleted == False,
            )
            .all()
        )

        raw_conn = db_session.connection().connection

        # 清空旧索引并重建
        raw_conn.execute(f"DELETE FROM {self.FTS_TABLE_NAME}")

        for p in products:
            raw_conn.execute(
                f"INSERT INTO {self.FTS_TABLE_NAME} (rowid, name, description, tags, brand, category) "
                f"VALUES (?, ?, ?, ?, ?, ?)",
                (p.id, p.name or "", p.description or "", p.tags or "", p.brand or "", p.category or ""),
            )

        raw_conn.commit()
        logger.info(f"FTS5 索引同步完成，共 {len(products)} 个文档")

    # ---- 文档管理 ----

    def add_document(
        self,
        doc_id: int,
        title: str = "",
        content: str = "",
        category: str = "",
        price: float = 0.0,
        region: str = "",
        tags: str = "",
        brand: str = "",
    ) -> None:
        # FTS5 需要 db_session 来操作，这里只记录到内存中备用
        # 实际的 add 操作通过 rebuild 或外部调用完成
        # 这个方法保留兼容性
        pass

    def remove_document(self, doc_id: int) -> None:
        # 需要 db_session
        pass

    def clear(self) -> None:
        self._initialized = False

    # ---- 搜索 ----

    def search(
        self,
        query: str,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "relevance",
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """使用 FTS5 搜索"""
        result = {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "query": query,
        }

        if not query or not query.strip():
            return result

        # 需要 db_session — 这里使用全局 get_db
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            self._ensure_fts_table(db)

            filters = filters or {}

            # 构造 FTS5 查询语句
            # 使用 jieba 分词增强查询
            query_tokens = tokenize_query(query)
            if not query_tokens:
                return result

            # FTS5 查询语法：对每个 token 做前缀匹配
            fts_queries = []
            for t in query_tokens:
                if len(t) == 1:
                    fts_queries.append(f'"{t}"')
                else:
                    fts_queries.append(f'"{t}"*')

            fts_query = " AND ".join(fts_queries)

            raw_conn = db.connection().connection

            # 构建基础查询
            base_sql = f"""
            SELECT p.id, p.name, p.description, p.category, p.price, p.tags, p.brand, p.created_at,
                   rank
            FROM {self.FTS_TABLE_NAME} fts
            JOIN products p ON fts.rowid = p.id
            WHERE {self.FTS_TABLE_NAME} MATCH ?
              AND p.status = 'approved'
            """

            params = [fts_query]

            # 应用过滤器
            if "category" in filters and filters["category"]:
                base_sql += " AND p.category = ?"
                params.append(filters["category"].strip())
            if "min_price" in filters and filters["min_price"] is not None:
                base_sql += " AND p.price >= ?"
                params.append(filters["min_price"])
            if "max_price" in filters and filters["max_price"] is not None:
                base_sql += " AND p.price <= ?"
                params.append(filters["max_price"])

            # 排序
            if sort_by == "price_asc":
                base_sql += " ORDER BY p.price ASC, rank DESC"
            elif sort_by == "price_desc":
                base_sql += " ORDER BY p.price DESC, rank DESC"
            elif sort_by == "newest":
                base_sql += " ORDER BY p.created_at DESC, rank DESC"
            else:
                base_sql += " ORDER BY rank DESC"

            # 统计总数
            count_sql = f"""
            SELECT COUNT(*)
            FROM {self.FTS_TABLE_NAME} fts
            JOIN products p ON fts.rowid = p.id
            WHERE {self.FTS_TABLE_NAME} MATCH ?
              AND p.status = 'approved'
            """
            count_params = [fts_query]

            if "category" in filters and filters["category"]:
                count_sql += " AND p.category = ?"
                count_params.append(filters["category"].strip())
            if "min_price" in filters and filters["min_price"] is not None:
                count_sql += " AND p.price >= ?"
                count_params.append(filters["min_price"])
            if "max_price" in filters and filters["max_price"] is not None:
                count_sql += " AND p.price <= ?"
                count_params.append(filters["max_price"])

            total = raw_conn.execute(count_sql, count_params).fetchone()[0]

            # 分页
            offset = (page - 1) * page_size
            base_sql += " LIMIT ? OFFSET ?"
            params.extend([page_size, offset])

            rows = raw_conn.execute(base_sql, params).fetchall()

            items = []
            for row in rows:
                (
                    pid,
                    name,
                    description,
                    category,
                    price,
                    tags,
                    brand,
                    created_at,
                    rank,
                ) = row

                # 提取 region（从 specs JSON）
                product = db.query(type("P", (), {}).__class__).from_orm(None) if False else None
                # 从 products 表查 region
                region = ""
                try:
                    p_obj = db.query(type("X", (object,), {}))
                except Exception:
                    pass

                # 简化：直接从数据库查
                from app.models import Product

                p_obj = db.query(Product).filter(Product.id == pid, Product.is_deleted == False).first()
                region = ""
                if p_obj and p_obj.specs:
                    try:
                        specs = json.loads(p_obj.specs)
                        region = specs.get("产地", specs.get("产地/发货地", ""))
                    except (json.JSONDecodeError, TypeError):
                        pass

                hl_title = highlight_title(name or "", query)
                hl_content = highlight_text(description or "", query, max_length=200)

                items.append(
                    {
                        "id": pid,
                        "title": name or "",
                        "description": (description or "")[:300],
                        "category": category or "",
                        "price": price or 0.0,
                        "region": region,
                        "tags": tags or "",
                        "brand": brand or "",
                        "score": round(float(rank), 2) if rank else 0.0,
                        "highlight_title": hl_title,
                        "highlight_content": hl_content,
                    }
                )

            result["items"] = items
            result["total"] = total
            return result

        except Exception as e:
            logger.error(f"FTS5 搜索失败: {e}", exc_info=True)
            return result
        finally:
            db.close()

    def suggest(self, prefix: str, limit: int = 10) -> list[str]:
        if not prefix or not prefix.strip():
            return []

        from app.database import SessionLocal

        db = SessionLocal()
        try:
            self._ensure_fts_table(db)
            raw_conn = db.connection().connection

            # FTS5 前缀匹配
            fts_query = f'"{prefix.strip()}"*'
            rows = raw_conn.execute(
                f"""
                SELECT DISTINCT name FROM {self.FTS_TABLE_NAME}
                WHERE {self.FTS_TABLE_NAME} MATCH ?
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()

            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"FTS5 suggest 失败: {e}")
            return []
        finally:
            db.close()

    def rebuild(self, db_session=None) -> int:
        """从数据库重建 FTS5 索引"""
        if db_session is None:
            return 0

        try:
            self._ensure_fts_table(db_session)
            self._sync_fts_data(db_session)
            raw_conn = db_session.connection().connection
            count = raw_conn.execute(f"SELECT COUNT(*) FROM {self.FTS_TABLE_NAME}").fetchone()[0]
            return count
        except Exception as e:
            logger.error(f"FTS5 重建失败: {e}", exc_info=True)
            return 0

    @property
    def size(self) -> int:
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            raw_conn = db.connection().connection
            count = raw_conn.execute(f"SELECT COUNT(*) FROM {self.FTS_TABLE_NAME}").fetchone()[0]
            return count
        except Exception:
            return 0
        finally:
            db.close()

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "engine": "fts5",
            "initialized": self._initialized,
        }


# ======================================================================
# 引擎工厂
# ======================================================================

_is_sqlite_cache = None
_has_fts5_cache = None


def _is_sqlite() -> bool:
    """检测当前数据库是否为 SQLite"""
    global _is_sqlite_cache
    if _is_sqlite_cache is not None:
        return _is_sqlite_cache

    try:
        from app.database import DATABASE_URL

        _is_sqlite_cache = not DATABASE_URL  # 无 DATABASE_URL = SQLite
        return _is_sqlite_cache
    except ImportError:
        _is_sqlite_cache = True
        return True


def _has_fts5() -> bool:
    """检测 SQLite 是否支持 FTS5"""
    global _has_fts5_cache
    if _has_fts5_cache is not None:
        return _has_fts5_cache

    if os.environ.get("SEARCH_FORCE_FTS5", "0") == "1":
        _has_fts5_cache = True
        return True
    if os.environ.get("SEARCH_DISABLE_FTS5", "0") == "1":
        _has_fts5_cache = False
        return False

    try:
        # 使用原生 sqlite3 模块检测
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        conn.execute("DROP TABLE t")
        conn.close()
        _has_fts5_cache = True
        return True
    except Exception:
        _has_fts5_cache = False
        return False


def get_search_engine() -> SearchEngine:
    """获取搜索引擎实例

    自动选择策略:
    - SEARCH_BACKEND=memory → MemorySearchEngine
    - SEARCH_BACKEND=fts5  → FTS5SearchEngine（仅 SQLite）
    - SEARCH_BACKEND=auto  → SQLite+FTS5=FTS5, else=Memory
    """
    global _search_engine_instance

    if _search_engine_instance is not None:
        return _search_engine_instance

    backend = SEARCH_BACKEND

    if backend == "memory":
        engine = MemorySearchEngine()
        logger.info("搜索引擎: MemorySearchEngine (手动指定)")
    elif backend == "fts5":
        if _is_sqlite() and _has_fts5():
            engine = FTS5SearchEngine()
            logger.info("搜索引擎: FTS5SearchEngine (手动指定)")
        else:
            logger.warning("FTS5 引擎不可用（非 SQLite 或无 FTS5 支持），回退到 MemorySearchEngine")
            engine = MemorySearchEngine()
    else:  # auto
        if _is_sqlite() and _has_fts5():
            engine = FTS5SearchEngine()
            logger.info("搜索引擎: FTS5SearchEngine (自动检测: SQLite+FTS5)")
        else:
            engine = MemorySearchEngine()
            logger.info(
                f"搜索引擎: MemorySearchEngine (自动检测: {'非SQLite' if not _is_sqlite() else 'SQLite但无FTS5'})"
            )

    _search_engine_instance = engine

    # 首次使用时自动重建（如果索引为空）
    try:
        if isinstance(engine, MemorySearchEngine) and engine.size == 0:
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                count = engine.rebuild(db)
                if count > 0:
                    logger.info(f"搜索引擎首次启动完成：已索引 {count} 个文档")
            finally:
                db.close()
    except Exception as e:
        logger.warning(f"搜索引擎首次重建失败（将在首次搜索时重试）: {e}")

    return engine


# ======================================================================
# 全局单例 & 向后兼容
# ======================================================================

_search_engine_instance: SearchEngine | None = None


# 向后兼容: 保留旧的 SearchIndex 类名
class SearchIndex(MemorySearchEngine):
    """SearchIndex — 向后兼容包装类"""

    pass


def get_search_index() -> SearchIndex:
    """向后兼容: 获取 SearchIndex 实例"""
    engine = get_search_engine()
    if isinstance(engine, SearchIndex):
        return engine
    # 如果不是 MemorySearchEngine，返回一个 MemorySearchEngine 实例
    return SearchIndex()


def rebuild_search_index(db_session=None) -> int:
    """向后兼容: 重建搜索索引"""
    engine = get_search_engine()
    return engine.rebuild(db_session)


# 导出
__all__ = [
    "SearchEngine",
    "MemorySearchEngine",
    "FTS5SearchEngine",
    "SearchIndex",
    "get_search_engine",
    "get_search_index",
    "rebuild_search_index",
    "tokenize",
    "tokenize_query",
    "highlight_text",
    "highlight_title",
    "simple_tokenize",
    "jieba_tokenize",
]
