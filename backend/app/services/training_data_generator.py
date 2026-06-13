"""
链客宝AI 训练数据增强生成器
============================
基于现有规则评分引擎的6维评分维度，生成合成训练数据。

6维评分规则:
  1. 类别匹配 (0-40分) — 类目 Jaccard / 文本相似度
  2. 关键词匹配 (0-40分) — TF-IDF + 重叠率
  3. 价格匹配 (0-20分) — 预算区间匹配度
  4. 冷启动加权 (1.2x) — 新鲜度加成
  5. 反馈调整 (±0.10) — 用户反馈权重
  6. 特征集成 (10%) — feature_pipeline 综合相似度

策略:
  - 对每个合成样本，从6个维度随机采样特征值
  - 用规则评分公式计算弱标签 (0~1)
  - 添加随机扰动 (高斯噪声) 模拟真实数据分布
  - 平衡正负样本
"""

import logging
import os
from typing import Any

import numpy as np

# 确保从项目根目录可导入
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

# 数据保存路径
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "models")
AUGMENTED_DATA_PATH = os.path.join(MODELS_DIR, "training_data_augmented.npz")

# FEATURE_NAMES 与 matching_model.py 保持一致
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

# 规则权重（与 matching_engine.py 保持一致）
CATEGORY_WEIGHT = 0.40   # 类别 0-40 分 → 40%
KEYWORD_WEIGHT = 0.40    # 关键词 0-40 分 → 40%
PRICE_WEIGHT = 0.20      # 价格 0-20 分 → 20%
COLD_START_BOOST = 1.2   # 冷启动乘数
FEATURE_WEIGHT = 0.10    # 特征集成权重
FEEDBACK_MAX = 0.10      # 反馈最大调整

# 合成数据量
DEFAULT_N_SAMPLES = 600

# 随机种子
RANDOM_SEED = 42


# ============================================================
# 规则评分函数（模拟 matching_engine 的评分逻辑）
# ============================================================


def _rule_category_score(category_sim: float) -> float:
    """类别匹配分数映射到 [0, 1]"""
    # category_sim 本身就是 jaccard 相似度 [0, 1]
    # 规则引擎中映射到 0-40分，这里归一化到 0~1
    return float(category_sim)


def _rule_keyword_score(text_sim: float) -> float:
    """关键词匹配分数映射到 [0, 1]"""
    # text_sim 是 TF-IDF 余弦相似度 [0, 1]
    # 规则引擎中映射到 0-40分
    return float(text_sim)


def _rule_price_score(price_budget_sim: float) -> float:
    """价格匹配分数映射到 [0, 1]"""
    # price_budget_sim 是价格-预算匹配度 [0, 1]
    # 规则引擎中映射到 0-20分
    return float(price_budget_sim)


def _rule_cold_start_bonus(is_cold_prod: float, is_cold_need: float) -> float:
    """冷启动加权乘数"""
    if is_cold_prod > 0.5 or is_cold_need > 0.5:
        return COLD_START_BOOST
    return 1.0


def _rule_feedback_adjustment(base_score: float) -> float:
    """模拟反馈调整"""
    # 随机 ±0.05 的反馈调整
    noise = np.random.uniform(-FEEDBACK_MAX * 0.5, FEEDBACK_MAX * 0.5)
    return float(np.clip(base_score + noise, 0.0, 1.0))


def _rule_feature_blend(base_score: float, feature_sim: float) -> float:
    """特征集成混合"""
    if feature_sim > 0.3:
        return float(base_score * (1.0 - FEATURE_WEIGHT) + feature_sim * FEATURE_WEIGHT)
    return float(base_score)


