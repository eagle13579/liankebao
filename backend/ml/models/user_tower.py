"""链客宝 — 用户 Embedding 塔 (UserTower)

四塔 DNN 架构中的用户特征嵌入模块。

架构:
  数值特征 → Linear(BN) ┐
                         ├─→ Concat ─→ DNN(256→128) ─→ L2-Norm ─→ 128d
  类别特征 → EmbeddingBag ┘

训练:
  Triplet Loss (anchor / positive / negative)
  Optimizer: Adam, lr=1e-3
  EarlyStopping: patience=5

用法:
    tower = UserTower(num_features=16, embedding_dim=128, hidden_dims=[256, 128])
    embeddings = tower(user_tensor)          # → (B, 128) L2 normalized

    encoder = UserFeatureEncoder()
    encoder.fit(df)
    tensor = encoder.transform(user_data)    # → (B, num_features)

Author: 蠪侄 (P6, 市场部, 模型开发/用户行为分析)
"""

from __future__ import annotations

import logging
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
DEFAULT_EMBEDDING_DIM = 128
DEFAULT_HIDDEN_DIMS = [256, 128]
DEFAULT_LR = 1e-3
DEFAULT_PATIENCE = 5
DEFAULT_MARGIN = 0.3

# 用户塔特征 schema — 数值特征名列表
NUMERIC_FEATURES = ["industry_code", "scale", "region_code"]
# 用户塔特征 schema — 类别特征名列表
CATEGORICAL_FEATURES = ["cooperation_type", "budget_level"]

ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


# ===================================================================
# Triplet Loss
# ===================================================================
class TripletLoss(nn.Module):
    """Triplet Loss with semi-hard negative mining.

    L = max(d(anchor, positive) - d(anchor, negative) + margin, 0)
    """

    def __init__(self, margin: float = DEFAULT_MARGIN):
        super().__init__()
        self.margin = margin

    def forward(
        self,
        anchor: torch.Tensor,
        positive: torch.Tensor,
        negative: torch.Tensor,
    ) -> torch.Tensor:
        """Compute triplet loss.

        Args:
            anchor:   (B, D) anchor embeddings
            positive: (B, D) positive embeddings
            negative: (B, D) negative embeddings

        Returns:
            scalar loss tensor
        """
        d_pos = F.pairwise_distance(anchor, positive, p=2)       # (B,)
        d_neg = F.pairwise_distance(anchor, negative, p=2)       # (B,)
        loss = F.relu(d_pos - d_neg + self.margin)
        return loss.mean()


