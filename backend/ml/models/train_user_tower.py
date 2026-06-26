"""链客宝 — 用户塔训练脚本

从反馈数据构建 Triplet 样本, 训练 UserTower。

用法:
    python -m ml.models.train_user_tower
    python -m ml.models.train_user_tower --epochs 20 --batch-size 128
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

# ── 确保能找到 ml 模块 ──
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

try:
    import torch
except ImportError:
    print("错误: 需要 PyTorch. 请执行: pip install torch")
    sys.exit(1)

from ml.models.user_tower import (
    UserTower,
    UserFeatureEncoder,
    UserTowerTrainer,
    NUMERIC_FEATURES,
    CATEGORICAL_FEATURES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
DEFAULT_EPOCHS = 50
DEFAULT_BATCH_SIZE = 64
DEFAULT_EMBEDDING_DIM = 128
DEFAULT_LR = 1e-3
DEFAULT_PATIENCE = 5
MODEL_SAVE_DIR = Path(__file__).resolve().parent / "checkpoints"


# ===================================================================
# 数据生成 (模拟反馈数据 → Triplet)
# ===================================================================
def generate_synthetic_feedback(n_samples: int = 1000, seed: int = 42) -> "pd.DataFrame":
    """生成模拟用户反馈数据用于训练。

    Args:
        n_samples: 样本数
        seed:      随机种子

    Returns:
        pd.DataFrame, 包含用户特征列 + 反馈标签
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas required for data generation")

    rng = np.random.RandomState(seed)

    df = pd.DataFrame({
        # ── 数值特征 ──
        "industry_code": rng.randint(1, 21, size=n_samples),       # 行业代码 1~20
        "scale":         rng.choice([1, 10, 50, 100, 500, 1000], size=n_samples),  # 规模
        "region_code":   rng.randint(1, 35, size=n_samples),       # 地区代码 1~34
        # ── 类别特征 ──
        "cooperation_type": rng.choice(
            ["supply", "demand", "cooperation", "investment"], size=n_samples
        ),
        "budget_level": rng.choice(
            ["low", "medium", "high", "premium"], size=n_samples
        ),
        # ── 反馈标签 (用于构建 Triplet) ──
        "feedback_score": rng.choice([1, 2, 3, 4, 5], size=n_samples, p=[0.1, 0.1, 0.2, 0.3, 0.3]),
    })
    return df


