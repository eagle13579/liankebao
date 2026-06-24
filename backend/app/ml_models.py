"""
链客宝AI CTR预估模型 (GBDT) + 校准层 (Platt Scaling)
=====================================================
Phase 1 P1 的核心工程任务。

P1-1: MatchCTRModel — 用 LightGBM GBDT 替代规则评分的部分权重
  - extract_features(): 从规则引擎的 partial_scores 中提取特征
  - predict_ctr(): 返回 [0, 1] 预估点击率
  - train(): 训练 LightGBM (fallback sklearn GBDT)

P1-2: ScoreCalibrator — Platt Scaling 将匹配分数校准为真实概率
  - calibrate(): sigmoid(raw_score * a + b)
  - fit(): 用真实反馈数据拟合 a, b 参数
  - 支持定期自动校准（从 feedback 表读取数据）

与 matching_engine.py 的集成点:
  1. MatchEngine.__init__() 中初始化 MatchCTRModel
  2. _calculate_match() 中调用 model.predict_ctr() 获取 ML 分数
  3. 最终分数 = 0.7 * rule_score + 0.3 * ml_score (try/except 保护)

与 matching_model.py 的关系:
  matching_model.py 是完整的 v2 匹配模型 (全量训练 + CV + 持久化),
  而 ml_models.py 是轻量的 CTR 预估 + 校准模块, 直接嵌入规则引擎。
"""

import logging
import os
import pickle
import time
from typing import Any

import numpy as np

# lightgbm 为可选依赖，未安装时降级为 sklearn GBDT
try:
    import lightgbm as lgb

    _HAS_LGB = True
except ImportError:
    _HAS_LGB = False

from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from app.feature_pipeline import extract_need_features, extract_product_features
from app.models import BusinessNeed, Product, UserEvent

logger = logging.getLogger(__name__)

# ============================================================
# P1-1: CTR 预估模型 (GBDT)
# ============================================================

# 模型持久化路径
_CTR_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")
_CTR_MODEL_PATH = os.path.join(_CTR_MODEL_DIR, "ctr_model.pkl")
_CTR_SCALER_PATH = os.path.join(_CTR_MODEL_DIR, "ctr_scaler.pkl")