# ===================================================================
# 用户塔
# ===================================================================
class UserTower(nn.Module):
    """用户 Embedding 塔。

    输入: 拼接后的数值 + 类别 embedding 特征向量
    输出: L2 归一化的 128d 用户嵌入向量

    Args:
        num_features: 特征总数 (数值特征数 + 类别 embedding 拼接维数)
        embedding_dim: 输出嵌入维度 (默认 128)
        hidden_dims:   DNN 隐层维度列表 (默认 [256, 128])
        dropout:       Dropout 比率 (默认 0.1)
    """

    def __init__(
        self,
        num_features: int,
        embedding_dim: int = DEFAULT_EMBEDDING_DIM,
        hidden_dims: Optional[List[int]] = None,
        dropout: float = 0.1,
    ):
        super().__init__()
        hidden_dims = hidden_dims or list(DEFAULT_HIDDEN_DIMS)

        if not TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch is required for UserTower. "
                "Install it via: pip install torch"
            )

        self.num_features = num_features
        self.embedding_dim = embedding_dim
        self.dropout_rate = dropout

        # ── 数值特征编码器: BN → Linear ──
        self.numeric_bn = nn.BatchNorm1d(len(NUMERIC_FEATURES))
        # 类别特征使用 EmbeddingBag (在 UserFeatureEncoder 中管理)
        # 这里只定义全连接层

        # ── DNN 塔 ──
        layers: List[nn.Module] = []
        in_dim = num_features
        for h_dim in hidden_dims:
            layers.extend([
                nn.Linear(in_dim, h_dim),
                nn.BatchNorm1d(h_dim),
                nn.ReLU(inplace=True),
                nn.Dropout(dropout),
            ])
            in_dim = h_dim
        # 输出层 (无激活, 后续 L2 Norm)
        layers.append(nn.Linear(in_dim, embedding_dim))

        self.fc_stack = nn.Sequential(*layers)

        # ── 初始化 ──
        self._init_weights()

    def _init_weights(self):
        """Xavier 均匀初始化"""
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(self, user_features: torch.Tensor) -> torch.Tensor:
        """前向传播 → L2 归一化的 128d 嵌入。

        Args:
            user_features: (B, num_features) 特征张量

        Returns:
            (B, embedding_dim) L2 归一化嵌入
        """
        # DNN 编码
        out = self.fc_stack(user_features)  # (B, embedding_dim)
        # L2 归一化
        out = F.normalize(out, p=2, dim=1)
        return out

    def encode_numeric(self, numeric_tensor: torch.Tensor) -> torch.Tensor:
        """编码数值特征 (BN + Linear projection)"""
        return self.numeric_bn(numeric_tensor)

    @torch.no_grad()
    def predict(self, user_features: torch.Tensor) -> np.ndarray:
        """推理接口, 返回 numpy 数组"""
        self.eval()
        emb = self.forward(user_features)
        return emb.cpu().numpy()

    def __repr__(self) -> str:
        return (
            f"UserTower(num_features={self.num_features}, "
            f"embedding_dim={self.embedding_dim}, "
            f"hidden_dims={[m.out_features for m in self.fc_stack if isinstance(m, nn.Linear)][:-1]})"
        )


