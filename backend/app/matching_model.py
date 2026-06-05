"""
链客宝 LightGBM 匹配模型
========================
可学习的匹配模型，替代规则权重。

设计原则:
  1. 轻量 — 无外部服务依赖，单文件可运行
  2. 增量学习 — partial_fit 支持在线更新
  3. 与 feature_pipeline 特征输出兼容
  4. 不影响现有规则引擎（USE_ML_MODEL=False 时无入侵）

架构:
  - build_feature_vector(prod_feat, need_feat) → np.ndarray
  - train(data_loader)          → 全量训练
  - predict(features)           → 返回 [0,1] 匹配分数
  - partial_fit(features, labels) → 增量更新
  - load_training_data(db)      → 从 UserEvent 读取标注数据
"""

import logging
import os
import pickle
import time
from pathlib import Path
from typing import Any

import numpy as np

# lightgbm 为可选依赖，未安装时降级为 sklearn GBDT
try:
    import lightgbm as lgb

    _HAS_LGB = True
except ImportError:
    _HAS_LGB = False

from sklearn.ensemble import GradientBoostingRegressor
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

# 正负样本映射
POSITIVE_EVENTS = {"click", "like", "adopt", "view", "recommend_like"}
NEGATIVE_EVENTS = {"skip", "dislike", "close", "recommend_dislike"}

# ============================================================
# 特征工程
# ============================================================

