"""
链客宝AI 特征工程管道
===================
为匹配引擎提供可独立运行、结构化特征提取与相似度计算管道。

设计目标:
  1. 可独立于 matching_engine 运行（零耦合）
  2. 可作为 matching_engine 的降级（简化版）或增强（ML 特征供给）
  3. 返回结构化特征字典，供未来 ML 模型使用
  4. 函数式接口，无类状态依赖，易于测试和集成

接口函数:
  - extract_product_features(product)       → dict[str, Any]
  - extract_need_features(need)             → dict[str, Any]
  - compute_similarity(prod_feat, need_feat) → float (0~1)
  - combine_scores(cat, kw, price, feat, weights) → float (0~1)
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

import jieba
import numpy as np

from app.models import BusinessNeed, Product
from app.stop_words import STOP_WORDS  # 已迁移到共享模块
from app.utils import normalize_text, parse_budget  # 已迁移到共享模块

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

# 默认权重配置（与 matching_engine 保持一致）
DEFAULT_WEIGHTS = {
    "category": 0.40,
    "keyword": 0.40,
    "price": 0.20,
    "feature": 0.00,  # 特征相似度默认不启用，由调用方指定
}

# TF-IDF 配置
TFIDF_MAX_FEATURES = 1000
TFIDF_NGRAM_RANGE = (1, 2)

# 停用词表（已迁移到 app.stop_words — 保持兼容）
# 原硬编码停用词表已移至 app/stop_words.py
STOP_WORDS: set[str] = STOP_WORDS  # type: ignore  # 保持原变量名对外兼容

# 已知类目列表（用于 one-hot / multi-label 编码）
KNOWN_CATEGORIES: list[str] = [
    "大健康",
    "食品",
    "企业服务",
    "企业家服务",
    "教育培训",
    "科技产品",
    "SaaS硬件",
    "消费品",
    "工业",
    "农业",
    "文化传媒",
    "金融",
    "房地产",
    "物流",
    "医疗",
    "其他",
]

# ============================================================
# 内部工具函数
# ============================================================


def _normalize_text(text: str | None) -> str:
    """规范化文本：去空格、去标点、转小写
    已迁移到 app.utils — 保持兼容
    """
    return normalize_text(text)


def _extract_keywords(text: str | None) -> list[str]:
    """jieba 分词 + 停用词过滤"""
    if not text:
        return []
    normalized = _normalize_text(text)
    words = jieba.lcut(normalized)
    return [w for w in words if len(w) >= 2 and w not in STOP_WORDS]


def _category_vector(category: str | None) -> dict[str, float]:
    """将类目编码为多标签向量（支持同义词映射）

    返回 {category_name: confidence} 格式，可序列化。
    """
    if not category:
        return {}

    cat = _normalize_text(category)
    result: dict[str, float] = {}

    # 精确匹配已知类目
    for known in KNOWN_CATEGORIES:
        if cat == _normalize_text(known):
            result[known] = 1.0
            return result

    # 模糊匹配（包含关系）
    for known in KNOWN_CATEGORIES:
        known_norm = _normalize_text(known)
        if cat in known_norm or known_norm in cat:
            result[known] = 0.8
        elif len(set(cat) & set(known_norm)) / max(len(set(cat) | set(known_norm)), 1) > 0.5:
            result[known] = 0.5

    if not result:
        result["其他"] = 1.0

    return result


def _price_normalized(product: Product) -> float:
    """价格归一化到 [0, 1] 区间

    使用 log 压缩 + sigmoid 映射处理极端值：
      price_norm = 1 / (1 + e^(-log(price+1)/4 + 2))
    使得大多数价格落在 0~1 合理区间。
    """
    price = getattr(product, "sale_price", None) or product.price
    if price <= 0:
        return 0.0
    # log 压缩 + 平移缩放
    log_price = np.log1p(price)
    # 假设 10元~1e7元 范围映射到 0~1
    norm = 1.0 / (1.0 + np.exp(-(log_price - 8.0) / 2.5))
    return round(float(norm), 4)


def _recency_score(created_at: datetime | None, decay_days: float = 90.0) -> float:
    """新鲜度分数 [0, 1]，越新越接近 1

    Args:
        created_at: 创建时间
        decay_days: 半衰期（天），默认 90 天后衰减到 0.5
    """
    if created_at is None:
        return 0.0

    # 确保 datetime 有时区信息
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)

    now = datetime.now(UTC)
    delta_days = (now - created_at).total_seconds() / 86400.0

    if delta_days <= 0:
        return 1.0

    # 指数衰减
    score = np.exp(-delta_days / decay_days)
    return round(float(score), 4)


def _parse_budget(budget_str: str | None) -> tuple[float, float] | None:
    """解析预算字符串，返回 (min, max) 元组
    已迁移到 app.utils — 保持兼容
    """
    return parse_budget(budget_str)


def _build_text_corpus(
    *fields: str | None,
) -> str:
    """将多个文本字段拼接为用于 TF-IDF 的语料"""
    parts = [f.strip() for f in fields if f and f.strip()]
    return " ".join(parts)


# ============================================================
# TF-IDF 向量化（有状态缓存 — 模块级懒加载）
# ============================================================

_TFIDF_VECTORIZER = None
_TFIDF_FITTED = False


def _get_tfidf_vectorizer():
    """获取 TF-IDF 向量器（单例懒加载）"""
    global _TFIDF_VECTORIZER
    if _TFIDF_VECTORIZER is None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        _TFIDF_VECTORIZER = TfidfVectorizer(
            max_features=TFIDF_MAX_FEATURES,
            analyzer="word",
            token_pattern=r"(?u)\b\w+\b",
            ngram_range=TFIDF_NGRAM_RANGE,
            sublinear_tf=True,
        )
    return _TFIDF_VECTORIZER


def _compute_tfidf_vector(text_a: str, text_b: str) -> tuple[np.ndarray, np.ndarray]:
    """计算两段文本的 TF-IDF 向量（使用缓存的向量器，首次调用时 fit）

    Returns:
        (vec_a, vec_b): 两个 TF-IDF 向量
    """
    global _TFIDF_FITTED
    vectorizer = _get_tfidf_vectorizer()
    corpus = [text_a, text_b]
    if not _TFIDF_FITTED:
        tfidf_matrix = vectorizer.fit_transform(corpus)
        _TFIDF_FITTED = True
    else:
        tfidf_matrix = vectorizer.transform(corpus)
    return tfidf_matrix[0:1].toarray()[0], tfidf_matrix[1:2].toarray()[0]


def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """计算余弦相似度"""
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


# ============================================================
# 核心特征提取函数
# ============================================================


def extract_product_features(product: Product) -> dict[str, Any]:
    """从 Product ORM 对象中提取结构化特征

    Returns:
        包含以下字段的字典:
        - id: int
        - category_vector: dict[str, float] — 类目多标签编码
        - keywords: list[str] — jieba 关键词
        - text_corpus: str — 用于 TF-IDF 的完整文本
        - price_norm: float — 归一化价格 [0, 1]
        - price_raw: float — 原始价格
        - recency_score: float — 新鲜度 [0, 1]
        - extracted_at: float — Unix 时间戳
    """
    # 文本特征
    text_corpus = _build_text_corpus(
        product.name,
        product.description,
        getattr(product, "tags", None),
        getattr(product, "brand", None),
        product.category,
    )
    keywords = _extract_keywords(text_corpus)

    # 类目特征
    category_vector = _category_vector(product.category)

    # 价格特征
    price_norm = _price_normalized(product)
    price_raw = getattr(product, "sale_price", None) or product.price

    # 新鲜度
    recency = _recency_score(product.created_at)

    return {
        "id": product.id,
        "source_type": "product",
        "category_vector": category_vector,
        "keywords": keywords,
        "text_corpus": text_corpus,
        "price_norm": price_norm,
        "price_raw": price_raw,
        "recency_score": recency,
        "extracted_at": time.time(),
    }


def extract_need_features(need: BusinessNeed) -> dict[str, Any]:
    """从 BusinessNeed ORM 对象中提取结构化特征

    Returns:
        包含以下字段的字典:
        - id: int
        - category_vector: dict[str, float] — 类目多标签编码
        - keywords: list[str] — jieba 关键词
        - text_corpus: str — 用于 TF-IDF 的完整文本
        - budget_range: tuple[float, float] | None — 预算范围 (min, max)
        - budget_mid: float | None — 预算中点（归一化后）
        - recency_score: float — 新鲜度 [0, 1]
        - extracted_at: float — Unix 时间戳
    """
    # 文本特征
    text_corpus = _build_text_corpus(
        need.title,
        need.description,
        need.category,
    )
    keywords = _extract_keywords(text_corpus)

    # 类目特征
    category_vector = _category_vector(need.category)

    # 预算特征
    budget_range = _parse_budget(need.budget)
    budget_mid = None
    if budget_range:
        low, high = budget_range
        if high == float("inf"):
            budget_mid = float(low)  # 以最低值为代表
        elif high > 0:
            budget_mid = (low + high) / 2.0
        else:
            budget_mid = low

    # 新鲜度
    recency = _recency_score(need.created_at)

    return {
        "id": need.id,
        "source_type": "need",
        "category_vector": category_vector,
        "keywords": keywords,
        "text_corpus": text_corpus,
        "budget_range": budget_range,
        "budget_mid": budget_mid,
        "recency_score": recency,
        "extracted_at": time.time(),
    }


# ============================================================
# 相似度计算
# ============================================================


def compute_similarity(
    prod_features: dict[str, Any],
    need_features: dict[str, Any],
) -> float:
    """计算产品特征与需求特征的综合相似度 [0, 1]

    使用以下维度:
      1. 类目相似度 (category_sim): 基于 category_vector 的 Jaccard 相似度
      2. 关键词 TF-IDF 相似度 (text_sim): 基于 TF-IDF 余弦相似度
      3. 价格-预算匹配度 (price_budget_sim): 价格在预算范围内的匹配度
      4. 新鲜度匹配度 (recency_sim): 两者新鲜度的调和平均

    最终分数 = 0.45 * category_sim + 0.35 * text_sim + 0.15 * price_budget_sim + 0.05 * recency_sim
    """
    # 1. 类目相似度 — Jaccard 在类别向量上
    cat_sim = _category_similarity(
        prod_features.get("category_vector", {}),
        need_features.get("category_vector", {}),
    )

    # 2. 文本 TF-IDF 相似度
    text_sim = _text_similarity(
        prod_features.get("text_corpus", ""),
        need_features.get("text_corpus", ""),
    )

    # 3. 价格-预算匹配度
    price_budget_sim = _price_budget_similarity(
        prod_features.get("price_raw", 0.0),
        need_features.get("budget_range", None),
    )

    # 4. 新鲜度调和
    recency_sim = _recency_similarity(
        prod_features.get("recency_score", 0.0),
        need_features.get("recency_score", 0.0),
    )

    # 加权综合
    final_score = 0.45 * cat_sim + 0.35 * text_sim + 0.15 * price_budget_sim + 0.05 * recency_sim

    return round(float(np.clip(final_score, 0.0, 1.0)), 4)


def _category_similarity(
    cat_a: dict[str, float],
    cat_b: dict[str, float],
) -> float:
    """基于类别向量的 Jaccard 相似度"""
    if not cat_a or not cat_b:
        return 0.0

    keys_a = set(cat_a.keys())
    keys_b = set(cat_b.keys())

    intersection = keys_a & keys_b
    union = keys_a | keys_b

    if not union:
        return 0.0

    # 加权 Jaccard：交集内取最小置信度之和 / 并集内取最大置信度之和
    inter_weight = sum(min(cat_a[k], cat_b[k]) for k in intersection)
    union_weight = sum(max(cat_a.get(k, 0.0), cat_b.get(k, 0.0)) for k in union)

    if union_weight == 0:
        return 0.0

    return float(inter_weight / union_weight)


def _text_similarity(text_a: str, text_b: str) -> float:
    """基于 TF-IDF 的文本余弦相似度"""
    if not text_a.strip() or not text_b.strip():
        return 0.0

    try:
        vec_a, vec_b = _compute_tfidf_vector(text_a, text_b)
        return _cosine_similarity(vec_a, vec_b)
    except Exception as e:
        logger.debug(f"TF-IDF 文本相似度计算失败: {e}")
        return 0.0


def _price_budget_similarity(
    price_raw: float,
    budget_range: tuple[float, float] | None,
) -> float:
    """计算价格与预算范围的匹配度 [0, 1]

    逻辑:
      - 无预算 → 0.0
      - 价格在预算内 → 1.0（越接近中点越高）
      - 价格在预算外但差距不大 → 部分分
      - 价格远超预算 → 0.0
    """
    if budget_range is None or price_raw <= 0:
        return 0.0

    min_budget, max_budget = budget_range

    if min_budget <= price_raw <= max_budget:
        # 在预算范围内，中心点最高分
        span = max_budget - min_budget
        if span <= 0:
            return 1.0
        center = (min_budget + max_budget) / 2.0
        distance = abs(price_raw - center) / span
        return round(float(max(0.5, 1.0 - distance)), 4)

    # 超出预算
    if max_budget != float("inf") and price_raw > max_budget:
        ratio = max_budget / max(price_raw, 1)
        return round(float(max(0.0, ratio * 0.5)), 4)  # 最多 0.5
    elif min_budget > 0 and price_raw < min_budget:
        ratio = price_raw / min_budget
        return round(float(max(0.0, ratio * 0.5)), 4)  # 最多 0.5

    return 0.0


def _recency_similarity(recency_a: float, recency_b: float) -> float:
    """两个新鲜度分数的调和平均 — 鼓励双方都是新鲜的"""
    if recency_a <= 0 or recency_b <= 0:
        return 0.0
    # 几何平均（对低分更敏感）
    return float(np.sqrt(recency_a * recency_b))


# ============================================================
# 分数组合
# ============================================================


def combine_scores(
    category_score: float = 0.0,
    keyword_score: float = 0.0,
    price_score: float = 0.0,
    feature_score: float = 0.0,
    weights: dict[str, float] | None = None,
) -> float:
    """组合多个匹配分数为最终分数 [0, 1]

    支持自定义权重，默认使用 matching_engine 兼容的权重:
      category=0.40, keyword=0.40, price=0.20, feature=0.00

    所有输入分数应在 [0, 1] 区间内。
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    # 确保权重和为 1
    total_weight = sum(w.values())
    if total_weight <= 0:
        return 0.0

    # 归一化权重
    normalized_w = {k: v / total_weight for k, v in w.items()}

    final_score = (
        normalized_w["category"] * max(0.0, min(1.0, category_score))
        + normalized_w["keyword"] * max(0.0, min(1.0, keyword_score))
        + normalized_w["price"] * max(0.0, min(1.0, price_score))
        + normalized_w["feature"] * max(0.0, min(1.0, feature_score))
    )

    return round(float(final_score), 4)


