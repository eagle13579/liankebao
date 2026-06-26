"""链客宝 — 企业 Embedding 塔 (EnterpriseTower)

四塔 DNN 架构中的企业特征嵌入模块。

架构:
  企业特征 → BN → DNN(256→128) → L2-Norm → 128d

特征 (仿天眼查/企查查数据源):
  - 注册资本 (log 变换后)
  - 成立年限
  - 行业代码
  - 企业规模 (小型/中型/大型/巨型)
  - 信用评级 (AAA/AA/A/BBB/BB 等)
  - 风险数 (行政处罚/司法风险/经营风险总数)

用法:
    tower = EnterpriseTower(num_features=6, embedding_dim=128, hidden_dims=[256, 128])
    embeddings = tower(enterprise_features)  # → (B, 128) L2 normalized

    encoder = EnterpriseFeatureEncoder()
    encoder.fit(df)
    tensor = encoder.transform(enterprise_data)  # → (B, num_features)

Author: 长乘 (P6, 内容部, 风格visionary适合组合创新)
"""

from __future__ import annotations

import logging
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

# 企业塔特征 schema — 特征名列表 (全部作为数值特征处理, 类别特征映射为数值)
ENTERPRISE_FEATURES = [
    "registered_capital_log",  # 注册资本 (log 变换)
    "established_years",       # 成立年限
    "industry_code",           # 行业代码
    "enterprise_scale",        # 企业规模 (编码: 1=小型, 2=中型, 3=大型, 4=巨型)
    "credit_rating",           # 信用评级 (编码: 0=未知, 1=BBB以下, 2=BBB, 3=A, 4=AA, 5=AAA)
    "risk_count",              # 风险总数 (行政处罚+司法+经营)
]

# 信用评级映射
CREDIT_RATING_MAP: Dict[str, int] = {
    "unknown": 0,
    "D": 0, "C": 0,
    "BBB-": 1, "BBB": 2, "BBB+": 2,
    "A-": 3, "A": 3, "A+": 3,
    "AA-": 4, "AA": 4, "AA+": 4,
    "AAA": 5,
}

# 企业规模映射
ENTERPRISE_SCALE_MAP: Dict[str, int] = {
    "micro": 0,
    "small": 1,
    "medium": 2,
    "large": 3,
    "giant": 4,
}


# ===================================================================
# 企业塔
# ===================================================================
class EnterpriseTower(nn.Module):
    """企业 Embedding 塔。

    输入: 6 维企业特征 (数值化后)
    输出: L2 归一化的 128d 企业嵌入向量

    Args:
        num_features: 特征总数 (默认 6)
        embedding_dim: 输出嵌入维度 (默认 128)
        hidden_dims:   DNN 隐层维度列表 (默认 [256, 128])
        dropout:       Dropout 比率 (默认 0.1)
    """

    def __init__(
        self,
        num_features: int = len(ENTERPRISE_FEATURES),
        embedding_dim: int = DEFAULT_EMBEDDING_DIM,
        hidden_dims: Optional[List[int]] = None,
        dropout: float = 0.1,
    ):
        super().__init__()

        if not TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch is required for EnterpriseTower. "
                "Install it via: pip install torch"
            )

        self.num_features = num_features
        self.embedding_dim = embedding_dim
        self.dropout_rate = dropout

        hidden_dims = hidden_dims or list(DEFAULT_HIDDEN_DIMS)

        # ── 批量归一化 ──
        self.input_bn = nn.BatchNorm1d(num_features)

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

    def forward(self, enterprise_features: torch.Tensor) -> torch.Tensor:
        """前向传播 → L2 归一化的 128d 嵌入。

        Args:
            enterprise_features: (B, num_features) 特征张量

        Returns:
            (B, embedding_dim) L2 归一化嵌入
        """
        # BN 预处理
        x = self.input_bn(enterprise_features)
        # DNN 编码
        out = self.fc_stack(x)  # (B, embedding_dim)
        # L2 归一化
        out = F.normalize(out, p=2, dim=1)
        return out

    @torch.no_grad()
    def predict(self, enterprise_features: torch.Tensor) -> np.ndarray:
        """推理接口, 返回 numpy 数组"""
        self.eval()
        emb = self.forward(enterprise_features)
        return emb.cpu().numpy()

    def __repr__(self) -> str:
        return (
            f"EnterpriseTower(num_features={self.num_features}, "
            f"embedding_dim={self.embedding_dim})"
        )


