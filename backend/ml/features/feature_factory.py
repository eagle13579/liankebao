"""链客宝 — 200+维自动化特征工程工厂 (FeatureFactory)

自动化特征工程管线，从多数据源提取、变换、组合特征，
覆盖用户行为(40维)、企业画像(60维)、图谱(50维)、时序(30维)、文本(20维)五大类，
总计 200+ 维特征。

分层架构:
  FeatureFactory (facade)  →  FeatureBuilder (策略)  →  FeatureStore (缓存)
       ↓                          ↓                         ↓
  统一调用入口              各类特征构建器              LRU + TTL 缓存

Author: 奚鼠 (P6, 数据分析部, 特征工程)
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json
import logging
import math
import random
import statistics
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple, Union
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# ===================================================================
# 常量 & 配置
# ===================================================================

# 特征维度总数
TOTAL_FEATURE_DIM = 200
USER_FEATURE_DIM = 40
ENTERPRISE_FEATURE_DIM = 60
GRAPH_FEATURE_DIM = 50
TEMPORAL_FEATURE_DIM = 30
TEXT_FEATURE_DIM = 20

# 默认缓存 TTL (秒)
DEFAULT_CACHE_TTL = 3600

# 特征版本
FEATURE_VERSION = "2.0.0"


# ===================================================================
# 特征名称常量 (便于外部引用)
# ===================================================================

class FeatureNames:
    """所有特征名称的命名空间常量。"""

    # ── 用户行为特征 (40维) ──
    # 匹配历史 (8维)
    MATCH_TOTAL = "user_match_total"
    MATCH_SUCCESS = "user_match_success"
    MATCH_SUCCESS_RATE = "user_match_success_rate"
    MATCH_AVG_RESPONSE_TIME = "user_match_avg_response_time"
    MATCH_MOST_COMMON_TYPE = "user_match_most_common_type"
    MATCH_MOST_COMMON_TYPE_RATIO = "user_match_most_common_type_ratio"
    MATCH_RECENT_COUNT_7D = "user_match_recent_count_7d"
    MATCH_RECENT_COUNT_30D = "user_match_recent_count_30d"

    # 反馈特征 (8维)
    FEEDBACK_LIKE_COUNT = "user_feedback_like_count"
    FEEDBACK_DISLIKE_COUNT = "user_feedback_dislike_count"
    FEEDBACK_LIKE_RATE = "user_feedback_like_rate"
    FEEDBACK_DISLIKE_RATE = "user_feedback_dislike_rate"
    FEEDBACK_RATING_MEAN = "user_feedback_rating_mean"
    FEEDBACK_RATING_VAR = "user_feedback_rating_var"
    FEEDBACK_RATING_MIN = "user_feedback_rating_min"
    FEEDBACK_RATING_MAX = "user_feedback_rating_max"

    # 活跃度 (12维)
    ACTIVE_LAST_LOGIN_HOURS_AGO = "user_active_last_login_hours_ago"
    ACTIVE_LOGIN_COUNT_7D = "user_active_login_count_7d"
    ACTIVE_LOGIN_COUNT_30D = "user_active_login_count_30d"
    ACTIVE_LOGIN_FREQ_MEAN = "user_active_login_freq_mean"
    ACTIVE_LOGIN_FREQ_STD = "user_active_login_freq_std"
    ACTIVE_BROWSE_COUNT_7D = "user_active_browse_count_7d"
    ACTIVE_BROWSE_COUNT_30D = "user_active_browse_count_30d"
    ACTIVE_BROWSE_AVG_DURATION = "user_active_browse_avg_duration"
    ACTIVE_BROWSE_TOTAL_DURATION = "user_active_browse_total_duration"
    ACTIVE_SESSION_COUNT = "user_active_session_count"
    ACTIVE_SESSION_AVG_DURATION = "user_active_session_avg_duration"
    ACTIVE_SESSION_STD_DURATION = "user_active_session_std_duration"

    # 社交特征 (12维)
    SOCIAL_CONTACT_COUNT = "user_social_contact_count"
    SOCIAL_COMMON_CONTACT_COUNT = "user_social_common_contact_count"
    SOCIAL_CIRCLE_DENSITY = "user_social_circle_density"
    SOCIAL_CIRCLE_SIZE = "user_social_circle_size"
    SOCIAL_GROUP_COUNT = "user_social_group_count"
    SOCIAL_ACTIVE_GROUP_COUNT = "user_social_active_group_count"
    SOCIAL_MESSAGE_COUNT_7D = "user_social_message_count_7d"
    SOCIAL_MESSAGE_COUNT_30D = "user_social_message_count_30d"
    SOCIAL_AVG_RESPONSE_TIME = "user_social_avg_response_time"
    SOCIAL_FOLLOWING_COUNT = "user_social_following_count"
    SOCIAL_FOLLOWER_COUNT = "user_social_follower_count"
    SOCIAL_FOLLOWER_FOLLOWING_RATIO = "user_social_follower_following_ratio"

    # ── 企业特征 (60维) ──
    # 工商特征 (14维)
    ENT_REG_CAPITAL_RAW = "ent_reg_capital_raw"
    ENT_REG_CAPITAL_LOG = "ent_reg_capital_log"
    ENT_ESTABLISHED_YEARS = "ent_established_years"
    ENT_SHAREHOLDER_COUNT = "ent_shareholder_count"
    ENT_BRANCH_COUNT = "ent_branch_count"
    ENT_LEGAL_REP_AGE = "ent_legal_rep_age"
    ENT_REGION_CODE = "ent_region_code"
    ENT_COMPANY_TYPE_CODE = "ent_company_type_code"
    ENT_REG_CAPITAL_USD = "ent_reg_capital_usd"
    ENT_REG_CAPITAL_PER_SHAREHOLDER = "ent_reg_capital_per_shareholder"
    ENT_BRANCH_PER_YEAR = "ent_branch_per_year"
    ENT_CAPITAL_CHANGE_COUNT = "ent_capital_change_count"
    ENT_HISTORY_MONTHS = "ent_history_months"
    ENT_IS_LISTED = "ent_is_listed"

    # 信用特征 (14维)
    ENT_CREDIT_SCORE = "ent_credit_score"
    ENT_RISK_COUNT = "ent_risk_count"
    ENT_ADMIN_PENALTY_COUNT = "ent_admin_penalty_count"
    ENT_JUDICIAL_RISK_COUNT = "ent_judicial_risk_count"
    ENT_OPERATION_RISK_COUNT = "ent_operation_risk_count"
    ENT_IP_COUNT = "ent_ip_count"
    ENT_TRADEMARK_COUNT = "ent_trademark_count"
    ENT_PATENT_COUNT = "ent_patent_count"
    ENT_COPYRIGHT_COUNT = "ent_copyright_count"
    ENT_TAX_CREDIT_LEVEL = "ent_tax_credit_level"
    ENT_ENV_CREDIT_SCORE = "ent_env_credit_score"
    ENT_SOCIAL_CREDIT_CODE = "ent_social_credit_code"  # 哈希编码
    ENT_LITIGATION_COUNT = "ent_litigation_count"
    ENT_EXECUTION_COUNT = "ent_execution_count"

    # 行业特征 (12维)
    ENT_INDUSTRY_CODE = "ent_industry_code"
    ENT_INDUSTRY_CATEGORY = "ent_industry_category"
    ENT_INDUSTRY_CHAIN_POSITION = "ent_industry_chain_position"
    ENT_UPSTREAM_SUPPLIER_COUNT = "ent_upstream_supplier_count"
    ENT_DOWNSTREAM_CUSTOMER_COUNT = "ent_downstream_customer_count"
    ENT_INDUSTRY_COMPETITION_INDEX = "ent_industry_competition_index"
    ENT_INDUSTRY_GROWTH_RATE = "ent_industry_growth_rate"
    ENT_INDUSTRY_PROFIT_MARGIN = "ent_industry_profit_margin"
    ENT_CROSS_INDUSTRY_COUNT = "ent_cross_industry_count"
    ENT_MAIN_BUSINESS_RATIO = "ent_main_business_ratio"
    ENT_INDUSTRY_RANK = "ent_industry_rank"
    ENT_SUPPLIER_CONCENTRATION = "ent_supplier_concentration"

    # 规模特征 (10维)
    ENT_EMPLOYEE_COUNT = "ent_employee_count"
    ENT_EMPLOYEE_COUNT_LOG = "ent_employee_count_log"
    ENT_ESTIMATED_REVENUE = "ent_estimated_revenue"
    ENT_ESTIMATED_REVENUE_LOG = "ent_estimated_revenue_log"
    ENT_REVENUE_PER_EMPLOYEE = "ent_revenue_per_employee"
    ENT_COVERAGE_PROVINCE_COUNT = "ent_coverage_province_count"
    ENT_COVERAGE_CITY_COUNT = "ent_coverage_city_count"
    ENT_COVERAGE_COUNTRY_COUNT = "ent_coverage_country_count"
    ENT_ASSET_TOTAL = "ent_asset_total"
    ENT_ASSET_TOTAL_LOG = "ent_asset_total_log"

    # 额外特征 (10维，用于补齐60维)
    ENT_WEBSITE_RANK = "ent_website_rank"
    ENT_SOCIAL_MEDIA_FOLLOWERS = "ent_social_media_followers"
    ENT_RECRUITMENT_COUNT = "ent_recruitment_count"
    ENT_CERTIFICATION_COUNT = "ent_certification_count"
    ENT_QUALIFICATION_COUNT = "ent_qualification_count"
    ENT_ANNUAL_REPORT_SCORE = "ent_annual_report_score"
    ENT_GOVT_SUBSIDY_AMOUNT = "ent_govt_subsidy_amount"
    ENT_TAX_CONTRIBUTION = "ent_tax_contribution"
    ENT_IMPORT_EXPORT_VOLUME = "ent_import_export_volume"
    ENT_INVESTMENT_COUNT = "ent_investment_count"

    # ── 图谱特征 (50维) ──
    # 度数特征 (10维)
    GRAPH_DEGREE = "graph_degree"
    GRAPH_COOPERATION_COUNT = "graph_cooperation_count"
    GRAPH_COMPETITION_COUNT = "graph_competition_count"
    GRAPH_SUPPLIER_COUNT = "graph_supplier_count"
    GRAPH_CUSTOMER_COUNT = "graph_customer_count"
    GRAPH_INVESTOR_COUNT = "graph_investor_count"
    GRAPH_INVESTEE_COUNT = "graph_investee_count"
    GRAPH_IN_DEGREE = "graph_in_degree"
    GRAPH_OUT_DEGREE = "graph_out_degree"
    GRAPH_DEGREE_CENTRALITY = "graph_degree_centrality"

    # 中心性 (10维)
    GRAPH_PAGERANK = "graph_pagerank"
    GRAPH_BETWEENNESS = "graph_betweenness_centrality"
    GRAPH_CLOSENESS = "graph_closeness_centrality"
    GRAPH_EIGENVECTOR = "graph_eigenvector_centrality"
    GRAPH_HARMONIC = "graph_harmonic_centrality"
    GRAPH_KATZ = "graph_katz_centrality"
    GRAPH_LOAD = "graph_load_centrality"
    GRAPH_SUBGRAPH = "graph_subgraph_centrality"
    GRAPH_EDGE_BETWEENNESS = "graph_edge_betweenness"
    GRAPH_APPROX_CLOSENESS = "graph_approx_closeness"

    # 社区特征 (12维)
    GRAPH_COMMUNITY_ID = "graph_community_id"
    GRAPH_COMMUNITY_SIZE = "graph_community_size"
    GRAPH_COMMUNITY_DENSITY = "graph_community_density"
    GRAPH_COMMUNITY_MODULARITY = "graph_community_modularity"
    GRAPH_NUM_COMMUNITIES = "graph_num_communities"
    GRAPH_COMMUNITY_CONDUCTANCE = "graph_community_conductance"
    GRAPH_COMMUNITY_CUT_RATIO = "graph_community_cut_ratio"
    GRAPH_COMMUNITY_NORMALIZED_CUT = "graph_community_normalized_cut"
    GRAPH_COMMUNITY_TRIANGLE_COUNT = "graph_community_triangle_count"
    GRAPH_COMMUNITY_TRANSITIVITY = "graph_community_transitivity"
    GRAPH_COMMUNITY_SQ_CLUSTERING = "graph_community_sq_clustering"
    GRAPH_COMMUNITY_AVG_DEGREE = "graph_community_avg_degree"

    # 路径特征 (10维)
    GRAPH_SHORTEST_PATH_LEN = "graph_shortest_path_length"
    GRAPH_COMMON_NEIGHBORS = "graph_common_neighbors_count"
    GRAPH_JACCARD_SIMILARITY = "graph_jaccard_similarity"
    GRAPH_ADAMIC_ADAR = "graph_adamic_adar_index"
    GRAPH_RESOURCE_ALLOCATION = "graph_resource_allocation_index"
    GRAPH_PREF_ATTACHMENT = "graph_preferential_attachment"
    GRAPH_TOTAL_PATHS_2HOP = "graph_total_paths_2hop"
    GRAPH_TOTAL_PATHS_3HOP = "graph_total_paths_3hop"
    GRAPH_AVG_PATH_LENGTH = "graph_avg_path_length"
    GRAPH_DIAMETER = "graph_diameter"

    # 额外图谱特征 (8维，用于补齐50维)
    GRAPH_CLUSTERING_COEFF = "graph_clustering_coefficient"
    GRAPH_SQ_CLUSTERING = "graph_square_clustering"
    GRAPH_CORE_NUMBER = "graph_core_number"
    GRAPH_RICH_CLUB = "graph_rich_club_coefficient"
    GRAPH_ECCENTRICITY = "graph_eccentricity"
    GRAPH_PAGE_RANK_TRUST = "graph_pagerank_trust"
    GRAPH_RANDOM_WALK = "graph_random_walk_landing"
    GRAPH_GRAPH_HASH = "graph_hash_signature"

    # ── 时序特征 (30维) ──
    # 趋势 (10维)
    TEMP_MATCH_MA7 = "temp_match_ma7"
    TEMP_MATCH_MA30 = "temp_match_ma30"
    TEMP_MATCH_MOM = "temp_match_mom"
    TEMP_MATCH_QOQ = "temp_match_qoq"
    TEMP_MATCH_YOY = "temp_match_yoy"
    TEMP_MATCH_STD_7D = "temp_match_std_7d"
    TEMP_MATCH_STD_30D = "temp_match_std_30d"
    TEMP_MATCH_SKEW_30D = "temp_match_skew_30d"
    TEMP_MATCH_KURT_30D = "temp_match_kurt_30d"
    TEMP_MATCH_ACCELERATION = "temp_match_acceleration"

    # 季节性 (10维)
    TEMP_DAY_OF_WEEK = "temp_day_of_week"
    TEMP_MONTH_OF_YEAR = "temp_month_of_year"
    TEMP_IS_WEEKEND = "temp_is_weekend"
    TEMP_IS_HOLIDAY = "temp_is_holiday"
    TEMP_SEASON = "temp_season"
    TEMP_DOW_EFFECT_MATCH = "temp_dow_effect_match"
    TEMP_MONTH_EFFECT_MATCH = "temp_month_effect_match"
    TEMP_HOLIDAY_EFFECT_MATCH = "temp_holiday_effect_match"
    TEMP_SEASONAL_STRENGTH = "temp_seasonal_strength"
    TEMP_TREND_STRENGTH = "temp_trend_strength"

    # 衰减 (10维)
    TEMP_DECAY_WEIGHT_1D = "temp_decay_weight_1d"
    TEMP_DECAY_WEIGHT_3D = "temp_decay_weight_3d"
    TEMP_DECAY_WEIGHT_7D = "temp_decay_weight_7d"
    TEMP_DECAY_WEIGHT_14D = "temp_decay_weight_14d"
    TEMP_DECAY_WEIGHT_30D = "temp_decay_weight_30d"
    TEMP_DECAY_SUM_7D = "temp_decay_sum_7d"
    TEMP_DECAY_SUM_30D = "temp_decay_sum_30d"
    TEMP_DECAY_AVG_7D = "temp_decay_avg_7d"
    TEMP_DECAY_AVG_30D = "temp_decay_avg_30d"
    TEMP_DECAY_HALF_LIFE = "temp_decay_half_life"

    # ── 文本特征 (20维) ──
    TEXT_EMBEDDING_01 = "text_embedding_01"
    TEXT_EMBEDDING_02 = "text_embedding_02"
    TEXT_EMBEDDING_03 = "text_embedding_03"
    TEXT_EMBEDDING_04 = "text_embedding_04"
    TEXT_EMBEDDING_05 = "text_embedding_05"
    TEXT_EMBEDDING_06 = "text_embedding_06"
    TEXT_EMBEDDING_07 = "text_embedding_07"
    TEXT_EMBEDDING_08 = "text_embedding_08"
    TEXT_EMBEDDING_09 = "text_embedding_09"
    TEXT_EMBEDDING_10 = "text_embedding_10"
    TEXT_TFIDF_WORD_01 = "text_tfidf_word_01"
    TEXT_TFIDF_WORD_02 = "text_tfidf_word_02"
    TEXT_TFIDF_WORD_03 = "text_tfidf_word_03"
    TEXT_TFIDF_WORD_04 = "text_tfidf_word_04"
    TEXT_TFIDF_WORD_05 = "text_tfidf_word_05"
    TEXT_TFIDF_WORD_06 = "text_tfidf_word_06"
    TEXT_TFIDF_WORD_07 = "text_tfidf_word_07"
    TEXT_TFIDF_WORD_08 = "text_tfidf_word_08"
    TEXT_TFIDF_WORD_09 = "text_tfidf_word_09"
    TEXT_TFIDF_WORD_10 = "text_tfidf_word_10"


# ===================================================================
# 数据容器
# ===================================================================

@dataclass
class FeatureVector:
    """特征向量数据类。

    Attributes:
        features: 特征名→值的映射
        entity_type: 实体类型 (user/enterprise)
        entity_id: 实体ID
        version: 特征版本
        created_at: 创建时间戳
        dim: 特征维度
    """
    features: Dict[str, float]
    entity_type: str
    entity_id: str
    version: str = FEATURE_VERSION
    created_at: float = field(default_factory=time.time)
    dim: int = 0

    def __post_init__(self):
        self.dim = len(self.features)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典 (用于序列化)。"""
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "version": self.version,
            "created_at": self.created_at,
            "dim": self.dim,
            "features": self.features,
        }

    def to_vector(self, feature_names: Optional[List[str]] = None) -> np.ndarray:
        """转换为 numpy 向量。

        Args:
            feature_names: 指定的特征顺序列表，未提供时使用 self.features 的 key 顺序

        Returns:
            1D numpy array
        """
        if feature_names is None:
            feature_names = list(self.features.keys())
        return np.array([self.features.get(k, 0.0) for k in feature_names], dtype=np.float32)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeatureVector":
        """从字典恢复。"""
        return cls(
            features=data["features"],
            entity_type=data["entity_type"],
            entity_id=data["entity_id"],
            version=data.get("version", FEATURE_VERSION),
            created_at=data.get("created_at", time.time()),
        )