# ============================================================
# 全流程管道
# ============================================================


def run_pipeline(
    product: Product,
    need: BusinessNeed,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """运行完整的特征工程管道

    1. 提取产品和需求的特征
    2. 计算特征相似度
    3. 返回结构化结果

    Args:
        product: Product ORM 对象
        need: BusinessNeed ORM 对象
        weights: 可选权重覆盖

    Returns:
        {
            "features": {
                "product": {...},
                "need": {...},
            },
            "scores": {
                "category_similarity": float,
                "text_similarity": float,
                "price_budget_similarity": float,
                "recency_similarity": float,
                "feature_similarity": float,
                "combined_score": float,  # 使用 combine_scores 的组合分
            },
            "pipeline_version": "1.0",
        }
    """
    prod_feat = extract_product_features(product)
    need_feat = extract_need_features(need)

    feature_sim = compute_similarity(prod_feat, need_feat)

    # 如果需要，也可以计算与 matching_engine 兼容的子分数
    # 这里仅从 feature_sim 内部拆解（已包含各维度）
    # 实际子分数由外部传入或从特征中推导

    return {
        "features": {
            "product": prod_feat,
            "need": need_feat,
        },
        "scores": {
            "category_similarity": _category_similarity(
                prod_feat.get("category_vector", {}),
                need_feat.get("category_vector", {}),
            ),
            "text_similarity": _text_similarity(
                prod_feat.get("text_corpus", ""),
                need_feat.get("text_corpus", ""),
            ),
            "price_budget_similarity": _price_budget_similarity(
                prod_feat.get("price_raw", 0.0),
                need_feat.get("budget_range", None),
            ),
            "recency_similarity": _recency_similarity(
                prod_feat.get("recency_score", 0.0),
                need_feat.get("recency_score", 0.0),
            ),
            "feature_similarity": feature_sim,
            "combined_score": combine_scores(weights=weights),
        },
        "pipeline_version": "1.0",
    }
