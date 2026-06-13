"""
链客宝AI LightGBM 匹配模型 v2.0 (P1升级版)
=========================================
可学习的匹配模型，替代规则权重。

P1升级内容:
  1. 数据增强集成 — 读取 training_data_augmented.npz (500+ 合成样本)
  2. LightGBM 参数优化 — n_estimators=200, learning_rate=0.05, num_leaves=31
  3. 特征重要性分析 — 训练后输出各特征贡献度
  4. 交叉验证 (5-fold) — 更稳健的模型评估
  5. 评估指标 (Precision/Recall/F1 at top-k)
  6. A/B 模式 — predict_match_score 支持 mode='ml'|'rule'|'ensemble'
  7. ensemble 模式: 0.6*ML + 0.4*Rule

设计原则:
  1. 轻量 — 无外部服务依赖，单文件可运行
  2. 增量学习 — partial_fit 支持在线更新
  3. 与 feature_pipeline 特征输出兼容
  4. 不影响现有规则引擎（USE_ML_MODEL=False 时无入侵）

架构:
  - build_feature_vector(prod_feat, need_feat) → np.ndarray
  - train(data_loader)          → 全量训练（含 CV + 特征重要性）
  - predict(features)           → 返回 [0,1] 匹配分数
  - partial_fit(features, labels) → 增量更新
  - load_training_data(db)      → 从 UserEvent 读取标注数据
"""

import json
import logging
import os
import pickle
from typing import Any

import numpy as np

# lightgbm 为可选依赖，未安装时降级为 sklearn GBDT
try:
    import lightgbm as lgb

    _HAS_LGB = True
except ImportError:
    _HAS_LGB = False

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import precision_score, recall_score, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

from app import feature_pipeline as fp
from app.models import BusinessNeed, Product, UserEvent

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

# 主开关（外部可通过环境变量控制）
USE_ML_MODEL = os.environ.get("LIANKEBAO_USE_ML_MODEL", "false").lower() in (
    "true",
    "1",
    "yes",
)

# 模型持久化路径
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "matching_model.pkl")
SCALER_PATH = os.path.join(MODEL_DIR, "matching_scaler.pkl")
METADATA_PATH = os.path.join(MODEL_DIR, "matching_model_metadata.json")

# 增强训练数据路径
AUGMENTED_DATA_PATH = os.path.join(MODEL_DIR, "training_data_augmented.npz")

# 训练参数
LGB_PARAMS = {
    "n_estimators": 200,
    "learning_rate": 0.05,
    "max_depth": 5,
    "num_leaves": 31,
    "min_child_samples": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "random_state": 42,
    "verbose": -1,
}

# Ensemble 模式权重
ENSEMBLE_ML_WEIGHT = 0.6
ENSEMBLE_RULE_WEIGHT = 0.4

# 评估 Top-K
TOP_K_VALUES = [1, 3, 5, 10]

# 正负样本映射
POSITIVE_EVENTS = {"click", "like", "adopt", "view", "recommend_like"}
NEGATIVE_EVENTS = {"skip", "dislike", "close", "recommend_dislike"}

# 默认模式
DEFAULT_MODE = os.environ.get("LIANKEBAO_ML_MODE", "ml")

# ============================================================
# 特征工程
# ============================================================

FEATURE_NAMES = [
    "category_sim",       # 类目 Jaccard 相似度
    "text_sim",           # TF-IDF 余弦相似度
    "price_budget_sim",   # 价格-预算匹配度
    "recency_prod",       # 产品新鲜度
    "recency_need",       # 需求新鲜度
    "price_norm",         # 产品归一化价格
    "budget_mid_norm",    # 需求预算中点（归一化）
    "feature_sim",        # feature_pipeline 综合相似度
    "is_cold_prod",       # 产品是否为冷启动新品 (0/1)
    "is_cold_need",       # 需求是否为冷启动新需求 (0/1)
]

NUM_FEATURES = len(FEATURE_NAMES)


