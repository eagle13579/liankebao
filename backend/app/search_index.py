"""内存搜索索引 — 用于热词推荐和快速检索"""
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def simple_tokenize(text: str) -> List[str]:
    """简单中文分词：返回所有可搜索的token

    策略：
    - 英文/数字按空白和标点拆分，提取纯ASCII词组
    - 中文逐字符拆分（单字索引）
    - 提取中文双字组合（二元语法）
    - 同时保留原始字符串（用于完全匹配排序加分）
    """
    if not text:
        return []

    tokens = set()

    # 提取中文单字
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    for c in chinese_chars:
        tokens.add(c)

    # 提取双字组合（中文二元语法）
    for i in range(len(chinese_chars) - 1):
        bigram = chinese_chars[i] + chinese_chars[i + 1]
        tokens.add(bigram)

    # 提取纯英文/数字单词（从混合文本中提取）
    # 匹配连续的 ASCII 字母/数字（至少2个字符）
    for word in re.findall(r'[a-zA-Z0-9]{2,}', text):
        tokens.add(word.lower())

    # 也按空白/标点拆分的完整部分（用于混合词如 "Pro版"）
    for part in re.split(r'[,\s;:、，。；：\s]+', text):
        part = part.strip()
        if part and len(part) >= 2:
            tokens.add(part.lower())

    # 提取完整原文（用于相关性加分）
    if len(text) <= 100:
        tokens.add(text.lower().strip())

    return list(tokens)


class SearchDocument:
    """搜索文档"""
    __slots__ = ('id', 'title', 'content', 'category', 'price', 'region', '_raw_score')

    def __init__(self, doc_id: int, title: str, content: str = "",
                 category: str = "", price: float = 0.0, region: str = ""):
        self.id = doc_id
        self.title = title
        self.content = content
        self.category = category
        self.price = price
        self.region = region
        self._raw_score = 0.0