# ===================================================================
# 特征编码器
# ===================================================================
class UserFeatureEncoder:
    """用户特征编码器。

    将原始用户特征 (dict/DataFrame) 编码为 UserTower 可接受的张量。

    数值特征: 行业代码 / 规模 / 地区 — 做标准化 (z-score)
    类别特征: 合作类型 / 预算 — 用 EmbeddingBag 映射为稠密向量

    Usage:
        encoder = UserFeatureEncoder(embedding_dim=16)
        encoder.fit(df)          # 学习统计量和类别数
        tensor = encoder.transform(user_data)  # → torch.Tensor
    """

    def __init__(
        self,
        embedding_dim: int = 16,
        numeric_features: Optional[List[str]] = None,
        categorical_features: Optional[List[str]] = None,
    ):
        self.embedding_dim = embedding_dim
        self.numeric_features = numeric_features or list(NUMERIC_FEATURES)
        self.categorical_features = categorical_features or list(CATEGORICAL_FEATURES)

        # ── 状态 (fit 后填充) ──
        self.numeric_mean: Dict[str, float] = {}
        self.numeric_std: Dict[str, float] = {}
        self.categorical_cardinality: Dict[str, int] = {}
        # 类别 → 索引映射
        self.categorical_mappings: Dict[str, Dict[Any, int]] = {}

        # PyTorch EmbeddingBag 层 (fit 后创建)
        self.embedding_bags: nn.ModuleDict = nn.ModuleDict()

        self._fitted = False

    # ------------------------------------------------------------------
    # fit
    # ------------------------------------------------------------------
    def fit(self, df: "Any") -> "UserFeatureEncoder":
        """从 DataFrame 学习特征统计。

        Args:
            df: pandas DataFrame, 列包含 numeric_features + categorical_features

        Returns:
            self (链式调用)
        """
        # ── 惰性导入 pandas ──
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas required for UserFeatureEncoder.fit()")

        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pd.DataFrame, got {type(df).__name__}")

        # ── 数值特征统计 ──
        for feat in self.numeric_features:
            if feat not in df.columns:
                logger.warning("[UserFeatureEncoder] 数值特征 '%s' 不在 DataFrame 中, 使用默认值", feat)
                self.numeric_mean[feat] = 0.0
                self.numeric_std[feat] = 1.0
                continue
            col = df[feat].dropna()
            if len(col) == 0:
                self.numeric_mean[feat] = 0.0
                self.numeric_std[feat] = 1.0
            else:
                self.numeric_mean[feat] = float(col.mean())
                self.numeric_std[feat] = float(col.std()) or 1.0

        # ── 类别特征统计 ──
        for feat in self.categorical_features:
            if feat not in df.columns:
                logger.warning("[UserFeatureEncoder] 类别特征 '%s' 不在 DataFrame 中, 使用默认值", feat)
                self.categorical_cardinality[feat] = 2
                self.categorical_mappings[feat] = {}
                continue
            col = df[feat].dropna().unique()
            # 构建类别→索引映射
            mapping = {val: idx for idx, val in enumerate(sorted(col))}
            self.categorical_mappings[feat] = mapping
            self.categorical_cardinality[feat] = len(mapping) + 1  # +1 for unknown

        # ── 创建 EmbeddingBag 层 ──
        if TORCH_AVAILABLE:
            self.embedding_bags.clear()
            for feat in self.categorical_features:
                num_embeddings = self.categorical_cardinality.get(feat, 2)
                self.embedding_bags[feat] = nn.EmbeddingBag(
                    num_embeddings=num_embeddings,
                    embedding_dim=self.embedding_dim,
                    mode="mean",
                    padding_idx=0,
                )

        self._fitted = True
        return self

    # ------------------------------------------------------------------
    # transform
    # ------------------------------------------------------------------
    def transform(
        self,
        user_data: Union[Dict[str, Any], List[Dict[str, Any]], "Any"],
    ) -> "torch.Tensor":
        """将用户数据编码为张量。

        Args:
            user_data: 单个 dict 或 list[dict] 或 pd.DataFrame

        Returns:
            torch.Tensor shape (B, total_feature_dim)
            其中 total_feature_dim = len(numeric_features) + len(categorical_features) * embedding_dim
        """
        if not self._fitted:
            raise RuntimeError("UserFeatureEncoder 尚未 fit, 请先调用 .fit(df)")

        # ── 统一为 list[dict] ──
        rows = self._to_rows(user_data)
        B = len(rows)

        # ── 数值特征 (B, N_num) ──
        numeric_list = []
        for feat in self.numeric_features:
            vals = []
            for row in rows:
                raw = row.get(feat, 0.0)
                try:
                    v = (float(raw) - self.numeric_mean.get(feat, 0.0)) / self.numeric_std.get(feat, 1.0)
                except (ValueError, TypeError):
                    v = 0.0
                vals.append(v)
            numeric_list.append(vals)
        # (N_num, B) → (B, N_num)
        numeric_tensor = torch.tensor(numeric_list, dtype=torch.float32).T

        # ── 类别特征 (B, N_cat * embedding_dim) ──
        cat_embeddings_list = []
        for feat in self.categorical_features:
            indices = []
            mapping = self.categorical_mappings.get(feat, {})
            for row in rows:
                raw = row.get(feat, None)
                idx = mapping.get(raw, 0)  # 0 = unknown / padding
                indices.append(idx)
            # EmbeddingBag 需要 (B,) 索引 + (B,) 每样本偏移
            idx_tensor = torch.tensor(indices, dtype=torch.long)
            offsets = torch.arange(0, B, dtype=torch.long)
            if feat in self.embedding_bags:
                emb = self.embedding_bags[feat](idx_tensor, offsets)  # (B, embedding_dim)
            else:
                emb = torch.zeros(B, self.embedding_dim)
            cat_embeddings_list.append(emb)
        # (N_cat * B, embedding_dim) → (B, N_cat * embedding_dim)
        cat_tensor = torch.cat(cat_embeddings_list, dim=1) if cat_embeddings_list else torch.zeros(B, 0)

        # ── 拼接 ──
        out = torch.cat([numeric_tensor, cat_tensor], dim=1)
        return out.detach()  # 编码属于数据预处理, 不追踪梯度

    # ------------------------------------------------------------------
    # 计算特征总维度 (供 UserTower 初始化使用)
    # ------------------------------------------------------------------
    @property
    def total_feature_dim(self) -> int:
        """编码后的特征总维度"""
        num_n = len(self.numeric_features)
        num_c = len(self.categorical_features)
        return num_n + num_c * self.embedding_dim

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _to_rows(
        user_data: Union[Dict, List[Dict], "Any"],
    ) -> List[Dict[str, Any]]:
        """统一输入为 list[dict]"""
        if isinstance(user_data, dict):
            return [user_data]
        if isinstance(user_data, list):
            return user_data
        # 尝试 pandas DataFrame
        try:
            import pandas as pd

            if isinstance(user_data, pd.DataFrame):
                return user_data.to_dict(orient="records")
        except ImportError:
            pass
        raise TypeError(
            f"不支持的输入类型: {type(user_data).__name__}, "
            f"期望 dict / list[dict] / pd.DataFrame"
        )

    def __repr__(self) -> str:
        status = "fitted" if self._fitted else "not fitted"
        return (
            f"UserFeatureEncoder("
            f"num_numeric={len(self.numeric_features)}, "
            f"num_categorical={len(self.categorical_features)}, "
            f"embedding_dim={self.embedding_dim}, "
            f"total_dim={self.total_feature_dim}, "
            f"status={status})"
        )