# ===================================================================
# 特征存储 (FeatureStore)
# ===================================================================

class FeatureStore:
    """特征缓存存储，支持 LRU + TTL。

    架构:
        - 内存中的 OrderedDict (LRU淘汰)
        - 支持 TTL 过期
        - 批量获取接口
        - 缓存统计

    Attributes:
        _cache: LRU缓存表 (key → (expiry, FeatureVector))
        _stats: 缓存命中/未命中统计
    """

    def __init__(self, max_size: int = 10000, default_ttl: int = DEFAULT_CACHE_TTL):
        self._cache: OrderedDict[str, Tuple[float, FeatureVector]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._stats: Dict[str, int] = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "evictions": 0,
            "expirations": 0,
        }

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    def cache_get(self, key: str) -> Optional[FeatureVector]:
        """获取缓存项。如果不存在或已过期，返回 None。

        Args:
            key: 缓存键

        Returns:
            FeatureVector 或 None
        """
        if key not in self._cache:
            self._stats["misses"] += 1
            return None

        expiry, fv = self._cache[key]
        if time.time() > expiry:
            # 已过期
            del self._cache[key]
            self._stats["expirations"] += 1
            self._stats["misses"] += 1
            return None

        # LRU: 移到末尾
        self._cache.move_to_end(key)
        self._stats["hits"] += 1
        return fv

    def cache_set(
        self,
        key: str,
        features: FeatureVector,
        ttl: Optional[int] = None,
    ) -> None:
        """设置缓存项。

        Args:
            key: 缓存键
            features: 特征向量
            ttl: 过期秒数 (默认使用 default_ttl)
        """
        ttl = ttl if ttl is not None else self._default_ttl
        expiry = time.time() + ttl

        # 如果已存在，先删除
        if key in self._cache:
            del self._cache[key]

        # 淘汰: 超出最大大小
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
            self._stats["evictions"] += 1

        self._cache[key] = (expiry, features)
        self._stats["sets"] += 1

    def batch_get(self, keys: List[str]) -> List[Optional[FeatureVector]]:
        """批量获取缓存项。

        Args:
            keys: 缓存键列表

        Returns:
            FeatureVector 或 None 的列表 (与 keys 顺序对应)
        """
        return [self.cache_get(k) for k in keys]

    def batch_set(
        self,
        items: Dict[str, FeatureVector],
        ttl: Optional[int] = None,
    ) -> None:
        """批量设置缓存项。

        Args:
            items: 键→特征向量映射
            ttl: 过期秒数
        """
        for key, fv in items.items():
            self.cache_set(key, fv, ttl=ttl)

    # ------------------------------------------------------------------
    # 统计 & 管理
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """缓存统计。"""
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total_requests if total_requests > 0 else 0.0
        return {
            **self._stats,
            "hit_rate": round(hit_rate, 4),
            "current_size": len(self._cache),
            "max_size": self._max_size,
            "default_ttl": self._default_ttl,
        }

    def clear(self) -> int:
        """清空缓存。返回清除的条目数。"""
        count = len(self._cache)
        self._cache.clear()
        return count

    def invalidate(self, key: str) -> bool:
        """使指定键过期。"""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def invalidate_pattern(self, pattern: str) -> int:
        """使匹配前缀的键过期。"""
        count = 0
        keys_to_del = [k for k in self._cache if k.startswith(pattern)]
        for k in keys_to_del:
            del self._cache[k]
            count += 1
        return count

    @property
    def size(self) -> int:
        return len(self._cache)


# ===================================================================
# 基础特征构建器
# ===================================================================

class FeatureBuilder:
    """特征构建器基类，定义特征构建的通用接口。"""

    def build(self, entity_id: str, **kwargs) -> Dict[str, float]:
        """构建特征字典。子类必须实现。"""
        raise NotImplementedError

    @staticmethod
    def safe_divide(a: float, b: float, default: float = 0.0) -> float:
        """安全除法，避免除零。"""
        if b == 0 or math.isnan(b):
            return default
        return a / b

    @staticmethod
    def clip(value: float, lo: float = -1e10, hi: float = 1e10) -> float:
        """裁剪值到合法范围。"""
        return max(lo, min(hi, value))

    @staticmethod
    def log_transform(value: float, offset: float = 1.0) -> float:
        """log 变换 (零值安全)。"""
        return math.log(max(value, 0.0) + offset)

    @staticmethod
    def _validate_dim(features: Dict[str, float], expected: int) -> None:
        """验证特征维度。"""
        actual = len(features)
        if actual != expected:
            logger.warning(
                "特征维度不匹配: 期望 %d, 实际 %d (差值 %d)",
                expected, actual, actual - expected,
            )


# ===================================================================
# 用户行为特征构建器 (40维)
# ===================================================================