def compute_rule_score(features: np.ndarray) -> float:
    """基于6维特征计算规则评分（作为弱标签）

    Args:
        features: shape=(NUM_FEATURES,), 特征向量

    Returns:
        float: [0, 1] 规则评分
    """
    category_sim = features[0]
    text_sim = features[1]
    price_budget_sim = features[2]
    _recency_prod = features[3]
    _recency_need = features[4]
    _price_norm = features[5]
    _budget_mid_norm = features[6]
    feature_sim = features[7]
    is_cold_prod = features[8]
    is_cold_need = features[9]

    # 1-3: 基础分数 (0~100 分制 → 归一化到 0~1)
    cat_score = _rule_category_score(category_sim)
    kw_score = _rule_keyword_score(text_sim)
    price_score = _rule_price_score(price_budget_sim)

    total_score = (
        CATEGORY_WEIGHT * cat_score
        + KEYWORD_WEIGHT * kw_score
        + PRICE_WEIGHT * price_score
    )
    # total_score 在 [0, 1] 区间

    # 4. 冷启动加权
    total_score *= _rule_cold_start_bonus(is_cold_prod, is_cold_need)
    total_score = min(total_score, 1.0)

    # 5. 特征集成
    total_score = _rule_feature_blend(total_score, feature_sim)

    # 6. 反馈调整（加噪声模拟）
    total_score = _rule_feedback_adjustment(total_score)

    return float(np.clip(total_score, 0.0, 1.0))


# ============================================================
# 合成数据生成
# ============================================================


def _random_category_sim() -> float:
    """生成随机关联相似度"""
    # 40% 高相似, 30% 中相似, 30% 低相似
    r = np.random.random()
    if r < 0.40:
        return float(np.random.uniform(0.7, 1.0))
    elif r < 0.70:
        return float(np.random.uniform(0.3, 0.7))
    else:
        return float(np.random.uniform(0.0, 0.3))


def _random_text_sim() -> float:
    """生成随机文本相似度"""
    # 与 category_sim 弱相关
    return float(np.random.uniform(0.0, 1.0))


def _random_price_sim() -> float:
    """生成随机价格匹配度"""
    return float(np.random.uniform(0.0, 1.0))


def _random_recency() -> float:
    """生成随机新鲜度分数"""
    return float(np.random.uniform(0.0, 1.0))


def _random_feature_sim() -> float:
    """生成随机特征相似度"""
    return float(np.random.uniform(0.0, 1.0))


def _random_is_cold() -> float:
    """生成随机冷启动标记 (10% 概率为冷启动)"""
    return 1.0 if np.random.random() < 0.10 else 0.0


def _random_budget_mid_norm() -> float:
    """生成随机预算中点归一化值"""
    return float(np.random.uniform(0.0, 1.0))


def _random_price_norm() -> float:
    """生成随机价格归一化值"""
    return float(np.random.uniform(0.0, 1.0))


def generate_synthetic_sample() -> np.ndarray:
    """生成单个合成样本的特征向量

    各维度之间存在合理的相关性，使数据更接近真实分布：
    - 类目相似度高时，文本相似度也倾向于高
    - 价格匹配度与价格/预算相关

    Returns:
        shape=(NUM_FEATURES,) 的特征向量
    """
    vec = np.zeros(NUM_FEATURES, dtype=np.float64)

    # 1. 类目相似度
    vec[0] = _random_category_sim()

    # 2. 文本相似度 (与类目相似度弱相关)
    vec[1] = _random_text_sim()
    # 添加弱相关: 如果类目相似度高，文本相似度略高
    if vec[0] > 0.7:
        vec[1] = float(max(vec[1], np.random.uniform(0.3, 0.8)))
    elif vec[0] < 0.3:
        vec[1] = float(min(vec[1], np.random.uniform(0.0, 0.5)))

    # 3. 价格匹配度
    vec[2] = _random_price_sim()

    # 4-5. 新鲜度
    vec[3] = _random_recency()
    vec[4] = _random_recency()

    # 6. 产品价格
    vec[5] = _random_price_norm()

    # 7. 预算中点
    vec[6] = _random_budget_mid_norm()

    # 8. 特征相似度 (与类目+文本相似度弱相关)
    vec[7] = _random_feature_sim()
    vec[7] = float(0.3 * vec[0] + 0.3 * vec[1] + 0.4 * vec[7])
    vec[7] = float(np.clip(vec[7], 0.0, 1.0))

    # 9-10. 冷启动标记
    vec[8] = _random_is_cold()
    vec[9] = _random_is_cold()

    return vec


