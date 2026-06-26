"""链客宝 — 行为序列塔 (BehaviorTower)

四塔 DNN 架构中的用户行为序列嵌入模块。

架构:
  行为序列 → Embedding → TransformerEncoder → MeanPool → Linear(128) → L2-Norm → 128d

行为类型:
  - match: 匹配行为 (查看/收藏/沟通)
  - browse: 浏览行为 (浏览页面/查看详情)
  - feedback: 反馈行为 (点赞/评论/举报)

用法:
    tower = BehaviorTower(max_seq_len=50, feature_dim=32, hidden_dim=128, nhead=4, num_layers=2)
    behavior_emb = tower(behavior_tensor)  # → (B, 128) L2 normalized

    encoder = BehaviorSequenceEncoder()
    encoder.fit(df)
    tensor = encoder.transform(behavior_data)  # → (B, max_seq_len, feature_dim)

Author: 长乘 (P6, 内容部, 风格visionary适合组合创新)
"""

from __future__ import annotations

import logging
import math
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
DEFAULT_MAX_SEQ_LEN = 50
DEFAULT_FEATURE_DIM = 32
DEFAULT_HIDDEN_DIM = 128
DEFAULT_NHEAD = 4
DEFAULT_NUM_LAYERS = 2

# 行为类型编码
BEHAVIOR_TYPE_MAP = {
    "view": 0,
    "browse": 1,
    "search": 2,
    "match_view": 3,
    "match_favorite": 4,
    "match_contact": 5,
    "feedback_like": 6,
    "feedback_comment": 7,
    "feedback_report": 8,
    "share": 9,
}

# 行为序列特征维度 (embedding 维度)
BEHAVIOR_FEATURE_NAMES = [
    "behavior_type",     # 行为类型 (分类 → embedding)
    "timestamp_gap",     # 距上次行为的时间间隔 (数值)
    "duration",          # 行为持续时间/停留时长 (数值)
    "target_id",         # 目标企业 ID (分类 → embedding)
    "action_value",      # 行为价值权重 (数值)
]