class UserBehaviorBuilder(FeatureBuilder):
    """用户行为特征构建器 — 40维。

    数据来源:
        - match_history (匹配历史表)
        - feedback_log (反馈日志表)
        - user_activity (用户活跃度表)
        - social_graph (社交关系图)
    """

    def build(self, user_id: str, **kwargs) -> Dict[str, float]:
        """构建40维用户行为特征。

        Args:
            user_id: 用户ID
            **kwargs: 可选的原始数据覆盖 (用于测试/离线)

        Returns:
            40维特征字典
        """
        # 从数据源获取原始数据(模拟)
        raw = kwargs.get("raw_data", self._fetch_raw(user_id))

        features = {}
        features.update(self._build_match_features(raw))
        features.update(self._build_feedback_features(raw))
        features.update(self._build_active_features(raw))
        features.update(self._build_social_features(raw))

        # 验证维度
        self._validate_dim(features, USER_FEATURE_DIM)
        return features

    # ------------------------------------------------------------------
    # 匹配历史 (8维)
    # ------------------------------------------------------------------
    def _build_match_features(self, raw: Dict[str, Any]) -> Dict[str, float]:
        m = raw.get("match_history", {})
        total = max(m.get("total", 0), 0)
        success = max(m.get("success", 0), 0)
        recent_7d = max(m.get("recent_7d", 0), 0)
        recent_30d = max(m.get("recent_30d", 0), 0)

        avg_resp = m.get("avg_response_time", 0.0)
        most_common = m.get("most_common_type", 0)
        most_common_cnt = m.get("most_common_type_count", 0)

        return {
            FeatureNames.MATCH_TOTAL: float(total),
            FeatureNames.MATCH_SUCCESS: float(success),
            FeatureNames.MATCH_SUCCESS_RATE: self.safe_divide(float(success), float(total)),
            FeatureNames.MATCH_AVG_RESPONSE_TIME: float(avg_resp),
            FeatureNames.MATCH_MOST_COMMON_TYPE: float(most_common),
            FeatureNames.MATCH_MOST_COMMON_TYPE_RATIO: self.safe_divide(
                float(most_common_cnt), float(total)
            ),
            FeatureNames.MATCH_RECENT_COUNT_7D: float(recent_7d),
            FeatureNames.MATCH_RECENT_COUNT_30D: float(recent_30d),
        }

    # ------------------------------------------------------------------
    # 反馈特征 (8维)
    # ------------------------------------------------------------------
    def _build_feedback_features(self, raw: Dict[str, Any]) -> Dict[str, float]:
        f = raw.get("feedback", {})
        likes = max(f.get("like_count", 0), 0)
        dislikes = max(f.get("dislike_count", 0), 0)
        total_fb = likes + dislikes
        ratings = f.get("ratings", [3.0])

        rating_mean = float(np.mean(ratings)) if ratings else 0.0
        rating_var = float(np.var(ratings)) if len(ratings) > 1 else 0.0
        rating_min = float(min(ratings)) if ratings else 0.0
        rating_max = float(max(ratings)) if ratings else 0.0

        return {
            FeatureNames.FEEDBACK_LIKE_COUNT: float(likes),
            FeatureNames.FEEDBACK_DISLIKE_COUNT: float(dislikes),
            FeatureNames.FEEDBACK_LIKE_RATE: self.safe_divide(float(likes), float(total_fb)),
            FeatureNames.FEEDBACK_DISLIKE_RATE: self.safe_divide(float(dislikes), float(total_fb)),
            FeatureNames.FEEDBACK_RATING_MEAN: rating_mean,
            FeatureNames.FEEDBACK_RATING_VAR: rating_var,
            FeatureNames.FEEDBACK_RATING_MIN: rating_min,
            FeatureNames.FEEDBACK_RATING_MAX: rating_max,
        }

    # ------------------------------------------------------------------
    # 活跃度 (12维)
    # ------------------------------------------------------------------
    def _build_active_features(self, raw: Dict[str, Any]) -> Dict[str, float]:
        a = raw.get("activity", {})
        login_7d = max(a.get("login_count_7d", 0), 0)
        login_30d = max(a.get("login_count_30d", 0), 0)
        browse_7d = max(a.get("browse_count_7d", 0), 0)
        browse_30d = max(a.get("browse_count_30d", 0), 0)

        return {
            FeatureNames.ACTIVE_LAST_LOGIN_HOURS_AGO: float(a.get("last_login_hours_ago", 0)),
            FeatureNames.ACTIVE_LOGIN_COUNT_7D: float(login_7d),
            FeatureNames.ACTIVE_LOGIN_COUNT_30D: float(login_30d),
            FeatureNames.ACTIVE_LOGIN_FREQ_MEAN: self.safe_divide(float(login_30d), 30.0),
            FeatureNames.ACTIVE_LOGIN_FREQ_STD: float(a.get("login_freq_std", 0.0)),
            FeatureNames.ACTIVE_BROWSE_COUNT_7D: float(browse_7d),
            FeatureNames.ACTIVE_BROWSE_COUNT_30D: float(browse_30d),
            FeatureNames.ACTIVE_BROWSE_AVG_DURATION: float(a.get("browse_avg_duration", 0.0)),
            FeatureNames.ACTIVE_BROWSE_TOTAL_DURATION: float(a.get("browse_total_duration", 0.0)),
            FeatureNames.ACTIVE_SESSION_COUNT: float(a.get("session_count", 0)),
            FeatureNames.ACTIVE_SESSION_AVG_DURATION: float(a.get("session_avg_duration", 0.0)),
            FeatureNames.ACTIVE_SESSION_STD_DURATION: float(a.get("session_std_duration", 0.0)),
        }

    # ------------------------------------------------------------------
    # 社交特征 (12维)
    # ------------------------------------------------------------------
    def _build_social_features(self, raw: Dict[str, Any]) -> Dict[str, float]:
        s = raw.get("social", {})
        contact_cnt = max(s.get("contact_count", 0), 0)
        following = max(s.get("following_count", 0), 0)
        follower = max(s.get("follower_count", 0), 0)

        return {
            FeatureNames.SOCIAL_CONTACT_COUNT: float(contact_cnt),
            FeatureNames.SOCIAL_COMMON_CONTACT_COUNT: float(s.get("common_contact_count", 0)),
            FeatureNames.SOCIAL_CIRCLE_DENSITY: float(s.get("circle_density", 0.0)),
            FeatureNames.SOCIAL_CIRCLE_SIZE: float(s.get("circle_size", 0)),
            FeatureNames.SOCIAL_GROUP_COUNT: float(s.get("group_count", 0)),
            FeatureNames.SOCIAL_ACTIVE_GROUP_COUNT: float(s.get("active_group_count", 0)),
            FeatureNames.SOCIAL_MESSAGE_COUNT_7D: float(s.get("message_count_7d", 0)),
            FeatureNames.SOCIAL_MESSAGE_COUNT_30D: float(s.get("message_count_30d", 0)),
            FeatureNames.SOCIAL_AVG_RESPONSE_TIME: float(s.get("avg_response_time", 0.0)),
            FeatureNames.SOCIAL_FOLLOWING_COUNT: float(following),
            FeatureNames.SOCIAL_FOLLOWER_COUNT: float(follower),
            FeatureNames.SOCIAL_FOLLOWER_FOLLOWING_RATIO: self.safe_divide(
                float(follower), float(following)
            ),
        }

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    def _fetch_raw(self, user_id: str) -> Dict[str, Any]:
        """模拟从数据源获取原始数据。"""
        # 实际项目中将从数据库/数仓查询
        logger.debug("[UserBehaviorBuilder] 获取用户 %s 的原始行为数据", user_id)
        return {}

    @staticmethod
    def _validate_dim(features: Dict[str, float], expected: int) -> None:
        actual = len(features)
        if actual != expected:
            logger.warning(
                "特征维度不匹配: 期望 %d, 实际 %d", expected, actual
            )


# ===================================================================
# 企业特征构建器 (60维)
# ===================================================================

class EnterpriseFeatureBuilder(FeatureBuilder):
    """企业特征构建器 — 60维。

    数据来源:
        - enterprise_data (企业工商/信用/行业/规模数据)
        - risk_db (风险数据库)
        - ip_patent_db (知识产权库)
    """

    def build(self, enterprise_id: str, **kwargs) -> Dict[str, float]:
        """构建60维企业特征。

        Args:
            enterprise_id: 企业ID
            **kwargs: 可选的原始数据覆盖

        Returns:
            60维特征字典
        """
        raw = kwargs.get("raw_data", self._fetch_raw(enterprise_id))

        features = {}
        features.update(self._build_business_features(raw))
        features.update(self._build_credit_features(raw))
        features.update(self._build_industry_features(raw))
        features.update(self._build_scale_features(raw))
        features.update(self._build_extra_features(raw))

        self._validate_dim(features, ENTERPRISE_FEATURE_DIM)
        return features

    # ------------------------------------------------------------------
    # 工商特征 (14维)
    # ------------------------------------------------------------------
    def _build_business_features(self, raw: Dict[str, Any]) -> Dict[str, float]:
        b = raw.get("business", {})
        reg_capital = max(b.get("registered_capital", 0.0), 0.0)
        est_years = max(b.get("established_years", 0), 0)
        shareholders = max(b.get("shareholder_count", 0), 0)
        branches = max(b.get("branch_count", 0), 0)
        capital_changes = max(b.get("capital_change_count", 0), 0)

        return {
            FeatureNames.ENT_REG_CAPITAL_RAW: float(reg_capital),
            FeatureNames.ENT_REG_CAPITAL_LOG: self.log_transform(reg_capital),
            FeatureNames.ENT_ESTABLISHED_YEARS: float(est_years),
            FeatureNames.ENT_SHAREHOLDER_COUNT: float(shareholders),
            FeatureNames.ENT_BRANCH_COUNT: float(branches),
            FeatureNames.ENT_LEGAL_REP_AGE: float(b.get("legal_rep_age", 0)),
            FeatureNames.ENT_REGION_CODE: float(b.get("region_code", 0)),
            FeatureNames.ENT_COMPANY_TYPE_CODE: float(b.get("company_type_code", 0)),
            FeatureNames.ENT_REG_CAPITAL_USD: float(b.get("reg_capital_usd", reg_capital * 0.14)),
            FeatureNames.ENT_REG_CAPITAL_PER_SHAREHOLDER: self.safe_divide(
                float(reg_capital), float(shareholders)
            ),
            FeatureNames.ENT_BRANCH_PER_YEAR: self.safe_divide(
                float(branches), float(est_years) if est_years > 0 else 1.0
            ),
            FeatureNames.ENT_CAPITAL_CHANGE_COUNT: float(capital_changes),
            FeatureNames.ENT_HISTORY_MONTHS: float(est_years * 12),
            FeatureNames.ENT_IS_LISTED: float(b.get("is_listed", 0)),
        }

    # ------------------------------------------------------------------
    # 信用特征 (14维)
    # ------------------------------------------------------------------
    def _build_credit_features(self, raw: Dict[str, Any]) -> Dict[str, float]:
        c = raw.get("credit", {})
        admin_penalty = max(c.get("admin_penalty_count", 0), 0)
        judicial = max(c.get("judicial_risk_count", 0), 0)
        operation = max(c.get("operation_risk_count", 0), 0)
        total_risk = admin_penalty + judicial + operation

        return {
            FeatureNames.ENT_CREDIT_SCORE: float(c.get("credit_score", 600.0)),
            FeatureNames.ENT_RISK_COUNT: float(total_risk),
            FeatureNames.ENT_ADMIN_PENALTY_COUNT: float(admin_penalty),
            FeatureNames.ENT_JUDICIAL_RISK_COUNT: float(judicial),
            FeatureNames.ENT_OPERATION_RISK_COUNT: float(operation),
            FeatureNames.ENT_IP_COUNT: float(max(c.get("ip_count", 0), 0)),
            FeatureNames.ENT_TRADEMARK_COUNT: float(max(c.get("trademark_count", 0), 0)),
            FeatureNames.ENT_PATENT_COUNT: float(max(c.get("patent_count", 0), 0)),
            FeatureNames.ENT_COPYRIGHT_COUNT: float(max(c.get("copyright_count", 0), 0)),
            FeatureNames.ENT_TAX_CREDIT_LEVEL: float(c.get("tax_credit_level", 0)),
            FeatureNames.ENT_ENV_CREDIT_SCORE: float(c.get("env_credit_score", 0.0)),
            FeatureNames.ENT_SOCIAL_CREDIT_CODE: float(c.get("social_credit_code_hash", 0.0)),
            FeatureNames.ENT_LITIGATION_COUNT: float(max(c.get("litigation_count", 0), 0)),
            FeatureNames.ENT_EXECUTION_COUNT: float(max(c.get("execution_count", 0), 0)),
        }

    # ------------------------------------------------------------------
    # 行业特征 (12维)
    # ------------------------------------------------------------------
    def _build_industry_features(self, raw: Dict[str, Any]) -> Dict[str, float]:
        ind = raw.get("industry", {})
        return {
            FeatureNames.ENT_INDUSTRY_CODE: float(ind.get("industry_code", 0)),
            FeatureNames.ENT_INDUSTRY_CATEGORY: float(ind.get("category_code", 0)),
            FeatureNames.ENT_INDUSTRY_CHAIN_POSITION: float(ind.get("chain_position", 0.5)),
            FeatureNames.ENT_UPSTREAM_SUPPLIER_COUNT: float(max(ind.get("upstream_count", 0), 0)),
            FeatureNames.ENT_DOWNSTREAM_CUSTOMER_COUNT: float(max(ind.get("downstream_count", 0), 0)),
            FeatureNames.ENT_INDUSTRY_COMPETITION_INDEX: float(ind.get("competition_index", 0.5)),
            FeatureNames.ENT_INDUSTRY_GROWTH_RATE: float(ind.get("growth_rate", 0.0)),
            FeatureNames.ENT_INDUSTRY_PROFIT_MARGIN: float(ind.get("profit_margin", 0.0)),
            FeatureNames.ENT_CROSS_INDUSTRY_COUNT: float(max(ind.get("cross_industry_count", 0), 0)),
            FeatureNames.ENT_MAIN_BUSINESS_RATIO: float(ind.get("main_business_ratio", 1.0)),
            FeatureNames.ENT_INDUSTRY_RANK: float(max(ind.get("industry_rank", 0), 0)),
            FeatureNames.ENT_SUPPLIER_CONCENTRATION: float(ind.get("supplier_concentration", 0.0)),
        }

    # ------------------------------------------------------------------
    # 规模特征 (10维)
    # ------------------------------------------------------------------
    def _build_scale_features(self, raw: Dict[str, Any]) -> Dict[str, float]:
        sc = raw.get("scale", {})
        employees = max(sc.get("employee_count", 0), 0)
        revenue = max(sc.get("estimated_revenue", 0.0), 0.0)
        asset = max(sc.get("asset_total", 0.0), 0.0)

        return {
            FeatureNames.ENT_EMPLOYEE_COUNT: float(employees),
            FeatureNames.ENT_EMPLOYEE_COUNT_LOG: self.log_transform(employees),
            FeatureNames.ENT_ESTIMATED_REVENUE: float(revenue),
            FeatureNames.ENT_ESTIMATED_REVENUE_LOG: self.log_transform(revenue),
            FeatureNames.ENT_REVENUE_PER_EMPLOYEE: self.safe_divide(
                float(revenue), float(employees)
            ),
            FeatureNames.ENT_COVERAGE_PROVINCE_COUNT: float(max(sc.get("province_count", 0), 0)),
            FeatureNames.ENT_COVERAGE_CITY_COUNT: float(max(sc.get("city_count", 0), 0)),
            FeatureNames.ENT_COVERAGE_COUNTRY_COUNT: float(max(sc.get("country_count", 0), 0)),
            FeatureNames.ENT_ASSET_TOTAL: float(asset),
            FeatureNames.ENT_ASSET_TOTAL_LOG: self.log_transform(asset),
        }

    # ------------------------------------------------------------------
    # 额外特征 (10维)
    # ------------------------------------------------------------------
    def _build_extra_features(self, raw: Dict[str, Any]) -> Dict[str, float]:
        ext = raw.get("extra", {})
        return {
            FeatureNames.ENT_WEBSITE_RANK: float(ext.get("website_rank", 0.0)),
            FeatureNames.ENT_SOCIAL_MEDIA_FOLLOWERS: self.log_transform(
                ext.get("social_media_followers", 0)
            ),
            FeatureNames.ENT_RECRUITMENT_COUNT: float(max(ext.get("recruitment_count", 0), 0)),
            FeatureNames.ENT_CERTIFICATION_COUNT: float(max(ext.get("certification_count", 0), 0)),
            FeatureNames.ENT_QUALIFICATION_COUNT: float(max(ext.get("qualification_count", 0), 0)),
            FeatureNames.ENT_ANNUAL_REPORT_SCORE: float(ext.get("annual_report_score", 0.0)),
            FeatureNames.ENT_GOVT_SUBSIDY_AMOUNT: self.log_transform(
                ext.get("govt_subsidy_amount", 0.0)
            ),
            FeatureNames.ENT_TAX_CONTRIBUTION: self.log_transform(
                ext.get("tax_contribution", 0.0)
            ),
            FeatureNames.ENT_IMPORT_EXPORT_VOLUME: self.log_transform(
                ext.get("import_export_volume", 0.0)
            ),
            FeatureNames.ENT_INVESTMENT_COUNT: float(max(ext.get("investment_count", 0), 0)),
        }

    def _fetch_raw(self, enterprise_id: str) -> Dict[str, Any]:
        logger.debug("[EnterpriseFeatureBuilder] 获取企业 %s 的原始数据", enterprise_id)
        return {}