def build_triplets_from_feedback(
    df: "pd.DataFrame",
    encoder: UserFeatureEncoder,
    pos_threshold: int = 4,
    neg_threshold: int = 2,
    seed: int = 42,
) -> tuple:
    """从反馈 DataFrame 构建 Triplet (锚点, 正样本, 负样本)。

    - 正样本: feedback_score >= pos_threshold
    - 负样本: feedback_score <= neg_threshold
    - 锚点:   与正样本对应的用户特征

    Returns:
        (anchors, positives, negatives) 三个 torch.Tensor
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas required")

    rng = np.random.RandomState(seed)

    pos_df = df[df["feedback_score"] >= pos_threshold].copy()
    neg_df = df[df["feedback_score"] <= neg_threshold].copy()

    if len(pos_df) == 0 or len(neg_df) == 0:
        raise ValueError(
            f"正样本数={len(pos_df)}, 负样本数={len(neg_df)}, "
            f"无法构建 Triplet"
        )

    # 锚点 = 正样本 (用户特征)
    anchors = pos_df.drop(columns=["feedback_score"]).reset_index(drop=True)

    # 为正样本随机匹配负样本 (半硬负采样)
    n = len(anchors)
    neg_indices = rng.randint(0, len(neg_df), size=n)
    negatives = neg_df.iloc[neg_indices].drop(columns=["feedback_score"]).reset_index(drop=True)

    # 正样本 = 锚点自身加小噪声 (模拟"相似但不完全相同")
    positives = anchors.copy()
    for col in encoder.numeric_features:
        if col in positives.columns:
            noise = rng.randn(n) * 0.05 * positives[col].std()
            positives[col] = positives[col] + noise
            # 保持数值有效
            positives[col] = positives[col].clip(lower=0)

    # 编码
    a_tensor = encoder.transform(anchors)
    p_tensor = encoder.transform(positives)
    n_tensor = encoder.transform(negatives)

    return a_tensor, p_tensor, n_tensor


# ===================================================================
# 训练入口
# ===================================================================
def train(args: argparse.Namespace) -> UserTowerTrainer:
    """执行用户塔训练。

    Args:
        args: 命令行参数

    Returns:
        UserTowerTrainer 实例 (已训练)
    """
    print("=" * 60)
    print("  用户 Embedding 塔 — 训练")
    print("=" * 60)
    print()

    # ── 1. 生成数据 ──
    print("[1/5] 生成模拟反馈数据...")
    df = generate_synthetic_feedback(n_samples=args.n_samples, seed=42)
    print(f"       → {len(df)} 条记录, 正样本阈值≥{args.pos_threshold}, 负样本阈值≤{args.neg_threshold}")

    # ── 2. 特征编码器 ──
    print("[2/5] 训练特征编码器...")
    encoder = UserFeatureEncoder(embedding_dim=args.cat_embedding_dim)
    encoder.fit(df)
    print(f"       → {encoder}")
    print(f"       → 特征总维度: {encoder.total_feature_dim}")

    # ── 3. 构建 Triplet ──
    print("[3/5] 构建 Triplet 数据集...")
    a_tensor, p_tensor, n_tensor = build_triplets_from_feedback(
        df, encoder,
        pos_threshold=args.pos_threshold,
        neg_threshold=args.neg_threshold,
        seed=42,
    )
    N = a_tensor.size(0)
    split = int(N * 0.8)
    train_data = (a_tensor[:split], p_tensor[:split], n_tensor[:split])
    val_data = (a_tensor[split:], p_tensor[split:], n_tensor[split:])
    print(f"       → 训练集: {split} triplets, 验证集: {N - split} triplets")

    # ── 4. 构建模型 ──
    print("[4/5] 构建 UserTower 模型...")
    tower = UserTower(
        num_features=encoder.total_feature_dim,
        embedding_dim=args.embedding_dim,
        hidden_dims=[int(d) for d in args.hidden_dims.split(",")],
        dropout=args.dropout,
    )
    print(f"       → {tower}")
    print(f"       → 参数量: {sum(p.numel() for p in tower.parameters()):,}")

    # ── 5. 训练 ──
    print("[5/5] 开始训练...")
    trainer = UserTowerTrainer(
        tower=tower,
        encoder=encoder,
        lr=args.lr,
        patience=args.patience,
        margin=args.margin,
    )
    trainer.fit(
        train_anchors=train_data[0],
        train_positives=train_data[1],
        train_negatives=train_data[2],
        val_anchors=val_data[0],
        val_positives=val_data[1],
        val_negatives=val_data[2],
        epochs=args.epochs,
        batch_size=args.batch_size,
        verbose=True,
    )

    # ── 保存 ──
    if args.save_dir:
        save_path = Path(args.save_dir)
    else:
        save_path = MODEL_SAVE_DIR
    save_path.mkdir(parents=True, exist_ok=True)
    model_path = save_path / "user_tower.pt"
    trainer.save(str(model_path))
    print(f"\n  → 模型已保存: {model_path}")

    # ── 验证推理 ──
    print("\n  → 推理示例:")
    sample = a_tensor[:3]
    embeddings = trainer.tower.predict(sample)
    for i, emb in enumerate(embeddings):
        norm = np.linalg.norm(emb)
        print(f"      用户 {i+1}: norm={norm:.6f}, dim={emb.shape[0]}")

    print()
    print("=" * 60)
    print("  训练完成!")
    print("=" * 60)
    return trainer


# ===================================================================
# CLI
# ===================================================================
def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="链客宝 — 用户塔训练脚本",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS,
                        help="最大训练 epoch 数")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help="批大小")
    parser.add_argument("--lr", type=float, default=DEFAULT_LR,
                        help="学习率")
    parser.add_argument("--embedding-dim", type=int, default=DEFAULT_EMBEDDING_DIM,
                        help="用户嵌入维度")
    parser.add_argument("--cat-embedding-dim", type=int, default=16,
                        help="类别特征 EmbeddingBag 维度")
    parser.add_argument("--hidden-dims", type=str, default="256,128",
                        help="DNN 隐层维度, 逗号分隔")
    parser.add_argument("--dropout", type=float, default=0.1,
                        help="Dropout 比率")
    parser.add_argument("--patience", type=int, default=DEFAULT_PATIENCE,
                        help="早停 patience")
    parser.add_argument("--margin", type=float, default=0.3,
                        help="Triplet Loss margin")
    parser.add_argument("--n-samples", type=int, default=2000,
                        help="模拟数据样本数")
    parser.add_argument("--pos-threshold", type=int, default=4,
                        help="正样本评分阈值 (≥)")
    parser.add_argument("--neg-threshold", type=int, default=2,
                        help="负样本评分阈值 (≤)")
    parser.add_argument("--save-dir", type=str, default=None,
                        help="模型保存目录 (默认: ml/models/checkpoints/)")
    parser.add_argument("--seed", type=int, default=42,
                        help="随机种子")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    train(args)