class SearchIndex:
    """内存搜索索引

    使用倒排索引结构，支持文档的添加、移除和搜索。
    相关性排序：标题匹配 > 描述匹配 > 分类匹配
    """

    def __init__(self):
        self._documents: Dict[int, SearchDocument] = {}
        self._inverted_index: Dict[str, List[int]] = {}  # token -> [doc_id, ...]
        self._dirty = False

    def add_document(self, doc_id: int, title: str, content: str = "",
                     category: str = "", price: float = 0.0,
                     region: str = "") -> None:
        """添加文档到索引"""
        doc = SearchDocument(
            doc_id=doc_id,
            title=title or "",
            content=content or "",
            category=category or "",
            price=price,
            region=region or "",
        )

        # 如果已存在，先移除旧的 token
        if doc_id in self._documents:
            self._remove_document_tokens(doc_id)

        self._documents[doc_id] = doc
        self._index_document(doc)
        self._dirty = True

    def _remove_document_tokens(self, doc_id: int) -> None:
        """从倒排索引中移除文档的所有 token"""
        doc = self._documents.get(doc_id)
        if not doc:
            return

        all_tokens = set()
        for text in [doc.title, doc.content, doc.category, doc.region]:
            all_tokens.update(simple_tokenize(text))

        for token in all_tokens:
            if token in self._inverted_index:
                try:
                    self._inverted_index[token].remove(doc_id)
                    if not self._inverted_index[token]:
                        del self._inverted_index[token]
                except ValueError:
                    pass

    def _index_document(self, doc: SearchDocument) -> None:
        """将文档加入倒排索引"""
        all_texts = {
            'title': doc.title,
            'content': doc.content,
            'category': doc.category,
            'region': doc.region,
        }

        for field, text in all_texts.items():
            if not text:
                continue
            tokens = simple_tokenize(text)
            for token in tokens:
                if token not in self._inverted_index:
                    self._inverted_index[token] = []
                if doc.id not in self._inverted_index[token]:
                    self._inverted_index[token].append(doc.id)

    def remove_document(self, doc_id: int) -> None:
        """从索引中移除文档"""
        if doc_id in self._documents:
            self._remove_document_tokens(doc_id)
            del self._documents[doc_id]
            self._dirty = True

    def clear(self) -> None:
        """清空索引"""
        self._documents.clear()
        self._inverted_index.clear()
        self._dirty = True

    def _compute_score(self, doc: SearchDocument, query: str,
                       query_tokens: List[str]) -> float:
        """计算文档与查询的相关性分数

        评分规则：
        - 标题完全匹配：+10.0
        - 标题包含查询词：+8.0
        - 描述完全匹配：+5.0
        - 描述包含查询词：+3.0
        - 分类匹配：+2.0
        - 标签/region匹配：+1.0
        """
        score = 0.0
        ql = query.lower().strip()

        # === 标题匹配 ===
        title_lower = doc.title.lower()
        if ql and ql == title_lower:
            score += 10.0
        elif ql and ql in title_lower:
            score += 8.0
        else:
            # 部分 token 匹配标题
            for token in query_tokens:
                if token in title_lower:
                    score += 4.0

        # === 描述匹配 ===
        content_lower = doc.content.lower()
        if ql and ql == content_lower:
            score += 5.0
        elif ql and ql in content_lower:
            score += 3.0
        else:
            for token in query_tokens:
                if token in content_lower:
                    score += 1.5

        # === 分类匹配 ===
        cat_lower = doc.category.lower()
        for token in query_tokens:
            if token in cat_lower:
                score += 2.0

        # === Region匹配 ===
        region_lower = doc.region.lower()
        for token in query_tokens:
            if token in region_lower:
                score += 1.0

        return score

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索索引，返回按相关性排序的文档列表

        Args:
            query: 搜索关键词
            limit: 最大返回数量

        Returns:
            [{"id": int, "title": str, "score": float, ...}, ...]
        """
        if not query or not query.strip():
            return []

        query_tokens = simple_tokenize(query)
        if not query_tokens:
            return []

        # 收集匹配的文档ID（并集）
        matched_ids: Dict[int, float] = {}

        for token in query_tokens:
            doc_ids = self._inverted_index.get(token, [])
            for doc_id in doc_ids:
                doc = self._documents.get(doc_id)
                if doc:
                    score = self._compute_score(doc, query, query_tokens)
                    if doc_id in matched_ids:
                        matched_ids[doc_id] = max(matched_ids[doc_id], score)
                    else:
                        matched_ids[doc_id] = score

        # 按分数降序排序
        sorted_ids = sorted(matched_ids.items(), key=lambda x: -x[1])

        results = []
        for doc_id, score in sorted_ids[:limit]:
            doc = self._documents[doc_id]
            results.append({
                "id": doc.id,
                "title": doc.title,
                "content": doc.content[:200] if doc.content else "",
                "category": doc.category,
                "price": doc.price,
                "region": doc.region,
                "score": round(score, 2),
            })

        return results

    def suggest(self, prefix: str, limit: int = 10) -> List[str]:
        """前缀补全建议（用于搜索框下拉建议）

        Args:
            prefix: 输入前缀
            limit: 最多返回建议数

        Returns:
            [title1, title2, ...]
        """
        if not prefix or not prefix.strip():
            return []

        prefix_lower = prefix.lower().strip()
        suggestions = []

        for doc in self._documents.values():
            title = doc.title
            if prefix_lower in title.lower():
                suggestions.append(title)

        # 去重并限制数量
        seen = set()
        unique = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique.append(s)
                if len(unique) >= limit:
                    break

        return unique

    @property
    def size(self) -> int:
        """索引中文档数量"""
        return len(self._documents)

    @property
    def stats(self) -> Dict[str, Any]:
        """索引统计信息"""
        return {
            "documents": len(self._documents),
            "unique_tokens": len(self._inverted_index),
            "dirty": self._dirty,
        }


# ===== 全局单例 =====
_search_index = SearchIndex()


def get_search_index() -> SearchIndex:
    """获取全局搜索索引单例"""
    return _search_index


def rebuild_search_index(db_session=None) -> int:
    """从数据库重建搜索索引

    Args:
        db_session: SQLAlchemy session，如果为None则不重建

    Returns:
        索引的文档数量
    """
    if db_session is None:
        return 0

    from app.models import Product

    index = get_search_index()
    index.clear()

    products = db_session.query(Product).filter(
        Product.status == "approved"
    ).all()

    for p in products:
        # 尝试从 specs JSON 中提取产地信息
        region = ""
        if p.specs:
            try:
                import json
                specs = json.loads(p.specs)
                region = specs.get("产地", specs.get("产地/发货地", ""))
            except (json.JSONDecodeError, TypeError):
                pass

        index.add_document(
            doc_id=p.id,
            title=p.name or "",
            content=(p.description or "") + " " + (p.tags or ""),
            category=p.category or "",
            price=p.price or 0.0,
            region=region,
        )

    logger.info(f"搜索索引重建完成，共 {len(products)} 个文档")
    return len(products)