# ===================================================================
# 行为塔
# ===================================================================
class BehaviorTower(nn.Module):
    """行为序列 Embedding 塔。

    输入: (B, max_seq_len, feature_dim) 行为序列张量
    输出: L2 归一化的 128d 行为模式嵌入向量

    Args:
        max_seq_len: 最大序列长度 (默认 50)
        feature_dim:  每步行为特征维度 (默认 32)
        hidden_dim:   Transformer 隐层维度 (默认 128)
        nhead:        Multi-head attention 头数 (默认 4)
        num_layers:   Transformer encoder 层数 (默认 2)
        dropout:      Dropout 比率 (默认 0.1)
    """

    def __init__(
        self,
        max_seq_len: int = DEFAULT_MAX_SEQ_LEN,
        feature_dim: int = DEFAULT_FEATURE_DIM,
        hidden_dim: int = DEFAULT_HIDDEN_DIM,
        nhead: int = DEFAULT_NHEAD,
        num_layers: int = DEFAULT_NUM_LAYERS,
        dropout: float = 0.1,
    ):
        super().__init__()

        if not TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch is required for BehaviorTower. "
                "Install it via: pip install torch"
            )

        self.max_seq_len = max_seq_len
        self.feature_dim = feature_dim
        self.hidden_dim = hidden_dim

        # ── 输入投影: feature_dim → hidden_dim ──
        self.input_proj = nn.Linear(feature_dim, hidden_dim)

        # ── 位置编码 (可学习) ──
        self.pos_embedding = nn.Parameter(
            torch.randn(1, max_seq_len, hidden_dim) * 0.1
        )

        # ── Transformer Encoder ──
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=nhead,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            activation="relu",
            batch_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(
            encoder_layer,
            num_layers=num_layers,
        )

        # ── 序列聚合: Mean Pooling → Linear ──
        self.pool_proj = nn.Linear(hidden_dim, hidden_dim)

        # ── 输出层 → 128d ──
        self.output_proj = nn.Linear(hidden_dim, DEFAULT_HIDDEN_DIM)

        # ── 掩码 Token (用于填充位置) ──
        self.mask_token = nn.Parameter(torch.zeros(1, 1, feature_dim))

        # ── 初始化 ──
        self._init_weights()

    def _init_weights(self):
        """Xavier 初始化"""
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(
        self,
        behavior_sequence: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """前向传播 → L2 归一化的 128d 行为嵌入。

        Args:
            behavior_sequence: (B, max_seq_len, feature_dim) 行为序列
            mask: (B, max_seq_len) 布尔掩码, True=有效, False=填充

        Returns:
            (B, 128) L2 归一化嵌入
        """
        B, S, D = behavior_sequence.shape

        # ── 输入投影 + 位置编码 ──
        x = self.input_proj(behavior_sequence)  # (B, S, hidden_dim)
        x = x + self.pos_embedding[:, :S, :]

        # ── Transformer Encoder ──
        # 创建 attention mask: True = 需要忽略的位置
        if mask is not None:
            # mask: True=有效 → 转为 key_padding_mask: True=填充则忽略
            key_padding_mask = ~mask  # (B, S)
        else:
            key_padding_mask = None

        x = self.transformer_encoder(
            x,
            src_key_padding_mask=key_padding_mask,
        )  # (B, S, hidden_dim)

        # ── 序列聚合: 对有效位置做 mean pooling ──
        if mask is not None:
            mask_expanded = mask.unsqueeze(-1).float()  # (B, S, 1)
            x = x * mask_expanded
            seq_len = mask.sum(dim=1, keepdim=True).clamp(min=1)  # (B, 1)
            x_pooled = x.sum(dim=1) / seq_len  # (B, hidden_dim)
        else:
            x_pooled = x.mean(dim=1)  # (B, hidden_dim)

        # ── 输出投影 ──
        out = self.output_proj(self.pool_proj(x_pooled))  # (B, 128)

        # L2 归一化
        out = F.normalize(out, p=2, dim=1)
        return out

    @torch.no_grad()
    def predict(
        self,
        behavior_sequence: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
    ) -> np.ndarray:
        """推理接口, 返回 numpy 数组"""
        self.eval()
        emb = self.forward(behavior_sequence, mask)
        return emb.cpu().numpy()

    def __repr__(self) -> str:
        return (
            f"BehaviorTower(max_seq_len={self.max_seq_len}, "
            f"feature_dim={self.feature_dim}, "
            f"hidden_dim={self.hidden_dim})"
        )


# ===================================================================
# 行为序列编码器
# ===================================================================
class BehaviorSequenceEncoder:
    """行为序列编码器。

    将原始行为序列 (list[dict]) 编码为 BehaviorTower 可接受的张量。

    特征处理:
      - behavior_type: 类别 → embedding lookup
      - timestamp_gap: 数值 → 标准化
      - duration:      数值 → 标准化 (log 变换后)
      - target_id:     类别 → embedding lookup
      - action_value:  数值 → 标准化

    Usage:
        encoder = BehaviorSequenceEncoder(max_seq_len=50, embedding_dim=8)
        encoder.fit(df)
        tensor, mask = encoder.transform(behavior_data)
    """

    def __init__(
        self,
        max_seq_len: int = DEFAULT_MAX_SEQ_LEN,
        feature_dim: int = DEFAULT_FEATURE_DIM,
        numeric_features: Optional[List[str]] = None,
        categorical_features: Optional[List[str]] = None,
    ):
        self.max_seq_len = max_seq_len
        self.feature_dim = feature_dim
        self.numeric_features = numeric_features or [
            "timestamp_gap", "duration", "action_value",
        ]
        self.categorical_features = categorical_features or [
            "behavior_type", "target_id",
        ]

        # ── 状态 (fit 后填充) ──
        self.numeric_mean: Dict[str, float] = {}
        self.numeric_std: Dict[str, float] = {}
        self.categorical_cardinality: Dict[str, int] = {}
        self.categorical_mappings: Dict[str, Dict[Any, int]] = {}

        # embedding 层 (fit 后创建)
        self.embeddings: nn.ModuleDict = nn.ModuleDict()
        self.cat_embedding_dim = 8  # 每个类别特征的嵌入维度

        self._fitted = False

    # ------------------------------------------------------------------
    # fit
    # ------------------------------------------------------------------
    def fit(self, df: "Any") -> "BehaviorSequenceEncoder":
        """从 DataFrame 学习特征统计。

        Args:
            df: pandas DataFrame, 列为 ***扁平化*** 的行为特征
                (每行代表一次行为, 包含 numeric_features + categorical_features)

        Returns:
            self (链式调用)
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas required for BehaviorSequenceEncoder.fit()")

        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pd.DataFrame, got {type(df).__name__}")

        # ── 数值特征统计 ──
        for feat in self.numeric_features:
            if feat not in df.columns:
                logger.warning("[BehaviorSequenceEncoder] 数值特征 '%s' 不在 DataFrame 中, 使用默认值", feat)
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
                logger.warning("[BehaviorSequenceEncoder] 类别特征 '%s' 不在 DataFrame 中, 使用默认值", feat)
                self.categorical_cardinality[feat] = 2
                self.categorical_mappings[feat] = {}
                continue
            col = df[feat].dropna().unique()
            mapping = {}
            # behavior_type 使用预定义映射
            if feat == "behavior_type":
                for val in col:
                    mapping[val] = BEHAVIOR_TYPE_MAP.get(val, 0)
                # 确保所有预定义类型都在映射中
                for k, v in BEHAVIOR_TYPE_MAP.items():
                    if k not in mapping:
                        mapping[k] = v
            else:
                mapping = {val: idx + 1 for idx, val in enumerate(sorted(col))}
            self.categorical_mappings[feat] = mapping
            self.categorical_cardinality[feat] = len(mapping) + 1  # +1 for unknown

        # ── 创建 Embedding 层 ──
        if TORCH_AVAILABLE:
            self.embeddings.clear()
            for feat in self.categorical_features:
                num_embeddings = self.categorical_cardinality.get(feat, 2)
                self.embeddings[feat] = nn.Embedding(
                    num_embeddings=num_embeddings,
                    embedding_dim=self.cat_embedding_dim,
                    padding_idx=0,
                )

        self._fitted = True
        return self

    # ------------------------------------------------------------------
    # transform
    # ------------------------------------------------------------------
    def transform(
        self,
        behavior_sequences: Union[
            Dict[str, Any],                   # 单用户单序列
            List[Dict[str, Any]],             # 单用户的多个行为 (行为列表)
            List[List[Dict[str, Any]]],        # 多用户的多个行为
        ],
    ) -> Tuple["torch.Tensor", "torch.Tensor"]:
        """将行为序列数据编码为张量。

        Args:
            behavior_sequences: 行为序列数据
                - Dict: {behavior_type, timestamp_gap, duration, target_id, action_value}
                  (单条行为, 自动转为单元素序列)
                - List[Dict]: 单用户的行为序列
                - List[List[Dict]]: 多用户的行为序列

        Returns:
            (tensor, mask):
                tensor: (B, max_seq_len, feature_dim) 行为序列张量
                mask: (B, max_seq_len) 布尔掩码, True=有效
        """
        if not self._fitted:
            raise RuntimeError("BehaviorSequenceEncoder 尚未 fit, 请先调用 .fit(df)")

        # ── 统一为 List[List[Dict]] ──
        sequences = self._to_sequences(behavior_sequences)
        B = len(sequences)

        # ── 构建每个用户的特征序列 ──
        tensor_list = []
        mask_list = []

        for seq in sequences:
            # 截断或填充至 max_seq_len
            if len(seq) > self.max_seq_len:
                seq = seq[-self.max_seq_len:]  # 取最近的 N 条
            S = len(seq)

            # 构建特征矩阵 (S, feature_dim)
            features = self._encode_sequence(seq)
            tensor_list.append(features)
            mask_list.append(torch.ones(S, dtype=torch.bool))

        # ── 填充到统一长度 ──
        out_tensors = []
        out_masks = []
        for feat, m in zip(tensor_list, mask_list):
            S = feat.size(0)
            if S < self.max_seq_len:
                pad_len = self.max_seq_len - S
                # 填充零
                pad_tensor = torch.zeros(pad_len, self.feature_dim)
                feat = torch.cat([feat, pad_tensor], dim=0)
                pad_mask = torch.zeros(pad_len, dtype=torch.bool)
                m = torch.cat([m, pad_mask], dim=0)
            out_tensors.append(feat.unsqueeze(0))  # (1, max_seq_len, D)
            out_masks.append(m.unsqueeze(0))       # (1, max_seq_len)

        result = torch.cat(out_tensors, dim=0)  # (B, max_seq_len, D)
        mask_result = torch.cat(out_masks, dim=0)  # (B, max_seq_len)
        return result.detach(), mask_result.detach()

    # ------------------------------------------------------------------
    # 内部: 序列编码
    # ------------------------------------------------------------------
    def _encode_sequence(self, seq: List[Dict[str, Any]]) -> "torch.Tensor":
        """编码单条行为序列 → (S, feature_dim)"""
        S = len(seq)
        feat_list = []

        # 数值特征 (S, N_num)
        for feat in self.numeric_features:
            vals = []
            for row in seq:
                raw = row.get(feat, 0.0)
                try:
                    v = float(raw)
                except (ValueError, TypeError):
                    v = 0.0
                # duration 做 log 变换
                if feat == "duration" and v > 0:
                    v = math.log1p(v)
                mean_v = self.numeric_mean.get(feat, 0.0)
                std_v = self.numeric_std.get(feat, 1.0)
                vals.append((v - mean_v) / std_v)
            feat_list.append(torch.tensor(vals, dtype=torch.float32).unsqueeze(1))  # (S, 1)

        # 类别特征 (S, cat_embedding_dim)
        for feat in self.categorical_features:
            indices = []
            mapping = self.categorical_mappings.get(feat, {})
            for row in seq:
                raw = row.get(feat, None)
                idx = mapping.get(raw, 0)  # 0 = unknown / padding
                indices.append(idx)
            idx_tensor = torch.tensor(indices, dtype=torch.long)
            if feat in self.embeddings:
                emb = self.embeddings[feat](idx_tensor)  # (S, cat_embedding_dim)
            else:
                emb = torch.zeros(S, self.cat_embedding_dim)
            feat_list.append(emb)

        # 拼接: (S, N_num + N_cat * cat_embedding_dim)
        out = torch.cat(feat_list, dim=1)  # (S, feature_dim)

        # 如果拼接维度 < feature_dim, 补零
        if out.size(1) < self.feature_dim:
            pad = torch.zeros(S, self.feature_dim - out.size(1))
            out = torch.cat([out, pad], dim=1)
        # 如果拼接维度 > feature_dim, 截断
        elif out.size(1) > self.feature_dim:
            out = out[:, :self.feature_dim]

        return out

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _to_sequences(
        data: Union[Dict, List[Dict], List[List[Dict]]],
    ) -> List[List[Dict[str, Any]]]:
        """统一输入为 List[List[Dict]]"""
        if isinstance(data, dict):
            # 单条行为 → 1 用户, 1 行为
            return [[data]]
        if isinstance(data, list):
            if not data:
                return [[]]
            if isinstance(data[0], dict):
                # List[Dict] → 1 用户, 多个行为
                return [data]  # type: ignore
            if isinstance(data[0], list):
                # List[List[Dict]] → 多个用户
                return data  # type: ignore
        raise TypeError(
            f"不支持的输入类型: {type(data).__name__}, "
            f"期望 Dict / List[Dict] / List[List[Dict]]"
        )

    def __repr__(self) -> str:
        status = "fitted" if self._fitted else "not fitted"
        return (
            f"BehaviorSequenceEncoder("
            f"max_seq_len={self.max_seq_len}, "
            f"feature_dim={self.feature_dim}, "
            f"status={status})"
        )


# ===================================================================
# 简易测试 (python behavior_tower.py)
# ===================================================================
def _test_model_forward():
    """TC1: 模型前向传播"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    tower = BehaviorTower(max_seq_len=50, feature_dim=32, hidden_dim=128)
    x = torch.randn(4, 50, 32)
    out = tower(x)
    assert out.shape == (4, 128), f"输出 shape 应为 (4, 128), 收到 {out.shape}"
    norms = out.norm(p=2, dim=1)
    assert torch.allclose(norms, torch.ones(4), atol=1e-5), \
        f"L2 归一化后 norm 应 ≈1, 收到 {norms}"
    print("  ✓ test_model_forward")


def _test_model_with_mask():
    """TC2: 模型带掩码前向传播"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    tower = BehaviorTower(max_seq_len=10, feature_dim=8, hidden_dim=64)
    x = torch.randn(4, 10, 8)
    mask = torch.ones(4, 10, dtype=torch.bool)
    mask[:, 5:] = False  # 后半部分填充
    out = tower(x, mask)
    assert out.shape == (4, 128), f"输出 shape 应为 (4, 128), 收到 {out.shape}"
    print("  ✓ test_model_with_mask")


def _test_encoder_fit_transform():
    """TC3: 编码器 fit + transform (单一行为)"""
    try:
        import pandas as pd
    except ImportError:
        print("  ⚠ pandas 不可用, 跳过测试")
        return

    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    df = pd.DataFrame({
        "behavior_type": ["view", "browse", "match_view", "feedback_like", "search"],
        "timestamp_gap": [0.0, 1.0, 5.0, 10.0, 2.0],
        "duration": [5.0, 30.0, 120.0, 15.0, 8.0],
        "target_id": [101, 102, 103, 101, 104],
        "action_value": [1.0, 2.0, 5.0, 3.0, 1.0],
    })

    encoder = BehaviorSequenceEncoder(max_seq_len=10, feature_dim=32)
    encoder.fit(df)
    assert encoder._fitted, "fit 后 _fitted 应为 True"
    assert "behavior_type" in encoder.categorical_cardinality

    # transform 单条行为
    tensor, mask = encoder.transform({
        "behavior_type": "view",
        "timestamp_gap": 0.0,
        "duration": 5.0,
        "target_id": 101,
        "action_value": 1.0,
    })
    assert tensor.shape == (1, 10, 32), f"输出 shape 应为 (1, 10, 32), 收到 {tensor.shape}"
    assert mask.shape == (1, 10), f"mask shape 应为 (1, 10), 收到 {mask.shape}"
    assert mask[0, 0].item() is True, "第一个位置应为有效"
    assert mask[0, 1:].sum().item() == 0, "其余位置应为填充"
    print("  ✓ test_encoder_fit_transform")


def _test_encoder_sequence():
    """TC4: 编码器处理行为序列"""
    try:
        import pandas as pd
    except ImportError:
        print("  ⚠ pandas 不可用, 跳过测试")
        return

    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    df = pd.DataFrame({
        "behavior_type": ["view", "browse"],
        "timestamp_gap": [0.0, 1.0],
        "duration": [5.0, 30.0],
        "target_id": [101, 102],
        "action_value": [1.0, 2.0],
    })
    encoder = BehaviorSequenceEncoder(max_seq_len=10, feature_dim=32)
    encoder.fit(df)

    # 单用户的行为序列
    seq = [
        {"behavior_type": "view", "timestamp_gap": 0.0, "duration": 5.0, "target_id": 101, "action_value": 1.0},
        {"behavior_type": "browse", "timestamp_gap": 1.0, "duration": 30.0, "target_id": 102, "action_value": 2.0},
        {"behavior_type": "match_view", "timestamp_gap": 5.0, "duration": 120.0, "target_id": 103, "action_value": 3.0},
    ]
    tensor, mask = encoder.transform(seq)
    assert tensor.shape == (1, 10, 32), f"输出 shape 应为 (1, 10, 32), 收到 {tensor.shape}"
    assert mask[0, :3].sum().item() == 3, "前 3 个位置应为有效"
    assert mask[0, 3:].sum().item() == 0, "其余应为填充"
    print("  ✓ test_encoder_sequence")


def _test_encoder_batch():
    """TC5: 编码器批量处理多用户"""
    try:
        import pandas as pd
    except ImportError:
        print("  ⚠ pandas 不可用, 跳过测试")
        return

    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    df = pd.DataFrame({
        "behavior_type": ["view", "browse", "match_view"],
        "timestamp_gap": [0.0, 1.0, 5.0],
        "duration": [5.0, 30.0, 120.0],
        "target_id": [101, 102, 103],
        "action_value": [1.0, 2.0, 5.0],
    })
    encoder = BehaviorSequenceEncoder(max_seq_len=10, feature_dim=32)
    encoder.fit(df)

    # 多用户
    user1 = [
        {"behavior_type": "view", "timestamp_gap": 0.0, "duration": 5.0, "target_id": 101, "action_value": 1.0},
    ]
    user2 = [
        {"behavior_type": "browse", "timestamp_gap": 1.0, "duration": 30.0, "target_id": 102, "action_value": 2.0},
        {"behavior_type": "match_view", "timestamp_gap": 5.0, "duration": 120.0, "target_id": 103, "action_value": 5.0},
    ]
    tensor, mask = encoder.transform([user1, user2])
    assert tensor.shape == (2, 10, 32), f"输出 shape 应为 (2, 10, 32), 收到 {tensor.shape}"
    assert mask[0, 0].item() is True
    assert mask[1, :2].sum().item() == 2
    print("  ✓ test_encoder_batch")


def _test_encoder_truncation():
    """TC6: 编码器序列截断"""
    try:
        import pandas as pd
    except ImportError:
        print("  ⚠ pandas 不可用, 跳过测试")
        return

    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    df = pd.DataFrame({
        "behavior_type": ["view"],
        "timestamp_gap": [0.0],
        "duration": [5.0],
        "target_id": [101],
        "action_value": [1.0],
    })
    encoder = BehaviorSequenceEncoder(max_seq_len=3, feature_dim=16)
    encoder.fit(df)

    # 超过 max_seq_len 的序列
    long_seq = [
        {"behavior_type": "view", "timestamp_gap": float(i), "duration": 5.0, "target_id": 100 + i, "action_value": 1.0}
        for i in range(10)
    ]
    tensor, mask = encoder.transform(long_seq)
    assert tensor.shape == (1, 3, 16), f"截断后 shape 应为 (1, 3, 16), 收到 {tensor.shape}"
    assert mask[0].sum().item() == 3, "截断后 3 个位置都是有效的"
    print("  ✓ test_encoder_truncation")


def _test_tower_predict():
    """TC7: predict 接口"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    tower = BehaviorTower(max_seq_len=5, feature_dim=8, hidden_dim=64)
    x = torch.randn(2, 5, 8)
    out = tower.predict(x)
    assert isinstance(out, np.ndarray), f"predict 应返回 numpy, 收到 {type(out)}"
    assert out.shape == (2, 128), f"predict shape 应为 (2, 128), 收到 {out.shape}"
    print("  ✓ test_tower_predict")


def _test_tower_repr():
    """TC8: 模型 repr"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    tower = BehaviorTower(max_seq_len=10, feature_dim=16, hidden_dim=64)
    r = repr(tower)
    assert "BehaviorTower" in r
    assert "max_seq_len=10" in r
    print(f"  ✓ test_tower_repr: {r}")


# ===================================================================
# 主入口
# ===================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  行为序列塔 — 单元测试")
    print("=" * 60)
    print()

    tests = [
        ("模型前向传播", _test_model_forward),
        ("模型带掩码前向传播", _test_model_with_mask),
        ("编码器 fit+transform", _test_encoder_fit_transform),
        ("编码器处理序列", _test_encoder_sequence),
        ("编码器批量处理", _test_encoder_batch),
        ("编码器序列截断", _test_encoder_truncation),
        ("predict 接口", _test_tower_predict),
        ("模型 repr", _test_tower_repr),
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