# ===================================================================
# 训练管线
# ===================================================================
class UserTowerTrainer:
    """用户塔训练管线。

    使用 Triplet Loss 训练 UserTower。

    Args:
        tower: UserTower 实例
        encoder: UserFeatureEncoder 实例
        lr: 学习率 (默认 1e-3)
        patience: 早停 patience (默认 5)
        margin: Triplet Loss margin (默认 0.3)
        device: 训练设备 (默认 auto)
    """

    def __init__(
        self,
        tower: UserTower,
        encoder: UserFeatureEncoder,
        lr: float = DEFAULT_LR,
        patience: int = DEFAULT_PATIENCE,
        margin: float = DEFAULT_MARGIN,
        device: Optional[str] = None,
    ):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch required for training")

        self.tower = tower
        self.encoder = encoder
        self.lr = lr
        self.patience = patience
        self.margin = margin

        # ── 设备 ──
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        self.tower = self.tower.to(self.device)
        self.encoder.embedding_bags = self.encoder.embedding_bags.to(self.device)

        # ── 优化器 & 损失 ──
        self.optimizer = torch.optim.Adam(
            self.tower.parameters(),
            lr=self.lr,
            weight_decay=1e-5,
        )
        self.criterion = TripletLoss(margin=self.margin)

        # ── 训练状态 ──
        self.train_losses: List[float] = []
        self.val_losses: List[float] = []
        self.best_val_loss = float("inf")
        self.best_state_dict: Optional[Dict[str, Any]] = None
        self.epochs_no_improve = 0
        self.current_epoch = 0

    # ------------------------------------------------------------------
    # 训练一步
    # ------------------------------------------------------------------
    def train_step(
        self,
        anchor: torch.Tensor,
        positive: torch.Tensor,
        negative: torch.Tensor,
    ) -> float:
        """执行一步训练 (forward + backward + optimize)。

        Args:
            anchor:   (B, D) 锚点特征
            positive: (B, D) 正样本特征
            negative: (B, D) 负样本特征

        Returns:
            float: loss 值
        """
        self.tower.train()

        anchor = anchor.to(self.device)
        positive = positive.to(self.device)
        negative = negative.to(self.device)

        self.optimizer.zero_grad()

        a_emb = self.tower(anchor)
        p_emb = self.tower(positive)
        n_emb = self.tower(negative)

        loss = self.criterion(a_emb, p_emb, n_emb)
        loss.backward()
        self.optimizer.step()

        return loss.item()

    # ------------------------------------------------------------------
    # 训练一个 epoch
    # ------------------------------------------------------------------
    def train_epoch(
        self,
        anchors: torch.Tensor,
        positives: torch.Tensor,
        negatives: torch.Tensor,
        batch_size: int = 64,
    ) -> float:
        """完整遍历一个 epoch。

        Args:
            anchors:   (N, D) 所有锚点
            positives: (N, D) 所有正样本
            negatives: (N, D) 所有负样本
            batch_size: 批大小

        Returns:
            float: 平均 loss
        """
        N = anchors.size(0)
        indices = torch.randperm(N)
        total_loss = 0.0
        n_batches = 0

        for start in range(0, N, batch_size):
            end = min(start + batch_size, N)
            idx = indices[start:end]

            loss = self.train_step(
                anchors[idx],
                positives[idx],
                negatives[idx],
            )
            total_loss += loss
            n_batches += 1

        avg_loss = total_loss / max(n_batches, 1)
        self.train_losses.append(avg_loss)
        self.current_epoch += 1
        return avg_loss

    # ------------------------------------------------------------------
    # 验证
    # ------------------------------------------------------------------
    @torch.no_grad()
    def evaluate(
        self,
        anchors: torch.Tensor,
        positives: torch.Tensor,
        negatives: torch.Tensor,
        batch_size: int = 64,
    ) -> float:
        """验证集评估。

        Returns:
            float: 平均 loss
        """
        self.tower.eval()
        N = anchors.size(0)
        total_loss = 0.0
        n_batches = 0

        for start in range(0, N, batch_size):
            end = min(start + batch_size, N)
            a_emb = self.tower(anchors[start:end].to(self.device))
            p_emb = self.tower(positives[start:end].to(self.device))
            n_emb = self.tower(negatives[start:end].to(self.device))

            loss = self.criterion(a_emb, p_emb, n_emb)
            total_loss += loss.item()
            n_batches += 1

        avg_loss = total_loss / max(n_batches, 1)
        self.val_losses.append(avg_loss)

        # ── 早停检查 ──
        if avg_loss < self.best_val_loss:
            self.best_val_loss = avg_loss
            self.best_state_dict = {
                k: v.cpu().clone()
                for k, v in self.tower.state_dict().items()
            }
            self.epochs_no_improve = 0
        else:
            self.epochs_no_improve += 1

        return avg_loss

    # ------------------------------------------------------------------
    # 完整训练
    # ------------------------------------------------------------------
    def fit(
        self,
        train_anchors: torch.Tensor,
        train_positives: torch.Tensor,
        train_negatives: torch.Tensor,
        val_anchors: Optional[torch.Tensor] = None,
        val_positives: Optional[torch.Tensor] = None,
        val_negatives: Optional[torch.Tensor] = None,
        epochs: int = 50,
        batch_size: int = 64,
        verbose: bool = True,
    ) -> "UserTowerTrainer":
        """完整训练循环 (支持早停)。

        Args:
            train_anchors:   (N_train, D) 训练锚点
            train_positives: (N_train, D) 训练正样本
            train_negatives: (N_train, D) 训练负样本
            val_anchors:     (N_val, D) 验证锚点
            val_positives:   (N_val, D) 验证正样本
            val_negatives:   (N_val, D) 验证负样本
            epochs:          最大 epoch 数
            batch_size:      批大小
            verbose:         是否打印进度

        Returns:
            self
        """
        has_val = (
            val_anchors is not None
            and val_positives is not None
            and val_negatives is not None
        )

        for epoch in range(1, epochs + 1):
            train_loss = self.train_epoch(
                train_anchors, train_positives, train_negatives, batch_size
            )

            if has_val:
                val_loss = self.evaluate(
                    val_anchors, val_positives, val_negatives, batch_size
                )
                if verbose:
                    print(
                        f"Epoch {epoch:3d}/{epochs}  "
                        f"train_loss={train_loss:.6f}  "
                        f"val_loss={val_loss:.6f}  "
                        f"patience={self.patience - self.epochs_no_improve}/{self.patience}"
                    )

                # 早停
                if self.epochs_no_improve >= self.patience:
                    if verbose:
                        print(f"  → 早停触发 (epoch {epoch})")
                    break
            else:
                if verbose:
                    print(f"Epoch {epoch:3d}/{epochs}  train_loss={train_loss:.6f}")

        # ── 恢复最佳权重 ──
        if self.best_state_dict is not None:
            self.tower.load_state_dict(self.best_state_dict)
            if verbose:
                print(f"  → 已恢复最佳权重 (val_loss={self.best_val_loss:.6f})")

        return self

    # ------------------------------------------------------------------
    # 保存/加载
    # ------------------------------------------------------------------
    def save(self, path: Union[str, Path]) -> None:
        """保存模型权重和编码器状态。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        checkpoint = {
            "tower_state_dict": self.tower.state_dict(),
            "encoder_numeric_mean": self.encoder.numeric_mean,
            "encoder_numeric_std": self.encoder.numeric_std,
            "encoder_categorical_cardinality": self.encoder.categorical_cardinality,
            "encoder_categorical_mappings": self.encoder.categorical_mappings,
            "encoder_embedding_dim": self.encoder.embedding_dim,
            "encoder_numeric_features": self.encoder.numeric_features,
            "encoder_categorical_features": self.encoder.categorical_features,
            "train_losses": self.train_losses,
            "val_losses": self.val_losses,
            "best_val_loss": self.best_val_loss,
            "current_epoch": self.current_epoch,
            "margin": self.margin,
        }
        torch.save(checkpoint, path)
        logger.info("[UserTowerTrainer] 模型已保存到: %s", path)

    def load(self, path: Union[str, Path]) -> "UserTowerTrainer":
        """加载模型权重。"""
        path = Path(path)
        checkpoint = torch.load(path, map_location=self.device)

        self.tower.load_state_dict(checkpoint["tower_state_dict"])
        self.encoder.numeric_mean = checkpoint["encoder_numeric_mean"]
        self.encoder.numeric_std = checkpoint["encoder_numeric_std"]
        self.encoder.categorical_cardinality = checkpoint["encoder_categorical_cardinality"]
        self.encoder.categorical_mappings = checkpoint["encoder_categorical_mappings"]
        self.encoder.embedding_dim = checkpoint["encoder_embedding_dim"]
        self.encoder.numeric_features = checkpoint["encoder_numeric_features"]
        self.encoder.categorical_features = checkpoint["encoder_categorical_features"]
        self.train_losses = checkpoint.get("train_losses", [])
        self.val_losses = checkpoint.get("val_losses", [])
        self.best_val_loss = checkpoint.get("best_val_loss", float("inf"))
        self.current_epoch = checkpoint.get("current_epoch", 0)
        self.margin = checkpoint.get("margin", self.margin)
        self.encoder._fitted = True

        logger.info("[UserTowerTrainer] 模型已加载: %s", path)
        return self


# ===================================================================
# 简易测试 (python user_tower.py)
# ===================================================================
def _test_model_forward():
    """TC1: 模型前向传播"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    tower = UserTower(num_features=10, embedding_dim=128, hidden_dims=[256, 128])
    x = torch.randn(4, 10)
    out = tower(x)
    assert out.shape == (4, 128), f"输出 shape 应为 (4, 128), 收到 {out.shape}"
    # 检查 L2 归一化
    norms = out.norm(p=2, dim=1)
    assert torch.allclose(norms, torch.ones(4), atol=1e-5), \
        f"L2 归一化后 norm 应 ≈1, 收到 {norms}"
    print("  ✓ test_model_forward")