# ===================================================================
# 图谱特征构建器 (50维)
# ===================================================================

class GraphFeatureBuilder(FeatureBuilder):
    """图谱特征构建器 — 50维。

    数据来源:
        - 知识图谱 (Neo4j / NetworkX)
        - 企业关系网络

    支持两种模式:
        1. 直接传入 networkx.Graph 对象
        2. 通过 kwargs 传入原始数据
    """

    def build(self, node_id: str, **kwargs) -> Dict[str, float]:
        """构建50维图谱特征。

        Args:
            node_id: 图谱中的节点ID
            **kwargs:
                graph: networkx.Graph 对象 (可选)
                raw_data: 原始数据 dict (可选)
                target_node: 目标节点ID (计算路径特征使用)

        Returns:
            50维特征字典
        """
        graph = kwargs.get("graph")
        raw = kwargs.get("raw_data", self._fetch_raw(node_id))

        features = {}
        features.update(self._build_degree_features(node_id, graph, raw))
        features.update(self._build_centrality_features(node_id, graph, raw))
        features.update(self._build_community_features(node_id, graph, raw))
        features.update(self._build_path_features(node_id, graph, raw))
        features.update(self._build_extra_graph_features(node_id, graph, raw))

        self._validate_dim(features, GRAPH_FEATURE_DIM)
        return features

    # ------------------------------------------------------------------
    # 度数特征 (10维)
    # ------------------------------------------------------------------
    def _build_degree_features(
        self, node_id: str, graph: Any, raw: Dict[str, Any]
    ) -> Dict[str, float]:
        d = raw.get("degree", {})
        degree = max(d.get("degree", 0), 0)
        n_nodes = max(d.get("total_nodes", 1), 1)

        return {
            FeatureNames.GRAPH_DEGREE: float(degree),
            FeatureNames.GRAPH_COOPERATION_COUNT: float(max(d.get("cooperation_count", 0), 0)),
            FeatureNames.GRAPH_COMPETITION_COUNT: float(max(d.get("competition_count", 0), 0)),
            FeatureNames.GRAPH_SUPPLIER_COUNT: float(max(d.get("supplier_count", 0), 0)),
            FeatureNames.GRAPH_CUSTOMER_COUNT: float(max(d.get("customer_count", 0), 0)),
            FeatureNames.GRAPH_INVESTOR_COUNT: float(max(d.get("investor_count", 0), 0)),
            FeatureNames.GRAPH_INVESTEE_COUNT: float(max(d.get("investee_count", 0), 0)),
            FeatureNames.GRAPH_IN_DEGREE: float(max(d.get("in_degree", 0), 0)),
            FeatureNames.GRAPH_OUT_DEGREE: float(max(d.get("out_degree", 0), 0)),
            FeatureNames.GRAPH_DEGREE_CENTRALITY: self.safe_divide(
                float(degree), float(n_nodes - 1)
            ),
        }

    # ------------------------------------------------------------------
    # 中心性 (10维)
    # ------------------------------------------------------------------
    def _build_centrality_features(
        self, node_id: str, graph: Any, raw: Dict[str, Any]
    ) -> Dict[str, float]:
        c = raw.get("centrality", {})
        return {
            FeatureNames.GRAPH_PAGERANK: float(c.get("pagerank", 0.0)),
            FeatureNames.GRAPH_BETWEENNESS: float(c.get("betweenness", 0.0)),
            FeatureNames.GRAPH_CLOSENESS: float(c.get("closeness", 0.0)),
            FeatureNames.GRAPH_EIGENVECTOR: float(c.get("eigenvector", 0.0)),
            FeatureNames.GRAPH_HARMONIC: float(c.get("harmonic", 0.0)),
            FeatureNames.GRAPH_KATZ: float(c.get("katz", 0.0)),
            FeatureNames.GRAPH_LOAD: float(c.get("load", 0.0)),
            FeatureNames.GRAPH_SUBGRAPH: float(c.get("subgraph", 0.0)),
            FeatureNames.GRAPH_EDGE_BETWEENNESS: float(c.get("edge_betweenness", 0.0)),
            FeatureNames.GRAPH_APPROX_CLOSENESS: float(c.get("approx_closeness", 0.0)),
        }

    # ------------------------------------------------------------------
    # 社区特征 (12维)
    # ------------------------------------------------------------------
    def _build_community_features(
        self, node_id: str, graph: Any, raw: Dict[str, Any]
    ) -> Dict[str, float]:
        cm = raw.get("community", {})
        comm_size = max(cm.get("community_size", 1), 1)

        return {
            FeatureNames.GRAPH_COMMUNITY_ID: float(cm.get("community_id", 0)),
            FeatureNames.GRAPH_COMMUNITY_SIZE: float(comm_size),
            FeatureNames.GRAPH_COMMUNITY_DENSITY: float(cm.get("community_density", 0.0)),
            FeatureNames.GRAPH_COMMUNITY_MODULARITY: float(cm.get("modularity", 0.0)),
            FeatureNames.GRAPH_NUM_COMMUNITIES: float(max(cm.get("num_communities", 1), 1)),
            FeatureNames.GRAPH_COMMUNITY_CONDUCTANCE: float(cm.get("conductance", 0.0)),
            FeatureNames.GRAPH_COMMUNITY_CUT_RATIO: float(cm.get("cut_ratio", 0.0)),
            FeatureNames.GRAPH_COMMUNITY_NORMALIZED_CUT: float(cm.get("normalized_cut", 0.0)),
            FeatureNames.GRAPH_COMMUNITY_TRIANGLE_COUNT: float(max(cm.get("triangle_count", 0), 0)),
            FeatureNames.GRAPH_COMMUNITY_TRANSITIVITY: float(cm.get("transitivity", 0.0)),
            FeatureNames.GRAPH_COMMUNITY_SQ_CLUSTERING: float(cm.get("sq_clustering", 0.0)),
            FeatureNames.GRAPH_COMMUNITY_AVG_DEGREE: float(cm.get("avg_degree", 0.0)),
        }

    # ------------------------------------------------------------------
    # 路径特征 (10维)
    # ------------------------------------------------------------------
    def _build_path_features(
        self, node_id: str, graph: Any, raw: Dict[str, Any]
    ) -> Dict[str, float]:
        p = raw.get("path", {})
        return {
            FeatureNames.GRAPH_SHORTEST_PATH_LEN: float(p.get("shortest_path_length", -1)),
            FeatureNames.GRAPH_COMMON_NEIGHBORS: float(max(p.get("common_neighbors", 0), 0)),
            FeatureNames.GRAPH_JACCARD_SIMILARITY: float(p.get("jaccard_similarity", 0.0)),
            FeatureNames.GRAPH_ADAMIC_ADAR: float(p.get("adamic_adar", 0.0)),
            FeatureNames.GRAPH_RESOURCE_ALLOCATION: float(p.get("resource_allocation", 0.0)),
            FeatureNames.GRAPH_PREF_ATTACHMENT: float(p.get("preferential_attachment", 0.0)),
            FeatureNames.GRAPH_TOTAL_PATHS_2HOP: float(max(p.get("total_paths_2hop", 0), 0)),
            FeatureNames.GRAPH_TOTAL_PATHS_3HOP: float(max(p.get("total_paths_3hop", 0), 0)),
            FeatureNames.GRAPH_AVG_PATH_LENGTH: float(p.get("avg_path_length", 0.0)),
            FeatureNames.GRAPH_DIAMETER: float(max(p.get("diameter", 0), 0)),
        }

    # ------------------------------------------------------------------
    # 额外图谱特征 (8维)
    # ------------------------------------------------------------------
    def _build_extra_graph_features(
        self, node_id: str, graph: Any, raw: Dict[str, Any]
    ) -> Dict[str, float]:
        eg = raw.get("extra_graph", {})
        return {
            FeatureNames.GRAPH_CLUSTERING_COEFF: float(eg.get("clustering_coeff", 0.0)),
            FeatureNames.GRAPH_SQ_CLUSTERING: float(eg.get("sq_clustering", 0.0)),
            FeatureNames.GRAPH_CORE_NUMBER: float(max(eg.get("core_number", 0), 0)),
            FeatureNames.GRAPH_RICH_CLUB: float(eg.get("rich_club", 0.0)),
            FeatureNames.GRAPH_ECCENTRICITY: float(eg.get("eccentricity", 0.0)),
            FeatureNames.GRAPH_PAGE_RANK_TRUST: float(eg.get("pagerank_trust", 0.0)),
            FeatureNames.GRAPH_RANDOM_WALK: float(eg.get("random_walk_landing", 0.0)),
            FeatureNames.GRAPH_GRAPH_HASH: float(eg.get("graph_hash", 0.0)),
        }

    def _fetch_raw(self, node_id: str) -> Dict[str, Any]:
        logger.debug("[GraphFeatureBuilder] 获取节点 %s 的图谱数据", node_id)
        return {}


