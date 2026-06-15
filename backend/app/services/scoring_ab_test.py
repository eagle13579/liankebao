"""
链客宝AI 评分A/B测试框架
=========================
支持规则评分 vs ML评分 vs Ensemble 评分对比分析。

功能:
  1. 配置A/B比例 (如 50% ML, 50% Rule)
  2. 输出两组评分的分布对比
  3. 一致性分析 (Kendall Tau, Spearman)
  4. 统计显著性检验 (Mann-Whitney U)
  5. 可视化输出 (ASCII分布图)

使用方式:
  from app.services.scoring_ab_test import ScoreABTest, run_ab_test

  ab = ScoreABTest()
  result = ab.evaluate(prod_feat_list, need_feat_list)
  print(result.summary())
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================
# 数据类
# ============================================================


@dataclass
class ABTestConfig:
    """A/B 测试配置

    Attributes:
        ab_ratio: ML 模式的比例 (0.0~1.0), 1.0=全部ML, 0.0=全部规则
        ml_weight: Ensemble 模式下 ML 的权重
        seed: 随机种子（保证可复现）
    """

    ab_ratio: float = 0.5
    ml_weight: float = 0.6
    seed: int = 42


@dataclass
class ScorePair:
    """单个样本的评分对比

    Attributes:
        index: 样本索引
        ml_score: ML 模型评分
        rule_score: 规则评分
        ensemble_score: Ensemble 评分
        assigned_group: 分配的组 (ml/rule/ensemble)
    """

    index: int
    ml_score: float
    rule_score: float
    ensemble_score: float
    assigned_group: str = "ml"


@dataclass
class ABTestResult:
    """A/B 测试结果"""

    n_samples: int
    group_a_size: int
    group_b_size: int
    group_a_name: str = "ML"
    group_b_name: str = "Rule"
    group_a_scores: list[float] = field(default_factory=list)
    group_b_scores: list[float] = field(default_factory=list)
    score_pairs: list[ScorePair] = field(default_factory=list)
    kendall_tau: float | None = None
    spearman_r: float | None = None
    mwu_statistic: float | None = None
    mwu_pvalue: float | None = None
    rank_overlap_top10: float | None = None
    rank_overlap_top20: float | None = None

    def summary(self) -> str:
        """生成测试结果摘要"""
        lines = []
        lines.append("=" * 60)
        lines.append("评分 A/B 测试结果")
        lines.append("=" * 60)
        lines.append(f"  总样本数: {self.n_samples}")
        lines.append(f"  A组 ({self.group_a_name}): {self.group_a_size} 样本")
        lines.append(f"  B组 ({self.group_b_name}): {self.group_b_size} 样本")
        lines.append("")

        # 分布统计
        if self.group_a_scores:
            a_mean = np.mean(self.group_a_scores)
            a_std = np.std(self.group_a_scores)
            a_min = np.min(self.group_a_scores)
            a_max = np.max(self.group_a_scores)
            lines.append(f"  A组 ({self.group_a_name}) 评分分布:")
            lines.append(f"    均值={a_mean:.4f}, 标准差={a_std:.4f}")
            lines.append(f"    范围=[{a_min:.4f}, {a_max:.4f}]")
            # ASCII 直方图
            lines.append("    分布: " + _ascii_histogram(self.group_a_scores))

        if self.group_b_scores:
            b_mean = np.mean(self.group_b_scores)
            b_std = np.std(self.group_b_scores)
            b_min = np.min(self.group_b_scores)
            b_max = np.max(self.group_b_scores)
            lines.append(f"  B组 ({self.group_b_name}) 评分分布:")
            lines.append(f"    均值={b_mean:.4f}, 标准差={b_std:.4f}")
            lines.append(f"    范围=[{b_min:.4f}, {b_max:.4f}]")
            lines.append("    分布: " + _ascii_histogram(self.group_b_scores))

        lines.append("")

        # 一致性分析
        lines.append("  一致性分析:")
        if self.kendall_tau is not None:
            lines.append(f"    Kendall Tau: {self.kendall_tau:.4f}")
        if self.spearman_r is not None:
            lines.append(f"    Spearman R:  {self.spearman_r:.4f}")
        if self.mwu_pvalue is not None:
            sig = "显著差异" if self.mwu_pvalue < 0.05 else "无显著差异"
            lines.append(f"    MWU p-value: {self.mwu_pvalue:.4f} ({sig})")
        if self.rank_overlap_top10 is not None:
            lines.append(f"    Top-10 排序重叠率: {self.rank_overlap_top10:.2%}")
        if self.rank_overlap_top20 is not None:
            lines.append(f"    Top-20 排序重叠率: {self.rank_overlap_top20:.2%}")

        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """将结果转换为字典"""
        return {
            "n_samples": self.n_samples,
            "group_a": {
                "name": self.group_a_name,
                "size": self.group_a_size,
                "mean": round(float(np.mean(self.group_a_scores)), 4) if self.group_a_scores else None,
                "std": round(float(np.std(self.group_a_scores)), 4) if self.group_a_scores else None,
            },
            "group_b": {
                "name": self.group_b_name,
                "size": self.group_b_size,
                "mean": round(float(np.mean(self.group_b_scores)), 4) if self.group_b_scores else None,
                "std": round(float(np.std(self.group_b_scores)), 4) if self.group_b_scores else None,
            },
            "consistency": {
                "kendall_tau": self.kendall_tau,
                "spearman_r": self.spearman_r,
                "mwu_pvalue": self.mwu_pvalue,
                "rank_overlap_top10": self.rank_overlap_top10,
                "rank_overlap_top20": self.rank_overlap_top20,
            },
        }


# ============================================================
# 工具函数
# ============================================================


def _ascii_histogram(values: list[float], bins: int = 10, width: int = 30) -> str:
    """生成 ASCII 直方图"""
    if not values:
        return "[empty]"
    arr = np.array(values)
    hist, bin_edges = np.histogram(arr, bins=bins, range=(0.0, 1.0))
    max_count = max(hist) if max(hist) > 0 else 1
    bar_chars = []
    for i, count in enumerate(hist):
        bar_len = int(count / max_count * width)
        bar = "█" * bar_len
        bar_chars.append(f"[{bin_edges[i]:.1f}-{bin_edges[i + 1]:.1f}] {bar} ({count})")
    return "\n      " + "\n      ".join(bar_chars)


def _compute_kendall_tau(list_a: list[float], list_b: list[float]) -> float:
    """计算 Kendall Tau 秩相关系数

    衡量两组排序的一致性，取值范围 [-1, 1]。
    """
    n = min(len(list_a), len(list_b))
    if n < 2:
        return 0.0

    # 将列表转为排名
    rank_a = {i: r for i, r in enumerate(sorted(range(n), key=lambda i: list_a[i], reverse=True))}
    rank_b = {i: r for i, r in enumerate(sorted(range(n), key=lambda i: list_b[i], reverse=True))}

    concordant = 0
    discordant = 0

    for i in range(n):
        for j in range(i + 1, n):
            diff_a = rank_a[i] - rank_a[j]
            diff_b = rank_b[i] - rank_b[j]
            if diff_a * diff_b > 0:
                concordant += 1
            elif diff_a * diff_b < 0:
                discordant += 1

    total = concordant + discordant
    if total == 0:
        return 0.0

    return float((concordant - discordant) / total)


def _compute_spearman_r(list_a: list[float], list_b: list[float]) -> float:
    """计算 Spearman 秩相关系数"""
    n = min(len(list_a), len(list_b))
    if n < 3:
        return 0.0

    rank_a = {i: r for i, r in enumerate(sorted(range(n), key=lambda i: list_a[i]))}
    rank_b = {i: r for i, r in enumerate(sorted(range(n), key=lambda i: list_b[i]))}

    d_squared_sum = sum((rank_a[i] - rank_b[i]) ** 2 for i in range(n))
    denominator = n * (n**2 - 1) / 6.0
    if denominator == 0:
        return 0.0

    return float(1.0 - d_squared_sum / denominator)


def _compute_rank_overlap(
    list_a: list[float],
    list_b: list[float],
    top_k: int = 10,
) -> float:
    """计算两组评分在 top-k 的排序重叠率

    Returns:
        float: [0, 1] 重叠率
    """
    n = min(len(list_a), len(list_b), top_k)
    if n == 0:
        return 0.0

    top_a = set(np.argsort(list_a)[-n:])
    top_b = set(np.argsort(list_b)[-n:])
    overlap = len(top_a & top_b)
    return overlap / n


# ============================================================
# A/B 测试类
# ============================================================


class ScoreABTest:
    """评分 A/B 测试框架

    支持:
      - 按比例分配样本到 ML / Rule 组
      - 对比两组评分分布
      - 计算排序一致性
      - 统计显著性检验

    用法:
      ab = ScoreABTest()
      result = ab.evaluate(prod_feat_list, need_feat_list)
      print(result.summary())
    """

    def __init__(self, config: ABTestConfig | None = None):
        self.config = config or ABTestConfig()
        self._rng = random.Random(self.config.seed)

    def assign_group(self, index: int) -> str:
        """根据 A/B 比例分配组

        Args:
            index: 样本索引

        Returns:
            'ml' 或 'rule'
        """
        # 使用确定性分配以保证可复现
        self._rng.seed(self.config.seed + index)
        if self._rng.random() < self.config.ab_ratio:
            return "ml"
        return "rule"

    def evaluate(
        self,
        prod_feat_list: list[dict[str, Any]],
        need_feat_list: list[dict[str, Any]],
    ) -> ABTestResult:
        """执行 A/B 测试评估

        Args:
            prod_feat_list: 产品特征字典列表
            need_feat_list: 需求特征字典列表

        Returns:
            ABTestResult
        """
        from app.matching_model import (
            build_feature_vector,
            compute_rule_score_from_features,
            predict_match_score,
        )

        n = min(len(prod_feat_list), len(need_feat_list))
        if n == 0:
            logger.warning("ScoreABTest.evaluate: 空数据")
            return ABTestResult(n_samples=0, group_a_size=0, group_b_size=0)

        score_pairs: list[ScorePair] = []
        all_ml_scores: list[float] = []
        all_rule_scores: list[float] = []

        for i in range(n):
            try:
                # 构建特征向量
                vec = build_feature_vector(prod_feat_list[i], need_feat_list[i])

                # 计算两种评分
                ml_score = predict_match_score(prod_feat_list[i], need_feat_list[i], mode="ml")
                rule_score = compute_rule_score_from_features(vec)
                ensemble_score = predict_match_score(prod_feat_list[i], need_feat_list[i], mode="ensemble")

                all_ml_scores.append(ml_score)
                all_rule_scores.append(rule_score)

                group = self.assign_group(i)
                score_pairs.append(
                    ScorePair(
                        index=i,
                        ml_score=ml_score,
                        rule_score=rule_score,
                        ensemble_score=ensemble_score,
                        assigned_group=group,
                    )
                )

            except Exception as e:
                logger.debug(f"样本 [{i}] 评分计算失败: {e}")
                continue

        # 分组
        group_a_scores = [sp.ml_score for sp in score_pairs if sp.assigned_group == "ml"]
        group_b_scores = [sp.rule_score for sp in score_pairs if sp.assigned_group == "rule"]

        # 一致性分析
        kendall_tau = _compute_kendall_tau(all_ml_scores, all_rule_scores)
        spearman_r = _compute_spearman_r(all_ml_scores, all_rule_scores)
        rank_overlap_top10 = _compute_rank_overlap(all_ml_scores, all_rule_scores, top_k=10)
        rank_overlap_top20 = _compute_rank_overlap(all_ml_scores, all_rule_scores, top_k=20)

        # Mann-Whitney U 检验
        mwu_statistic = None
        mwu_pvalue = None
        try:
            from scipy.stats import mannwhitneyu

            if len(group_a_scores) > 0 and len(group_b_scores) > 0:
                stat, pval = mannwhitneyu(group_a_scores, group_b_scores, alternative="two-sided")
                mwu_statistic = float(stat)
                mwu_pvalue = float(pval)
        except ImportError:
            logger.info("scipy 未安装，跳过 MWU 检验")

        result = ABTestResult(
            n_samples=n,
            group_a_size=len(group_a_scores),
            group_b_size=len(group_b_scores),
            group_a_name="ML",
            group_b_name="Rule",
            group_a_scores=group_a_scores,
            group_b_scores=group_b_scores,
            score_pairs=score_pairs,
            kendall_tau=round(kendall_tau, 4) if kendall_tau is not None else None,
            spearman_r=round(spearman_r, 4) if spearman_r is not None else None,
            mwu_statistic=mwu_statistic,
            mwu_pvalue=round(mwu_pvalue, 4) if mwu_pvalue is not None else None,
            rank_overlap_top10=round(rank_overlap_top10, 4) if rank_overlap_top10 is not None else None,
            rank_overlap_top20=round(rank_overlap_top20, 4) if rank_overlap_top20 is not None else None,
        )

        logger.info(
            "A/B 测试完成",
            extra={
                "n_samples": n,
                "group_a": len(group_a_scores),
                "group_b": len(group_b_scores),
                "kendall_tau": result.kendall_tau,
                "spearman_r": result.spearman_r,
                "rank_overlap_top10": result.rank_overlap_top10,
            },
        )

        return result


def run_ab_test(
    prod_feat_list: list[dict[str, Any]],
    need_feat_list: list[dict[str, Any]],
    ab_ratio: float = 0.5,
) -> ABTestResult:
    """便捷函数：运行 A/B 测试

    Args:
        prod_feat_list: 产品特征字典列表
        need_feat_list: 需求特征字典列表
        ab_ratio: ML 比例 (0~1)

    Returns:
        ABTestResult
    """
    config = ABTestConfig(ab_ratio=ab_ratio)
    ab = ScoreABTest(config=config)
    return ab.evaluate(prod_feat_list, need_feat_list)


# ============================================================
# 独立测试入口
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    logger.info("=" * 60)
    logger.info("评分 A/B 测试框架 — 冒烟测试")
    logger.info("=" * 60)

    # 生成测试数据
    logger.info("\n[1] 生成测试数据...")
    n_test = 50
    prod_feats = []
    need_feats = []

    categories = ["大健康", "科技", "金融", "教育", "医疗", "制造", "零售", "农业"]
    corpuses = [
        "优质产品 服务 供应 高质量",
        "创新科技 解决方案 数字化",
        "金融服务 投资 理财 保险",
        "教育培训 课程 学习 在线",
        "医疗器械 健康 治疗 设备",
        "智能制造 工业 自动化 生产",
        "零售电商 商品 销售 渠道",
        "现代农业 种植 养殖 绿色",
    ]
    descriptions = [
        "寻找优质供应商 合作 长期",
        "需要技术方案 创新 高效",
        "金融服务需求 投资 稳健",
        "教育解决方案 培训 课程",
        "医疗设备采购 质量 可靠",
        "智能制造升级 自动化 效率",
        "零售渠道拓展 商品 供应链",
        "农业技术 绿色 可持续",
    ]

    for i in range(n_test):
        idx = i % len(categories)
        prod_feats.append(
            {
                "category_vector": {categories[idx]: 0.8, categories[(idx + 1) % len(categories)]: 0.2},
                "keywords": [categories[idx], "服务"],
                "text_corpus": corpuses[idx],
                "price_norm": 0.3 + (i % 7) * 0.1,
                "price_raw": 100.0 + i * 50.0,
                "recency_score": 0.5 + (i % 5) * 0.1,
            }
        )
        need_feats.append(
            {
                "category_vector": {categories[idx]: 0.7, categories[(idx + 2) % len(categories)]: 0.3},
                "keywords": [categories[idx], "合作"],
                "text_corpus": descriptions[idx],
                "budget_range": (5000, 50000 + i * 1000),
                "budget_mid": 20000.0 + i * 500.0,
                "recency_score": 0.4 + (i % 5) * 0.1,
            }
        )

    # 运行 A/B 测试
    logger.info(f"\n[2] 运行 A/B 测试 (n={n_test}, ratio=0.5)...")
    result = run_ab_test(prod_feats, need_feats, ab_ratio=0.5)

    # 输出结果摘要
    print()
    print(result.summary())

    # 转换为字典
    print()
    import json

    print("Dict output:")
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))

    # 测试不同比例
    logger.info("\n[3] 测试不同 A/B 比例...")
    for ratio in [0.0, 0.3, 0.7, 1.0]:
        r = run_ab_test(prod_feats, need_feats, ab_ratio=ratio)
        logger.info(f"  ratio={ratio:.1f}: A组={r.group_a_size}, B组={r.group_b_size}")

    logger.info("\n" + "=" * 60)
    logger.info("A/B 测试框架冒烟测试通过 ✓")
    logger.info("=" * 60)