# ===================================================================
# 企业特征编码器
# ===================================================================
class EnterpriseFeatureEncoder:
    """企业特征编码器。

    将原始企业特征 (dict/DataFrame) 编码为 EnterpriseTower 可接受的张量。

    特征处理:
      - 注册资本: log(注册资本 + 1) 变换后 z-score 标准化
      - 成立年限: 直接 z-score 标准化
      - 行业代码: z-score 标准化
      - 企业规模: 类别映射 → 数值 → z-score 标准化
      - 信用评级: 类别映射 → 数值 → z-score 标准化
      - 风险数: log(风险数 + 1) 变换后 z-score 标准化

    Usage:
        encoder = EnterpriseFeatureEncoder()
        encoder.fit(df)                  # 学习统计量
        tensor = encoder.transform(data) # → torch.Tensor
    """

    def __init__(
        self,
        features: Optional[List[str]] = None,
    ):
        self.features = features or list(ENTERPRISE_FEATURES)

        # ── 状态 (fit 后填充) ──
        self.feature_mean: Dict[str, float] = {}
        self.feature_std: Dict[str, float] = {}

        self._fitted = False

    # ------------------------------------------------------------------
    # fit
    # ------------------------------------------------------------------
    def fit(self, df: "Any") -> "EnterpriseFeatureEncoder":
        """从 DataFrame 学习特征统计量 (z-score 参数)。

        Args:
            df: pandas DataFrame, 列包含 features

        Returns:
            self (链式调用)
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas required for EnterpriseFeatureEncoder.fit()")

        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pd.DataFrame, got {type(df).__name__}")

        for feat in self.features:
            if feat not in df.columns:
                logger.warning(
                    "[EnterpriseFeatureEncoder] 特征 '%s' 不在 DataFrame 中, 使用默认值", feat
                )
                self.feature_mean[feat] = 0.0
                self.feature_std[feat] = 1.0
                continue
            col = df[feat].dropna()
            if len(col) == 0:
                self.feature_mean[feat] = 0.0
                self.feature_std[feat] = 1.0
            else:
                self.feature_mean[feat] = float(col.mean())
                self.feature_std[feat] = float(col.std()) or 1.0

        self._fitted = True
        return self

    # ------------------------------------------------------------------
    # transform
    # ------------------------------------------------------------------
    def transform(
        self,
        enterprise_data: Union[Dict[str, Any], List[Dict[str, Any]], "Any"],
    ) -> "torch.Tensor":
        """将企业数据编码为张量。

        Args:
            enterprise_data: 单个 dict 或 list[dict] 或 pd.DataFrame

        Returns:
            torch.Tensor shape (B, len(features))
        """
        if not self._fitted:
            raise RuntimeError("EnterpriseFeatureEncoder 尚未 fit, 请先调用 .fit(df)")

        # ── 统一为 list[dict] ──
        rows = self._to_rows(enterprise_data)
        B = len(rows)

        # ── 特征提取 (B, N) ──
        feat_vals = []
        for feat in self.features:
            vals = []
            for row in rows:
                raw = row.get(feat, 0.0)
                # 类别型特征进行编码映射
                if feat == "credit_rating" and isinstance(raw, str):
                    raw = CREDIT_RATING_MAP.get(raw, 0)
                elif feat == "enterprise_scale" and isinstance(raw, str):
                    raw = ENTERPRISE_SCALE_MAP.get(raw, 1)

                try:
                    v = float(raw)
                except (ValueError, TypeError):
                    v = 0.0

                # 特殊变换
                if feat == "registered_capital_log" or feat == "risk_count":
                    # 如果原始值已经是对数, 不做二次变换
                    # 如果原始值是原始金额/原始数, 做 log1p
                    # 从列名判断: registered_capital_log 表明已 log 变换
                    if feat == "registered_capital_log" and v > 1e6:
                        v = np.log1p(v)
                    if feat == "risk_count" and v > 100:
                        v = np.log1p(v)

                # z-score 标准化
                mean_v = self.feature_mean.get(feat, 0.0)
                std_v = self.feature_std.get(feat, 1.0)
                vals.append((v - mean_v) / std_v)
            feat_vals.append(vals)

        # (N, B) → (B, N)
        tensor = torch.tensor(feat_vals, dtype=torch.float32).T
        return tensor.detach()

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _to_rows(
        enterprise_data: Union[Dict, List[Dict], "Any"],
    ) -> List[Dict[str, Any]]:
        """统一输入为 list[dict]"""
        if isinstance(enterprise_data, dict):
            return [enterprise_data]
        if isinstance(enterprise_data, list):
            return enterprise_data
        try:
            import pandas as pd

            if isinstance(enterprise_data, pd.DataFrame):
                return enterprise_data.to_dict(orient="records")
        except ImportError:
            pass
        raise TypeError(
            f"不支持的输入类型: {type(enterprise_data).__name__}, "
            f"期望 dict / list[dict] / pd.DataFrame"
        )

    @property
    def total_feature_dim(self) -> int:
        return len(self.features)

    def __repr__(self) -> str:
        status = "fitted" if self._fitted else "not fitted"
        return (
            f"EnterpriseFeatureEncoder("
            f"num_features={len(self.features)}, "
            f"features={self.features}, "
            f"status={status})"
        )


# ===================================================================
# 简易测试 (python enterprise_tower.py)
# ===================================================================
def _test_model_forward():
    """TC1: 模型前向传播"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    tower = EnterpriseTower(num_features=6, embedding_dim=128, hidden_dims=[256, 128])
    x = torch.randn(4, 6)
    out = tower(x)
    assert out.shape == (4, 128), f"输出 shape 应为 (4, 128), 收到 {out.shape}"
    # 检查 L2 归一化
    norms = out.norm(p=2, dim=1)
    assert torch.allclose(norms, torch.ones(4), atol=1e-5), \
        f"L2 归一化后 norm 应 ≈1, 收到 {norms}"
    print("  ✓ test_model_forward")