# ===================================================================
# 时序特征构建器 (30维)
# ===================================================================

class TemporalFeatureBuilder(FeatureBuilder):
    """时序特征构建器 — 30维。

    数据来源:
        - daily_match_stats (每日匹配统计)
        - activity_timeline (活动时间线)
        - calendar_data (日历/节假日数据)
    """

    def build(self, user_id: str, **kwargs) -> Dict[str, float]:
        """构建30维时序特征。

        Args:
            user_id: 用户ID
            **kwargs: 可选的原始数据覆盖

        Returns:
            30维特征字典
        """
        raw = kwargs.get("raw_data", self._fetch_raw(user_id))

        features = {}
        features.update(self._build_trend_features(raw))
        features.update(self._build_seasonal_features(raw))
        features.update(self._build_decay_features(raw))

        self._validate_dim(features, TEMPORAL_FEATURE_DIM)
        return features

    # ------------------------------------------------------------------
    # 趋势特征 (10维)
    # ------------------------------------------------------------------
    def _build_trend_features(self, raw: Dict[str, Any]) -> Dict[str, float]:
        t = raw.get("trend", {})
        daily = t.get("daily_match_counts", [])
        n = len(daily)

        ma7 = self._calc_ma(daily, 7)
        ma30 = self._calc_ma(daily, 30)
        mom = self.safe_divide(ma7 - ma30, ma30) if ma30 > 0 else 0.0

        # 环比 (最近7天 vs 前7天)
        recent_7 = sum(daily[-7:]) if n >= 7 else sum(daily)
        prev_7 = sum(daily[-14:-7]) if n >= 14 else 0.0
        qoq = self.safe_divide(recent_7 - prev_7, prev_7) if prev_7 > 0 else 0.0

        # 同比 (最近30天 vs 去年同期)
        recent_30 = sum(daily[-30:]) if n >= 30 else sum(daily)
        prev_year = sum(daily[-390:-360]) if n >= 390 else 0.0
        yoy = self.safe_divide(recent_30 - prev_year, prev_year) if prev_year > 0 else 0.0

        std_7d = float(np.std(daily[-7:])) if n >= 7 else 0.0
        std_30d = float(np.std(daily[-30:])) if n >= 30 else 0.0
        skew_30d = float(self._calc_skew(daily[-30:])) if n >= 30 else 0.0
        kurt_30d = float(self._calc_kurtosis(daily[-30:])) if n >= 30 else 0.0

        # 加速度 (二阶差分均值)
        accel = 0.0
        if n >= 3:
            diffs = [daily[i] - daily[i - 1] for i in range(1, n)]
            diff2 = [diffs[i] - diffs[i - 1] for i in range(1, len(diffs))]
            accel = float(np.mean(diff2)) if diff2 else 0.0

        return {
            FeatureNames.TEMP_MATCH_MA7: ma7,
            FeatureNames.TEMP_MATCH_MA30: ma30,
            FeatureNames.TEMP_MATCH_MOM: self.clip(mom, -10, 10),
            FeatureNames.TEMP_MATCH_QOQ: self.clip(qoq, -10, 10),
            FeatureNames.TEMP_MATCH_YOY: self.clip(yoy, -10, 10),
            FeatureNames.TEMP_MATCH_STD_7D: std_7d,
            FeatureNames.TEMP_MATCH_STD_30D: std_30d,
            FeatureNames.TEMP_MATCH_SKEW_30D: self.clip(skew_30d, -10, 10),
            FeatureNames.TEMP_MATCH_KURT_30D: self.clip(kurt_30d, -10, 10),
            FeatureNames.TEMP_MATCH_ACCELERATION: self.clip(accel, -10, 10),
        }

    # ------------------------------------------------------------------
    # 季节性特征 (10维)
    # ------------------------------------------------------------------
    def _build_seasonal_features(self, raw: Dict[str, Any]) -> Dict[str, float]:
        s = raw.get("seasonal", {})
        now = datetime.now()

        dow = now.weekday()  # 0=Mon
        month = now.month
        is_weekend = 1.0 if dow >= 5 else 0.0
        is_holiday = 1.0 if s.get("is_holiday", False) else 0.0
        season = (month % 12 + 2) // 3  # 1=spring..4=winter

        return {
            FeatureNames.TEMP_DAY_OF_WEEK: float(dow),
            FeatureNames.TEMP_MONTH_OF_YEAR: float(month),
            FeatureNames.TEMP_IS_WEEKEND: is_weekend,
            FeatureNames.TEMP_IS_HOLIDAY: is_holiday,
            FeatureNames.TEMP_SEASON: float(season),
            FeatureNames.TEMP_DOW_EFFECT_MATCH: float(s.get("dow_effect", 0.0)),
            FeatureNames.TEMP_MONTH_EFFECT_MATCH: float(s.get("month_effect", 0.0)),
            FeatureNames.TEMP_HOLIDAY_EFFECT_MATCH: float(s.get("holiday_effect", 0.0)),
            FeatureNames.TEMP_SEASONAL_STRENGTH: float(s.get("seasonal_strength", 0.0)),
            FeatureNames.TEMP_TREND_STRENGTH: float(s.get("trend_strength", 0.0)),
        }

    # ------------------------------------------------------------------
    # 衰减特征 (10维)
    # ------------------------------------------------------------------
    def _build_decay_features(self, raw: Dict[str, Any]) -> Dict[str, float]:
        d = raw.get("decay", {})
        daily = d.get("daily_values", [])

        # 指数衰减权重: w = exp(-lambda * t), lambda = ln(2)/half_life
        half_life = d.get("half_life", 7.0)
        lam = math.log(2) / max(half_life, 0.1)

        decay_weights = {}
        horizons = [1, 3, 7, 14, 30]
        for h in horizons:
            decay_weights[f"decay_w_{h}d"] = math.exp(-lam * h)

        # 衰减加权和
        n = len(daily)
        decay_sum_7d = 0.0
        decay_sum_30d = 0.0
        for i in range(n):
            t = n - 1 - i
            w = math.exp(-lam * t)
            if t < 7:
                decay_sum_7d += daily[i] * w
            if t < 30:
                decay_sum_30d += daily[i] * w

        decay_avg_7d = decay_sum_7d / 7.0 if n >= 1 else 0.0
        decay_avg_30d = decay_sum_30d / 30.0 if n >= 1 else 0.0

        return {
            FeatureNames.TEMP_DECAY_WEIGHT_1D: decay_weights["decay_w_1d"],
            FeatureNames.TEMP_DECAY_WEIGHT_3D: decay_weights["decay_w_3d"],
            FeatureNames.TEMP_DECAY_WEIGHT_7D: decay_weights["decay_w_7d"],
            FeatureNames.TEMP_DECAY_WEIGHT_14D: decay_weights["decay_w_14d"],
            FeatureNames.TEMP_DECAY_WEIGHT_30D: decay_weights["decay_w_30d"],
            FeatureNames.TEMP_DECAY_SUM_7D: decay_sum_7d,
            FeatureNames.TEMP_DECAY_SUM_30D: decay_sum_30d,
            FeatureNames.TEMP_DECAY_AVG_7D: decay_avg_7d,
            FeatureNames.TEMP_DECAY_AVG_30D: decay_avg_30d,
            FeatureNames.TEMP_DECAY_HALF_LIFE: float(half_life),
        }

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    @staticmethod
    def _calc_ma(values: List[float], window: int) -> float:
        if not values:
            return 0.0
        recent = values[-window:] if len(values) >= window else values
        return float(np.mean(recent)) if recent else 0.0

    @staticmethod
    def _calc_skew(values: List[float]) -> float:
        """计算偏度。"""
        n = len(values)
        if n < 3:
            return 0.0
        mean = float(np.mean(values))
        std = float(np.std(values))
        if std == 0:
            return 0.0
        return float(n * sum((v - mean) ** 3 for v in values) / ((n - 1) * (n - 2) * std ** 3))

    @staticmethod
    def _calc_kurtosis(values: List[float]) -> float:
        """计算峰度 (超额峰度)。"""
        n = len(values)
        if n < 4:
            return 0.0
        mean = float(np.mean(values))
        std = float(np.std(values))
        if std == 0:
            return 0.0
        return float(
            (n * (n + 1) * sum((v - mean) ** 4 for v in values)
             / ((n - 1) * (n - 2) * (n - 3) * std ** 4))
            - 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))
        )

    def _fetch_raw(self, user_id: str) -> Dict[str, Any]:
        logger.debug("[TemporalFeatureBuilder] 获取用户 %s 的时序数据", user_id)
        return {}


# ===================================================================
# 文本特征构建器 (20维)
# ===================================================================

class TextFeatureBuilder(FeatureBuilder):
    """文本特征构建器 — 20维。

    数据来源:
        - enterprise_intro (企业简介文本)
        - product_desc (产品描述)
        - keyword_tags (关键词标签)

    处理流程:
        文本 → BGE-M3 Embedding (1024d) → PCA (20d)
        文本 → TF-IDF → Top20 关键词权重

    注意: 此处为模拟降维结果; 实际需部署 BGE-M3 模型 + PCA 模型。
    """

    def build(self, entity_id: str, **kwargs) -> Dict[str, float]:
        """构建20维文本特征。

        Args:
            entity_id: 实体ID (企业/用户)
            **kwargs: 可选的原始数据覆盖

        Returns:
            20维特征字典
        """
        raw = kwargs.get("raw_data", self._fetch_raw(entity_id))
        # 如果提供了外部 embedding，直接使用
        embeddings = kwargs.get("embeddings_20d",
                                raw.get("pca_embeddings", self._simulate_embeddings(entity_id)))
        tfidf_weights = kwargs.get("tfidf_top20",
                                    raw.get("tfidf_weights", self._simulate_tfidf(entity_id)))

        features = {}
        # Embedding 10维
        for i in range(10):
            features[getattr(FeatureNames, f"TEXT_EMBEDDING_{i+1:02d}")] = float(embeddings[i] if i < len(embeddings) else 0.0)
        # TF-IDF 10维
        for i in range(10):
            features[getattr(FeatureNames, f"TEXT_TFIDF_WORD_{i+1:02d}")] = float(tfidf_weights[i] if i < len(tfidf_weights) else 0.0)

        self._validate_dim(features, TEXT_FEATURE_DIM)
        return features

    def _simulate_embeddings(self, entity_id: str) -> List[float]:
        """模拟 PCA 降维后的 10 维文本 embedding。

        实际中将使用 BGE-M3 → 1024d → PCA → 10d。
        """
        # 使用 entity_id 的 hash 作为种子生成确定性 embedding
        seed = abs(hash(entity_id)) % (2 ** 32)
        rng = random.Random(seed)
        raw_emb = [rng.gauss(0, 1) for _ in range(10)]
        # L2 归一化
        norm = math.sqrt(sum(v ** 2 for v in raw_emb)) or 1.0
        return [v / norm for v in raw_emb]

    def _simulate_tfidf(self, entity_id: str) -> List[float]:
        """模拟 TF-IDF Top20 关键词权重。

        实际中将从分词 → TF-IDF 计算 → Top20 抽取。
        """
        seed = abs(hash(entity_id + "_tfidf")) % (2 ** 32)
        rng = random.Random(seed)
        weights = [rng.random() for _ in range(10)]
        # 归一化使得 sum = 1
        total = sum(weights) or 1.0
        return [w / total for w in weights]

    def _fetch_raw(self, entity_id: str) -> Dict[str, Any]:
        logger.debug("[TextFeatureBuilder] 获取实体 %s 的文本数据", entity_id)
        return {}


