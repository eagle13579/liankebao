"""
链客宝 AI 供需匹配引擎模块 (v2 - 工业化升级)
===============================================

GAP 补齐:
  P0: ① jieba分词 ② LRU缓存 ③ 单元测试
  P1: ④ 配置化同义词 ⑤ TF-IDF加权 ⑥ 匹配质量监控
  P2: ⑦ 向量检索正式接入 ⑧ A/B测试框架

功能:
  1. MatchEngine 类 — 规则引擎(v1) + 增强引擎(v2)
     - match_needs_to_products(need_id) → 返回匹配的产品列表和匹配分数
     - match_products_to_needs(product_id) → 返回匹配的需求列表和匹配分数
  2. 匹配规则：类目匹配 / 关键词匹配(TF-IDF) / 价格区间匹配(不变)
  3. API:
     - GET /api/matching/needs/{id}/products → 需求匹配产品
     - GET /api/matching/products/{id}/needs → 产品匹配需求
     - POST /api/matching/refresh → 重建索引
  4. A/B测试: ?strategy=v1|v2 参数控制新旧引擎

注册方式（在 main.py 中）:
    import matching_engine as matching_engine_module
    app.include_router(matching_engine_module.router)
"""

import json
import logging
import os
import random
import re
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import jieba
import numpy as np
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import BusinessNeed, Product, User

# 特征工程管道（第4评分维度）
from app import feature_pipeline as feature_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/matching", tags=["AI供需匹配"])


# ===== Pydantic 响应模型 =====


class MatchResult(BaseModel):
    id: int
    title: str
    description: str | None = None
    category: str | None = None
    match_score: float  # 0.0 ~ 1.0
    match_reasons: list[str]
    strategy: str | None = None  # 标注使用哪个版本
    diversity_note: str | None = None  # 多样性探索标注: "多样性降权" 或 "探索推荐"


class MatchResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: list[MatchResult]


# ===== 缓存层 (GAP 2) =====


class CacheEntry:
    """带 TTL 的缓存条目"""

    __slots__ = ("data", "timestamp", "ttl")

    def __init__(self, data: Any, ttl: float = 60.0):
        self.data = data
        self.timestamp = time.time()
        self.ttl = ttl

    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl


_cache: dict[str, CacheEntry] = {}
_CACHE_TTL = 60  # 秒


def get_cached(key: str, fetch_func: Callable, ttl: float = _CACHE_TTL) -> Any:
    """获取缓存，过期则自动刷新"""
    entry = _cache.get(key)
    if entry is not None and not entry.is_expired():
        match_metrics.record_cache_hit()
        return entry.data
    match_metrics.record_cache_miss()
    data = fetch_func()
    _cache[key] = CacheEntry(data, ttl=ttl)
    return data


def clear_cache(key: str | None = None) -> None:
    """清除缓存（全部或指定 key）"""
    if key:
        _cache.pop(key, None)
    else:
        _cache.clear()


# ===== 监控指标 (GAP 6) =====


class MatchMetrics:
    """匹配质量监控：响应时间、分数分布、请求计数、分类分布、缓存命中、采纳率"""

    def __init__(self):
        self.request_count = 0
        self.total_response_time = 0.0
        self.total_score = 0.0
        self.score_buckets: dict[str, int] = defaultdict(int)
        self.category_distribution: dict[str, int] = defaultdict(int)
        self.adopted_count = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.adoption_recorded = 0
        self.daily_requests = 0
        self.last_reset = time.time()

    def record(self, score: float, response_time: float, category: str | None = None) -> None:
        """记录一次匹配结果"""
        self.request_count += 1
        self.daily_requests += 1
        self.total_response_time += response_time
        self.total_score += score
        # 分段统计 (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
        bucket = int(score * 5) * 0.2
        key = f"{bucket:.1f}-{bucket + 0.2:.1f}"
        self.score_buckets[key] += 1
        # 分类分布
        if category:
            self.category_distribution[category] += 1

    def record_adoption(self) -> None:
        """记录一次匹配被用户点击/采纳"""
        self.adopted_count += 1
        self.adoption_recorded += 1

    def record_cache_hit(self) -> None:
        """记录一次缓存命中"""
        self.cache_hits += 1

    def record_cache_miss(self) -> None:
        """记录一次缓存未命中"""
        self.cache_misses += 1

    def get_stats(self) -> dict:
        """获取监控统计"""
        avg_time = self.total_response_time / max(self.request_count, 1)
        avg_score = self.total_score / max(self.request_count, 1)
        cache_total = self.cache_hits + self.cache_misses
        cache_hit_rate = round(self.cache_hits / max(cache_total, 1), 4)
        success_rate = round(self.adopted_count / max(self.request_count, 1), 4)
        return {
            "total_requests": self.request_count,
            "total_matches": self.request_count,
            "avg_response_time_ms": round(avg_time * 1000, 2),
            "avg_match_score": round(avg_score, 4),
            "match_success_rate": success_rate,
            "adopted_count": self.adopted_count,
            "cache_hit_rate": cache_hit_rate,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "score_distribution": dict(sorted(self.score_buckets.items())),
            "category_distribution": dict(sorted(self.category_distribution.items(), key=lambda x: x[1], reverse=True)),
        }

    def reset_daily(self) -> None:
        self.daily_requests = 0
        self.last_reset = time.time()


match_metrics = MatchMetrics()