def generate_training_data(
    n_samples: int = DEFAULT_N_SAMPLES,
    noise_level: float = 0.05,
    balance: bool = True,
    seed: int = RANDOM_SEED,
) -> tuple[np.ndarray, np.ndarray]:
    """生成合成训练数据

    Args:
        n_samples: 生成的样本总数
        noise_level: 添加到标签的高斯噪声标准差
        balance: 是否平衡正负样本（通过调整阈值）
        seed: 随机种子

    Returns:
        (X, y): 特征矩阵和标签向量
    """
    np.random.seed(seed)

    X_list = []
    y_list = []

    # 生成样本
    for _ in range(n_samples):
        vec = generate_synthetic_sample()
        label = compute_rule_score(vec)

        # 添加噪声模拟真实数据
        label += np.random.normal(0, noise_level)
        label = float(np.clip(label, 0.0, 1.0))

        X_list.append(vec)
        y_list.append(label)

    X = np.vstack(X_list)
    y = np.array(y_list, dtype=np.float64)

    # 如果需要平衡正负样本，调整阈值
    if balance:
        # 用中位数作为阈值，确保正负样本平衡
        threshold = np.median(y)
        y_binary = (y >= threshold).astype(np.float64)
        logger.info(
            "正负样本平衡",
            extra={
                "threshold": round(threshold, 4),
                "positive": int(np.sum(y_binary)),
                "negative": int(len(y_binary) - np.sum(y_binary)),
                "total": len(y_binary),
            },
        )
    else:
        # 用 0.5 作为阈值
        y_binary = (y >= 0.5).astype(np.float64)

    return X, y_binary


def save_augmented_data(X: np.ndarray, y: np.ndarray) -> str:
    """保存增强后的训练数据到文件

    Args:
        X: 特征矩阵
        y: 标签向量

    Returns:
        保存路径
    """
    os.makedirs(MODELS_DIR, exist_ok=True)
    np.savez_compressed(AUGMENTED_DATA_PATH, X=X, y=y)
    logger.info(
        "增强训练数据已保存",
        extra={
            "path": AUGMENTED_DATA_PATH,
            "samples": len(y),
            "features": X.shape[1],
            "positive": int(np.sum(y)),
            "negative": int(len(y) - np.sum(y)),
        },
    )
    return AUGMENTED_DATA_PATH


def load_augmented_data(path: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    """加载增强后的训练数据

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
    X = data["X"]
    y = data["y"]
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
# 主入口
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
    )

    logger.info("开始生成合成训练数据...")
    logger.info(f"特征数量: {NUM_FEATURES}")
    logger.info(f"特征名称: {FEATURE_NAMES}")
    logger.info(f"目标样本数: {DEFAULT_N_SAMPLES}")

    X, y = generate_training_data(n_samples=DEFAULT_N_SAMPLES)

    logger.info(f"生成完成: {len(y)} 样本")
    logger.info(f"正样本: {int(np.sum(y))}, 负样本: {int(len(y) - np.sum(y))}")

    # 特征统计
    for i, name in enumerate(FEATURE_NAMES):
        col = X[:, i]
        logger.info(
            f"  特征 [{i:2d}] {name:<20s}: "
            f"mean={col.mean():.4f}, std={col.std():.4f}, "
            f"min={col.min():.4f}, max={col.max():.4f}"
        )

    save_path = save_augmented_data(X, y)
    logger.info(f"数据已保存到: {save_path}")

    # 验证可加载
    X2, y2 = load_augmented_data()
    logger.info(f"验证加载: {len(y2)} 样本, 特征维度 {X2.shape[1]}")
    assert np.array_equal(X, X2), "数据不一致"
    assert np.array_equal(y, y2), "标签不一致"
    logger.info("数据生成完成 ✓")