def build_feature_vector(
    prod_feat: dict[str, Any],
    need_feat: dict[str, Any],
) -> np.ndarray:
    """将产品-需求特征对编码为 ML 模型的输入向量

    固定长度向量 = NUM_FEATURES，值与 FEATURE_NAMES 一一对应。

    Args:
        prod_feat: extract_product_features() 的输出
        need_feat: extract_need_features() 的输出

    Returns:
        shape=(NUM_FEATURES,) 的 float64 向量
    """
    vec = np.zeros(NUM_FEATURES, dtype=np.float64)

    # 1. 类目相似度 (Jaccard)
    cat_a = prod_feat.get("category_vector", {})
    cat_b = need_feat.get("category_vector", {})
    vec[0] = _jaccard_similarity(cat_a, cat_b)

    # 2. 文本 TF-IDF 余弦相似度
    text_a = prod_feat.get("text_corpus", "")
    text_b = need_feat.get("text_corpus", "")
    vec[1] = _text_sim(text_a, text_b)

    # 3. 价格-预算匹配度
    price_raw = prod_feat.get("price_raw", 0.0)
    budget_range = need_feat.get("budget_range", None)
    vec[2] = _price_budget_sim(price_raw, budget_range)

    # 4. 产品新鲜度
    vec[3] = prod_feat.get("recency_score", 0.0)

    # 5. 需求新鲜度
    vec[4] = need_feat.get("recency_score", 0.0)

    # 6. 产品归一化价格
    vec[5] = prod_feat.get("price_norm", 0.0)

    # 7. 需求预算中点（归一化）
    budget_mid = need_feat.get("budget_mid", None)
    vec[6] = _normalize_budget_mid(budget_mid)

    # 8. feature_pipeline 综合相似度
    try:
        sim = fp.compute_similarity(prod_feat, need_feat)
        vec[7] = sim
    except Exception as e:
        logger.debug(f"feature_pipeline.compute_similarity 失败: {e}")
        vec[7] = 0.0

    # 9. 冷启动标记
    vec[8] = 1.0 if prod_feat.get("recency_score", 0) > 0.9 else 0.0
    vec[9] = 1.0 if need_feat.get("recency_score", 0) > 0.9 else 0.0

    return vec


def _jaccard_similarity(cat_a: dict[str, float], cat_b: dict[str, float]) -> float:
    """加权 Jaccard 相似度（与 feature_pipeline 保持一致）"""
    if not cat_a or not cat_b:
        return 0.0
    keys_a = set(cat_a.keys())
    keys_b = set(cat_b.keys())
    intersection = keys_a & keys_b
    union = keys_a | keys_b
    if not union:
        return 0.0
    inter_weight = sum(min(cat_a[k], cat_b[k]) for k in intersection)
    union_weight = sum(max(cat_a.get(k, 0.0), cat_b.get(k, 0.0)) for k in union)
    if union_weight == 0:
        return 0.0
    return float(inter_weight / union_weight)


def _text_sim(text_a: str, text_b: str) -> float:
    """封装 feature_pipeline 的文本相似度"""
    if not text_a.strip() or not text_b.strip():
        return 0.0
    try:
        return fp._text_similarity(text_a, text_b)
    except Exception:
        return 0.0


def _price_budget_sim(
    price_raw: float,
    budget_range: tuple[float, float] | None,
) -> float:
    """封装 feature_pipeline 的价格-预算匹配度"""
    try:
        return fp._price_budget_similarity(price_raw, budget_range)
    except Exception:
        return 0.0


def _normalize_budget_mid(budget_mid: float | None) -> float:
    """归一化预算中点到 [0, 1]

    用 log 压缩处理较大金额。
    """
    if budget_mid is None or budget_mid <= 0:
        return 0.0
    log_val = np.log1p(budget_mid)
    # 假设 1000 ~ 1e9 范围映射到 0~1
    norm = 1.0 / (1.0 + np.exp(-(log_val - 10.0) / 3.0))
    return round(float(norm), 4)


# ============================================================
# 规则评分计算（用于 ensemble 模式）
# ============================================================


def compute_rule_score_from_features(features: np.ndarray) -> float:
    """基于特征向量计算规则评分

    与 matching_engine.py 的 _calculate_match 逻辑保持一致。

    Args:
        features: shape=(NUM_FEATURES,) 特征向量

    Returns:
        float: [0, 1] 规则评分
    """
    CATEGORY_WEIGHT = 0.40
    KEYWORD_WEIGHT = 0.40
    PRICE_WEIGHT = 0.20
    COLD_START_BOOST = 1.2
    FEATURE_WEIGHT = 0.10

    category_sim = features[0]
    text_sim = features[1]
    price_budget_sim = features[2]
    feature_sim = features[7]
    is_cold_prod = features[8]
    is_cold_need = features[9]

    # 基础分数 [0, 1]
    total = CATEGORY_WEIGHT * float(category_sim) + KEYWORD_WEIGHT * float(text_sim) + PRICE_WEIGHT * float(price_budget_sim)

    # 冷启动加权
    if is_cold_prod > 0.5 or is_cold_need > 0.5:
        total *= COLD_START_BOOST
    total = min(total, 1.0)

    # 特征集成
    if feature_sim > 0.3:
        total = total * (1.0 - FEATURE_WEIGHT) + float(feature_sim) * FEATURE_WEIGHT

    return float(np.clip(total, 0.0, 1.0))