def _test_feature_encoder_fit_transform():
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
        "registered_capital_log": [1.0, 2.0, 3.0, 4.0, 5.0],
        "established_years": [1, 3, 5, 10, 20],
        "industry_code": [1, 2, 3, 4, 5],
        "enterprise_scale": [1, 2, 3, 2, 4],
        "credit_rating": [3, 4, 5, 2, 3],
        "risk_count": [0, 1, 5, 10, 3],
    })

    encoder = EnterpriseFeatureEncoder()
    encoder.fit(df)
    assert encoder._fitted, "fit 后 _fitted 应为 True"
    assert "registered_capital_log" in encoder.feature_mean
    assert "risk_count" in encoder.feature_mean

    # transform
    tensor = encoder.transform({
        "registered_capital_log": 3.0,
        "established_years": 5,
        "industry_code": 3,
        "enterprise_scale": 3,
        "credit_rating": 5,
        "risk_count": 5,
    })
    assert tensor.shape == (1, 6), \
        f"输出 shape 应为 (1, 6), 收到 {tensor.shape}"
    print("  ✓ test_feature_encoder_fit_transform")


def _test_encoder_string_mapping():
    """TC3: 编码器字符串映射 (信用评级/企业规模)"""
    try:
        import pandas as pd
    except ImportError:
        print("  ⚠ pandas 不可用, 跳过测试")
        return

    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    df = pd.DataFrame({
        "registered_capital_log": [1.0, 2.0],
        "established_years": [3, 5],
        "industry_code": [1, 2],
        "enterprise_scale": [1, 2],
        "credit_rating": [3, 4],
        "risk_count": [0, 1],
    })
    encoder = EnterpriseFeatureEncoder()
    encoder.fit(df)

    # 使用字符串映射
    tensor = encoder.transform({
        "registered_capital_log": 2.0,
        "established_years": 5,
        "industry_code": 2,
        "enterprise_scale": "large",
        "credit_rating": "AAA",
        "risk_count": 1,
    })
    assert tensor.shape == (1, 6), f"输出 shape 应为 (1, 6), 收到 {tensor.shape}"
    print("  ✓ test_encoder_string_mapping")


def _test_encoder_raw_values_transform():
    """TC4: 编码器处理原始大数值 (自动 log1p)"""
    try:
        import pandas as pd
    except ImportError:
        print("  ⚠ pandas 不可用, 跳过测试")
        return

    if not TORCH_AVAILABLE:
        print("  ⚠ pandas 不可用, 跳过测试")
        return

    df = pd.DataFrame({
        "registered_capital_log": [1.0, 2.0],
        "established_years": [3, 5],
        "industry_code": [1, 2],
        "enterprise_scale": [1, 2],
        "credit_rating": [3, 4],
        "risk_count": [0, 1],
    })
    encoder = EnterpriseFeatureEncoder()
    encoder.fit(df)

    # 非常大的原始值应触发 log1p
    tensor = encoder.transform({
        "registered_capital_log": 50000000.0,  # 5 千万, 应被 log1p
        "established_years": 5,
        "industry_code": 2,
        "enterprise_scale": 3,
        "credit_rating": 4,
        "risk_count": 200,  # 大风险数, 应被 log1p
    })
    assert tensor.shape == (1, 6)
    # 值不应是 NaN
    assert not torch.isnan(tensor).any(), "变换结果不应包含 NaN"
    print("  ✓ test_encoder_raw_values_transform")