# ===================================================================
# 特征工厂 (主入口)
# ===================================================================

class FeatureFactory:
    """特征工程工厂 — 统一特征构建入口。

    使用策略模式组合多个 FeatureBuilder，提供:
        - 单类别特征构建
        - 全量 200+ 维特征构建
        - 特征名称查询
        - 可选的缓存层 (FeatureStore)

    Usage:
        factory = FeatureFactory()
        features = factory.build_all("user", "user_001")
        print(features.dim)  # 200

        # 带缓存
        store = FeatureStore()
        factory = FeatureFactory(store=store)
        features = factory.build_all("enterprise", "ent_001")
    """

    def __init__(
        self,
        store: Optional[FeatureStore] = None,
        enable_cache: bool = True,
    ):
        self.store = store or FeatureStore()
        self.enable_cache = enable_cache

        # 注册构建器
        self._builders: Dict[str, FeatureBuilder] = {
            "user_behavior": UserBehaviorBuilder(),
            "enterprise": EnterpriseFeatureBuilder(),
            "graph": GraphFeatureBuilder(),
            "temporal": TemporalFeatureBuilder(),
            "text": TextFeatureBuilder(),
        }

        # 全量特征名列表 (按固定顺序)
        self._all_feature_names: Optional[List[str]] = None

    # ------------------------------------------------------------------
    # 单类别特征构建
    # ------------------------------------------------------------------

    def build_user_features(self, user_id: str, **kwargs) -> Dict[str, float]:
        """构建40维用户行为特征。"""
        return self._build_and_cache(
            "user_behavior", f"user:{user_id}", user_id, **kwargs
        )

    def build_enterprise_features(self, enterprise_id: str, **kwargs) -> Dict[str, float]:
        """构建60维企业特征。"""
        return self._build_and_cache(
            "enterprise", f"ent:{enterprise_id}", enterprise_id, **kwargs
        )

    def build_graph_features(
        self, node_id: str, graph: Any = None, **kwargs
    ) -> Dict[str, float]:
        """构建50维图谱特征。

        Args:
            node_id: 节点ID
            graph: networkx.Graph 对象 (可选)
            **kwargs: 其他参数传递给构建器
        """
        return self._build_and_cache(
            "graph", f"graph:{node_id}", node_id, graph=graph, **kwargs
        )

    def build_temporal_features(self, user_id: str, **kwargs) -> Dict[str, float]:
        """构建30维时序特征。"""
        return self._build_and_cache(
            "temporal", f"temp:{user_id}", user_id, **kwargs
        )

    def build_text_features(self, entity_id: str, **kwargs) -> Dict[str, float]:
        """构建20维文本特征。"""
        return self._build_and_cache(
            "text", f"text:{entity_id}", entity_id, **kwargs
        )

    # ------------------------------------------------------------------
    # 全量特征构建 (200+维)
    # ------------------------------------------------------------------

    def build_all(
        self,
        entity_type: str,
        entity_id: str,
        **kwargs,
    ) -> FeatureVector:
        """构建完整 200+ 维特征向量。

        Args:
            entity_type: 实体类型 ("user" 或 "enterprise")
            entity_id: 实体ID
            **kwargs:
                graph: 图谱对象 (用于图谱特征)
                target_node: 目标节点ID (用于路径特征)
                extra_data: 各构建器的原始数据覆盖

        Returns:
            FeatureVector 包含全部特征
        """
        cache_key = f"all:{entity_type}:{entity_id}"

        # 缓存命中
        if self.enable_cache:
            cached = self.store.cache_get(cache_key)
            if cached is not None:
                logger.debug("[FeatureFactory] 缓存命中: %s", cache_key)
                return cached
            logger.debug("[FeatureFactory] 缓存未命中: %s", cache_key)

        # 构建各分类特征
        extra = kwargs.get("extra_data", {})

        if entity_type == "user":
            user_feats = self.build_user_features(entity_id, raw_data=extra.get("user"))
            ent_feats = self.build_enterprise_features(
                kwargs.get("enterprise_id", entity_id),
                raw_data=extra.get("enterprise"),
            )
            temp_feats = self.build_temporal_features(entity_id, raw_data=extra.get("temporal"))
        else:
            user_feats = self.build_user_features(
                kwargs.get("user_id", entity_id),
                raw_data=extra.get("user"),
            )
            ent_feats = self.build_enterprise_features(entity_id, raw_data=extra.get("enterprise"))
            temp_feats = self.build_temporal_features(
                kwargs.get("user_id", entity_id),
                raw_data=extra.get("temporal"),
            )

        graph_feats = self.build_graph_features(
            entity_id,
            graph=kwargs.get("graph"),
            raw_data=extra.get("graph"),
        )

        text_feats = self.build_text_features(entity_id, raw_data=extra.get("text"))

        # 合并 → 按固定顺序排列
        all_features = {}
        all_features.update(user_feats)
        all_features.update(ent_feats)
        all_features.update(graph_feats)
        all_features.update(temp_feats)
        all_features.update(text_feats)

        # 验证总维度
        if len(all_features) != TOTAL_FEATURE_DIM:
            logger.warning(
                "总特征维度不匹配: 期望 %d, 实际 %d",
                TOTAL_FEATURE_DIM, len(all_features),
            )

        fv = FeatureVector(
            features=all_features,
            entity_type=entity_type,
            entity_id=entity_id,
            version=FEATURE_VERSION,
        )

        # 写入缓存
        if self.enable_cache:
            self.store.cache_set(cache_key, fv)
            logger.debug("[FeatureFactory] 缓存写入: %s (%d维)", cache_key, fv.dim)

        return fv

    # ------------------------------------------------------------------
    # 特征名称 & 元数据
    # ------------------------------------------------------------------

    def get_feature_names(self, category: Optional[str] = None) -> List[str]:
        """获取特征名列表。

        Args:
            category: 特征类别名称 (user/enterprise/graph/temporal/text/all)
                      默认返回全量特征名 (200维)

        Returns:
            特征名列表 (按固定顺序)
        """
        category_map = {
            "user": [getattr(FeatureNames, a) for a in dir(FeatureNames)
                     if a.startswith("MATCH_") or a.startswith("FEEDBACK_")
                     or a.startswith("ACTIVE_") or a.startswith("SOCIAL_")],
            "enterprise": [getattr(FeatureNames, a) for a in dir(FeatureNames)
                           if a.startswith("ENT_")],
            "graph": [getattr(FeatureNames, a) for a in dir(FeatureNames)
                      if a.startswith("GRAPH_")],
            "temporal": [getattr(FeatureNames, a) for a in dir(FeatureNames)
                         if a.startswith("TEMP_")],
            "text": [getattr(FeatureNames, a) for a in dir(FeatureNames)
                     if a.startswith("TEXT_")],
        }

        if category and category in category_map:
            return category_map[category]

        # 全量 (缓存)
        if self._all_feature_names is None:
            all_names = []
            for cat in ["user", "enterprise", "graph", "temporal", "text"]:
                all_names.extend(category_map[cat])
            self._all_feature_names = all_names

        return self._all_feature_names

    def get_feature_meta(self) -> Dict[str, Any]:
        """返回特征元数据。"""
        names = self.get_feature_names()
        by_category = {}
        for cat in ["user", "enterprise", "graph", "temporal", "text"]:
            cat_names = self.get_feature_names(cat)
            by_category[cat] = {
                "count": len(cat_names),
                "names": cat_names,
            }

        return {
            "version": FEATURE_VERSION,
            "total_dim": len(names),
            "categories": by_category,
        }

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _build_and_cache(
        self,
        builder_key: str,
        cache_key: str,
        entity_id: str,
        **kwargs,
    ) -> Dict[str, float]:
        """构建单个类别的特征，支持缓存。"""
        if self.enable_cache and builder_key != "graph":
            cached = self.store.cache_get(cache_key)
            if cached is not None:
                logger.debug("[FeatureFactory] 缓存命中: %s", cache_key)
                return cached.features

        builder = self._builders[builder_key]
        features = builder.build(entity_id, **kwargs)

        if self.enable_cache and builder_key != "graph":
            fv = FeatureVector(
                features=features,
                entity_type=builder_key,
                entity_id=entity_id,
                version=FEATURE_VERSION,
            )
            self.store.cache_set(cache_key, fv)

        return features

    @property
    def builders(self) -> Dict[str, FeatureBuilder]:
        return dict(self._builders)

    @property
    def feature_store(self) -> FeatureStore:
        return self.store


# ===================================================================
# 便捷工具函数
# ===================================================================

def make_feature_vector(
    entity_type: str,
    entity_id: str,
    features: Optional[Dict[str, float]] = None,
) -> FeatureVector:
    """快速创建一个 FeatureVector。

    Args:
        entity_type: 实体类型
        entity_id: 实体ID
        features: 特征字典 (为 None 时用默认工厂构建)

    Returns:
        FeatureVector
    """
    if features is None:
        factory = FeatureFactory(enable_cache=False)
        return factory.build_all(entity_type, entity_id)
    return FeatureVector(
        features=features,
        entity_type=entity_type,
        entity_id=entity_id,
    )


def merge_feature_vectors(
    vectors: List[FeatureVector],
    entity_type: str,
    entity_id: str,
) -> FeatureVector:
    """合并多个 FeatureVector 为一个。

    Args:
        vectors: 特征向量列表
        entity_type: 目标实体类型
        entity_id: 目标实体ID

    Returns:
        合并后的 FeatureVector
    """
    merged = {}
    for v in vectors:
        merged.update(v.features)
    return FeatureVector(
        features=merged,
        entity_type=entity_type,
        entity_id=entity_id,
    )


def compute_feature_correlation(
    fv1: FeatureVector,
    fv2: FeatureVector,
    common_only: bool = True,
) -> float:
    """计算两个特征向量的皮尔逊相关系数。

    Args:
        fv1: 特征向量1
        fv2: 特征向量2
        common_only: 是否只计算共同特征

    Returns:
        相关系数 [-1, 1]
    """
    common_keys = set(fv1.features.keys()) & set(fv2.features.keys())
    if not common_keys:
        return 0.0

    if common_only:
        keys = list(common_keys)
    else:
        keys = list(set(fv1.features.keys()) | set(fv2.features.keys()))

    v1 = np.array([fv1.features.get(k, 0.0) for k in keys])
    v2 = np.array([fv2.features.get(k, 0.0) for k in keys])

    mask = ~(np.isnan(v1) | np.isnan(v2))
    v1, v2 = v1[mask], v2[mask]

    if len(v1) < 2:
        return 0.0

    corr = np.corrcoef(v1, v2)[0, 1]
    return float(corr) if not np.isnan(corr) else 0.0


# ===================================================================
# 快速验证 (python feature_factory.py)
# ===================================================================

def _test_feature_store_basic():
    """TC1: FeatureStore 基础读写"""
    store = FeatureStore()
    fv = FeatureVector(features={"a": 1.0}, entity_type="test", entity_id="t1")

    # 写入
    store.cache_set("test:1", fv)
    assert store.size == 1

    # 读取
    got = store.cache_get("test:1")
    assert got is not None
    assert got.features["a"] == 1.0

    # 不存在
    assert store.cache_get("nonexistent") is None
    print("  ✓ test_feature_store_basic")


def _test_feature_store_ttl():
    """TC2: FeatureStore TTL 过期"""
    store = FeatureStore(default_ttl=0)  # 立即过期
    fv = FeatureVector(features={"x": 1.0}, entity_type="test", entity_id="t2")
    store.cache_set("test:2", fv, ttl=0)
    time.sleep(0.01)
    assert store.cache_get("test:2") is None
    print("  ✓ test_feature_store_ttl")