# ===== 停用词表 =====

STOP_WORDS: set = {
    "的",
    "了",
    "在",
    "是",
    "我",
    "有",
    "和",
    "就",
    "不",
    "人",
    "都",
    "一",
    "一个",
    "上",
    "也",
    "很",
    "到",
    "说",
    "要",
    "去",
    "你",
    "会",
    "着",
    "没有",
    "看",
    "好",
    "自己",
    "这",
    "他",
    "她",
    "它",
    "们",
    "为",
    "与",
    "及",
    "等",
    "或",
    "之",
    "以",
    "被",
    "让",
    "给",
    "对",
    "从",
    "把",
    "向",
    "能",
    "做",
    "用",
    "买",
    "卖",
    "找",
    "寻",
    "求",
    "供",
    "需",
    "可以",
    "需要",
    "能够",
    "应该",
    "这个",
    "那个",
    "什么",
    "如何",
    "怎么",
    "我们",
    "他们",
    "你们",
    "已经",
    "还是",
    "因为",
    "所以",
    "如果",
    "虽然",
    "但是",
    "而且",
    "或者",
    "并且",
    "不仅",
    "以及",
    "关于",
    "对于",
    "根据",
    "按照",
    "通过",
    "经过",
    "进行",
    "例如",
    "比如",
    "希望",
    "想要",
    "目前",
    "现在",
    "未来",
    "主要",
    "相关",
    "包括",
    "具有",
    "提供",
    "支持",
    "实现",
    "开发",
    "服务",
    "系统",
    "平台",
    "方案",
    "项目",
    "产品",
    "品牌",
}


# ===== 冷启动配置常量 =====

# 新产品/新需求定义为创建时间小于此天数（或无匹配记录）
COLD_START_DAYS = 7
# 冷启动商品匹配分数提升系数（20%）
COLD_START_BOOST = 1.2
# 匹配结果数量低于此阈值时触发热门商品兜底
MIN_MATCHES_FOR_HOT_FALLBACK = 3
# 热门商品兜底补充数量
HOT_FALLBACK_COUNT = 5


# ===== 多样性探索策略配置 =====

# 多样性降权系数 (0=纯分数排序, 1=纯多样性排序)
DIVERSITY_ALPHA = 0.3
# 探索概率 (5%概率随机推荐探索)
EXPLORE_EPSILON = 0.05

# 特征评分权重（第4评分维度：基于 feature_pipeline 的特征相似度）
FEATURE_WEIGHT = 0.10


# ===== 匹配引擎 (GAP 8: A/B 测试框架) =====