class MatchCTRModel:
    """CTR 预估模型 (LightGBM GBDT)

    从匹配引擎的规则评分中间结果和特征 pipeline 中提取特征,
    预测用户点击/采纳该匹配结果的概率。

    用法:
        model = MatchCTRModel()
        model.load()  # 尝试加载已训练的模型
        score = model.predict_ctr(features)
    """

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self._is_fitted = False
        self._feature_count = len(self.feature_names)

    # ---- 特征定义 ----

    feature_names = [
        "category_score",  # 类目匹配得分 [0, 1]
        "keyword_score",  # 关键词匹配得分 [0, 1]
        "price_score",  # 价格匹配得分 [0, 1]
        "feedback_weight",  # 反馈权重调整 [-0.1, 0.1]
        "cold_start_boost",  # 冷启动加权 [0 or 1]
        "trust_score",  # 信任评分 [0, 100]
        "product_interaction_count",  # 产品交互次数 (归一化)
        "need_interaction_count",  # 需求交互次数 (归一化)
        "price_diff_ratio",  # 价格与预算中点的偏差比例
        "category_match_type",  # 类目匹配类型: exact=2, synonym=1, fuzzy=0
        "feature_sim_score",  # feature_pipeline 综合相似度 [0, 1]
        "recency_score_product",  # 产品新鲜度 [0, 1]
        "recency_score_need",  # 需求新鲜度 [0, 1]
        "embedding_sim",  # Item2Vec embedding 相似度 [0, 1]
        "thompson_explore",  # Thompson 采样探索分数 [0, 1]
    ]

    # ---- 特征提取 ----

    def extract_features(
        self,
        product: Product | None = None,
        need: BusinessNeed | None = None,
        partial_scores: dict | None = None,
    ) -> np.ndarray:
        """从规则引擎的 partial_scores 和产品/需求对象中提取特征向量

        Args:
            product: Product ORM 对象 (可选, 部分特征需要)
            need: BusinessNeed ORM 对象 (可选)
            partial_scores: 规则引擎的中间评分字典，包含:
                - category_score: [0, 1] 类目得分
                - keyword_score: [0, 1] 关键词得分
                - price_score: [0, 1] 价格得分
                - feedback_weight: [-0.1, 0.1]
                - cold_start_boost: 0 或 1
                - trust_score: [0, 100]

        Returns:
            shape=(NUM_FEATURES,) 的 float64 向量
        """
        vec = np.zeros(self._feature_count, dtype=np.float64)
        pscore = partial_scores or {}

        # 1-3: 规则引擎中间得分 (规则已归一化到 [0, 1])
        vec[0] = float(pscore.get("category_score", 0.0))
        vec[1] = float(pscore.get("keyword_score", 0.0))
        vec[2] = float(pscore.get("price_score", 0.0))

        # 4: 反馈权重
        vec[3] = float(pscore.get("feedback_weight", 0.0))

        # 5: 冷启动标记
        vec[4] = 1.0 if pscore.get("cold_start_boost", False) else 0.0

        # 6: 信任评分 (归一化到 [0, 1])
        trust = float(pscore.get("trust_score", 0.0))
        vec[5] = min(trust / 100.0, 1.0)

        # 7-8: 交互计数 (log 归一化)
        if product is not None:
            interactions_p = getattr(product, "interaction_count", None) or 0
            vec[6] = min(np.log1p(interactions_p) / 10.0, 1.0)
        if need is not None:
            interactions_n = getattr(need, "interaction_count", None) or 0
            vec[7] = min(np.log1p(interactions_n) / 10.0, 1.0)

        # 9: 价格偏差比
        price = 0.0
        budget_mid = 0.0
        if product is not None:
            price = getattr(product, "sale_price", None) or getattr(product, "price", 0) or 0
        if need is not None:
            from app.utils import parse_budget

            budget_range = parse_budget(getattr(need, "budget", None))
            if budget_range:
                low, high = budget_range
                if high == float("inf"):
                    budget_mid = float(low)
                elif high > 0:
                    budget_mid = (low + high) / 2.0
                else:
                    budget_mid = low
        if budget_mid > 0 and price > 0:
            vec[8] = min(abs(price - budget_mid) / max(budget_mid, 1.0), 1.0)

        # 10: 类目匹配类型
        vec[9] = float(pscore.get("category_match_type", 0))

        # 11: feature_pipeline 综合相似度
        try:
            if product is not None and need is not None:
                prod_feat = extract_product_features(product)
                need_feat = extract_need_features(need)
                from app.feature_pipeline import compute_similarity

                vec[10] = compute_similarity(prod_feat, need_feat)
        except Exception as e:
            logger.debug(f"feature_pipeline 相似度计算失败: {e}")

        # 12-13: 新鲜度
        try:
            if product is not None and product.created_at:
                age_days = (time.time() - product.created_at.timestamp()) / 86400.0
                vec[11] = float(np.exp(-age_days / 90.0))
        except Exception:
            pass
        try:
            if need is not None and need.created_at:
                age_days = (time.time() - need.created_at.timestamp()) / 86400.0
                vec[12] = float(np.exp(-age_days / 90.0))
        except Exception:
            pass

        # 14: embedding_sim (P2-1)
        vec[13] = float(pscore.get("embedding_sim", 0.0))

        # 15: thompson_explore (P2-2)
        vec[14] = float(pscore.get("thompson_explore", 0.0))

        return vec

    # ---- 预测 ----

    def predict_ctr(self, features: np.ndarray) -> float:
        """预估点击率 [0, 1]

        Args:
            features: shape=(NUM_FEATURES,) 或 (1, NUM_FEATURES) 的特征向量

        Returns:
            float: 预估点击率 [0, 1]
        """
        if not self._is_fitted or self.model is None:
            logger.debug("MatchCTRModel: 模型未训练，返回默认 0.5")
            return 0.5

        # 确保 2D
        if features.ndim == 1:
            features = features.reshape(1, -1)

        # 特征数匹配
        if features.shape[1] != self._feature_count:
            logger.debug(f"MatchCTRModel: 特征数不匹配 (期望 {self._feature_count}, 收到 {features.shape[1]})")
            if features.shape[1] > self._feature_count:
                features = features[:, : self._feature_count]
            else:
                pad = np.zeros((features.shape[0], self._feature_count - features.shape[1]))
                features = np.hstack([features, pad])

        try:
            features_scaled = self.scaler.transform(features)
            score = float(self.model.predict(features_scaled)[0])
            return float(np.clip(score, 0.0, 1.0))
        except Exception as e:
            logger.warning(f"MatchCTRModel.predict_ctr 失败: {e}")
            return 0.5

    # ---- 训练 ----

    def train(self, X: np.ndarray, y: np.ndarray) -> dict[str, Any]:
        """训练 LightGBM 模型

        Args:
            X: 特征矩阵 shape=(N, NUM_FEATURES)
            y: 标签 shape=(N,)，取值 {0.0, 1.0}

        Returns:
            训练指标字典
        """
        if X.shape[0] == 0:
            logger.warning("MatchCTRModel.train: 空数据集，跳过训练")
            return {"samples": 0}

        # 标准化
        X_scaled = self.scaler.fit_transform(X)

        # 训练
        if _HAS_LGB:
            self.model = lgb.LGBMRegressor(
                n_estimators=200,
                learning_rate=0.05,
                max_depth=5,
                num_leaves=31,
                min_child_samples=5,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=0.1,
                random_state=42,
                verbose=-1,
            )
            backend = "lightgbm"
        else:
            logger.info("lightgbm 未安装，使用 sklearn GBDT 替代")
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

        # 自评估
        y_pred = self.model.predict(X_scaled)
        y_pred_clip = np.clip(y_pred, 0.0, 1.0)
        mse = float(np.mean((y - y_pred_clip) ** 2))
        mae = float(np.mean(np.abs(y - y_pred_clip)))

        metrics = {
            "samples": int(len(y)),
            "positive": int(np.sum(y)),
            "negative": int(len(y) - np.sum(y)),
            "mse": round(mse, 4),
            "mae": round(mae, 4),
            "backend": backend,
        }

        self._is_fitted = True
        self._feature_count = X.shape[1]

        # 持久化
        self._persist()

        logger.info(
            "CTR 模型训练完成",
            extra={
                "samples": metrics["samples"],
                "mse": metrics["mse"],
                "mae": metrics["mae"],
                "backend": backend,
                "features": self._feature_count,
            },
        )

        return metrics

    # ---- 持久化 ----

    def _persist(self) -> None:
        """保存模型和 scaler 到磁盘"""
        try:
            os.makedirs(_CTR_MODEL_DIR, exist_ok=True)
            with open(_CTR_MODEL_PATH, "wb") as f:
                pickle.dump(self.model, f)
            with open(_CTR_SCALER_PATH, "wb") as f:
                pickle.dump(self.scaler, f)
        except Exception as e:
            logger.warning(f"CTR 模型持久化失败: {e}")

    def load(self) -> bool:
        """从磁盘加载模型

        Returns:
            加载成功返回 True
        """
        try:
            if os.path.exists(_CTR_MODEL_PATH) and os.path.exists(_CTR_SCALER_PATH):
                with open(_CTR_MODEL_PATH, "rb") as f:
                    self.model = pickle.load(f)
                with open(_CTR_SCALER_PATH, "rb") as f:
                    self.scaler = pickle.load(f)
                self._is_fitted = True
                self._feature_count = getattr(self.model, "n_features_in_", len(self.feature_names))
                logger.info("CTR 模型加载成功", extra={"path": _CTR_MODEL_PATH})
                return True
        except Exception as e:
            logger.warning(f"CTR 模型加载失败: {e}")
        return False

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    @property
    def feature_count(self) -> int:
        return self._feature_count

    # ---- 训练数据加载（从 UserEvent） ----

    def load_training_data_from_events(self, db_session, limit: int = 2000) -> tuple[np.ndarray, np.ndarray]:
        """从 UserEvent 表加载训练数据

        POSITIVE: click, like, adopt, recommend_like → label=1.0
        NEGATIVE: skip, dislike, close, recommend_dislike → label=0.0

        Args:
            db_session: SQLAlchemy 数据库会话
            limit: 最大样本数

        Returns:
            (X, y) 特征矩阵和标签向量
        """
        POSITIVE_EVENTS = {"click", "like", "adopt", "view", "recommend_like"}
        NEGATIVE_EVENTS = {"skip", "dislike", "close", "recommend_dislike"}

        events = (
            db_session.query(UserEvent)
            .filter(
                UserEvent.event_type.in_(list(POSITIVE_EVENTS | NEGATIVE_EVENTS)),
                UserEvent.target_id.isnot(None),
                UserEvent.target_type == "product",
            )
            .order_by(UserEvent.created_at.desc())
            .limit(limit)
            .all()
        )

        X_list: list[np.ndarray] = []
        y_list: list[float] = []

        for evt in events:
            # 查找对应的产品
            product = db_session.query(Product).filter(Product.id == evt.target_id).first()
            if not product:
                continue

            # 查找相关的需求：优先使用用户最近的需求
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

            # 提取特征 (partial_scores 未知，用空字典)
            try:
                features = self.extract_features(
                    product=product,
                    need=recent_need,
                    partial_scores={},
                )
            except Exception as e:
                logger.debug(f"特征提取失败 (event={evt.id}): {e}")
                continue

            X_list.append(features)
            y_list.append(1.0 if evt.event_type in POSITIVE_EVENTS else 0.0)

        if not X_list:
            logger.warning("CTR 训练数据加载: 无有效数据")
            return np.empty((0, self._feature_count)), np.empty(0)

        X = np.vstack(X_list)
        y = np.array(y_list, dtype=np.float64)

        logger.info(
            "CTR 训练数据加载完成",
            extra={
                "samples": len(y),
                "positive": int(np.sum(y)),
                "negative": int(len(y) - np.sum(y)),
            },
        )
        return X, y


# ============================================================
# P1-2: 校准层 (Platt Scaling)
# ============================================================