# ============================================================
# 训练数据管道
# ============================================================


def load_training_data(db_session) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """从 UserEvent 表读取用户行为，构造训练数据

    映射规则:
      - POSITIVE: click, like, adopt, view, recommend_like → label=1.0
      - NEGATIVE: skip, dislike, close, recommend_dislike → label=0.0

    Returns:
        (X, y, event_ids)
        X: 特征矩阵 shape=(N, NUM_FEATURES)
        y: 标签向量 shape=(N,)
        event_ids: 对应的事件 ID 列表，用于追溯
    """
    events = (
        db_session.query(UserEvent)
        .filter(
            UserEvent.event_type.in_(list(POSITIVE_EVENTS | NEGATIVE_EVENTS)),
            UserEvent.target_id.isnot(None),
            UserEvent.target_type == "product",
        )
        .order_by(UserEvent.created_at.desc())
        .limit(5000)
        .all()
    )

    X_list: list[np.ndarray] = []
    y_list: list[float] = []
    event_ids: list[int] = []

    for evt in events:
        # 尝试找到产品
        product = db_session.query(Product).filter(Product.id == evt.target_id).first()
        if not product:
            continue

        # 给每个事件匹配一个「最近的需求」作为配对
        recent_need = (
            db_session.query(BusinessNeed)
            .filter(
                BusinessNeed.user_id == evt.user_id,
                BusinessNeed.status == "open",
            )
            .order_by(BusinessNeed.created_at.desc())
            .first()
        )
        if not recent_need:
            recent_need = (
                db_session.query(BusinessNeed)
                .filter(BusinessNeed.status == "open")
                .order_by(BusinessNeed.created_at.desc())
                .first()
            )
        if not recent_need:
            continue

        # 提取特征
        try:
            prod_feat = fp.extract_product_features(product)
            need_feat = fp.extract_need_features(recent_need)
        except Exception as e:
            logger.debug(f"特征提取失败 (event={evt.id}): {e}")
            continue

        X_list.append(build_feature_vector(prod_feat, need_feat))
        y_list.append(1.0 if evt.event_type in POSITIVE_EVENTS else 0.0)
        event_ids.append(evt.id)

    if not X_list:
        logger.warning("load_training_data: 无有效训练数据")
        return np.empty((0, NUM_FEATURES)), np.empty(0), []

    X = np.vstack(X_list)
    y = np.array(y_list, dtype=np.float64)

    logger.info(
        "训练数据加载完成",
        extra={
            "samples": len(y),
            "positive": int(np.sum(y)),
            "negative": int(len(y) - np.sum(y)),
            "features": NUM_FEATURES,
        },
    )

    return X, y, event_ids