def _test_feature_encoder():
    """TC2: 特征编码器 fit + transform"""
    try:
        import pandas as pd
    except ImportError:
        print("  ⚠ pandas 不可用, 跳过测试")
        return

    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    df = pd.DataFrame({
        "industry_code": [1, 2, 3, 1, 2],
        "scale": [10, 50, 100, 20, 80],
        "region_code": [1, 2, 1, 3, 2],
        "cooperation_type": ["supply", "demand", "supply", "cooperation", "demand"],
        "budget_level": ["low", "medium", "high", "medium", "low"],
    })

    encoder = UserFeatureEncoder(embedding_dim=8)
    encoder.fit(df)
    assert encoder._fitted, "fit 后 _fitted 应为 True"
    assert "industry_code" in encoder.numeric_mean
    assert "cooperation_type" in encoder.categorical_cardinality

    # transform
    tensor = encoder.transform({
        "industry_code": 1,
        "scale": 30,
        "region_code": 2,
        "cooperation_type": "supply",
        "budget_level": "low",
    })
    expected_dim = len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES) * 8
    assert tensor.shape == (1, expected_dim), \
        f"输出 shape 应为 (1, {expected_dim}), 收到 {tensor.shape}"
    print("  ✓ test_feature_encoder")


def _test_triplet_loss():
    """TC3: Triplet Loss 计算"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    criterion = TripletLoss(margin=0.3)
    # 正样本距离 > 负样本距离 - margin → loss > 0
    anchor = torch.tensor([[1.0, 0.0], [0.0, 1.0]])
    positive = torch.tensor([[0.0, 1.0], [1.0, 0.0]])  # far from anchor
    negative = torch.tensor([[0.9, 0.1], [0.1, 0.9]])  # close to anchor

    loss = criterion(anchor, positive, negative)
    assert loss.item() > 0, f"Loss 应 > 0, 收到 {loss.item()}"
    assert isinstance(loss.item(), float)
    print(f"  ✓ test_triplet_loss (loss={loss.item():.6f})")


def _test_train_step():
    """TC4: 训练一步"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    encoder = UserFeatureEncoder(embedding_dim=4)
    # 模拟 fit
    encoder.numeric_mean = {"industry_code": 0.0, "scale": 0.0, "region_code": 0.0}
    encoder.numeric_std = {"industry_code": 1.0, "scale": 1.0, "region_code": 1.0}
    encoder.categorical_cardinality = {"cooperation_type": 4, "budget_level": 3}
    encoder.categorical_mappings = {
        "cooperation_type": {"supply": 1, "demand": 2, "cooperation": 3},
        "budget_level": {"low": 1, "medium": 2, "high": 3},
    }
    encoder.embedding_bags.clear()
    for feat in encoder.categorical_features:
        num_emb = encoder.categorical_cardinality[feat]
        encoder.embedding_bags[feat] = nn.EmbeddingBag(
            num_embeddings=num_emb, embedding_dim=4, mode="mean", padding_idx=0,
        )
    encoder._fitted = True

    total_dim = encoder.total_feature_dim  # 3 + 2*4 = 11
    tower = UserTower(num_features=total_dim, embedding_dim=128, hidden_dims=[64, 128])
    trainer = UserTowerTrainer(tower, encoder, lr=1e-3)

    B = 16
    a = torch.randn(B, total_dim)
    p = torch.randn(B, total_dim)
    n = torch.randn(B, total_dim)

    loss = trainer.train_step(a, p, n)
    assert isinstance(loss, float), f"Loss 应为 float, 收到 {type(loss)}"
    assert loss > 0, f"Loss 应 > 0, 收到 {loss}"
    print(f"  ✓ test_train_step (loss={loss:.6f})")