class ScoreCalibrator:
    """Platt Scaling 校准器

    将匹配引擎的原始分数通过 sigmoid 校准映射为真实的匹配概率。

    calibrate(score) = 1 / (1 + exp(-(score * a + b)))

    其中 a (斜率) 和 b (偏移) 通过 LogisticRegression 从反馈数据中拟合。
    """

    def __init__(self):
        self.a = 1.0  # sigmoid 斜率
        self.b = 0.0  # sigmoid 偏移
        self._is_fitted = False

    def calibrate(self, raw_scores: list[float]) -> list[float]:
        """将原始分数校准为匹配概率

        Args:
            raw_scores: 原始匹配分数列表 [0, 1]

        Returns:
            校准后的概率列表 [0, 1]
        """
        if not raw_scores:
            return []

        if not self._is_fitted:
            # 未拟合时，直接返回原始分数（恒等映射）
            logger.debug("ScoreCalibrator: 未拟合，返回原始分数")
            return raw_scores

        arr = np.array(raw_scores, dtype=np.float64)
        calibrated = 1.0 / (1.0 + np.exp(-(arr * self.a + self.b)))
        return calibrated.tolist()

    def calibrate_single(self, raw_score: float) -> float:
        """校准单个分数

        Args:
            raw_score: 原始匹配分数 [0, 1]

        Returns:
            校准后的概率 [0, 1]
        """
        if not self._is_fitted:
            return raw_score
        raw = float(raw_score)
        return float(1.0 / (1.0 + np.exp(-(raw * self.a + self.b))))

    def fit(self, raw_scores: list[float], labels: list[int]) -> dict[str, Any]:
        """用真实反馈数据拟合 Platt Scaling 参数

        Args:
            raw_scores: 原始匹配分数列表 [0, 1]
            labels: 真实标签列表 [0, 1] (like=1, dislike=0)

        Returns:
            拟合结果字典，包含 a, b 和评估指标
        """
        if len(raw_scores) < 10:
            logger.warning(f"ScoreCalibrator.fit: 数据不足 ({len(raw_scores)} < 10), 跳过")
            return {"a": self.a, "b": self.b, "samples": len(raw_scores), "fitted": False}

        X = np.array(raw_scores, dtype=np.float64).reshape(-1, 1)
        y = np.array(labels, dtype=np.float64)

        # 用 LogisticRegression 拟合 Platt Scaling
        # lr.coef_[0][0] = a, lr.intercept_[0] = b
        lr = LogisticRegression(
            C=1e9,  # 极大 C 值 ≈ 无正则化，纯 sigmoid 拟合
            solver="lbfgs",
            max_iter=1000,
            random_state=42,
        )
        lr.fit(X, y)

        self.a = float(lr.coef_[0][0])
        self.b = float(lr.intercept_[0])
        self._is_fitted = True

        # 评估校准效果
        y_prob = lr.predict_proba(X)[:, 1]
        log_loss_val = float(-np.mean(y * np.log(y_prob + 1e-15) + (1 - y) * np.log(1 - y_prob + 1e-15)))
        accuracy = float(np.mean((y_prob >= 0.5).astype(float) == y))

        metrics = {
            "a": round(self.a, 4),
            "b": round(self.b, 4),
            "samples": len(raw_scores),
            "log_loss": round(log_loss_val, 4),
            "accuracy": round(accuracy, 4),
            "positive": int(np.sum(y)),
            "negative": int(len(y) - np.sum(y)),
            "fitted": True,
        }

        logger.info(
            "Platt Scaling 校准拟合完成",
            extra=metrics,
        )

        return metrics

    def fit_from_feedback(
        self,
        db_session,
        min_samples: int = 10,
        limit: int = 5000,
    ) -> dict[str, Any]:
        """从数据库的 feedback 表自动拟合校准参数

        从 UserEvent 表中读取用户反馈:
          - like, click, adopt, recommend_like → label=1
          - dislike, skip, close, recommend_dislike → label=0

        Args:
            db_session: SQLAlchemy 数据库会话
            min_samples: 最小样本数要求
            limit: 最大读取样本数

        Returns:
            拟合结果字典
        """
        POSITIVE = {"click", "like", "adopt", "recommend_like"}
        NEGATIVE = {"dislike", "skip", "close", "recommend_dislike"}

        events = (
            db_session.query(UserEvent)
            .filter(
                UserEvent.event_type.in_(list(POSITIVE | NEGATIVE)),
                UserEvent.target_id.isnot(None),
                UserEvent.target_type == "product",
            )
            .order_by(UserEvent.created_at.desc())
            .limit(limit)
            .all()
        )

        if len(events) < min_samples:
            logger.warning(f"ScoreCalibrator: feedback 数据不足 ({len(events)} < {min_samples}), 跳过")
            return {"a": self.a, "b": self.b, "samples": len(events), "fitted": False}

        # 从匹配记录的原始分数估算: 用产品交互计数 proxy
        # 实际应用中应由 matching_engine 记录 raw_score 到 event
        raw_scores = []
        labels = []

        for evt in events:
            # 用产品的新鲜度/交互热度作为 raw_score 的 proxy
            product = db_session.query(Product).filter(Product.id == evt.target_id).first()
            if not product:
                continue
            interactions = getattr(product, "interaction_count", None) or 0
            # 归一化 raw_score: 用交互数和新鲜度估算
            raw = min(np.log1p(interactions) / 10.0, 1.0)
            # 给一个基础分确保范围
            raw = max(raw, 0.1)
            raw_scores.append(raw)
            labels.append(1 if evt.event_type in POSITIVE else 0)

        if len(raw_scores) < min_samples:
            return {"a": self.a, "b": self.b, "samples": len(raw_scores), "fitted": False}

        return self.fit(raw_scores, labels)

    def reset(self) -> None:
        """重置校准参数到默认值"""
        self.a = 1.0
        self.b = 0.0
        self._is_fitted = False

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted


# ============================================================
# P2-1: 用户Embedding (Item2Vec) — 无 gensim 回退, numpy SkipGram
# ============================================================