def _test_embedding_similarity():
    """TC5: 相似企业产生相似嵌入"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    tower = EnterpriseTower(num_features=6, embedding_dim=128)
    tower.eval()
    # 两家相似企业 (同行业, 规模相近)
    x1 = torch.tensor([[1.0, 5.0, 1.0, 2.0, 4.0, 1.0]])
    x2 = torch.tensor([[1.1, 5.1, 1.0, 2.0, 4.0, 1.0]])  # 相似
    x3 = torch.tensor([[10.0, 20.0, 9.0, 4.0, 1.0, 20.0]])  # 不相似

    e1 = tower(x1)
    e2 = tower(x2)
    e3 = tower(x3)

    sim_similar = F.cosine_similarity(e1, e2).item()
    sim_dissimilar = F.cosine_similarity(e1, e3).item()
    assert sim_similar > sim_dissimilar, \
        f"相似企业的余弦相似度 ({sim_similar:.4f}) 应高于不相似企业 ({sim_dissimilar:.4f})"
    print(f"  ✓ test_embedding_similarity (sim_similar={sim_similar:.4f}, sim_diff={sim_dissimilar:.4f})")


def _test_batch_transform():
    """TC6: 批量 transform"""
    try:
        import pandas as pd
    except ImportError:
        print("  ⚠ pandas 不可用, 跳过测试")
        return

    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    df = pd.DataFrame({
        "registered_capital_log": [1.0, 2.0, 3.0],
        "established_years": [1, 3, 5],
        "industry_code": [1, 2, 3],
        "enterprise_scale": [1, 2, 3],
        "credit_rating": [3, 4, 5],
        "risk_count": [0, 1, 2],
    })
    encoder = EnterpriseFeatureEncoder()
    encoder.fit(df)

    data = [
        {"registered_capital_log": 2.0, "established_years": 3,
         "industry_code": 2, "enterprise_scale": 2, "credit_rating": 4, "risk_count": 1},
        {"registered_capital_log": 3.0, "established_years": 5,
         "industry_code": 3, "enterprise_scale": 3, "credit_rating": 5, "risk_count": 2},
    ]
    tensor = encoder.transform(data)
    assert tensor.shape == (2, 6), \
        f"批量 transform 期望 (2, 6), 收到 {tensor.shape}"
    print(f"  ✓ test_batch_transform (shape={tuple(tensor.shape)})")


def _test_tower_predict():
    """TC7: predict 接口返回 numpy"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    tower = EnterpriseTower(num_features=6, embedding_dim=128)
    x = torch.randn(2, 6)
    out = tower.predict(x)
    assert isinstance(out, np.ndarray), f"predict 应返回 numpy, 收到 {type(out)}"
    assert out.shape == (2, 128), f"predict shape 应为 (2, 128), 收到 {out.shape}"
    print("  ✓ test_tower_predict")


def _test_tower_repr():
    """TC8: 模型 repr"""
    if not TORCH_AVAILABLE:
        print("  ⚠ PyTorch 不可用, 跳过测试")
        return

    tower = EnterpriseTower(num_features=6, embedding_dim=64, hidden_dims=[128, 64])
    r = repr(tower)
    assert "EnterpriseTower" in r
    assert "num_features=6" in r
    print(f"  ✓ test_tower_repr: {r}")


# ===================================================================
# 主入口
# ===================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  企业 Embedding 塔 — 单元测试")
    print("=" * 60)
    print()

    tests = [
        ("模型前向传播", _test_model_forward),
        ("特征编码器 fit+transform", _test_feature_encoder_fit_transform),
        ("字符串映射", _test_encoder_string_mapping),
        ("原始大值自动变换", _test_encoder_raw_values_transform),
        ("嵌入相似性", _test_embedding_similarity),
        ("批量 transform", _test_batch_transform),
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