def _test_feature_store_stats():
    """TC3: FeatureStore 统计"""
    store = FeatureStore()
    fv = FeatureVector(features={"a": 1.0}, entity_type="test", entity_id="t3")

    store.cache_set("k1", fv)
    store.cache_get("k1")  # hit
    store.cache_get("k1")  # hit
    store.cache_get("nope")  # miss

    s = store.stats()
    assert s["hits"] == 2
    assert s["misses"] == 1
    assert s["sets"] == 1
    assert s["hit_rate"] > 0
    print("  ✓ test_feature_store_stats")


def _test_feature_store_batch():
    """TC4: FeatureStore 批量操作"""
    store = FeatureStore()
    items = {
        f"batch:{i}": FeatureVector(
            features={"v": float(i)},
            entity_type="batch",
            entity_id=str(i),
        )
        for i in range(3)
    }
    store.batch_set(items)
    results = store.batch_get(["batch:0", "batch:1", "batch:2", "nonexistent"])
    assert results[0] is not None
    assert results[1] is not None
    assert results[2] is not None
    assert results[3] is None
    print("  ✓ test_feature_store_batch")


def _test_feature_store_lru_eviction():
    """TC5: FeatureStore LRU 淘汰"""
    store = FeatureStore(max_size=2)
    for i in range(4):
        fv = FeatureVector(features={"v": float(i)}, entity_type="lru", entity_id=str(i))
        store.cache_set(f"key:{i}", fv)

    # 最早两个应被淘汰
    assert store.size == 2
    assert store.cache_get("key:0") is None
    assert store.cache_get("key:1") is None
    assert store.cache_get("key:2") is not None
    assert store.cache_get("key:3") is not None
    print("  ✓ test_feature_store_lru_eviction")


def _test_user_features_dim():
    """TC6: 用户行为特征维度 (40维)"""
    builder = UserBehaviorBuilder()
    raw = _make_mock_user_raw("u001")
    feats = builder.build("u001", raw_data=raw)
    assert len(feats) == USER_FEATURE_DIM, f"期望 {USER_FEATURE_DIM}, 实际 {len(feats)}"
    # 所有值应为有限数值
    for k, v in feats.items():
        assert math.isfinite(v), f"{k} 的值 {v} 不是有限数值"
    print(f"  ✓ test_user_features_dim ({len(feats)}维)")


def _test_user_features_ranges():
    """TC7: 用户行为特征值范围"""
    builder = UserBehaviorBuilder()
    raw = _make_mock_user_raw("u001")
    feats = builder.build("u001", raw_data=raw)

    # 成功率应在 [0, 1]
    sr = feats[FeatureNames.MATCH_SUCCESS_RATE]
    assert 0 <= sr <= 1.0, f"成功率范围异常: {sr}"

    # like rate + dislike rate ≤ 1
    lr = feats[FeatureNames.FEEDBACK_LIKE_RATE]
    dr = feats[FeatureNames.FEEDBACK_DISLIKE_RATE]
    assert 0 <= lr <= 1.0
    assert 0 <= dr <= 1.0
    assert lr + dr <= 1.0 + 1e-6

    # 评分均值应在 [0, 5]
    rm = feats[FeatureNames.FEEDBACK_RATING_MEAN]
    assert 0 <= rm <= 5.0, f"评分均值范围异常: {rm}"

    print("  ✓ test_user_features_ranges")


def _test_enterprise_features_dim():
    """TC8: 企业特征维度 (60维)"""
    builder = EnterpriseFeatureBuilder()
    raw = _make_mock_enterprise_raw("ent_001")
    feats = builder.build("ent_001", raw_data=raw)
    assert len(feats) == ENTERPRISE_FEATURE_DIM, f"期望 {ENTERPRISE_FEATURE_DIM}, 实际 {len(feats)}"
    for k, v in feats.items():
        assert math.isfinite(v), f"{k} 的值 {v} 不是有限数值"
    print(f"  ✓ test_enterprise_features_dim ({len(feats)}维)")


def _test_enterprise_features_log_transform():
    """TC9: 企业特征 log 变换"""
    builder = EnterpriseFeatureBuilder()
    raw = _make_mock_enterprise_raw("ent_002", capital=0, employees=0)
    feats = builder.build("ent_002", raw_data=raw)

    # 注册资本 log(0+1) = 0
    assert feats[FeatureNames.ENT_REG_CAPITAL_LOG] == 0.0
    # 员工 log(0+1) = 0
    assert feats[FeatureNames.ENT_EMPLOYEE_COUNT_LOG] == 0.0
    assert math.isfinite(feats[FeatureNames.ENT_REVENUE_PER_EMPLOYEE])
    print("  ✓ test_enterprise_features_log_transform")


def _test_graph_features_dim():
    """TC10: 图谱特征维度 (50维)"""
    builder = GraphFeatureBuilder()
    raw = _make_mock_graph_raw("node_001")
    feats = builder.build("node_001", raw_data=raw)
    assert len(feats) == GRAPH_FEATURE_DIM, f"期望 {GRAPH_FEATURE_DIM}, 实际 {len(feats)}"
    for k, v in feats.items():
        assert math.isfinite(v), f"{k} 的值 {v} 不是有限数值"
    print(f"  ✓ test_graph_features_dim ({len(feats)}维)")


def _test_temporal_features_dim():
    """TC11: 时序特征维度 (30维)"""
    builder = TemporalFeatureBuilder()
    raw = _make_mock_temporal_raw("u001")
    feats = builder.build("u001", raw_data=raw)
    assert len(feats) == TEMPORAL_FEATURE_DIM, f"期望 {TEMPORAL_FEATURE_DIM}, 实际 {len(feats)}"
    for k, v in feats.items():
        assert math.isfinite(v), f"{k} 的值 {v} 不是有限数值"
    print(f"  ✓ test_temporal_features_dim ({len(feats)}维)")


def _test_temporal_trend_values():
    """TC12: 时序趋势特征计算"""
    builder = TemporalFeatureBuilder()
    # 单调递增数据
    raw = {
        "trend": {
            "daily_match_counts": [float(i) for i in range(60)],
        },
        "seasonal": {},
        "decay": {
            "daily_values": [float(i) for i in range(60)],
            "half_life": 7.0,
        },
    }
    feats = builder.build("u_test", raw_data=raw)

    # MA30 > MA7 (递增趋势)
    assert feats[FeatureNames.TEMP_MATCH_MA30] > feats[FeatureNames.TEMP_MATCH_MA7]
    # MOM > 0
    assert feats[FeatureNames.TEMP_MATCH_MOM] > 0
    # 加速度 > 0 (二阶差分均值正)
    assert feats[FeatureNames.TEMP_MATCH_ACCELERATION] > 0
    print("  ✓ test_temporal_trend_values")


def _test_text_features_dim():
    """TC13: 文本特征维度 (20维)"""
    builder = TextFeatureBuilder()
    feats = builder.build("ent_001")
    assert len(feats) == TEXT_FEATURE_DIM, f"期望 {TEXT_FEATURE_DIM}, 实际 {len(feats)}"
    for k, v in feats.items():
        assert math.isfinite(v), f"{k} 的值 {v} 不是有限数值"
    print(f"  ✓ test_text_features_dim ({len(feats)}维)")


def _test_text_embedding_normalization():
    """TC14: 文本 embedding L2 归一化"""
    builder = TextFeatureBuilder()
    feats = builder.build("ent_005")

    emb_keys = [getattr(FeatureNames, f"TEXT_EMBEDDING_{i+1:02d}") for i in range(10)]
    emb_vals = [feats[k] for k in emb_keys]
    norm = math.sqrt(sum(v ** 2 for v in emb_vals))
    assert abs(norm - 1.0) < 1e-5, f"embedding L2 范数应为 1, 实际 {norm}"
    print("  ✓ test_text_embedding_normalization")


def _test_factory_build_all_user():
    """TC15: FeatureFactory.build_all 用户全量特征 (200维)"""
    factory = FeatureFactory(enable_cache=False)
    fv = factory.build_all("user", "user_001",
                           extra_data={
                               "user": _make_mock_user_raw("user_001"),
                               "enterprise": _make_mock_enterprise_raw("ent_001"),
                               "temporal": _make_mock_temporal_raw("user_001"),
                               "graph": _make_mock_graph_raw("user_001"),
                               "text": {"pca_embeddings": [0.1] * 10, "tfidf_weights": [0.1] * 10},
                           })
    assert fv.dim == TOTAL_FEATURE_DIM, f"期望 {TOTAL_FEATURE_DIM}, 实际 {fv.dim}"
    assert fv.entity_type == "user"
    assert fv.entity_id == "user_001"
    # 验证特征值有限
    for k, v in fv.features.items():
        assert math.isfinite(v), f"{k} 的值 {v} 不是有限数值"
    print(f"  ✓ test_factory_build_all_user ({fv.dim}维)")


def _test_factory_build_all_enterprise():
    """TC16: FeatureFactory.build_all 企业全量特征 (200维)"""
    factory = FeatureFactory(enable_cache=False)
    fv = factory.build_all("enterprise", "ent_001",
                           extra_data={
                               "user": _make_mock_user_raw("user_001"),
                               "enterprise": _make_mock_enterprise_raw("ent_001"),
                               "temporal": _make_mock_temporal_raw("u1"),
                               "graph": _make_mock_graph_raw("ent_001"),
                               "text": {"pca_embeddings": [0.2] * 10, "tfidf_weights": [0.1] * 10},
                           })
    assert fv.dim == TOTAL_FEATURE_DIM, f"期望 {TOTAL_FEATURE_DIM}, 实际 {fv.dim}"
    print(f"  ✓ test_factory_build_all_enterprise ({fv.dim}维)")


def _test_factory_cache():
    """TC17: FeatureFactory 缓存"""
    store = FeatureStore()
    factory = FeatureFactory(store=store, enable_cache=True)

    fv1 = factory.build_all("user", "cache_test",
                            extra_data={
                                "user": _make_mock_user_raw("cache_test"),
                                "enterprise": _make_mock_enterprise_raw("e1"),
                                "temporal": _make_mock_temporal_raw("cache_test"),
                                "graph": _make_mock_graph_raw("cache_test"),
                                "text": {"pca_embeddings": [0.1] * 10, "tfidf_weights": [0.1] * 10},
                            })
    fv2 = factory.build_all("user", "cache_test",
                            extra_data={
                                "user": _make_mock_user_raw("cache_test"),
                                "enterprise": _make_mock_enterprise_raw("e1"),
                                "temporal": _make_mock_temporal_raw("cache_test"),
                                "graph": _make_mock_graph_raw("cache_test"),
                                "text": {"pca_embeddings": [0.1] * 10, "tfidf_weights": [0.1] * 10},
                            })
    # 从缓存获取，特征应一致
    assert fv1.features == fv2.features
    s = store.stats()
    assert s["hits"] >= 1
    print("  ✓ test_factory_cache")


def _test_factory_feature_names():
    """TC18: FeatureFactory 特征名称列表"""
    factory = FeatureFactory()
    names = factory.get_feature_names()
    assert len(names) == TOTAL_FEATURE_DIM, f"期望 {TOTAL_FEATURE_DIM} 个特征名, 实际 {len(names)}"

    # 按类别
    cat_names = factory.get_feature_names("user")
    assert len(cat_names) == USER_FEATURE_DIM
    cat_names = factory.get_feature_names("enterprise")
    assert len(cat_names) == ENTERPRISE_FEATURE_DIM
    cat_names = factory.get_feature_names("graph")
    assert len(cat_names) == GRAPH_FEATURE_DIM
    cat_names = factory.get_feature_names("temporal")
    assert len(cat_names) == TEMPORAL_FEATURE_DIM
    cat_names = factory.get_feature_names("text")
    assert len(cat_names) == TEXT_FEATURE_DIM

    # 所有特征名唯一
    assert len(set(names)) == len(names), "特征名存在重复!"

    print("  ✓ test_factory_feature_names")


def _test_feature_vector_serialization():
    """TC19: FeatureVector 序列化/反序列化"""
    fv = FeatureVector(
        features={"a": 1.0, "b": 2.0},
        entity_type="user",
        entity_id="u001",
    )
    d = fv.to_dict()
    restored = FeatureVector.from_dict(d)
    assert restored.features == fv.features
    assert restored.entity_type == fv.entity_type
    assert restored.entity_id == fv.entity_id
    print("  ✓ test_feature_vector_serialization")