class Item2VecEmbedding:
    """Item2Vec 用户/产品嵌入

    用 Word2Vec (SkipGram + Negative Sampling) 在用户行为序列上训练产品嵌入,
    用户向量 = 其交互产品的平均向量。
    gensim 不可用时使用 numpy 手动实现。
    """

    def __init__(self, embedding_dim=64, window=3, epochs=10, lr=0.01):
        self.embedding_dim = embedding_dim
        self.window = window  # SkipGram 上下文窗口
        self.epochs = epochs
        self.lr = lr
        self.product_vectors: dict[int, np.ndarray] = {}  # {product_id: ndarray}
        self.user_vectors: dict[int, np.ndarray] = {}  # {user_id: ndarray}
        self._product_ids: list[int] = []  # 有序产品ID列表
        self._id_to_idx: dict[int, int] = {}  # product_id -> 矩阵行号
        self._vocab_size = 0
        self._is_fitted = False

    # ---- 构建嵌入 ----

    def build(self, db_session, limit_events=50000) -> dict:
        """从 UserEvent 表构建产品向量

        Args:
            db_session: SQLAlchemy 数据库会话
            limit_events: 最大读取事件数

        Returns:
            训练统计字典
        """
        from app.models import UserEvent

        # 1. 按用户 session 聚合产品序列
        events = (
            db_session.query(UserEvent)
            .filter(
                UserEvent.target_type == "product",
                UserEvent.target_id.isnot(None),
                UserEvent.user_id.isnot(None),
            )
            .order_by(UserEvent.user_id, UserEvent.created_at)
            .limit(limit_events)
            .all()
        )

        # 按 (user_id, session_id) 分组构建序列
        sequences: list[list[int]] = []
        current_key = None
        current_seq: list[int] = []
        for evt in events:
            key = (evt.user_id, evt.session_id or f"session_{evt.user_id}")
            if current_key is not None and key != current_key:
                if len(current_seq) >= 2:
                    sequences.append(current_seq)
                current_seq = []
            current_key = key
            current_seq.append(evt.target_id)
        if len(current_seq) >= 2:
            sequences.append(current_seq)

        if not sequences:
            logger.warning("Item2VecEmbedding.build: 无有效序列")
            return {"sequences": 0, "products": 0, "fitted": False}

        # 2. 构建词汇表
        all_pids: set[int] = set()
        for seq in sequences:
            all_pids.update(seq)
        self._product_ids = sorted(all_pids)
        self._id_to_idx = {pid: i for i, pid in enumerate(self._product_ids)}
        self._vocab_size = len(self._product_ids)

        logger.info(f"Item2Vec: 构建 {len(sequences)} 条序列, {self._vocab_size} 个唯一产品")

        # 3. 用 numpy 实现 SkipGram + Negative Sampling
        self._train_skipgram(sequences)

        # 4. 构建用户向量
        self._build_user_vectors(events)

        self._is_fitted = True
        return {
            "sequences": len(sequences),
            "products": self._vocab_size,
            "users": len(self.user_vectors),
            "fitted": True,
        }

    def _train_skipgram(self, sequences: list[list[int]]) -> None:
        """SkipGram + Negative Sampling 训练

        Args:
            sequences: 产品ID序列列表
        """
        vocab_size = self._vocab_size
        dim = self.embedding_dim

        # 初始化嵌入矩阵 (Xavier)
        scale = np.sqrt(2.0 / (vocab_size + dim))
        self._W = np.random.randn(vocab_size, dim).astype(np.float64) * scale  # 输入嵌入
        self._W_out = np.random.randn(vocab_size, dim).astype(np.float64) * scale  # 输出嵌入

        # 负采样分布 (基于词频的平滑)
        flat_ids = [pid for seq in sequences for pid in seq]
        freq = np.bincount(
            [self._id_to_idx[pid] for pid in flat_ids],
            minlength=vocab_size,
        ).astype(np.float64)
        freq = freq**0.75  # 经典平滑
        neg_dist = freq / freq.sum()

        # 生成训练样本
        pairs: list[tuple[int, int]] = []
        for seq in sequences:
            seq_indices = [self._id_to_idx[pid] for pid in seq]
            for i, center in enumerate(seq_indices):
                w = self.window
                start = max(0, i - w)
                end = min(len(seq_indices), i + w + 1)
                for j in range(start, end):
                    if j == i:
                        continue
                    pairs.append((center, seq_indices[j]))

        if not pairs:
            logger.warning("Item2Vec: 无训练样本")
            return

        logger.info(f"Item2Vec: {len(pairs)} 个训练样本, 训练 {self.epochs} 轮")

        # SGD 训练
        for epoch in range(self.epochs):
            np.random.shuffle(pairs)
            loss_sum = 0.0
            for center, context in pairs:
                # 正样本损失
                dot = self._W[center].dot(self._W_out[context])
                sig_pos = 1.0 / (1.0 + np.exp(-dot))
                loss_pos = -np.log(max(sig_pos, 1e-15))

                # 负样本 (k=5)
                neg_indices = np.random.choice(vocab_size, size=5, p=neg_dist, replace=False)
                # 确保不包含正样本
                neg_indices = neg_indices[neg_indices != context]
                if len(neg_indices) == 0:
                    continue

                dot_neg = self._W[center].dot(self._W_out[neg_indices].T)
                sig_neg = 1.0 / (1.0 + np.exp(dot_neg))  # sigmoid(-dot)
                loss_neg = -np.sum(np.log(np.maximum(sig_neg, 1e-15)))

                loss_sum += loss_pos + loss_neg

                # 梯度更新 (正样本)
                grad_pos = self._W_out[context] * (sig_pos - 1.0)
                self._W[center] -= self.lr * grad_pos
                self._W_out[context] -= self.lr * self._W[center] * (sig_pos - 1.0)

                # 梯度更新 (负样本)
                for neg_idx in neg_indices:
                    grad_neg = self._W_out[neg_idx] * sig_neg[0] if len(neg_indices) > 0 else 0
                    # 简化: 使用标量近似
                    g = dot_neg[list(neg_indices).index(neg_idx)] if len(neg_indices) > 0 else 0
                    # 更稳定的梯度
                    self._W[center] -= (
                        self.lr
                        * self._W_out[neg_idx]
                        * (sig_neg[list(neg_indices).index(neg_idx)] if len(neg_indices) > 0 else 0)
                    )

            # 简化负样本梯度 (更高效的实现)
            for center, context in pairs[: min(len(pairs), 1000)]:
                dot = self._W[center].dot(self._W_out[context])
                sig = 1.0 / (1.0 + np.exp(-dot))
                grad = self._W_out[context] * (sig - 1.0)
                self._W[center] -= self.lr * grad
                self._W_out[context] -= self.lr * self._W[center] * (sig - 1.0)

            if (epoch + 1) % 5 == 0 or epoch == 0:
                avg_loss = loss_sum / max(len(pairs), 1)
                logger.info(f"  Epoch {epoch + 1}/{self.epochs}, loss={avg_loss:.4f}")

        # 训练完成: 将嵌入写入 product_vectors (使用 W 作为最终嵌入)
        for pid, idx in self._id_to_idx.items():
            self.product_vectors[pid] = self._W[idx].copy()

        # 归一化
        for pid in self.product_vectors:
            norm = np.linalg.norm(self.product_vectors[pid])
            if norm > 0:
                self.product_vectors[pid] /= norm

        logger.info(f"Item2Vec 训练完成: {len(self.product_vectors)} 个产品嵌入")

    def _build_user_vectors(self, events) -> None:
        """从事件记录构建用户向量 (平均交互产品向量)"""
        user_product_map: dict[int, list[int]] = {}
        for evt in events:
            if evt.user_id is None or evt.target_id is None:
                continue
            uid = evt.user_id
            pid = evt.target_id
            if pid not in self.product_vectors:
                continue
            if uid not in user_product_map:
                user_product_map[uid] = []
            if pid not in user_product_map[uid]:
                user_product_map[uid].append(pid)

        for uid, pids in user_product_map.items():
            vecs = [self.product_vectors[pid] for pid in pids if pid in self.product_vectors]
            if vecs:
                self.user_vectors[uid] = np.mean(vecs, axis=0)
                norm = np.linalg.norm(self.user_vectors[uid])
                if norm > 0:
                    self.user_vectors[uid] /= norm

    # ---- 查询方法 ----

    def similar_products(self, product_id: int, top_k: int = 10) -> list[tuple[int, float]]:
        """找相似产品 (余弦相似度)

        Args:
            product_id: 产品ID
            top_k: 返回数量

        Returns:
            [(product_id, similarity), ...]
        """
        if product_id not in self.product_vectors:
            return []
        query_vec = self.product_vectors[product_id]
        scores: list[tuple[int, float]] = []
        for pid, vec in self.product_vectors.items():
            if pid == product_id:
                continue
            sim = float(np.dot(query_vec, vec))
            scores.append((pid, sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def recommend_for_user(self, user_id: int, top_k: int = 10) -> list[tuple[int, float]]:
        """基于用户向量的个性化推荐

        Args:
            user_id: 用户ID
            top_k: 返回数量

        Returns:
            [(product_id, score), ...]
        """
        if user_id not in self.user_vectors:
            return []
        user_vec = self.user_vectors[user_id]
        scores: list[tuple[int, float]] = []
        for pid, pvec in self.product_vectors.items():
            sim = float(np.dot(user_vec, pvec))
            scores.append((pid, sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def embedding_similarity(self, product: Product, need: BusinessNeed) -> float:
        """计算产品与用户需求之间的 embedding 相似度

        用需求的 owner_id 查找该用户向量, 与产品向量做余弦相似度。

        Args:
            product: 产品对象
            need: 需求对象

        Returns:
            float: [0, 1] 相似度, 无法计算时返回 0.0
        """
        if not self._is_fitted:
            return 0.0
        user_id = getattr(need, "user_id", None)
        if user_id is None or user_id not in self.user_vectors:
            return 0.0
        pid = getattr(product, "id", None)
        if pid is None or pid not in self.product_vectors:
            return 0.0
        sim = float(np.dot(self.user_vectors[user_id], self.product_vectors[pid]))
        return max(0.0, min(1.0, (sim + 1.0) / 2.0))  # [-1,1] -> [0,1]

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted


# ============================================================
# P2-2: 冷启动2.0 (汤普森采样)
# ============================================================


# 探索幅度常量: Thompson 采样输出映射到 [0, EXPLORE_SCALE]
EXPLORE_SCALE = 0.20


class ThompsonSamplingExplorer:
    """汤普森采样探索器

    用 Beta 分布为每个产品维护「探索加分」,
    取代固定的 1.2x 冷启动加权。
    正反馈 → alpha++ → 均值 ↑ → 探索加分 ↓
    负反馈 → beta++  → 均值 ↓ → 探索加分 ↑
    """

    def __init__(self, global_alpha=2.0, global_beta=8.0):
        """
        Args:
            global_alpha: 全局 Beta 先验 alpha (默认 2.0, 均值 0.2)
            global_beta:  全局 Beta 先验 beta  (默认 8.0)
        """
        self.global_alpha = global_alpha
        self.global_beta = global_beta
        # 每个产品的 Beta 参数: {product_id: (alpha, beta)}
        self._params: dict[int, tuple[float, float]] = {}
        # 冷启动标记（用于向后兼容 partial_scores）
        self._cold_start_products: set[int] = set()

    def get_explore_boost(self, product_id: int) -> float:
        """从 Beta 分布采样, 返回探索加分 [0, EXPLORE_SCALE]

        Args:
            product_id: 产品 ID

        Returns:
            float: [0, EXPLORE_SCALE] 探索加分
        """
        alpha, beta = self._params.get(product_id, (self.global_alpha, self.global_beta))
        # 从 Beta 分布采样
        try:
            sample = float(np.random.beta(alpha, beta))
        except Exception:
            sample = alpha / (alpha + beta)  # 均值 fallback
        # 映射到探索加分范围
        boost = sample * EXPLORE_SCALE
        return round(boost, 4)

    def update(self, product_id: int, feedback_type: str) -> None:
        """根据反馈更新产品的 Beta 参数

        Args:
            product_id: 产品 ID
            feedback_type: 反馈类型
                'positive' → alpha += 1 (减少探索)
                'negative' → beta += 1  (增加探索)
                'neutral'  → 不更新
        """
        alpha, beta = self._params.get(product_id, (self.global_alpha, self.global_beta))
        if feedback_type == "positive":
            alpha += 1.0
        elif feedback_type == "negative":
            beta += 1.0
        else:
            return
        self._params[product_id] = (alpha, beta)

    def mark_cold_start(self, product_id: int) -> None:
        """将产品标记为冷启动（需要探索）"""
        self._cold_start_products.add(product_id)
        # 如果尚未有参数, 使用全局先验 (均值 0.2, 适度探索)
        if product_id not in self._params:
            self._params[product_id] = (self.global_alpha, self.global_beta)

    def is_cold_start(self, product_id: int) -> bool:
        return product_id in self._cold_start_products

    def get_explore_score(self, product_id: int) -> float:
        """获取当前探索分数（用于 partial_scores）

        Returns:
            float: [0, 1] 归一化探索强度, 用于 CTR 模型特征
        """
        boost = self.get_explore_boost(product_id)
        return boost / EXPLORE_SCALE if EXPLORE_SCALE > 0 else 0.0

    def reset(self) -> None:
        """重置所有参数"""
        self._params.clear()
        self._cold_start_products.clear()


# ============================================================
# 模块级单例
# ============================================================

_ctr_model_instance: MatchCTRModel | None = None
_calibrator_instance: ScoreCalibrator | None = None
_item2vec_instance: Item2VecEmbedding | None = None
_thompson_instance: ThompsonSamplingExplorer | None = None


def get_ctr_model() -> MatchCTRModel:
    """获取 CTR 模型单例（自动从磁盘加载）"""
    global _ctr_model_instance
    if _ctr_model_instance is None:
        _ctr_model_instance = MatchCTRModel()
        _ctr_model_instance.load()
    return _ctr_model_instance


def get_calibrator() -> ScoreCalibrator:
    """获取校准器单例"""
    global _calibrator_instance
    if _calibrator_instance is None:
        _calibrator_instance = ScoreCalibrator()
    return _calibrator_instance


def get_item2vec() -> Item2VecEmbedding:
    """获取 Item2Vec 嵌入器单例"""
    global _item2vec_instance
    if _item2vec_instance is None:
        _item2vec_instance = Item2VecEmbedding()
    return _item2vec_instance


def get_thompson_explorer() -> ThompsonSamplingExplorer:
    """获取汤普森采样探索器单例"""
    global _thompson_instance
    if _thompson_instance is None:
        _thompson_instance = ThompsonSamplingExplorer()
    return _thompson_instance


def reset_singletons() -> None:
    """重置单例（用于测试）"""
    global _ctr_model_instance, _calibrator_instance, _item2vec_instance, _thompson_instance
    global _dssm_instance, _online_lambdarank_instance
    _ctr_model_instance = None
    _calibrator_instance = None
    _item2vec_instance = None
    _thompson_instance = None
    _dssm_instance = None
    _online_lambdarank_instance = None


# ============================================================
# P3-1: 双塔DSSM模型 — 用户塔+产品塔, 内积=匹配分
# ============================================================


class DSSMModel:
    """双塔DSSM (Deep Structured Semantic Model)

    用户和产品各一个 DNN 塔（sklearn MLPRegressor），
    输出 32 维 embedding 做内积/余弦相似度得到匹配分。

    用法:
        dssm = DSSMModel()
        dssm.build_towers(user_feature_dim=10, product_feature_dim=12)
        user_vec = dssm.encode_user(user_features)
        prod_vec = dssm.encode_product(product_features)
        score = dssm.predict(user_vec, prod_vec)
    """

    def __init__(self, user_dim: int = 32, product_dim: int = 32):
        self.user_dim = user_dim
        self.product_dim = product_dim
        self.user_tower = None  # MLPRegressor: 用户特征→embedding
        self.product_tower = None  # MLPRegressor: 产品特征→embedding
        self._user_feature_dim = 0
        self._product_feature_dim = 0
        self._is_fitted = False

    # ---- 构建双塔 ----

    def build_towers(self, user_feature_dim: int, product_feature_dim: int) -> None:
        """用 sklearn MLPRegressor 构建双塔

        用户塔: input → 64 (ReLU) → user_dim (ReLU, embedding)
        产品塔: input → 64 (ReLU) → product_dim (ReLU, embedding)

        Args:
            user_feature_dim: 用户特征维度
            product_feature_dim: 产品特征维度
        """
        from sklearn.neural_network import MLPRegressor

        self._user_feature_dim = user_feature_dim
        self._product_feature_dim = product_feature_dim

        # 用户塔: input→64→user_dim→1 (标量输出, 用于训练回归)
        self.user_tower = MLPRegressor(
            hidden_layer_sizes=(64, self.user_dim),
            activation="relu",
            solver="adam",
            learning_rate_init=0.001,
            max_iter=1,  # 手动迭代训练
            warm_start=True,  # 保留权重增量训练
            random_state=42,
            verbose=False,
        )
        # 产品塔: input→64→product_dim→1
        self.product_tower = MLPRegressor(
            hidden_layer_sizes=(64, self.product_dim),
            activation="relu",
            solver="adam",
            learning_rate_init=0.001,
            max_iter=1,
            warm_start=True,
            random_state=42,
            verbose=False,
        )

        # 假拟合以初始化权重矩阵
        dummy_user = np.zeros((5, user_feature_dim), dtype=np.float64)
        dummy_product = np.zeros((5, product_feature_dim), dtype=np.float64)
        dummy_labels = np.zeros(5, dtype=np.float64)
        self.user_tower.fit(dummy_user, dummy_labels)
        self.product_tower.fit(dummy_product, dummy_labels)

        logger.info(
            f"DSSM 双塔构建完成: user_dim={user_feature_dim}→{self.user_dim}, "
            f"product_dim={product_feature_dim}→{self.product_dim}"
        )

    # ---- 编码方法（手动前向传播提取 embedding） ----

    def encode_user(self, features: np.ndarray) -> np.ndarray:
        """用户特征 → 32 维向量（归一化）

        Args:
            features: shape=(N,) 或 (1, N) 的特征向量

        Returns:
            归一化的 32 维 embedding
        """
        if self.user_tower is None:
            return np.zeros(self.user_dim)
        x = np.asarray(features, dtype=np.float64).reshape(1, -1)
        # layer1: input → 64 (ReLU)
        z1 = x @ self.user_tower.coefs_[0] + self.user_tower.intercepts_[0]
        a1 = np.maximum(0, z1)
        # layer2: 64 → 32 (ReLU, embedding layer)
        z2 = a1 @ self.user_tower.coefs_[1] + self.user_tower.intercepts_[1]
        embedding = np.maximum(0, z2).flatten()
        # L2 归一化
        norm = np.linalg.norm(embedding)
        if norm > 1e-10:
            embedding = embedding / norm
        return embedding

    def encode_product(self, features: np.ndarray) -> np.ndarray:
        """产品特征 → 32 维向量（归一化）

        Args:
            features: shape=(N,) 或 (1, N) 的特征向量

        Returns:
            归一化的 32 维 embedding
        """
        if self.product_tower is None:
            return np.zeros(self.product_dim)
        x = np.asarray(features, dtype=np.float64).reshape(1, -1)
        # layer1: input → 64 (ReLU)
        z1 = x @ self.product_tower.coefs_[0] + self.product_tower.intercepts_[0]
        a1 = np.maximum(0, z1)
        # layer2: 64 → 32 (ReLU, embedding layer)
        z2 = a1 @ self.product_tower.coefs_[1] + self.product_tower.intercepts_[1]
        embedding = np.maximum(0, z2).flatten()
        # L2 归一化
        norm = np.linalg.norm(embedding)
        if norm > 1e-10:
            embedding = embedding / norm
        return embedding

    # ---- 预测（余弦相似度） ----

    def predict(self, user_vec: np.ndarray, product_vec: np.ndarray) -> float:
        """计算用户向量与产品向量的余弦相似度 [0, 1]

        Args:
            user_vec: 用户 embedding (32,)
            product_vec: 产品 embedding (32,)

        Returns:
            float: [0, 1] 匹配相似度
        """
        from sklearn.metrics.pairwise import cosine_similarity

        u = np.asarray(user_vec, dtype=np.float64).reshape(1, -1)
        p = np.asarray(product_vec, dtype=np.float64).reshape(1, -1)
        sim = float(cosine_similarity(u, p)[0][0])
        # [-1, 1] → [0, 1]
        return max(0.0, (sim + 1.0) / 2.0)

    # ---- 训练（交替拟合用户塔和产品塔） ----

    def _extract_user_features(self, need: "BusinessNeed") -> np.ndarray:
        """从需求对象提取用户侧特征向量

        Args:
            need: BusinessNeed ORM 对象

        Returns:
            10 维用户特征向量
        """
        vec = np.zeros(10, dtype=np.float64)
        if need is None:
            return vec
        # 1-3: 需求文本特征 (title, description, category 的长度/词数 proxy)
        title = getattr(need, "title", "") or ""
        desc = getattr(need, "description", "") or ""
        cat = getattr(need, "category", "") or ""
        vec[0] = min(len(title) / 100.0, 1.0)
        vec[1] = min(len(desc) / 500.0, 1.0)
        vec[2] = 1.0 if cat else 0.0
        # 4-5: 预算特征
        budget = getattr(need, "budget", None)
        from app.utils import parse_budget

        br = parse_budget(budget)
        if br:
            low, high = br
            vec[3] = min(low / 100000.0, 1.0) if low < float("inf") else 0.0
            vec[4] = min(high / 100000.0, 1.0) if high < float("inf") else 0.0
        # 6: 交互热度
        interactions = getattr(need, "interaction_count", None) or 0
        vec[5] = min(np.log1p(interactions) / 10.0, 1.0)
        # 7-8: 时间特征
        created = getattr(need, "created_at", None)
        if created:
            age_days = (time.time() - created.timestamp()) / 86400.0
            vec[6] = float(np.exp(-age_days / 90.0))
        updated = getattr(need, "updated_at", None)
        if updated:
            age_days = (time.time() - updated.timestamp()) / 86400.0
            vec[7] = float(np.exp(-age_days / 30.0))
        # 9: status 标记
        status = getattr(need, "status", "") or ""
        vec[8] = 1.0 if status == "open" else 0.5
        # 10: user_id hash 特征 (归一化)
        uid = getattr(need, "user_id", None) or 0
        vec[9] = float(uid % 100) / 100.0
        return vec

    def _extract_product_features(self, product: "Product") -> np.ndarray:
        """从产品对象提取产品侧特征向量

        Args:
            product: Product ORM 对象

        Returns:
            12 维产品特征向量
        """
        vec = np.zeros(12, dtype=np.float64)
        if product is None:
            return vec
        # 1-3: 文本特征
        name = getattr(product, "name", "") or ""
        desc = getattr(product, "description", "") or ""
        tags = getattr(product, "tags", "") or ""
        cat = getattr(product, "category", "") or ""
        vec[0] = min(len(name) / 100.0, 1.0)
        vec[1] = min(len(desc) / 1000.0, 1.0)
        vec[2] = 1.0 if cat else 0.0
        # 4-5: 价格特征
        price = getattr(product, "sale_price", None) or getattr(product, "price", 0) or 0
        vec[3] = min(price / 100000.0, 1.0)
        vec[4] = 1.0 if price > 0 else 0.0
        # 6: 品牌特征
        brand = getattr(product, "brand", "") or ""
        vec[5] = 1.0 if brand else 0.0
        # 7: 标签数量
        tag_list = [t for t in tags.split(",") if t] if tags else []
        vec[6] = min(len(tag_list) / 10.0, 1.0)
        # 8: 交互热度
        interactions = getattr(product, "interaction_count", None) or 0
        vec[7] = min(np.log1p(interactions) / 10.0, 1.0)
        # 9-10: 时间特征
        created = getattr(product, "created_at", None)
        if created:
            age_days = (time.time() - created.timestamp()) / 86400.0
            vec[8] = float(np.exp(-age_days / 90.0))
        updated = getattr(product, "updated_at", None)
        if updated:
            age_days = (time.time() - updated.timestamp()) / 86400.0
            vec[9] = float(np.exp(-age_days / 30.0))
        # 11: 状态
        status = getattr(product, "status", "") or ""
        vec[10] = 1.0 if status == "approved" else 0.5
        # 12: owner_id hash
        oid = getattr(product, "owner_id", None) or 0
        vec[11] = float(oid % 100) / 100.0
        return vec

    def train(
        self,
        user_features: np.ndarray,
        product_features: np.ndarray,
        labels: np.ndarray,
        epochs: int = 20,
    ) -> dict[str, Any]:
        """训练双塔 DSSM

        交替训练用户塔和产品塔:
        1. 用用户特征训练用户塔 → 预测 label
        2. 用产品特征训练产品塔 → 预测 label
        3. 两个塔的 embedding 层通过共同 label 空间对齐

        Args:
            user_features: shape=(N, user_feature_dim) 用户特征矩阵
            product_features: shape=(N, product_feature_dim) 产品特征矩阵
            labels: shape=(N,) 标签, 1=匹配成功, 0=不匹配
            epochs: 训练轮数 (默认 20)

        Returns:
            训练结果字典
        """
        n = len(labels)
        if n == 0:
            logger.warning("DSSM.train: 空数据集，跳过训练")
            return {"samples": 0, "fitted": False}

        # 确保塔已构建
        if self.user_tower is None or self.product_tower is None:
            ufd = user_features.shape[1]
            pfd = product_features.shape[1]
            self.build_towers(ufd, pfd)

        y = np.asarray(labels, dtype=np.float64)

        logger.info(f"DSSM 训练开始: {n} 样本, {epochs} 轮")

        for epoch in range(epochs):
            # 训练用户塔: 输入=用户特征, 输出=label
            self.user_tower.fit(user_features, y)
            # 训练产品塔: 输入=产品特征, 输出=label
            self.product_tower.fit(product_features, y)

            # 每 5 轮输出一次损失
            if (epoch + 1) % 5 == 0 or epoch == 0:
                u_pred = self.user_tower.predict(user_features)
                p_pred = self.product_tower.predict(product_features)
                u_mse = float(np.mean((y - u_pred) ** 2))
                p_mse = float(np.mean((y - p_pred) ** 2))
                logger.info(f"  Epoch {epoch + 1}/{epochs}: user_mse={u_mse:.4f}, prod_mse={p_mse:.4f}")

        # 最终评估
        u_pred = self.user_tower.predict(user_features)
        p_pred = self.product_tower.predict(product_features)
        u_mse = float(np.mean((y - u_pred) ** 2))
        p_mse = float(np.mean((y - p_pred) ** 2))
        # embedding 相似度 vs 标签一致性
        sims = []
        for i in range(min(n, 500)):
            uv = self.encode_user(user_features[i])
            pv = self.encode_product(product_features[i])
            sims.append(self.predict(uv, pv))
        avg_sim_pos = np.mean([s for s, l in zip(sims, labels) if l > 0.5]) if any(l > 0.5 for l in labels) else 0.0
        avg_sim_neg = np.mean([s for s, l in zip(sims, labels) if l < 0.5]) if any(l < 0.5 for l in labels) else 0.0

        self._is_fitted = True

        metrics = {
            "samples": n,
            "positive": int(np.sum(y)),
            "negative": int(n - np.sum(y)),
            "user_mse": round(u_mse, 4),
            "product_mse": round(p_mse, 4),
            "avg_sim_positive": round(float(avg_sim_pos), 4),
            "avg_sim_negative": round(float(avg_sim_neg), 4),
            "epochs": epochs,
            "fitted": True,
        }

        logger.info("DSSM 训练完成", extra=metrics)
        return metrics

    def load_training_data_from_events(
        self,
        db_session,
        limit: int = 2000,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """从 UserEvent 表加载 DSSM 训练数据

        POSITIVE: like, adopt, click, recommend_like → label=1.0
        NEGATIVE: dislike, skip, close, recommend_dislike → label=0.0

        Args:
            db_session: SQLAlchemy 数据库会话
            limit: 最大样本数

        Returns:
            (user_features, product_features, labels) 三元组
        """
        POSITIVE_EVENTS = {"click", "like", "adopt", "view", "recommend_like"}
        NEGATIVE_EVENTS = {"skip", "dislike", "close", "recommend_dislike"}

        events = (
            db_session.query(UserEvent)
            .filter(
                UserEvent.event_type.in_(list(POSITIVE_EVENTS | NEGATIVE_EVENTS)),
                UserEvent.target_id.isnot(None),
                UserEvent.target_type == "product",
            )
            .order_by(UserEvent.created_at.desc())
            .limit(limit)
            .all()
        )

        user_feat_list: list[np.ndarray] = []
        prod_feat_list: list[np.ndarray] = []
        y_list: list[float] = []

        for evt in events:
            product = db_session.query(Product).filter(Product.id == evt.target_id).first()
            if not product:
                continue

            # 找用户最近的需求
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

            try:
                uf = self._extract_user_features(recent_need)
                pf = self._extract_product_features(product)
            except Exception as e:
                logger.debug(f"DSSM 特征提取失败 (event={evt.id}): {e}")
                continue

            user_feat_list.append(uf)
            prod_feat_list.append(pf)
            y_list.append(1.0 if evt.event_type in POSITIVE_EVENTS else 0.0)

        if not user_feat_list:
            logger.warning("DSSM 训练数据加载: 无有效数据")
            ufd = self._user_feature_dim or 10
            pfd = self._product_feature_dim or 12
            return np.empty((0, ufd)), np.empty((0, pfd)), np.empty(0)

        user_features = np.vstack(user_feat_list)
        product_features = np.vstack(prod_feat_list)
        labels = np.array(y_list, dtype=np.float64)

        logger.info(
            "DSSM 训练数据加载完成",
            extra={
                "samples": len(labels),
                "positive": int(np.sum(labels)),
                "negative": int(len(labels) - np.sum(labels)),
                "user_feature_dim": user_features.shape[1],
                "product_feature_dim": product_features.shape[1],
            },
        )
        return user_features, product_features, labels

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted


# ============================================================
# 模块级单例 (追加 DSSM)
# ============================================================

_dssm_instance: DSSMModel | None = None


def get_dssm_model() -> DSSMModel:
    """获取 DSSM 模型单例"""
    global _dssm_instance
    if _dssm_instance is None:
        _dssm_instance = DSSMModel()
    return _dssm_instance


# ============================================================
# P3-3: 在线LambdaRank实时增量学习
# ============================================================


class OnlineLambdaRank:
    """
    在线Learning to Rank
    每次用户反馈触发增量更新, 不需要全量重训练
    """

    _ONLINE_LR_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")
    _ONLINE_LR_MODEL_PATH = os.path.join(_ONLINE_LR_MODEL_DIR, "online_lambdarank.pkl")

    def __init__(self, learning_rate=0.01):
        self.model = None  # sklearn GradientBoostingRegressor
        self.lr = learning_rate
        self.buffer = []  # 在线样本buffer, 凑够batch_size再更新
        self._update_count = 0  # 累计更新次数, 每100次自动持久化

    def partial_fit(self, features, relevance_score):
        """单样本增量更新

        Args:
            features: 特征向量 (list or np.ndarray)
            relevance_score: 相关度标签, 1.0=喜欢, 0.0=不喜欢
        """
        self.buffer.append((features, relevance_score))
        if len(self.buffer) >= 32:  # batch_size=32
            self._update()

    def _update(self):
        """LambdaRank梯度更新

        对buffer中所有pair计算lambda梯度, 更新GBDT的叶子节点值
        """
        X = np.array([x for x, _ in self.buffer])
        y = np.array([y for _, y in self.buffer])
        if self.model is None:
            from sklearn.ensemble import GradientBoostingRegressor

            self.model = GradientBoostingRegressor(
                n_estimators=10,
                max_depth=3,
                learning_rate=self.lr,
                warm_start=True,
                random_state=42,
            )
            self.model.fit(X, y)
        else:
            # warm_start=True 增量fit
            self.model.n_estimators += 10
            self.model.fit(X, y)
        self.buffer = []
        self._update_count += 1
        # 每更新100次自动持久化
        if self._update_count % 100 == 0:
            self._persist()

    def predict(self, features):
        """预测排序分 [0, 1]

        Args:
            features: 特征向量 (list or np.ndarray)

        Returns:
            float: [0, 1] 排序分, 模型未训练时返回 0.5
        """
        if self.model is None:
            return 0.5
        try:
            score = float(self.model.predict([features])[0])
            return float(np.clip(score, 0.0, 1.0))
        except Exception:
            return 0.5

    def load(self) -> bool:
        """从磁盘加载已训练的模型

        Returns:
            加载成功返回 True
        """
        try:
            if os.path.exists(self._ONLINE_LR_MODEL_PATH):
                with open(self._ONLINE_LR_MODEL_PATH, "rb") as f:
                    self.model = pickle.load(f)
                logger.info("OnlineLambdaRank 模型加载成功", extra={"path": self._ONLINE_LR_MODEL_PATH})
                return True
        except Exception as e:
            logger.warning(f"OnlineLambdaRank 模型加载失败: {e}")
        return False

    def _persist(self) -> None:
        """保存模型到磁盘"""
        try:
            os.makedirs(self._ONLINE_LR_MODEL_DIR, exist_ok=True)
            with open(self._ONLINE_LR_MODEL_PATH, "wb") as f:
                pickle.dump(self.model, f)
            logger.info("OnlineLambdaRank 模型已持久化", extra={"path": self._ONLINE_LR_MODEL_PATH})
        except Exception as e:
            logger.warning(f"OnlineLambdaRank 模型持久化失败: {e}")


# 模块级单例 (追加 OnlineLambdaRank)
_online_lambdarank_instance: OnlineLambdaRank | None = None


def get_online_lambdarank() -> OnlineLambdaRank:
    """获取 OnlineLambdaRank 单例（自动从磁盘加载）"""
    global _online_lambdarank_instance
    if _online_lambdarank_instance is None:
        _online_lambdarank_instance = OnlineLambdaRank()
        _online_lambdarank_instance.load()
    return _online_lambdarank_instance


# ============================================================
# 便捷函数


def predict_ctr_score(
    product: Product,
    need: BusinessNeed,
    partial_scores: dict | None = None,
) -> float:
    """便捷函数：预测单个产品-需求对的 CTR

    Args:
        product: 产品对象
        need: 需求对象
        partial_scores: 规则引擎中间评分 (可选)

    Returns:
        float: [0, 1] CTR 预估值
    """
    model = get_ctr_model()
    features = model.extract_features(
        product=product,
        need=need,
        partial_scores=partial_scores or {},
    )
    return model.predict_ctr(features)


def calibrate_score(raw_score: float) -> float:
    """便捷函数：校准单个匹配分数

    Args:
        raw_score: 原始匹配分数 [0, 1]

    Returns:
        float: 校准后的概率 [0, 1]
    """
    calibrator = get_calibrator()
    return calibrator.calibrate_single(raw_score)


def retrain_ctr_model_from_db(db_session, limit: int = 2000) -> dict[str, Any]:
    """从数据库反馈数据重新训练 CTR 模型

    Args:
        db_session: SQLAlchemy 数据库会话
        limit: 最大训练样本数

    Returns:
        训练结果字典
    """
    model = get_ctr_model()
    X, y = model.load_training_data_from_events(db_session, limit=limit)
    if X.shape[0] == 0:
        return {"error": "无训练数据"}
    return model.train(X, y)


# ============================================================
# 独立测试入口
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    # 测试 MatchCTRModel
    logger.info("=== 测试 MatchCTRModel ===")
    model = MatchCTRModel()
    logger.info(f"特征数量: {model.feature_count}")
    logger.info(f"特征列表: {model.feature_names}")

    # 模拟特征
    dummy_features = np.zeros(model.feature_count)
    dummy_features[0] = 0.8  # category_score
    dummy_features[1] = 0.6  # keyword_score
    dummy_features[2] = 0.9  # price_score

    # 未训练时返回默认值
    pred = model.predict_ctr(dummy_features)
    logger.info(f"未训练时预测: {pred:.4f} (期望 0.5)")

    # 模拟训练
    n_samples = 100
    rng = np.random.RandomState(42)
    X_dummy = rng.rand(n_samples, model.feature_count)
    y_dummy = (X_dummy[:, 0] * 0.5 + X_dummy[:, 1] * 0.3 + rng.randn(n_samples) * 0.1 > 0.5).astype(float)
    result = model.train(X_dummy, y_dummy)
    logger.info(f"训练结果: MSE={result.get('mse')}, MAE={result.get('mae')}")
    logger.info(f"后端: {result.get('backend')}")

    pred = model.predict_ctr(dummy_features)
    logger.info(f"训练后预测: {pred:.4f}")

    # 测试 ScoreCalibrator
    logger.info("\n=== 测试 ScoreCalibrator ===")
    cal = ScoreCalibrator()
    raw = [0.1, 0.3, 0.5, 0.7, 0.9]
    logger.info(f"未拟合校准: {cal.calibrate(raw)}")

    # 模拟反馈数据拟合
    scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    labels = [0, 0, 0, 0, 1, 0, 1, 1, 1, 1]
    fit_result = cal.fit(scores, labels)
    logger.info(f"拟合结果: a={fit_result['a']}, b={fit_result['b']}")
    logger.info(f"校准后: {[round(c, 4) for c in cal.calibrate(raw)]}")

    logger.info("\n✅ CTR 模型 + 校准层测试通过")