def load_augmented_data(path: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    """加载增强训练数据

    Args:
        path: 数据文件路径，默认使用 AUGMENTED_DATA_PATH

    Returns:
        (X, y)
    """
    path = path or AUGMENTED_DATA_PATH
    if not os.path.exists(path):
        logger.warning(f"增强数据文件不存在: {path}")
        return np.empty((0, NUM_FEATURES)), np.empty(0)

    data = np.load(path)
    X = data["X"].astype(np.float64)
    y = data["y"].astype(np.float64)
    logger.info(
        "增强训练数据已加载",
        extra={
            "path": path,
            "samples": len(y),
            "features": X.shape[1],
        },
    )
    return X, y


# ============================================================
# 评估工具
# ============================================================


def evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    top_k_values: list[int] | None = None,
) -> dict[str, Any]:
    """评估预测效果

    计算:
      - Precision/Recall/F1 at top-k
      - MSE, MAE
      - AUC (如果 sklearn 可用)

    Args:
        y_true: 真实标签
        y_pred: 预测分数 [0, 1]
        top_k_values: 要计算的 top-k 值列表

    Returns:
        评估指标字典
    """
    if top_k_values is None:
        top_k_values = TOP_K_VALUES

    metrics: dict[str, Any] = {}

    # 基础回归指标
    y_pred_clip = np.clip(y_pred, 0.0, 1.0)
    metrics["mse"] = float(np.mean((y_true - y_pred_clip) ** 2))
    metrics["mae"] = float(np.mean(np.abs(y_true - y_pred_clip)))
    metrics["n_samples"] = int(len(y_true))

    # 二值化 — 用中位数作为阈值
    threshold = float(np.median(y_pred_clip)) if len(y_pred_clip) > 0 else 0.5
    y_pred_binary = (y_pred_clip >= threshold).astype(int)
    y_true_int = y_true.astype(int)

    # 全局指标
    try:
        metrics["precision"] = round(float(precision_score(y_true_int, y_pred_binary, zero_division=0)), 4)
        metrics["recall"] = round(float(recall_score(y_true_int, y_pred_binary, zero_division=0)), 4)
        metrics["f1"] = round(float(f1_score(y_true_int, y_pred_binary, zero_division=0)), 4)
        metrics["threshold"] = round(threshold, 4)
    except Exception as e:
        logger.warning(f"全局指标计算失败: {e}")

    # Top-k 指标
    for k in top_k_values:
        if k > len(y_true):
            continue
        # 取预测分数最高的 k 个
        top_k_idx = np.argsort(y_pred_clip)[-k:]
        top_k_true = y_true[top_k_idx]
        hits = int(np.sum(top_k_true))
        metrics[f"top_{k}_hits"] = hits
        metrics[f"top_{k}_precision"] = round(hits / k, 4)
        metrics[f"top_{k}_recall"] = round(hits / max(np.sum(y_true), 1), 4)

    # AUC（如果可用）
    try:
        from sklearn.metrics import roc_auc_score

        metrics["auc"] = round(float(roc_auc_score(y_true, y_pred_clip)), 4)
    except Exception:
        pass

    return metrics