def _test_compute_correlation():
    """TC20: 特征相关性计算"""
    fv1 = FeatureVector(features={"a": 1.0, "b": 2.0, "c": 3.0}, entity_type="t", entity_id="t1")
    fv2 = FeatureVector(features={"a": 2.0, "b": 4.0, "c": 6.0}, entity_type="t", entity_id="t2")  # 完全正相关
    fv3 = FeatureVector(features={"a": 6.0, "b": 4.0, "c": 2.0}, entity_type="t", entity_id="t3")  # 负相关

    corr = compute_feature_correlation(fv1, fv2)
    assert abs(corr - 1.0) < 1e-5, f"完全正相关应为 1.0, 实际 {corr}"

    corr_neg = compute_feature_correlation(fv1, fv3)
    assert abs(corr_neg - (-1.0)) < 1e-5, f"完全负相关应为 -1.0, 实际 {corr_neg}"

    print("  ✓ test_compute_correlation")


# ===================================================================
# Mock 数据生成器
# ===================================================================

def _make_mock_user_raw(user_id: str) -> Dict[str, Any]:
    """生成模拟用户原始数据。"""
    seed = abs(hash(user_id)) % (2 ** 32)
    rng = random.Random(seed)

    total_matches = rng.randint(10, 500)
    success = rng.randint(1, total_matches)
    ratings = [rng.uniform(1, 5) for _ in range(rng.randint(5, 20))]

    return {
        "match_history": {
            "total": total_matches,
            "success": success,
            "avg_response_time": rng.uniform(0.5, 48.0),
            "most_common_type": rng.randint(1, 5),
            "most_common_type_count": rng.randint(1, total_matches // 2),
            "recent_7d": rng.randint(0, 20),
            "recent_30d": rng.randint(0, 100),
        },
        "feedback": {
            "like_count": rng.randint(0, 200),
            "dislike_count": rng.randint(0, 50),
            "ratings": ratings,
        },
        "activity": {
            "last_login_hours_ago": rng.uniform(0, 720),
            "login_count_7d": rng.randint(0, 14),
            "login_count_30d": rng.randint(0, 60),
            "login_freq_std": rng.uniform(0, 2),
            "browse_count_7d": rng.randint(0, 200),
            "browse_count_30d": rng.randint(0, 2000),
            "browse_avg_duration": rng.uniform(10, 600),
            "browse_total_duration": rng.uniform(100, 36000),
            "session_count": rng.randint(1, 50),
            "session_avg_duration": rng.uniform(60, 3600),
            "session_std_duration": rng.uniform(0, 600),
        },
        "social": {
            "contact_count": rng.randint(0, 500),
            "common_contact_count": rng.randint(0, 200),
            "circle_density": rng.uniform(0, 1),
            "circle_size": rng.randint(0, 200),
            "group_count": rng.randint(0, 50),
            "active_group_count": rng.randint(0, 20),
            "message_count_7d": rng.randint(0, 200),
            "message_count_30d": rng.randint(0, 2000),
            "avg_response_time": rng.uniform(0.1, 24),
            "following_count": rng.randint(0, 500),
            "follower_count": rng.randint(0, 2000),
        },
    }


def _make_mock_enterprise_raw(
    enterprise_id: str,
    capital: Optional[float] = None,
    employees: Optional[int] = None,
) -> Dict[str, Any]:
    """生成模拟企业原始数据。"""
    seed = abs(hash(enterprise_id)) % (2 ** 32)
    rng = random.Random(seed)

    reg_capital = capital if capital is not None else rng.uniform(1e5, 1e9)
    emp_count = employees if employees is not None else rng.randint(10, 10000)
    est_years = rng.randint(1, 50)

    return {
        "business": {
            "registered_capital": reg_capital,
            "established_years": est_years,
            "shareholder_count": rng.randint(1, 50),
            "branch_count": rng.randint(0, 30),
            "legal_rep_age": rng.randint(25, 65),
            "region_code": rng.randint(1, 35),
            "company_type_code": rng.randint(1, 10),
            "reg_capital_usd": reg_capital * 0.14,
            "capital_change_count": rng.randint(0, 20),
            "is_listed": rng.randint(0, 1),
        },
        "credit": {
            "credit_score": rng.uniform(300, 950),
            "admin_penalty_count": rng.randint(0, 10),
            "judicial_risk_count": rng.randint(0, 20),
            "operation_risk_count": rng.randint(0, 15),
            "ip_count": rng.randint(0, 500),
            "trademark_count": rng.randint(0, 200),
            "patent_count": rng.randint(0, 300),
            "copyright_count": rng.randint(0, 100),
            "tax_credit_level": rng.randint(1, 5),
            "env_credit_score": rng.uniform(0, 100),
            "social_credit_code_hash": rng.random(),
            "litigation_count": rng.randint(0, 30),
            "execution_count": rng.randint(0, 10),
        },
        "industry": {
            "industry_code": rng.randint(1, 100),
            "category_code": rng.randint(1, 20),
            "chain_position": rng.uniform(0, 1),
            "upstream_count": rng.randint(0, 50),
            "downstream_count": rng.randint(0, 50),
            "competition_index": rng.uniform(0, 1),
            "growth_rate": rng.uniform(-0.3, 0.5),
            "profit_margin": rng.uniform(-0.2, 0.6),
            "cross_industry_count": rng.randint(0, 5),
            "main_business_ratio": rng.uniform(0.5, 1.0),
            "industry_rank": rng.randint(1, 500),
            "supplier_concentration": rng.uniform(0, 1),
        },
        "scale": {
            "employee_count": emp_count,
            "estimated_revenue": rng.uniform(1e6, 1e10),
            "province_count": rng.randint(1, 34),
            "city_count": rng.randint(1, 100),
            "country_count": rng.randint(1, 10),
            "asset_total": rng.uniform(1e6, 1e11),
        },
        "extra": {
            "website_rank": rng.uniform(1, 100000),
            "social_media_followers": rng.randint(0, 100000),
            "recruitment_count": rng.randint(0, 200),
            "certification_count": rng.randint(0, 50),
            "qualification_count": rng.randint(0, 30),
            "annual_report_score": rng.uniform(0, 100),
            "govt_subsidy_amount": rng.uniform(0, 1e7),
            "tax_contribution": rng.uniform(0, 1e8),
            "import_export_volume": rng.uniform(0, 1e8),
            "investment_count": rng.randint(0, 50),
        },
    }


def _make_mock_graph_raw(node_id: str) -> Dict[str, Any]:
    """生成模拟图谱原始数据。"""
    seed = abs(hash(node_id)) % (2 ** 32)
    rng = random.Random(seed)
    n_nodes = rng.randint(50, 5000)
    degree = rng.randint(0, n_nodes - 1)

    return {
        "degree": {
            "degree": degree,
            "total_nodes": n_nodes,
            "cooperation_count": rng.randint(0, max(degree, 1)),
            "competition_count": rng.randint(0, max(degree, 1)),
            "supplier_count": rng.randint(0, max(degree, 1)),
            "customer_count": rng.randint(0, max(degree, 1)),
            "investor_count": rng.randint(0, max(degree, 1)),
            "investee_count": rng.randint(0, max(degree, 1)),
            "in_degree": rng.randint(0, max(degree, 1)),
            "out_degree": rng.randint(0, max(degree, 1)),
        },
        "centrality": {
            "pagerank": rng.uniform(0, 0.1),
            "betweenness": rng.uniform(0, 0.5),
            "closeness": rng.uniform(0, 1),
            "eigenvector": rng.uniform(0, 1),
            "harmonic": rng.uniform(0, 1),
            "katz": rng.uniform(0, 1),
            "load": rng.uniform(0, 0.5),
            "subgraph": rng.uniform(0, 1),
            "edge_betweenness": rng.uniform(0, 0.5),
            "approx_closeness": rng.uniform(0, 1),
        },
        "community": {
            "community_id": rng.randint(0, 20),
            "community_size": rng.randint(1, 500),
            "community_density": rng.uniform(0, 1),
            "modularity": rng.uniform(0, 1),
            "num_communities": rng.randint(1, 50),
            "conductance": rng.uniform(0, 1),
            "cut_ratio": rng.uniform(0, 1),
            "normalized_cut": rng.uniform(0, 1),
            "triangle_count": rng.randint(0, 1000),
            "transitivity": rng.uniform(0, 1),
            "sq_clustering": rng.uniform(0, 1),
            "avg_degree": rng.uniform(0, 50),
        },
        "path": {
            "shortest_path_length": rng.randint(-1, 10),
            "common_neighbors": rng.randint(0, 100),
            "jaccard_similarity": rng.uniform(0, 1),
            "adamic_adar": rng.uniform(0, 10),
            "resource_allocation": rng.uniform(0, 10),
            "preferential_attachment": rng.uniform(0, 1000),
            "total_paths_2hop": rng.randint(0, 1000),
            "total_paths_3hop": rng.randint(0, 10000),
            "avg_path_length": rng.uniform(1, 10),
            "diameter": rng.randint(1, 20),
        },
        "extra_graph": {
            "clustering_coeff": rng.uniform(0, 1),
            "sq_clustering": rng.uniform(0, 1),
            "core_number": rng.randint(0, 20),
            "rich_club": rng.uniform(0, 1),
            "eccentricity": rng.randint(0, 10),
            "pagerank_trust": rng.uniform(0, 1),
            "random_walk_landing": rng.uniform(0, 0.1),
            "graph_hash": rng.random(),
        },
    }


def _make_mock_temporal_raw(user_id: str) -> Dict[str, Any]:
    """生成模拟时序原始数据。"""
    seed = abs(hash(user_id + "_temporal")) % (2 ** 32)
    rng = random.Random(seed)
    n_days = 90
    daily = [max(0, rng.gauss(10, 5) + i * 0.05) for i in range(n_days)]

    return {
        "trend": {
            "daily_match_counts": daily,
        },
        "seasonal": {
            "is_holiday": rng.random() < 0.1,
            "dow_effect": rng.uniform(-0.5, 0.5),
            "month_effect": rng.uniform(-0.3, 0.3),
            "holiday_effect": rng.uniform(-0.5, 0.5),
            "seasonal_strength": rng.uniform(0, 1),
            "trend_strength": rng.uniform(0, 1),
        },
        "decay": {
            "daily_values": daily,
            "half_life": 7.0,
        },
    }


# ===================================================================
# 主入口
# ===================================================================

def run_all_tests():
    """运行所有测试用例。"""
    print("=" * 60)
    print("  链客宝特征工程工厂 — 测试套件")
    print("=" * 60)

    tests = [
        ("FeatureStore 基础读写", _test_feature_store_basic),
        ("FeatureStore TTL 过期", _test_feature_store_ttl),
        ("FeatureStore 统计", _test_feature_store_stats),
        ("FeatureStore 批量操作", _test_feature_store_batch),
        ("FeatureStore LRU 淘汰", _test_feature_store_lru_eviction),
        ("用户行为特征维度", _test_user_features_dim),
        ("用户行为特征值范围", _test_user_features_ranges),
        ("企业特征维度", _test_enterprise_features_dim),
        ("企业特征 log 变换", _test_enterprise_features_log_transform),
        ("图谱特征维度", _test_graph_features_dim),
        ("时序特征维度", _test_temporal_features_dim),
        ("时序趋势特征计算", _test_temporal_trend_values),
        ("文本特征维度", _test_text_features_dim),
        ("文本 embedding 归一化", _test_text_embedding_normalization),
        ("全量特征构建(用户)", _test_factory_build_all_user),
        ("全量特征构建(企业)", _test_factory_build_all_enterprise),
        ("FeatureFactory 缓存", _test_factory_cache),
        ("特征名称列表", _test_factory_feature_names),
        ("FeatureVector 序列化", _test_feature_vector_serialization),
        ("特征相关性计算", _test_compute_correlation),
    ]

    passed = 0
    failed = 0

    for name, func in tests:
        try:
            func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  ✗ {name}: {e}")
            import traceback
            traceback.print_exc()

    print("-" * 60)
    total = passed + failed
    print(f"  结果: {passed}/{total} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    run_all_tests()