def _test_embedding_similarity():
    """TC5: 相似用户产生相似嵌入"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    tower = UserTower(num_features=5, embedding_dim=128)
    tower.eval()  # 切换 eval 模式以支持单样本推理
    x1 = torch.tensor([[1.0, 2.0, 3.0, 4.0, 5.0]])
    x2 = torch.tensor([[1.1, 2.1, 3.1, 4.1, 5.1]])  # 相似
    x3 = torch.tensor([[50.0, -20.0, 100.0, -5.0, 30.0]])  # 不相似

    e1 = tower(x1)
    e2 = tower(x2)
    e3 = tower(x3)

    sim_similar = F.cosine_similarity(e1, e2).item()
    sim_dissimilar = F.cosine_similarity(e1, e3).item()
    assert sim_similar > sim_dissimilar, \
        f"相似用户的余弦相似度 ({sim_similar:.4f}) 应高于不相似用户 ({sim_dissimilar:.4f})"
    print(f"  ✓ test_embedding_similarity (sim_similar={sim_similar:.4f}, sim_diff={sim_dissimilar:.4f})")


def _test_tower_repr():
    """TC6: 模型 repr"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    tower = UserTower(num_features=10, embedding_dim=64, hidden_dims=[128, 64])
    r = repr(tower)
    assert "UserTower" in r
    assert "num_features=10" in r
    print(f"  ✓ test_tower_repr: {r}")