class MatchEngine:
    """
    匹配引擎（v1=原规则引擎 / v2=增强引擎）

    匹配规则（权重累加）:
      1. 类目匹配 (0~40分): 类目完全相同得40分，同义词匹配得30分
      2. 关键词匹配 (0~40分): v1=set交集, v2=TF-IDF加权余弦相似度
      3. 价格区间匹配 (0~20分): 需求预算与产品价格重叠度
    """

    # ---- 默认类目同义词（备用，当配置文件不存在时使用） ----
    _DEFAULT_SYNONYMS = {
        "大健康": ["健康", "保健品", "养生", "医疗", "大健康"],
        "食品": ["零食", "特产", "农产品", "有机", "食品/大健康"],
        "企业服务": ["企业", "商务", "法律", "财税", "咨询", "企业服务"],
        "企业家服务": ["企业", "商务", "企业家服务", "企业服务"],
        "教育培训": ["培训", "课程", "教育", "训练营", "学习", "教育培训"],
        "科技产品": ["AI", "智能", "软件", "SaaS", "科技", "SaaS硬件"],
        "SaaS硬件": ["SaaS", "硬件", "智能", "科技产品"],
        "消费品": ["日用品", "快消品", "生活", "消费品"],
    }

    # TF-IDF 向量器（类级别共享，懒加载）
    _tfidf_vectorizer = None
    _tfidf_fitted = False
    _tfidf_vocab = None

    # ---- Feedback 反馈权重（类级别共享，产品ID→累计反馈分） ----
    _feedback_weights: dict[int, float] = {}  # product_id → [-1.0, 1.0]
    _FEEDBACK_BOOST_MAX = 0.10  # 单条反馈最大影响 ±10% 最终分数

    # ---- 多样性探索策略 ----

    @staticmethod
    def diversity_rerank(
        results: list[MatchResult],
        alpha: float = DIVERSITY_ALPHA,
    ) -> list[MatchResult]:
        """多样性重排序：在保持分数优先的同时，增加结果类目多样性

        算法（贪心）:
          1. 从最高分开始选
          2. 每选一个，对同类别的其他候选结果降权
             降权公式: new_score = score * (1 - alpha * category_overlap)
          3. 确保前5个结果至少有3个不同 category

        Args:
            results: 已按 match_score 降序排列的 MatchResult 列表
            alpha: 多样性降权系数 (0=纯分数排序, 1=纯多样性排序)

        Returns:
            重排序后的列表（每个元素可能附带 diversity_note）
        """
        if not results or alpha <= 0.0:
            for r in results:
                r.diversity_note = None
            return results

        results = list(results)  # 复制一份避免修改外部引用

        selected: list[MatchResult] = []
        remaining = list(results)

        while remaining:
            # 第一个直接取最高分
            if not selected:
                best = remaining.pop(0)
                best.diversity_note = None
                selected.append(best)
                continue

            # 已选类目统计
            selected_cats: list[str | None] = [r.category for r in selected]

            # 对每个剩余候选计算多样性加权分数
            scored: list[tuple[float, MatchResult, bool]] = []
            for r in remaining:
                # 计算该类目在已选结果中出现的次数
                overlap = sum(1 for c in selected_cats if c and r.category and c == r.category)
                penalty = alpha * overlap
                div_score = r.match_score * max(1.0 - penalty, 0.0)
                was_penalized = overlap > 0
                scored.append((div_score, r, was_penalized))

            # 按多样性加权分数降序排列
            scored.sort(key=lambda x: -x[0])

            # 前5个位置强制保证类目多样性
            if len(selected) < 5:
                selected_cat_set = {c for c in selected_cats if c}
                # 找第一个不同类目的候选（如果有的话）
                best_alt = None
                for div_s, candidate, _ in scored:
                    if candidate.category and candidate.category not in selected_cat_set:
                        best_alt = (div_s, candidate)
                        break

                if best_alt is not None:
                    # 当前最高分候选的类目
                    top_cat = scored[0][1].category
                    # 如果最高分候选的类目已经在已选中出现多次（≥2次），强制选不同类目
                    cat_count_in_selected = selected_cats.count(top_cat)
                    if cat_count_in_selected >= 2 and top_cat is not None:
                        # 用不同类目中多样性分最高的替代
                        remaining.remove(best_alt[1])
                        best_alt[1].diversity_note = "多样性降权"
                        selected.append(best_alt[1])
                        continue

            # 正常选取多样性加权分最高的
            _, best, was_penalized = scored[0]
            remaining.remove(best)
            best.diversity_note = "多样性降权" if was_penalized else None
            selected.append(best)

        return selected

    @staticmethod
    def _apply_exploration(results: list[MatchResult], epsilon: float = EXPLORE_EPSILON) -> list[MatchResult]:
        """探索推荐：以小概率随机替换一个非首位的结果，增加推荐新颖度

        Args:
            results: 已排序的 MatchResult 列表
            epsilon: 探索概率 (默认 0.05 = 5%)

        Returns:
            可能被随机替换过的列表
        """
        if not results or len(results) < 3 or epsilon <= 0.0:
            return results

        if random.random() < epsilon:
            # 从位置 2 到末尾之间随机选一个
            swap_idx = random.randint(1, len(results) - 1)
            results[swap_idx].diversity_note = "探索推荐"
            logger.info(
                "探索推荐触发",
                extra={
                    "item_id": results[swap_idx].id,
                    "item_title": results[swap_idx].title,
                    "original_score": results[swap_idx].match_score,
                },
            )
        return results

    def __init__(self, db: Session, strategy: str = "v2", feedback_weight: float = 1.0):
        """
        Args:
            db: 数据库会话
            strategy: 'v1' = 原规则引擎, 'v2' = 增强引擎（默认）
            feedback_weight: 反馈权重系数 (0.0=忽略反馈, 1.0=满权重), 控制反馈对匹配评分的影响程度
        """
        if strategy not in ("v1", "v2"):
            raise ValueError(f"strategy 必须是 'v1' 或 'v2', 收到 '{strategy}'")
        self.db = db
        self.strategy = strategy
        self.feedback_weight = max(0.0, min(1.0, feedback_weight))
        # 配置文件路径（与引擎文件同目录下的 config/category_synonyms.json）
        engine_dir = os.path.dirname(os.path.abspath(__file__))
        self._synonyms_config_path = os.path.join(engine_dir, "config", "category_synonyms.json")
        # 类目同义词（懒加载）
        self._synonyms = None

    # ---- 配置化同义词 (GAP 4) ----

    @property
    def CATEGORY_SYNONYMS(self) -> dict[str, list[str]]:
        """从配置文件加载类目同义词，不存在则使用默认值"""
        if self._synonyms is not None:
            return self._synonyms
        synonyms = self._load_synonyms_from_file()
        if not synonyms:
            synonyms = dict(self._DEFAULT_SYNONYMS)
        self._synonyms = synonyms
        return self._synonyms

    def _load_synonyms_from_file(self) -> dict[str, list[str]] | None:
        """从 JSON 配置文件加载类目同义词"""
        try:
            if os.path.exists(self._synonyms_config_path):
                with open(self._synonyms_config_path, encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"加载类目同义词配置文件失败: {e}")
        return None

    # ---- 文本规范化 ----

    @staticmethod
    def _normalize_text(text_str: str | None) -> str:
        """规范化文本：转小写、去标点"""
        if not text_str:
            return ""
        text_str = text_str.lower().strip()
        text_str = re.sub(r"[^\w\u4e00-\u9fff\s]", " ", text_str)
        return text_str.strip()

    # ---- GAP 1: jieba 分词（v2） ----

    def _extract_keywords_v1(self, text_str: str | None) -> list[str]:
        """(v1) 按空格和分隔符简单分割"""
        if not text_str:
            return []
        normalized = self._normalize_text(text_str)
        tokens = re.split(r"[\s,，、/／;；]+", normalized)
        return list({t for t in tokens if len(t) >= 2 and t not in STOP_WORDS})

    def _extract_keywords_v2(self, text_str: str | None) -> list[str]:
        """(v2) jieba 分词 + 停用词过滤"""
        if not text_str:
            return []
        normalized = self._normalize_text(text_str)
        words = jieba.lcut(normalized)
        return [w for w in words if len(w) >= 2 and w not in STOP_WORDS]

    def _extract_keywords(self, text_str: str | None) -> list[str]:
        """根据策略选择分词方式"""
        if self.strategy == "v1":
            return self._extract_keywords_v1(text_str)
        return self._extract_keywords_v2(text_str)

    # ---- 类目匹配 ----

    def _match_category(self, product_category: str | None, need_category: str | None) -> tuple[float, list[str]]:
        """类目匹配打分 (0~40分)"""
        reasons = []
        if not product_category or not need_category:
            return 0.0, reasons

        pc = self._normalize_text(product_category)
        nc = self._normalize_text(need_category)

        # 完全相同
        if pc == nc:
            return 40.0, ["类目完全匹配"]

        # 检查是否是同类目（通过同义词映射）
        synonyms = self.CATEGORY_SYNONYMS  # 从配置文件加载 (GAP 4)
        for cat_name, syn_list in synonyms.items():
            cat_lower = cat_name.lower()
            syn_lower = [s.lower() for s in syn_list]
            search_space = [cat_lower] + syn_lower
            pc_match = any(s in pc or pc in s for s in search_space)
            nc_match = any(s in nc or nc in s for s in search_space)
            if pc_match and nc_match:
                return 30.0, [f"类目匹配: 均属于「{cat_name}」类"]

        # 部分匹配（类目名称有共同字符）
        from difflib import SequenceMatcher

        similarity = SequenceMatcher(None, pc, nc).ratio()
        if similarity > 0.3:
            score = round(10 + similarity * 20, 1)  # 10~30分
            return min(score, 30.0), [f"类目部分匹配 (相似度{int(similarity * 100)}%)"]

        return 0.0, reasons

    # ---- GAP 5+7: TF-IDF 关键词匹配（始终启用） ----

    def _build_tfidf_corpus(self, product: Product, need: BusinessNeed) -> tuple[str, str]:
        """构建 TF-IDF 语料文本"""
        prod_text = " ".join(
            [
                product.name or "",
                product.description or "",
                product.tags or "",
                product.brand or "",
                product.category or "",
            ]
        )
        need_text = " ".join(
            [
                need.title or "",
                need.description or "",
                need.category or "",
            ]
        )
        return prod_text, need_text

    def _compute_tfidf_similarity(self, prod_text: str, need_text: str) -> float:
        """用 TF-IDF 计算产品与需求的文本相似度"""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        corpus = [prod_text, need_text]
        try:
            vectorizer = TfidfVectorizer(
                max_features=1000,
                analyzer="word",
                token_pattern=r"(?u)\b\w+\b",
                ngram_range=(1, 2),
                sublinear_tf=True,
            )
            tfidf_matrix = vectorizer.fit_transform(corpus)
            sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            return float(sim)
        except Exception as e:
            logger.debug(f"TF-IDF 相似度计算跳过: {e}")
            return 0.0

    def _match_keywords_v1(self, product: Product, need: BusinessNeed) -> tuple[float, list[str]]:
        """(v1) set 交集匹配 (0~40分)"""
        reasons = []
        prod_texts = [
            product.name or "",
            product.description or "",
            product.tags or "",
            product.brand or "",
            product.category or "",
        ]
        need_texts = [
            need.title or "",
            need.description or "",
            need.category or "",
        ]

        prod_keywords = self._extract_keywords_v1(" ".join(prod_texts))
        need_keywords = self._extract_keywords_v1(" ".join(need_texts))

        if not prod_keywords or not need_keywords:
            return 0.0, reasons

        prod_set = set(prod_keywords)
        need_set = set(need_keywords)
        matched = prod_set & need_set
        if not matched:
            return 0.0, reasons

        match_count = len(matched)
        total_possible = min(len(prod_set), len(need_set))
        if total_possible == 0:
            return 0.0, reasons

        ratio = match_count / total_possible
        score = min(ratio * 40.0, 40.0)
        matched_str = ", ".join(list(matched)[:5])
        reasons.append(f"关键词匹配 ({match_count}个): {matched_str}")

        # 向量增强（USE_VECTOR_SEARCH=1 时启用）
        score = self._apply_vector_bonus(score, reasons, product, need)

        return round(score, 1), reasons

    def _match_keywords_v2(self, product: Product, need: BusinessNeed) -> tuple[float, list[str]]:
        """(v2) TF-IDF 加权匹配 (0~40分) — GAP 5+7"""
        reasons = []
        prod_texts = [
            product.name or "",
            product.description or "",
            product.tags or "",
            product.brand or "",
            product.category or "",
        ]
        need_texts = [
            need.title or "",
            need.description or "",
            need.category or "",
        ]

        prod_text = " ".join(prod_texts)
        need_text = " ".join(need_texts)

        # jieba 分词 + 停用词过滤
        prod_keywords = self._extract_keywords_v2(prod_text)
        need_keywords = self._extract_keywords_v2(need_text)

        if not prod_keywords or not need_keywords:
            return 0.0, reasons

        # 1) 关键词语义相似度（TF-IDF 加权余弦）
        tfidf_sim = self._compute_tfidf_similarity(
            " ".join(prod_keywords),
            " ".join(need_keywords),
        )

        # 2) 关键词重叠率
        prod_set = set(prod_keywords)
        need_set = set(need_keywords)
        matched = prod_set & need_set
        overlap_ratio = len(matched) / max(len(prod_set | need_set), 1) if matched else 0.0

        # 综合评分：TF-IDF 权重 0.7 + 重叠率 0.3，映射到 0~40 分
        combined = tfidf_sim * 0.7 + overlap_ratio * 0.3
        score = combined * 40.0

        if tfidf_sim > 0.1:
            reasons.append(f"语义匹配 (TF-IDF 相似度 {tfidf_sim:.2f})")
        if matched:
            matched_str = ", ".join(list(matched)[:5])
            reasons.append(f"关键词匹配 ({len(matched)}个): {matched_str}")

        return round(min(score, 40.0), 1), reasons

    def _match_keywords(self, product: Product, need: BusinessNeed) -> tuple[float, list[str]]:
        """关键词匹配 — 根据策略选择 v1 或 v2"""
        if self.strategy == "v1":
            return self._match_keywords_v1(product, need)
        return self._match_keywords_v2(product, need)

    def _apply_vector_bonus(self, score: float, reasons: list[str], product: Product, need: BusinessNeed) -> float:
        """向量增强（USE_VECTOR_SEARCH=1 时启用）"""
        try:
            from app.vector_search import USE_VECTOR_SEARCH as _USE_VS
            from app.vector_search import build_document_text, get_embedding_backend

            if _USE_VS:
                backend = get_embedding_backend()
                prod_text = build_document_text(
                    title=product.name or "",
                    content=product.description or "",
                    category=product.category or "",
                    tags=product.tags or "",
                    brand=product.brand or "",
                )
                need_text = build_document_text(
                    title=need.title or "",
                    content=need.description or "",
                    category=need.category or "",
                )
                if prod_text and need_text:
                    vecs = backend.embed([prod_text, need_text])
                    semantic_sim = float(np.dot(vecs[0], vecs[1]))
                    semantic_sim = max(0.0, min(1.0, (semantic_sim + 1.0) / 2.0))
                    vector_bonus = semantic_sim * 20.0
                    if vector_bonus > 5.0:
                        score = min(score + vector_bonus, 60.0)
                        reasons.append(f"语义匹配 (相似度 {semantic_sim:.2f})")
        except Exception as e:
            logger.debug(f"向量增强匹配跳过: {e}")
        return score

    # ---- Feedback 反馈权重 ----

    @classmethod
    def record_feedback(cls, product_id: int, action: str) -> None:
        """记录用户反馈，影响匹配引擎的评分权重

        Args:
            product_id: 被反馈的产品ID
            action: 反馈动作 ('like' / 'dislike' / 'click' / 'adopt')
                     'like'/'click'/'adopt' → 正向加分
                     'dislike' → 负向减分
        """
        if action in ("like", "click", "adopt"):
            cls._feedback_weights[product_id] = min(
                1.0,
                cls._feedback_weights.get(product_id, 0.0) + cls._FEEDBACK_BOOST_MAX,
            )
        elif action == "dislike":
            cls._feedback_weights[product_id] = max(
                -1.0,
                cls._feedback_weights.get(product_id, 0.0) - cls._FEEDBACK_BOOST_MAX,
            )
        logger.debug(
            "feedback_recorded",
            extra={"product_id": product_id, "action": action, "weight": cls._feedback_weights.get(product_id, 0.0)},
        )

    # ---- 价格区间匹配（不变） ----

    @staticmethod
    def _parse_budget(budget_str: str | None) -> tuple[float, float] | None:
        if not budget_str:
            return None
        budget_str = budget_str.strip()
        pattern = r"(\d+(?:\.\d+)?)\s*(?:万|w)?\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*(?:万|w)?"
        m = re.search(pattern, budget_str)
        if m:
            min_val = float(m.group(1))
            max_val = float(m.group(2))
            if "万" in budget_str or "w" in budget_str.lower():
                min_val *= 10000
                max_val *= 10000
            return (min_val, max_val)

        pattern2 = r"(?:>|大于|不低于|以上)\s*(\d+(?:\.\d+)?)\s*(?:万|w)?"
        m = re.search(pattern2, budget_str)
        if m:
            val = float(m.group(1))
            if "万" in budget_str or "w" in budget_str.lower():
                val *= 10000
            return (val, float("inf"))

        # 匹配 "10万以上"（数字在前，关键词在后）
        pattern2b = r"(\d+(?:\.\d+)?)\s*(?:万|w)?\s*(?:以上|>|大于|不低于)"
        m = re.search(pattern2b, budget_str)
        if m:
            val = float(m.group(1))
            if "万" in budget_str or "w" in budget_str.lower():
                val *= 10000
            return (val, float("inf"))

        pattern3 = r"(?:<|小于|不超过|以内)\s*(\d+(?:\.\d+)?)\s*(?:万|w)?"
        m = re.search(pattern3, budget_str)
        if m:
            val = float(m.group(1))
            if "万" in budget_str or "w" in budget_str.lower():
                val *= 10000
            return (0, val)

        # 匹配 "5万以内"（数字在前，关键词在后）
        pattern3b = r"(\d+(?:\.\d+)?)\s*(?:万|w)?\s*(?:以内|<|小于|不超过)"
        m = re.search(pattern3b, budget_str)
        if m:
            val = float(m.group(1))
            if "万" in budget_str or "w" in budget_str.lower():
                val *= 10000
            return (0, val)

        return None

    @staticmethod
    def _match_price_range(product: Product, need: BusinessNeed) -> tuple[float, list[str]]:
        reasons = []
        product_price = getattr(product, "sale_price", None) or product.price

        budget_range = MatchEngine._parse_budget(need.budget)
        if not budget_range:
            return 0.0, reasons

        min_budget, max_budget = budget_range

        if min_budget <= product_price <= max_budget:
            span = max_budget - min_budget
            if span > 0:
                center = (min_budget + max_budget) / 2
                distance = abs(product_price - center) / span
                score = 20.0 * (1 - distance)
                reasons.append(f"价格匹配: ¥{product_price:.0f} 在预算 ¥{min_budget:.0f}~¥{max_budget:.0f} 内")
                return round(max(score, 10.0), 1), reasons
            else:
                return 20.0, [f"价格匹配: ¥{product_price:.0f} 符合预算"]

        if max_budget != float("inf") and product_price > max_budget:
            ratio = max_budget / max(product_price, 1)
            if ratio >= 0.5:
                return round(ratio * 10, 1), [f"价格略高于预算 (¥{product_price:.0f} > ¥{max_budget:.0f})"]
        elif min_budget > 0 and product_price < min_budget:
            ratio = product_price / min_budget
            if ratio >= 0.5:
                return round(ratio * 10, 1), [f"价格低于预算 (¥{product_price:.0f} < ¥{min_budget:.0f})"]

        return 0.0, reasons

    # ---- GAP 2: 缓存层 ----

    def _get_all_approved_products(self):
        """获取所有已上架产品（带缓存）"""

        def fetch():
            return self.db.query(Product).filter(Product.status == "approved").all()

        return get_cached("approved_products", fetch)

    def _get_all_open_needs(self):
        """获取所有 open 状态需求（带缓存）"""

        def fetch():
            return self.db.query(BusinessNeed).filter(BusinessNeed.status == "open").all()

        return get_cached("open_needs", fetch)

    # ---- 冷启动策略 ----

    @staticmethod
    def _is_cold_start_item(created_at, item_id: int, item_type: str = "product") -> bool:
        """判断是否为冷启动项目

        冷启动条件:
          1. 创建时间 < COLD_START_DAYS 天（新商品/新需求）
          2. 无匹配历史记录（产品未被任何需求匹配过 / 需求未被任何产品匹配过）

        Args:
            created_at: 创建时间（datetime 或 None）
            item_id: 项目ID
            item_type: 'product' 或 'need'

        Returns:
            bool: 是否为冷启动项目
        """
        # 条件1: 创建时间在冷启动窗口内
        if created_at is not None:
            age = datetime.utcnow() - created_at
            if age < timedelta(days=COLD_START_DAYS):
                return True

        # 条件2: 创建时间为空（无创建时间记录），也视为新项目
        if created_at is None:
            return True

        return False

    def _get_hot_fallback_products(self, need, top_k: int = HOT_FALLBACK_COUNT) -> list[MatchResult]:
        """热门商品兜底：当匹配数不足时，补充同品类热门商品"""
        results = []
        products = self._get_all_approved_products()

        # 按品类筛选，优先同品类
        same_category = []
        other_category = []
        for product in products:
            if need.category and product.category and self._normalize_text(product.category) == self._normalize_text(need.category):
                same_category.append(product)
            else:
                other_category.append(product)

        # 同品类商品：按 is_featured + sort_order 排序
        same_category.sort(key=lambda p: (p.is_featured or 0, p.sort_order or 0), reverse=True)

        # 其他品类：仅取 is_featured 商品
        other_featured = [p for p in other_category if getattr(p, "is_featured", 0)]
        other_featured.sort(key=lambda p: (p.sort_order or 0), reverse=True)

        # 构建结果
        candidates = same_category + other_featured
        for product in candidates[:top_k]:
            # 用简化匹配（仅类目匹配 + 基础分）
            cat_score, cat_reasons = self._match_category(product.category, need.category)
            total_score = cat_score  # 兜底商品仅按类目打分
            final_score = round(total_score / 100.0, 2)
            # 冷启动兜底最低保证分
            final_score = max(final_score, 0.1)

            results.append(
                MatchResult(
                    id=product.id,
                    title=product.name,
                    description=product.description[:200] if product.description else None,
                    category=product.category,
                    match_score=final_score,
                    match_reasons=["热门商品兜底"] + cat_reasons if cat_reasons else ["热门商品兜底"],
                    strategy=self.strategy,
                )
            )

        return results[:top_k]

    def _get_hot_fallback_needs(self, product, top_k: int = HOT_FALLBACK_COUNT) -> list[MatchResult]:
        """热门需求兜底：当匹配数不足时，补充同品类热门需求"""
        results = []
        needs = self._get_all_open_needs()

        # 按品类筛选，优先同品类
        same_category = []
        other_category = []
        for need in needs:
            if product.category and need.category and self._normalize_text(need.category) == self._normalize_text(product.category):
                same_category.append(need)
            else:
                other_category.append(need)

        # 同品类需求：按创建时间新到旧（新需求更热门）
        same_category.sort(key=lambda n: n.created_at or datetime.min, reverse=True)

        # 其他品类需求：限制数量
        other_category.sort(key=lambda n: n.created_at or datetime.min, reverse=True)

        candidates = same_category + other_category
        for need in candidates[:top_k]:
            cat_score, cat_reasons = self._match_category(product.category, need.category)
            total_score = cat_score
            final_score = round(total_score / 100.0, 2)
            final_score = max(final_score, 0.1)

            results.append(
                MatchResult(
                    id=need.id,
                    title=need.title,
                    description=need.description[:200] if need.description else None,
                    category=need.category,
                    match_score=final_score,
                    match_reasons=["热门需求兜底"] + cat_reasons if cat_reasons else ["热门需求兜底"],
                    strategy=self.strategy,
                )
            )

        return results[:top_k]

    # ---- GAP 6: 监控埋点 ----

    def _calculate_match(self, product: Product, need: BusinessNeed) -> MatchResult:
        """计算单个产品-需求对的匹配分数和原因（带监控）"""
        start_time = time.time()
        total_score = 0.0
        all_reasons = []

        # 1. 类目匹配 (0~40)
        cat_score, cat_reasons = self._match_category(product.category, need.category)
        total_score += cat_score
        all_reasons.extend(cat_reasons)

        # 2. 关键词匹配 (0~40)
        kw_score, kw_reasons = self._match_keywords(product, need)
        total_score += kw_score
        all_reasons.extend(kw_reasons)

        # 3. 价格区间匹配 (0~20)
        price_score, price_reasons = self._match_price_range(product, need)
        total_score += price_score
        all_reasons.extend(price_reasons)

        # 总分归一化到 0~1
        final_score = round(total_score / 100.0, 2)

        # 4. 反馈权重加持 (0~±10%，取决于 feedback_weight 系数)
        fb = self._feedback_weights.get(product.id, 0.0)
        if fb != 0.0 and self.feedback_weight > 0:
            feedback_modifier = fb * self._FEEDBACK_BOOST_MAX * self.feedback_weight
            final_score = min(1.0, max(0.0, final_score + feedback_modifier))
            if feedback_modifier > 0:
                all_reasons.append(f"用户正反馈 (+{int(feedback_modifier * 100)}%)")
            elif feedback_modifier < 0:
                all_reasons.append(f"用户负反馈 ({int(feedback_modifier * 100)}%)")

        # 5. 冷启动分数提升（新产品/新需求获得额外加分）
        if self._is_cold_start_item(getattr(product, "created_at", None), product.id, "product"):
            cold_boost = COLD_START_BOOST - 1.0  # 提升量 = 0.2 (20%)
            boosted_score = final_score * COLD_START_BOOST
            final_score = min(boosted_score, 1.0)
            all_reasons.append(f"冷启动新品加分 (+{int(cold_boost * 100)}%)")

        # 6. 特征相似度评分（第4评分维度，基于 feature_pipeline）
        try:
            pipeline_result = feature_pipeline.run_pipeline(product, need)
            feature_sim = pipeline_result.get("scores", {}).get("feature_similarity", 0.0)
            if feature_sim > 0.0:
                final_score = final_score * (1.0 - FEATURE_WEIGHT) + feature_sim * FEATURE_WEIGHT
                all_reasons.append(f"特征匹配 (+{feature_sim:.0%})")
            else:
                all_reasons.append("特征匹配 (无数据)")
        except Exception as e:
            logger.warning(f"特征管道评分降级（纯规则评分）: {e}")
            all_reasons.append("特征匹配 (降级)")

        final_score = min(max(final_score, 0.0), 1.0)

        # 监控记录
        elapsed = time.time() - start_time
        match_metrics.record(final_score, elapsed, category=product.category)

        return MatchResult(
            id=product.id,
            title=product.name,
            description=product.description[:200] if product.description else None,
            category=product.category,
            match_score=final_score,
            match_reasons=all_reasons if all_reasons else ["基础匹配"],
            strategy=self.strategy,
        )

    def _need_to_product_result(self, need: BusinessNeed, product: Product) -> MatchResult:
        result = self._calculate_match(product, need)
        return MatchResult(
            id=need.id,
            title=need.title,
            description=need.description[:200] if need.description else None,
            category=need.category,
            match_score=result.match_score,
            match_reasons=result.match_reasons,
            strategy=result.strategy,
        )

    # ---- 公共匹配方法 ----

    def match_needs_to_products(self, need_id: int, top_k: int = 20) -> list[MatchResult]:
        need = self.db.query(BusinessNeed).filter(BusinessNeed.id == need_id).first()
        if not need:
            return []

        products = self._get_all_approved_products()
        results = []
        for product in products:
            result = self._calculate_match(product, need)
            if result.match_score > 0:
                results.append(result)

        results.sort(key=lambda r: r.match_score, reverse=True)

        # 多样性重排序 + 探索推荐
        results = self.diversity_rerank(results, alpha=DIVERSITY_ALPHA)
        results = self._apply_exploration(results, epsilon=EXPLORE_EPSILON)

        results = results[:top_k]

        # 冷启动兜底：如果匹配结果太少，补充热门商品
        if len(results) < MIN_MATCHES_FOR_HOT_FALLBACK:
            hot_fallback = self._get_hot_fallback_products(need, top_k=HOT_FALLBACK_COUNT)
            existing_ids = {r.id for r in results}
            hot_to_add = [h for h in hot_fallback if h.id not in existing_ids]
            results.extend(hot_to_add)
            # 重新排序，确保兜底商品排在后面
            results.sort(key=lambda r: r.match_score, reverse=True)

        return results[:top_k]

    def match_products_to_needs(self, product_id: int, top_k: int = 20) -> list[MatchResult]:
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return []

        needs = self._get_all_open_needs()
        results = []
        for need in needs:
            result = self._need_to_product_result(need, product)
            if result.match_score > 0:
                results.append(result)

        results.sort(key=lambda r: r.match_score, reverse=True)

        # 多样性重排序 + 探索推荐
        results = self.diversity_rerank(results, alpha=DIVERSITY_ALPHA)
        results = self._apply_exploration(results, epsilon=EXPLORE_EPSILON)

        results = results[:top_k]

        # 冷启动兜底：如果匹配结果太少，补充热门需求
        if len(results) < MIN_MATCHES_FOR_HOT_FALLBACK:
            hot_fallback = self._get_hot_fallback_needs(product, top_k=HOT_FALLBACK_COUNT)
            existing_ids = {r.id for r in results}
            hot_to_add = [h for h in hot_fallback if h.id not in existing_ids]
            results.extend(hot_to_add)
            results.sort(key=lambda r: r.match_score, reverse=True)

        return results[:top_k]