FEATURE_NAMES = [
    "category_sim",  # 类目 Jaccard 相似度
    "text_sim",  # TF-IDF 余弦相似度
    "price_budget_sim",  # 价格-预算匹配度
    "recency_prod",  # 产品新鲜度
    "recency_need",  # 需求新鲜度
    "price_norm",  # 产品归一化价格
    "budget_mid_norm",  # 需求预算中点（归一化）
    "feature_sim",  # feature_pipeline 综合相似度
    "is_cold_prod",  # 产品是否为冷启动新品 (0/1)
    "is_cold_need",  # 需求是否为冷启动新需求 (0/1)
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
        product = (
            db_session.query(Product)
            .filter(Product.id == evt.target_id)
            .first()
        )
        if not product:
            continue

        # 给每个事件匹配一个「最近的需求」作为配对
        # 实际上事件本身没有记录"对应哪个需求"，所以这里用该用户最近浏览的需求
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
            # 如果没有该用户的需求，用任意一个 open 需求
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


# ============================================================
# 模型封装
# ============================================================


class MatchingModel:
    """LightGBM 匹配模型封装

    提供 train / predict / partial_fit 统一接口。
    当 lightgbm 不可用时，自动降级为 sklearn GradientBoostingRegressor。
    """

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self._is_fitted = False
        self._feature_count = NUM_FEATURES

    # ---- 训练 ----

    def train(self, X: np.ndarray, y: np.ndarray) -> dict[str, Any]:
        """全量训练

        Args:
            X: 特征矩阵 shape=(N, NUM_FEATURES)
            y: 标签 shape=(N,) 取值 {0.0, 1.0}

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

        self.model.fit(X_scaled, y)

        # 预测自评估
        y_pred = self.model.predict(X_scaled)
        y_pred_clip = np.clip(y_pred, 0.0, 1.0)
        mse = float(np.mean((y - y_pred_clip) ** 2))
        mae = float(np.mean(np.abs(y - y_pred_clip)))

        self._is_fitted = True
        self._feature_count = X.shape[1]

        # 持久化
        self._persist()

        logger.info(
            "模型训练完成",
            extra={
                "samples": len(y),
                "features": X.shape[1],
                "mse": round(mse, 4),
                "mae": round(mae, 4),
                "backend": "lightgbm" if _HAS_LGB else "sklearn_gbdt",
            },
        )

        return {
            "samples": int(len(y)),
            "positive": int(np.sum(y)),
            "negative": int(len(y) - np.sum(y)),
            "mse": round(mse, 4),
            "mae": round(mae, 4),
        }

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
                f"MatchingModel.predict: 特征数不匹配 "
                f"(期望 {self._feature_count}, 收到 {X.shape[1]}), "
                f"截断/填充处理"
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

        # 合并历史 + 新数据（保留历史样本的标记）
        # 重新训练而非真正增量，保证质量（数据量不大时适用）
        # 实际生产环境可用 lightgbm 的 train(init_model=...) 做增量
        try:
            # 从持久化路径取出历史数据（如果存在）
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
        """保存模型和 scaler 到磁盘"""
        try:
            os.makedirs(MODEL_DIR, exist_ok=True)
            with open(MODEL_PATH, "wb") as f:
                pickle.dump(self.model, f)
            with open(SCALER_PATH, "wb") as f:
                pickle.dump(self.scaler, f)
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
# 便捷函数
# ============================================================


def predict_match_score(
    prod_feat: dict[str, Any],
    need_feat: dict[str, Any],
) -> float:
    """便捷函数：对单个 (产品, 需求) 特征对预测匹配分数

    Args:
        prod_feat: extract_product_features() 的输出
        need_feat: extract_need_features() 的输出

    Returns:
        float: [0, 1] 匹配分数
    """
    vec = build_feature_vector(prod_feat, need_feat)
    model = get_model()
    score = model.predict(vec.reshape(1, -1))
    return float(score[0])


# ============================================================
# 独立测试入口
# ============================================================

if __name__ == "__main__":
    # 无数据库依赖的冒烟测试
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    logger.info("运行 MatchingModel 冒烟测试...")
    logger.info(f"LightGBM 可用: {_HAS_LGB}")
    logger.info(f"USE_ML_MODEL: {USE_ML_MODEL}")
    logger.info(f"特征数量: {NUM_FEATURES}")
    logger.info(f"特征名称: {FEATURE_NAMES}")

    # 1. 构造假数据测试特征向量
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
    logger.info(f"特征向量: {vec}")
    logger.info(f"期望维度: {NUM_FEATURES}, 实际: {len(vec)}")
    assert len(vec) == NUM_FEATURES, f"特征维度错误: {len(vec)} ≠ {NUM_FEATURES}"

    # 2. 测试训练 + 预测
    model = MatchingModel()
    # 构造假训练数据
    X_fake = np.random.rand(50, NUM_FEATURES).astype(np.float64)
    y_fake = np.random.randint(0, 2, size=50).astype(np.float64)
    metrics = model.train(X_fake, y_fake)
    logger.info(f"训练指标: {metrics}")

    pred = model.predict(vec.reshape(1, -1))
    logger.info(f"预测分数: {pred[0]:.4f}")
    assert 0.0 <= pred[0] <= 1.0, f"预测分数越界: {pred[0]}"

    # 3. 测试 partial_fit
    X_new = np.random.rand(10, NUM_FEATURES).astype(np.float64)
    y_new = np.random.randint(0, 2, size=10).astype(np.float64)
    up_metrics = model.partial_fit(X_new, y_new)
    logger.info(f"增量更新指标: {up_metrics}")

    # 4. 测试持久化
    model._persist()
    model2 = MatchingModel()
    loaded = model2.load()
    logger.info(f"模型加载: {'成功' if loaded else '失败'}")

    if loaded:
        pred2 = model2.predict(vec.reshape(1, -1))
        logger.info(f"加载后预测: {pred2[0]:.4f}")

    # 5. 便捷函数测试
    score = predict_match_score(dummy_prod_feat, dummy_need_feat)
    logger.info(f"便捷函数预测: {score:.4f}")

    # 清理测试文件
    for p in [MODEL_PATH, SCALER_PATH]:
        if os.path.exists(p):
            os.remove(p)
            logger.info(f"已清理: {p}")

    logger.info("冒烟测试通过 ✓")