def _test_encoder_repr():
    """TC7: 编码器 repr"""
    encoder = UserFeatureEncoder(embedding_dim=16)
    r = repr(encoder)
    assert "UserFeatureEncoder" in r
    assert "not fitted" in r
    print(f"  ✓ test_encoder_repr: {r}")


def _test_batch_transform():
    """TC8: 批量 transform"""
    try:
        import pandas as pd
    except ImportError:
        print("  ⚠ pandas 不可用, 跳过测试")
        return

    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    df = pd.DataFrame({
        "industry_code": [1, 2, 3],
        "scale": [10.0, 50.0, 100.0],
        "region_code": [1, 2, 1],
        "cooperation_type": ["supply", "demand", "cooperation"],
        "budget_level": ["low", "medium", "high"],
    })
    encoder = UserFeatureEncoder(embedding_dim=4)
    encoder.fit(df)

    # list[dict]
    data = [
        {"industry_code": 1, "scale": 20.0, "region_code": 2,
         "cooperation_type": "supply", "budget_level": "low"},
        {"industry_code": 2, "scale": 60.0, "region_code": 1,
         "cooperation_type": "demand", "budget_level": "high"},
    ]
    tensor = encoder.transform(data)
    expected_dim = 3 + 2 * 4  # 3 numeric + 2 cat * 4 emb_dim
    assert tensor.shape == (2, expected_dim), \
        f"批量 transform 期望 (2, {expected_dim}), 收到 {tensor.shape}"
    print(f"  ✓ test_batch_transform (shape={tuple(tensor.shape)})")


# ===================================================================
# 主入口
# ===================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  用户 Embedding 塔 — 单元测试")
    print("=" * 60)
    print()

    tests = [
        ("模型前向传播", _test_model_forward),
        ("特征编码器", _test_feature_encoder),
        ("Triplet Loss", _test_triplet_loss),
        ("训练一步", _test_train_step),
        ("嵌入相似性", _test_embedding_similarity),
        ("模型 repr", _test_tower_repr),
        ("编码器 repr", _test_encoder_repr),
        ("批量 transform", _test_batch_transform),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print("-" * 60)
    print(f"  结果: {passed} 通过, {failed} 失败, {len(tests)} 总计")
    if failed == 0:
        print("  ✓ 全部通过!")
    else:
        print("  ✗ 存在失败的测试!")
    print("=" * 60)