def cross_validate_model(
    model: Any,
    X: np.ndarray,
    y: np.ndarray,
    n_folds: int = 5,
) -> dict[str, Any]:
    """对模型进行 k-fold 交叉验证

    Args:
        model: 已初始化的模型实例（支持 .fit 和 .predict）
        X: 特征矩阵
        y: 标签向量
        n_folds: 折数

    Returns:
        交叉验证指标字典
    """
    if X.shape[0] < n_folds:
        logger.warning(f"样本数 ({X.shape[0]}) 少于折数 ({n_folds})，使用留一法")
        n_folds = max(2, X.shape[0])

    try:
        skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
        # 将连续标签转化为分层标签用于 CV
        y_discrete = (y >= np.median(y) if len(y) > 0 else y).astype(int)

        fold_metrics = []
        fold_idx = 0

        for train_idx, val_idx in skf.split(X, y_discrete):
            fold_idx += 1
            X_train, X_val = X[train_idx], X[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            # 训练时使用 StandardScaler
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_val_scaled = scaler.transform(X_val)

            # 克隆模型
            if _HAS_LGB:
                fold_model = lgb.LGBMRegressor(**LGB_PARAMS)
            else:
                fold_model = GradientBoostingRegressor(
                    n_estimators=100,
                    learning_rate=0.05,
                    max_depth=4,
                    min_samples_leaf=5,
                    subsample=0.8,
                    random_state=42,
                )

            fold_model.fit(X_train_scaled, y_train)
            y_pred = fold_model.predict(X_val_scaled)

            fold_eval = evaluate_predictions(y_val.numpy() if hasattr(y_val, 'numpy') else y_val, y_pred)
            fold_eval["fold"] = fold_idx
            fold_eval["train_samples"] = len(y_train)
            fold_eval["val_samples"] = len(y_val)
            fold_metrics.append(fold_eval)

        # 聚合指标
        cv_metrics: dict[str, Any] = {
            "n_folds": n_folds,
            "folds": fold_metrics,
        }

        # 对各折取平均
        for key in ["mse", "mae", "precision", "recall", "f1", "auc"]:
            values = [fm.get(key, float("nan")) for fm in fold_metrics if key in fm]
            valid_values = [v for v in values if not (isinstance(v, float) and (v != v))]
            if valid_values:
                cv_metrics[f"avg_{key}"] = round(float(np.mean(valid_values)), 4)
                cv_metrics[f"std_{key}"] = round(float(np.std(valid_values)), 4)

        logger.info(
            "交叉验证完成",
            extra={
                "n_folds": n_folds,
                "avg_mse": cv_metrics.get("avg_mse"),
                "avg_f1": cv_metrics.get("avg_f1"),
                "avg_precision": cv_metrics.get("avg_precision"),
                "avg_recall": cv_metrics.get("avg_recall"),
            },
        )

        return cv_metrics

    except Exception as e:
        logger.error(f"交叉验证失败: {e}")
        return {"n_folds": n_folds, "error": str(e)}


def extract_feature_importance(model: Any) -> list[dict[str, Any]]:
    """提取特征重要性

    Args:
        model: 已训练的模型 (LightGBM 或 sklearn GBDT)

    Returns:
        特征重要性列表，按重要性降序排列
    """
    if model is None:
        return []

    try:
        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
        else:
            return []

        n_features = min(len(importances), len(FEATURE_NAMES))
        importance_list = []
        for i in range(n_features):
            importance_list.append(
                {
                    "index": i,
                    "name": FEATURE_NAMES[i] if i < len(FEATURE_NAMES) else f"feature_{i}",
                    "importance": float(importances[i]),
                }
            )

        # 按重要性降序排列
        importance_list.sort(key=lambda x: x["importance"], reverse=True)

        # 计算相对重要性 (百分比)
        total = sum(item["importance"] for item in importance_list)
        if total > 0:
            for item in importance_list:
                item["relative_importance"] = round(item["importance"] / total * 100, 2)

        return importance_list

    except Exception as e:
        logger.warning(f"特征重要性提取失败: {e}")
        return []


# ============================================================
# 模型封装
# ============================================================


class MatchingModel:
    """LightGBM 匹配模型封装 (v2.0)

    提供 train / predict / partial_fit 统一接口。
    当 lightgbm 不可用时，自动降级为 sklearn GradientBoostingRegressor。
    """

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self._is_fitted = False
        self._feature_count = NUM_FEATURES
        self._feature_importance: list[dict[str, Any]] = []
        self._cv_results: dict[str, Any] = {}
        self._training_metrics: dict[str, Any] = {}

    # ---- 训练 ----

    def train(self, X: np.ndarray, y: np.ndarray, do_cv: bool = True) -> dict[str, Any]:
        """全量训练（含交叉验证和特征重要性）

        Args:
            X: 特征矩阵 shape=(N, NUM_FEATURES)
            y: 标签 shape=(N,) 取值 {0.0, 1.0}
            do_cv: 是否执行交叉验证

        Returns:
            训练指标字典
        """
        if X.shape[0] == 0:
            logger.warning("MatchingModel.train: 空数据集，跳过训练")
            return {"samples": 0}

        # 标准化
        X_scaled = self.scaler.fit_transform(X)

        # 训练
        if _HAS_LGB:
            self.model = lgb.LGBMRegressor(**LGB_PARAMS)
            backend = "lightgbm"
        else:
            logger.info("lightgbm 未安装，使用 sklearn GBDT 替代训练")
            self.model = GradientBoostingRegressor(
                n_estimators=100,
                learning_rate=0.05,
                max_depth=4,
                min_samples_leaf=5,
                subsample=0.8,
                random_state=42,
            )
            backend = "sklearn_gbdt"

        self.model.fit(X_scaled, y)

        # 预测自评估
        y_pred = self.model.predict(X_scaled)
        self._training_metrics = evaluate_predictions(y, y_pred)

        # 特征重要性
        self._feature_importance = extract_feature_importance(self.model)

        self._is_fitted = True
        self._feature_count = X.shape[1]

        # 交叉验证
        if do_cv and X.shape[0] >= 5:
            self._cv_results = cross_validate_model(self.model, X, y, n_folds=5)
        else:
            self._cv_results = {"n_folds": 0, "note": "skipped (样本数不足)"}

        # 持久化
        self._persist()

        # 记录日志
        log_extra = {
            "samples": len(y),
            "features": X.shape[1],
            "mse": self._training_metrics.get("mse"),
            "mae": self._training_metrics.get("mae"),
            "precision": self._training_metrics.get("precision"),
            "recall": self._training_metrics.get("recall"),
            "f1": self._training_metrics.get("f1"),
            "auc": self._training_metrics.get("auc"),
            "backend": backend,
            "cv_folds": self._cv_results.get("n_folds", 0),
        }

        if self._feature_importance:
            top_features = self._feature_importance[:3]
            log_extra["top_features"] = [f"{f['name']}({f['relative_importance']}%)" for f in top_features]

        if self._cv_results.get("avg_f1") is not None:
            log_extra["cv_avg_f1"] = self._cv_results["avg_f1"]
            log_extra["cv_avg_precision"] = self._cv_results.get("avg_precision")

        logger.info("模型训练完成", extra=log_extra)

        results = {
            "samples": int(len(y)),
            "positive": int(np.sum(y)),
            "negative": int(len(y) - np.sum(y)),
            "backend": backend,
            "training_metrics": self._training_metrics,
            "feature_importance": self._feature_importance,
            "cv_results": self._cv_results,
        }

        return results

    # ---- 预测 ----

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测匹配分数

        Args:
            X: 特征矩阵 shape=(N, NUM_FEATURES) 或 (NUM_FEATURES,)

        Returns:
            分数数组 shape=(N,)，取值 [0, 1]
        """
        if not self._is_fitted or self.model is None:
            logger.warning("MatchingModel.predict: 模型未训练，返回默认分数 0.5")
            n = X.shape[0] if X.ndim == 2 else 1
            return np.full(n, 0.5, dtype=np.float64)

        # 确保 2D
        if X.ndim == 1:
            X = X.reshape(1, -1)

        # 确保特征数匹配
        if X.shape[1] != self._feature_count:
            logger.warning(
                f"MatchingModel.predict: 特征数不匹配 (期望 {self._feature_count}, 收到 {X.shape[1]}), 截断/填充处理"
            )
            if X.shape[1] > self._feature_count:
                X = X[:, : self._feature_count]
            else:
                pad = np.zeros((X.shape[0], self._feature_count - X.shape[1]))
                X = np.hstack([X, pad])

        X_scaled = self.scaler.transform(X)
        scores = self.model.predict(X_scaled)
        return np.clip(scores, 0.0, 1.0).astype(np.float64)

    # ---- 增量学习 ----

    def partial_fit(self, X: np.ndarray, y: np.ndarray) -> dict[str, Any]:
        """增量学习（在线更新）

        策略:
          1. 如果模型尚未训练，调用 train()
          2. 如果已训练，结合原有数据做 warm-start 增量更新
          3. 按批次合并特征统计更新 scaler

        Args:
            X: 新样本特征矩阵
            y: 新样本标签

        Returns:
            更新后的指标
        """
        if X.shape[0] == 0:
            return {"updated": 0}

        if not self._is_fitted:
            return self.train(X, y)

        # 合并历史 + 新数据
        try:
            history_path = os.path.join(MODEL_DIR, "training_history.npz")
            if os.path.exists(history_path):
                hist = np.load(history_path)
                X_hist = hist["X"]
                y_hist = hist["y"]
                X_combined = np.vstack([X_hist, X])
                y_combined = np.concatenate([y_hist, y])
            else:
                X_combined = X
                y_combined = y

            # 保存合并后的历史
            os.makedirs(MODEL_DIR, exist_ok=True)
            np.savez_compressed(history_path, X=X_combined, y=y_combined)

            return self.train(X_combined, y_combined)

        except Exception as e:
            logger.error(f"MatchingModel.partial_fit 失败: {e}")
            return {"updated": 0, "error": str(e)}

    # ---- 持久化 ----

    def _persist(self) -> None:
        """保存模型、scaler 和元数据到磁盘"""
        try:
            os.makedirs(MODEL_DIR, exist_ok=True)
            with open(MODEL_PATH, "wb") as f:
                pickle.dump(self.model, f)
            with open(SCALER_PATH, "wb") as f:
                pickle.dump(self.scaler, f)

            # 保存元数据
            metadata = {
                "is_fitted": self._is_fitted,
                "feature_count": self._feature_count,
                "feature_names": FEATURE_NAMES,
                "training_metrics": self._training_metrics,
                "feature_importance": self._feature_importance,
                "cv_results": self._cv_results,
                "lgb_params": LGB_PARAMS,
                "has_lightgbm": _HAS_LGB,
            }
            with open(METADATA_PATH, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.warning(f"模型持久化失败: {e}")

    def load(self) -> bool:
        """从磁盘加载模型

        Returns:
            加载成功返回 True，否则 False
        """
        try:
            if os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH):
                with open(MODEL_PATH, "rb") as f:
                    self.model = pickle.load(f)
                with open(SCALER_PATH, "rb") as f:
                    self.scaler = pickle.load(f)
                self._is_fitted = True
                self._feature_count = getattr(self.model, "n_features_in_", NUM_FEATURES)

                # 加载元数据（如果存在）
                if os.path.exists(METADATA_PATH):
                    try:
                        with open(METADATA_PATH, "r", encoding="utf-8") as f:
                            metadata = json.load(f)
                        self._feature_importance = metadata.get("feature_importance", [])
                        self._cv_results = metadata.get("cv_results", {})
                        self._training_metrics = metadata.get("training_metrics", {})
                    except Exception:
                        pass

                logger.info("模型加载成功", extra={"path": MODEL_PATH})
                return True
        except Exception as e:
            logger.warning(f"模型加载失败: {e}")
        return False

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    @property
    def feature_count(self) -> int:
        return self._feature_count

    @property
    def feature_importance(self) -> list[dict[str, Any]]:
        return self._feature_importance

    @property
    def cv_results(self) -> dict[str, Any]:
        return self._cv_results

    @property
    def training_metrics(self) -> dict[str, Any]:
        return self._training_metrics


# ============================================================
# 模块级单例
# ============================================================

_model_instance: MatchingModel | None = None


def get_model() -> MatchingModel:
    """获取匹配模型单例

    自动从磁盘加载已保存的模型。
    """
    global _model_instance
    if _model_instance is None:
        _model_instance = MatchingModel()
        _model_instance.load()
    return _model_instance


def reset_model() -> None:
    """重置模型单例（用于测试）"""
    global _model_instance
    _model_instance = None


# ============================================================
# 便捷函数（含 A/B 模式支持）
# ============================================================


def predict_match_score(
    prod_feat: dict[str, Any],
    need_feat: dict[str, Any],
    mode: str | None = None,
) -> float:
    """便捷函数：对单个 (产品, 需求) 特征对预测匹配分数

    支持三种模式:
      - 'ml': 纯 ML 模型预测
      - 'rule': 纯规则评分
      - 'ensemble': 0.6*ML + 0.4*Rule 混合评分
      - None: 使用 DEFAULT_MODE (环境变量 LIANKEBAO_ML_MODE)

    Args:
        prod_feat: extract_product_features() 的输出
        need_feat: extract_need_features() 的输出
        mode: 评分模式 (ml|rule|ensemble)

    Returns:
        float: [0, 1] 匹配分数
    """
    if mode is None:
        mode = DEFAULT_MODE

    vec = build_feature_vector(prod_feat, need_feat)

    # 规则评分
    rule_score = compute_rule_score_from_features(vec)

    if mode == "rule":
        return rule_score

    # ML 评分
    model = get_model()
    if model.is_fitted:
        ml_score = float(model.predict(vec.reshape(1, -1))[0])
    else:
        logger.warning("ML 模型未训练，使用规则评分作为 fallback")
        ml_score = rule_score

    if mode == "ml":
        return ml_score

    if mode == "ensemble":
        return float(np.clip(
            ENSEMBLE_ML_WEIGHT * ml_score + ENSEMBLE_RULE_WEIGHT * rule_score,
            0.0,
            1.0,
        ))

    # 未知模式，默认返回 ML 评分
    logger.warning(f"未知评分模式 '{mode}'，使用 ML 评分")
    return ml_score


def retrain_from_augmented_data(do_cv: bool = True) -> dict[str, Any]:
    """从增强训练数据重新训练模型

    自动加载 augmented 数据，训练模型并保存。

    Returns:
        训练结果字典
    """
    X, y = load_augmented_data()
    if X.shape[0] == 0:
        logger.error("无可用的增强训练数据，请先运行 training_data_generator.py")
        return {"error": "no augmented data available"}

    model = get_model()
    results = model.train(X, y, do_cv=do_cv)
    return results


# ============================================================
# 独立测试入口
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    logger.info("=" * 60)
    logger.info("MatchingModel v2.0 P1 升级测试")
    logger.info("=" * 60)
    logger.info(f"LightGBM 可用: {_HAS_LGB}")
    logger.info(f"USE_ML_MODEL: {USE_ML_MODEL}")
    logger.info(f"默认模式: {DEFAULT_MODE}")
    logger.info(f"特征数量: {NUM_FEATURES}")
    logger.info(f"特征名称: {FEATURE_NAMES}")

    # 1. 加载增强数据
    logger.info("\n[1] 加载增强训练数据...")
    X_aug, y_aug = load_augmented_data()
    logger.info(f"  增强数据: {len(y_aug)} 样本, {X_aug.shape[1]} 特征")

    # 2. 构造假数据测试特征向量
    logger.info("\n[2] 测试特征向量构建...")
    dummy_prod_feat = {
        "category_vector": {"大健康": 1.0},
        "keywords": ["保健品", "健康"],
        "text_corpus": "优质保健品 健康食品 大健康",
        "price_norm": 0.65,
        "price_raw": 299.0,
        "recency_score": 0.95,
    }
    dummy_need_feat = {
        "category_vector": {"大健康": 1.0},
        "keywords": ["健康", "养生"],
        "text_corpus": "寻找健康保健品供应商 大健康",
        "budget_range": (10000, 50000),
        "budget_mid": 30000.0,
        "recency_score": 0.85,
    }

    vec = build_feature_vector(dummy_prod_feat, dummy_need_feat)
    logger.info(f"  特征向量: {vec}")
    assert len(vec) == NUM_FEATURES, f"特征维度错误: {len(vec)} ≠ {NUM_FEATURES}"
    logger.info("  特征向量构建 ✓")

    # 3. 使用增强数据训练
    logger.info(f"\n[3] 训练模型 ({len(y_aug)} 样本, 5-fold CV)...")
    model = MatchingModel()
    results = model.train(X_aug, y_aug, do_cv=True)
    logger.info(f"  训练指标: {json.dumps(results.get('training_metrics', {}), ensure_ascii=False)}")

    # 4. 特征重要性
    logger.info("\n[4] 特征重要性:")
    for fi in results.get("feature_importance", []):
        logger.info(f"  [{fi['index']:2d}] {fi['name']:<20s} {fi.get('relative_importance', fi['importance']):>6.2f}%")

    # 5. 交叉验证结果
    cv = results.get("cv_results", {})
    logger.info(f"\n[5] 交叉验证 ({cv.get('n_folds', 0)}-fold):")
    for key in ["avg_mse", "avg_f1", "avg_precision", "avg_recall", "std_mse", "std_f1"]:
        if key in cv:
            logger.info(f"  {key}: {cv[key]}")

    # 6. 测试预测（三种模式）
    logger.info("\n[6] 测试预测（三种模式）:")
    ml_score = predict_match_score(dummy_prod_feat, dummy_need_feat, mode="ml")
    rule_score = predict_match_score(dummy_prod_feat, dummy_need_feat, mode="rule")
    ensemble_score = predict_match_score(dummy_prod_feat, dummy_need_feat, mode="ensemble")
    logger.info(f"  ML 评分:      {ml_score:.4f}")
    logger.info(f"  规则评分:     {rule_score:.4f}")
    logger.info(f"  Ensemble 评分: {ensemble_score:.4f}")
    assert 0.0 <= ml_score <= 1.0, f"ML 评分越界: {ml_score}"
    assert 0.0 <= rule_score <= 1.0, f"规则评分越界: {rule_score}"
    assert 0.0 <= ensemble_score <= 1.0, f"Ensemble 评分越界: {ensemble_score}"

    # 7. 测试 persist + load
    logger.info("\n[7] 测试持久化...")
    model._persist()
    model2 = MatchingModel()
    loaded = model2.load()
    logger.info(f"  模型加载: {'成功' if loaded else '失败'}")
    if loaded:
        pred2 = model2.predict(vec.reshape(1, -1))
        logger.info(f"  加载后预测: {pred2[0]:.4f}")
        logger.info(f"  特征重要性: {model2.feature_importance[:3]}")
        logger.info(f"  CV 结果: {model2.cv_results.get('avg_f1', 'N/A')}")

    # 8. 测试增量学习
    logger.info("\n[8] 测试增量学习...")
    X_new = np.random.rand(10, NUM_FEATURES).astype(np.float64)
    y_new = np.random.randint(0, 2, size=10).astype(np.float64)
    up_metrics = model.partial_fit(X_new, y_new)
    logger.info(f"  增量更新: {up_metrics.get('samples', up_metrics.get('updated', 0))} 样本")

    # 9. 规则评分函数测试
    logger.info("\n[9] 规则评分函数测试...")
    rule_sc = compute_rule_score_from_features(vec)
    logger.info(f"  规则评分 (直接调用): {rule_sc:.4f}")

    logger.info("\n" + "=" * 60)
    logger.info("P1 升级测试完成 ✓")
    logger.info("=" * 60)