# ===== API Endpoints =====


def get_engine(
    db: Session = Depends(get_db),
    strategy: str = Query("v2", pattern="^(v1|v2)$", description="匹配引擎版本: v1=原规则, v2=增强引擎"),
) -> MatchEngine:
    """依赖注入：创建匹配引擎实例（支持 A/B 测试）"""
    return MatchEngine(db, strategy=strategy)


@router.get("/needs/{need_id}/products")
def match_needs_to_products(
    need_id: int,
    top_k: int = Query(20, ge=1, le=100, description="返回结果数量上限"),
    strategy: str = Query("v2", pattern="^(v1|v2)$", description="A/B测试: v1=原规则, v2=增强引擎"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据需求ID匹配相关产品（支持 A/B 测试）"""
    engine = MatchEngine(db, strategy=strategy)
    results = engine.match_needs_to_products(need_id, top_k=top_k)
    return {
        "code": 200,
        "message": "success",
        "data": [r.model_dump() for r in results],
        "strategy": strategy,
    }


@router.get("/products/{product_id}/needs")
def match_products_to_needs(
    product_id: int,
    top_k: int = Query(20, ge=1, le=100, description="返回结果数量上限"),
    strategy: str = Query("v2", pattern="^(v1|v2)$", description="A/B测试: v1=原规则, v2=增强引擎"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据产品ID匹配相关需求（支持 A/B 测试）"""
    engine = MatchEngine(db, strategy=strategy)
    results = engine.match_products_to_needs(product_id, top_k=top_k)
    return {
        "code": 200,
        "message": "success",
        "data": [r.model_dump() for r in results],
        "strategy": strategy,
    }


@router.post("/refresh")
def refresh_index(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    重建匹配索引（清除缓存、预热数据）
    """
    clear_cache()  # GAP 2: 清除缓存

    products = db.query(Product).filter(Product.status == "approved").count()
    needs = db.query(BusinessNeed).filter(BusinessNeed.status == "open").count()

    # 预热缓存
    engine = MatchEngine(db, strategy="v2")
    engine._get_all_approved_products()
    engine._get_all_open_needs()

    logger.info(
        "匹配索引已刷新",
        extra={"products": products, "needs": needs, "user": current_user.username},
    )
    return {
        "code": 200,
        "message": "匹配索引已刷新",
        "data": {
            "products_count": products,
            "needs_count": needs,
            "status": "ready",
        },
    }


@router.get("/metrics")
def get_matching_metrics(
    current_user: User = Depends(get_current_user),
):
    """获取匹配引擎监控指标：匹配次数、成功率、分类分布、平均分、缓存命中率"""
    return {
        "code": 200,
        "message": "success",
        "data": match_metrics.get_stats(),
    }


@router.post("/metrics/adopt")
def record_match_adoption(
    current_user: User = Depends(get_current_user),
):
    """记录一次匹配被用户采纳/点击，用于计算匹配成功率"""
    match_metrics.record_adoption()
    return {
        "code": 200,
        "message": "success",
        "data": {
            "adopted_count": match_metrics.adopted_count,
            "match_success_rate": round(
                match_metrics.adopted_count / max(match_metrics.request_count, 1), 4
            ),
        },
    }


@router.get("/metrics/summary")
def get_matching_summary(
    current_user: User = Depends(get_current_user),
):
    """获取匹配质量看板摘要数据"""
    stats = match_metrics.get_stats()
    return {
        "code": 200,
        "message": "success",
        "data": {
            "total_matches": stats["total_matches"],
            "match_success_rate": stats["match_success_rate"],
            "avg_match_score": stats["avg_match_score"],
            "avg_response_time_ms": stats["avg_response_time_ms"],
            "cache_hit_rate": stats["cache_hit_rate"],
            "category_distribution": stats["category_distribution"],
            "score_distribution": stats["score_distribution"],
        },
    }


@router.get("/cache/status")
def get_cache_status(
    current_user: User = Depends(get_current_user),
):
    """获取缓存状态"""
    now = time.time()
    cache_info = {}
    for key, entry in _cache.items():
        cache_info[key] = {
            "age_seconds": round(now - entry.timestamp, 1),
            "ttl": entry.ttl,
            "expired": entry.is_expired(),
        }
    return {
        "code": 200,
        "message": "success",
        "data": cache_info,
    }
