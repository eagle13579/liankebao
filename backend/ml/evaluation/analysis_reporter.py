"""
链客宝 - A/B实验结果分析报告引擎
==================================
提供 ExperimentAnalyzer（统计推断）和 ReportGenerator（报告输出）两类核心组件。
支持置信区间、显著检验（参数+非参数）、效应量、功效分析及多重比较校正。

依赖:
    - scipy (推荐, 但纯 Python 后备同样可用)
    - numpy (仅用于功效分析近似, 非必需)
"""

import json
import math
import random
import statistics
from typing import Optional

# ---------------------------------------------------------------------------
# 尝试导入 scipy（增强统计精度）
# ---------------------------------------------------------------------------
_HAS_SCIPY = False
try:
    from scipy import stats as scipy_stats
    from scipy.stats import t as scipy_t

    _HAS_SCIPY = True
except ImportError:
    scipy_stats = None
    scipy_t = None


# ===========================================================================
# 辅助函数
# ===========================================================================


def _cohens_d(control: list, treatment: list) -> float:
    """计算 Cohen's d 效应量。

    d = (mean_treatment - mean_control) / pooled_std

    Args:
        control: 对照组原始值列表。
        treatment: 实验组原始值列表。

    Returns:
        Cohen's d 值。正值表示实验组均值更高。
    """
    n1, n2 = len(control), len(treatment)
    if n1 < 2 or n2 < 2:
        return 0.0
    m1, m2 = statistics.mean(control), statistics.mean(treatment)
    v1, v2 = statistics.variance(control), statistics.variance(treatment)
    pooled_std = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    if pooled_std == 0:
        return 0.0
    return (m2 - m1) / pooled_std


def _hedges_g(control: list, treatment: list) -> float:
    """Hedges' g（Cohen's d 的小样本校正版本）。

    校正因子: J = 1 - 3 / (4 * (n1 + n2) - 9)
    """
    d = _cohens_d(control, treatment)
    n1, n2 = len(control), len(treatment)
    # Hedges' 校正因子
    df = n1 + n2 - 2
    if df < 1:
        return d
    j = 1 - 3.0 / (4.0 * df - 1.0)
    return d * j


def _welch_ttest(a: list, b: list):
    """Welch t-test（不等方差独立样本 t 检验）。

    Returns:
        (t_statistic, p_value, df, method_name)
    """
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return 0.0, 1.0, 0.0, "welch_ttest"

    m1, m2 = statistics.mean(a), statistics.mean(b)
    v1, v2 = statistics.variance(a), statistics.variance(b)

    se = math.sqrt(v1 / n1 + v2 / n2)
    if se == 0:
        return 0.0, 1.0, 0.0, "welch_ttest"

    t = (m2 - m1) / se

    # Welch-Satterthwaite degrees of freedom
    num = (v1 / n1 + v2 / n2) ** 2
    den = (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
    df = num / den if den > 0 else 1.0

    if _HAS_SCIPY:
        p_value = scipy_stats.t.sf(abs(t), df) * 2.0
    else:
        p_value = _t_distribution_p_value(t, df)

    return t, max(p_value, 1e-300), df, "welch_ttest"


def _mann_whitney_u(a: list, b: list):
    """Mann-Whitney U 检验（非参数，双尾）。

    Returns:
        (U_statistic, p_value, method_name)
    """
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return 0.0, 1.0, "mann_whitney_u"

    if _HAS_SCIPY:
        try:
            stat, p = scipy_stats.mannwhitneyu(a, b, alternative="two-sided")
            return stat, max(p, 1e-300), "mann_whitney_u"
        except Exception:
            pass

    # 纯 Python 实现（大样本正态近似）
    combined = [(v, 0) for v in a] + [(v, 1) for v in b]
    combined.sort(key=lambda x: x[0])
    # 处理 ties
    ranks = []
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j + 1) / 2.0
        for k in range(i, j):
            ranks.append((avg_rank, combined[k][1]))
        i = j

    r1 = sum(r for r, grp in ranks if grp == 0)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u = min(u1, u2)

    # 正态近似
    mu = n1 * n2 / 2.0
    # tie 校正
    tie_counts = {}
    for v, _ in combined:
        tie_counts[v] = tie_counts.get(v, 0) + 1
    tie_correction = sum(t**3 - t for t in tie_counts.values() if t > 1)
    sigma = math.sqrt(
        (n1 * n2 / 12.0) * ((n1 + n2 + 1) - tie_correction / ((n1 + n2) * (n1 + n2 - 1)))
    )
    if sigma == 0:
        return u, 1.0, "mann_whitney_u"

    z = (u - mu) / sigma
    if _HAS_SCIPY:
        p = scipy_stats.norm.sf(abs(z)) * 2.0
    else:
        p = _normal_approx_p(z)
    return u, max(p, 1e-300), "mann_whitney_u"


def _bootstrap_ci_diff(a: list, b: list, n_resamples: int = 5000, ci: float = 0.95):
    """Bootstrap 法计算两组均值差的置信区间。

    Returns:
        (lower, upper) 置信区间。
    """
    alpha = 1.0 - ci
    combined = a + b
    n_a, n_b = len(a), len(b)
    if n_a == 0 or n_b == 0:
        return float("nan"), float("nan")

    diffs = []
    for _ in range(n_resamples):
        sample_a = [random.choice(combined) for _ in range(n_a)]
        sample_b = [random.choice(combined) for _ in range(n_b)]
        diffs.append(statistics.mean(sample_a) - statistics.mean(sample_b))
    diffs.sort()
    lower = diffs[int(n_resamples * alpha / 2)]
    upper = diffs[int(n_resamples * (1 - alpha / 2))]
    return lower, upper


def _bootstrap_ci_single(values: list, n_resamples: int = 5000, ci: float = 0.95):
    """Bootstrap 法计算单组均值的置信区间。

    Returns:
        (lower, upper) 置信区间。
    """
    alpha = 1.0 - ci
    n = len(values)
    if n < 2:
        return float("nan"), float("nan")

    means = []
    for _ in range(n_resamples):
        sample = [random.choice(values) for _ in range(n)]
        means.append(statistics.mean(sample))
    means.sort()
    lower = means[int(n_resamples * alpha / 2)]
    upper = means[int(n_resamples * (1 - alpha / 2))]
    return lower, upper


def _t_distribution_p_value(t: float, df: float) -> float:
    """t 分布双尾 p-value 近似（使用不完全 Beta 函数或纯数值近似）。

    当 scipy 不可用时回退到此方法。
    """
    x = df / (df + t * t)
    try:
        from scipy.special import betainc

        p = betainc(df / 2, 0.5, x)
        return min(p, 1.0 - p) * 2.0
    except ImportError:
        pass

    # 当 df 较大时使用正态近似
    if df > 100:
        return _normal_approx_p(t)
    # 否则用简单数值积分近似（仅适用于极粗糙估计）
    return _normal_approx_p(t)  # 接受近似精度损失


def _normal_approx_p(z: float) -> float:
    """标准正态分布双尾 p-value 近似（Polya 近似）。"""
    x = abs(z)
    b0, b1, b2, b3, b4, b5 = (
        0.319381530,
        -0.356563782,
        1.781477937,
        -1.821255978,
        1.330274429,
        0.2316419,
    )
    t = 1.0 / (1.0 + b5 * x)
    phi = math.exp(-x * x / 2) / math.sqrt(2 * math.pi)
    poly = ((b4 * t + b3) * t + b2) * t + b1 * t + b0
    p = phi * poly * t
    return min(p * 2.0, 1.0)


def _pooled_std(control: list, treatment: list) -> float:
    """计算两组合并标准差。"""
    n1, n2 = len(control), len(treatment)
    if n1 < 2 or n2 < 2:
        return 0.0
    v1 = statistics.variance(control) if n1 > 1 else 0.0
    v2 = statistics.variance(treatment) if n2 > 1 else 0.0
    return math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))


def _bonferroni_correct(p_values: list, alpha: float = 0.05) -> list:
    """Bonferroni 多重比较校正。

    Args:
        p_values: 原始 p-value 列表。
        alpha: 总体显著性水平。

    Returns:
        (corrected_alpha, is_significant_list)
    """
    m = len(p_values)
    if m == 0:
        return alpha, []
    corrected_alpha = alpha / m
    return corrected_alpha, [p < corrected_alpha for p in p_values]


def _required_sample_size(effect_size: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """计算两组独立 t-test 所需最小样本量（每组）。

    使用正态近似公式:
        n = 2 * ((z_{alpha/2} + z_beta) / d)^2

    Args:
        effect_size: 期望检测的 Cohen's d 效应量。
        alpha: 显著性水平（双尾）。
        power: 检验功效 (1 - beta)。

    Returns:
        每组所需最小样本量。
    """
    if effect_size <= 0:
        return float("inf")

    # z 分数
    z_alpha = _normal_quantile(1.0 - alpha / 2.0)
    z_beta = _normal_quantile(power)

    n = 2.0 * ((z_alpha + z_beta) / effect_size) ** 2
    return max(4, math.ceil(n))


def _normal_quantile(p: float) -> float:
    """标准正态分布分位数（Acklam 近似）。

    Args:
        p: 累积概率 (0 < p < 1)。

    Returns:
        对应的 z 值。
    """
    if p <= 0 or p >= 1:
        return 0.0

    if _HAS_SCIPY:
        return scipy_stats.norm.ppf(p)

    # Acklam 近似算法
    # 系数
    a1 = -3.969683028665376e01
    a2 = 2.209460984245205e02
    a3 = -2.759285104469687e02
    a4 = 1.383577518672690e02
    a5 = -3.066479806614716e01
    a6 = 2.506628277459239e00

    b1 = -5.447609879822406e01
    b2 = 1.615858368580409e02
    b3 = -1.556989798598866e02
    b4 = 6.680131188771972e01
    b5 = -1.328068155288572e01

    c1 = -7.784894002430293e-03
    c2 = -3.223964580411365e-01
    c3 = -2.400758277161838e00
    c4 = -2.549732539343734e00
    c5 = 4.374664141464968e00
    c6 = 2.938163982698783e00

    d1 = 7.784695709041462e-03
    d2 = 3.224671290700398e-01
    d3 = 2.445134137142996e00
    d4 = 3.754408661907416e00

    p_low = 0.02425
    p_high = 1.0 - p_low

    if p < p_low:
        # 左尾
        q = math.sqrt(-2.0 * math.log(p))
        z = (((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6) / (
            ((((d1 * q + d2) * q + d3) * q + d4) * q + 1.0)
        )
    elif p <= p_high:
        # 中间区域
        q = p - 0.5
        r = q * q
        z = (((((a1 * r + a2) * r + a3) * r + a4) * r + a5) * r + a6) * q / (
            ((((b1 * r + b2) * r + b3) * r + b4) * r + b5) * r + 1.0
        )
    else:
        # 右尾
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        z = -(((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6) / (
            ((((d1 * q + d2) * q + d3) * q + d4) * q + 1.0)
        )
    return z


# ===========================================================================
# ExperimentAnalyzer
# ===========================================================================


class ExperimentAnalyzer:
    """A/B 实验结果分析器。

    封装 ChampionChallenger 实例，提供置信区间、显著检验、效应量、
    功效分析和完整实验报告功能。

    Args:
        champion_challenger_instance: ChampionChallenger 实例。
    """

    def __init__(self, champion_challenger_instance):
        self.cc = champion_challenger_instance
        self.config = champion_challenger_instance.config
        self._last_tests = {}  # 缓存最近的检验结果

    # ---- 数据获取 -----------------------------------------------------------

    def _get_data(self, metric: str) -> tuple:
        """获取指定指标的两组原始值。

        Returns:
            (control_values, treatment_values)
        """
        raw = self.cc._get_raw_values(metric)
        return raw.get("control", []), raw.get("treatment", [])

    # ---- 置信区间 -----------------------------------------------------------

    def compute_confidence_interval(
        self, metric: str, group: str, confidence: float = 0.95, method: str = "auto"
    ) -> tuple:
        """计算指定组在某指标上的置信区间。

        Args:
            metric: 指标名。
            group: 组名 ('control' 或 'treatment')。
            confidence: 置信水平，默认 0.95。
            method: 方法，'auto' | 't' | 'bootstrap'。auto 优先使用 t 分布。

        Returns:
            (lower, upper) 置信区间上下界。
        """
        control, treatment = self._get_data(metric)
        values = control if group == "control" else treatment

        if len(values) < 2:
            return (float("nan"), float("nan"))

        mean = statistics.mean(values)
        n = len(values)

        if method == "auto" or method == "t":
            if _HAS_SCIPY:
                # 使用 scipy 的 t.interval
                sem = statistics.stdev(values) / math.sqrt(n) if n > 1 else 0.0
                if sem > 0:
                    ci = scipy_t.interval(confidence, df=n - 1, loc=mean, scale=sem)
                    return (ci[0], ci[1])
            else:
                # 手动计算 t 分布 CI
                sem = statistics.stdev(values) / math.sqrt(n) if n > 1 else 0.0
                if sem > 0:
                    t_crit = _normal_quantile(1.0 - (1.0 - confidence) / 2.0)
                    # 小样本时近似用 t 分布
                    if n < 30:
                        t_crit = _t_approx_critical(1.0 - (1.0 - confidence) / 2.0, n - 1)
                    margin = t_crit * sem
                    return (mean - margin, mean + margin)

        # bootstrap 方法
        return _bootstrap_ci_single(values, ci=confidence)

    def compute_ci_diff(
        self, metric: str, confidence: float = 0.95, method: str = "auto"
    ) -> dict:
        """计算两组均值差的置信区间。

        Args:
            metric: 指标名。
            confidence: 置信水平。
            method: 'auto' | 't' | 'bootstrap'。

        Returns:
            {
                'mean_diff': float,          # treatment - control
                'ci_lower': float,
                'ci_upper': float,
                'method': str
            }
        """
        control, treatment = self._get_data(metric)
        if len(control) < 2 or len(treatment) < 2:
            return {"mean_diff": float("nan"), "ci_lower": float("nan"), "ci_upper": float("nan"), "method": "none"}

        m1, m2 = statistics.mean(control), statistics.mean(treatment)
        mean_diff = m2 - m1

        if method == "auto" or method == "t":
            if _HAS_SCIPY and len(control) > 1 and len(treatment) > 1:
                # Welch t-interval for difference of means
                v1 = statistics.variance(control)
                v2 = statistics.variance(treatment)
                n1, n2 = len(control), len(treatment)
                se = math.sqrt(v1 / n1 + v2 / n2)

                # Welch-Satterthwaite df
                num = (v1 / n1 + v2 / n2) ** 2
                den = (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
                df = num / den if den > 0 else 1.0

                if se > 0 and df > 0:
                    t_crit = scipy_t.ppf(1.0 - (1.0 - confidence) / 2.0, df)
                    margin = t_crit * se
                    return {
                        "mean_diff": mean_diff,
                        "ci_lower": mean_diff - margin,
                        "ci_upper": mean_diff + margin,
                        "method": "welch_t",
                    }

        # bootstrap fallback
        lower, upper = _bootstrap_ci_diff(control, treatment, ci=confidence)
        return {
            "mean_diff": mean_diff,
            "ci_lower": lower,
            "ci_upper": upper,
            "method": "bootstrap",
        }

    # ---- 显著检验 -----------------------------------------------------------

    def significance_test(
        self,
        metric: str,
        alpha: float = 0.05,
        method: str = "auto",
    ) -> dict:
        """对两组在指定指标上进行显著性检验。

        Args:
            metric: 指标名。
            alpha: 显著性水平。
            method: 'auto' | 't_test' | 'mann_whitney' | 'bootstrap'。

        Returns:
            {
                'p_value': float,
                'significant': bool,
                'method': str,           # 实际使用的方法
                'test_statistic': float,
                'control_mean': float,
                'treatment_mean': float,
                'lift_pct': float,
                'n_control': int,
                'n_treatment': int,
            }
        """
        control, treatment = self._get_data(metric)
        n1, n2 = len(control), len(treatment)

        if n1 < 2 or n2 < 2:
            return {
                "p_value": 1.0,
                "significant": False,
                "method": "insufficient_data",
                "test_statistic": 0.0,
                "control_mean": statistics.mean(control) if control else 0.0,
                "treatment_mean": statistics.mean(treatment) if treatment else 0.0,
                "lift_pct": 0.0,
                "n_control": n1,
                "n_treatment": n2,
            }

        m1 = statistics.mean(control)
        m2 = statistics.mean(treatment)
        lift = ((m2 - m1) / m1 * 100) if m1 != 0 else 0.0

        if method == "auto":
            # 自动选择: 大样本/正态->Welch t; 小样本->Mann-Whitney
            if n1 >= 30 and n2 >= 30:
                t_stat, p_val, df, meth = _welch_ttest(control, treatment)
                method_used = meth
            else:
                u_stat, p_val, meth = _mann_whitney_u(control, treatment)
                t_stat = u_stat
                method_used = meth

            # 如果 p 值可疑（如恰好为 1.0），尝试另一种方法
            if p_val >= 1.0 or math.isnan(p_val):
                if method_used.startswith("welch"):
                    u_stat, p_val, meth = _mann_whitney_u(control, treatment)
                    t_stat = u_stat
                    method_used = meth
                else:
                    t_stat, p_val, df, meth = _welch_ttest(control, treatment)
                    method_used = meth

        elif method == "t_test":
            t_stat, p_val, df, method_used = _welch_ttest(control, treatment)
        elif method == "mann_whitney":
            t_stat, p_val, method_used = _mann_whitney_u(control, treatment)
        elif method == "bootstrap":
            lower, upper = _bootstrap_ci_diff(control, treatment, ci=1.0 - alpha)
            # bootstrap 不直接给 p-value，用 CI 推断显著性
            p_val = alpha if (lower <= 0 <= upper) else alpha / 100.0
            method_used = "bootstrap"
            t_stat = 0.0
        else:
            t_stat, p_val, df, method_used = _welch_ttest(control, treatment)

        significant = p_val < alpha

        result = self._to_native({
            "p_value": round(p_val, 6),
            "significant": significant,
            "method": method_used,
            "test_statistic": round(t_stat, 6),
            "control_mean": round(m1, 6),
            "treatment_mean": round(m2, 6),
            "lift_pct": round(lift, 4),
            "n_control": n1,
            "n_treatment": n2,
        })
        self._last_tests[metric] = result
        return result

    # ---- 效应量 -------------------------------------------------------------

    def _to_native(self, obj):
        """将 numpy 类型转换为 Python 原生类型。"""
        if isinstance(obj, (list, tuple)):
            return [self._to_native(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self._to_native(v) for k, v in obj.items()}
        if hasattr(obj, "item"):
            return obj.item()
        return obj

    def effect_size(self, metric: str, method: str = "cohens_d") -> dict:
        """计算两组在指定指标上的效应量。

        Args:
            metric: 指标名。
            method: 'cohens_d' | 'hedges_g' | 'cliffs_delta'。

        Returns:
            {
                'effect_size': float,
                'method': str,
                'interpretation': str,
                'control_mean': float,
                'treatment_mean': float,
                'pooled_std': float,
                'direction': str,
            }
        """
        control, treatment = self._get_data(metric)
        n1, n2 = len(control), len(treatment)

        if n1 < 2 or n2 < 2:
            return self._to_native({
                "effect_size": 0.0,
                "method": method,
                "interpretation": "insufficient_data",
                "control_mean": statistics.mean(control) if control else 0.0,
                "treatment_mean": statistics.mean(treatment) if treatment else 0.0,
                "pooled_std": 0.0,
                "direction": "unknown",
            })

        m1 = statistics.mean(control)
        m2 = statistics.mean(treatment)

        if method == "hedges_g":
            es = _hedges_g(control, treatment)
        else:
            # 默认 Cohen's d
            es = _cohens_d(control, treatment)

        pooled_s = _pooled_std(control, treatment)

        # 效应量解释（Cohen 标准）
        abs_es = abs(es)
        if abs_es < 0.2:
            interp = "very_small"
        elif abs_es < 0.5:
            interp = "small"
        elif abs_es < 0.8:
            interp = "medium"
        else:
            interp = "large"

        return self._to_native({
            "effect_size": round(es, 6),
            "method": method,
            "interpretation": interp,
            "control_mean": round(m1, 6),
            "treatment_mean": round(m2, 6),
            "pooled_std": round(pooled_s, 6),
            "direction": "treatment_higher" if es > 0 else "control_higher",
        })

    # ---- 功效分析 -----------------------------------------------------------

    def power_analysis(
        self,
        effect_size: Optional[float] = None,
        metric: Optional[str] = None,
        alpha: float = 0.05,
        power: float = 0.8,
    ) -> dict:
        """功效分析：计算检测给定效应量所需最小样本量。

        必须提供 effect_size 或 metric 之一。
        如果提供 metric，则从实际数据计算 Cohen's d。

        Args:
            effect_size: 期望检测的效应量（Cohen's d）。如果提供则忽略 metric。
            metric: 指标名，用于从数据计算效应量。
            alpha: 显著性水平。
            power: 检验功效 (1 - beta)。

        Returns:
            {
                'required_n_per_group': int,
                'effect_size': float,
                'alpha': float,
                'power': float,
                'interpretation': str,
            }
        """
        if effect_size is None and metric is None:
            raise ValueError("必须提供 effect_size 或 metric 之一")

        if effect_size is None and metric is not None:
            es_info = self.effect_size(metric)
            effect_size = es_info["effect_size"]

        if effect_size is None or effect_size <= 0:
            return {
                "required_n_per_group": float("inf"),
                "effect_size": 0.0,
                "alpha": alpha,
                "power": power,
                "interpretation": "效应量过小或为零，无法计算样本量",
            }

        n = _required_sample_size(effect_size, alpha, power)

        interpretation = (
            f"每组至少需要 {n} 个样本才能以 {power*100:.0f}% 的检验功效"
            f"检测到 Cohen's d = {effect_size:.3f} 的效应量（α = {alpha}）。"
        )

        return {
            "required_n_per_group": n,
            "effect_size": round(effect_size, 6),
            "alpha": alpha,
            "power": power,
            "interpretation": interpretation,
        }

    # ---- 完整报告 -----------------------------------------------------------

    def report(self, experiment_id: str, alpha: float = 0.05, bonferroni: bool = True) -> dict:
        """生成完整的 A/B 实验分析报告。

        Args:
            experiment_id: 实验 ID（用于元数据）。
            alpha: 显著性水平。
            bonferroni: 是否对多指标进行 Bonferroni 校正。

        Returns:
            dict: 包含实验元数据、各指标分析结果、汇总统计的完整报告。
        """
        metrics = self.config.metrics
        n_metrics = len(metrics)

        # ---- 收集各指标数据 ----
        metrics_analysis = {}
        all_p_values = []
        metric_results = []

        for metric in metrics:
            sig = self.significance_test(metric, alpha=alpha)
            es = self.effect_size(metric)
            ci_diff = self.compute_ci_diff(metric)
            ci_control = self.compute_confidence_interval(metric, "control")
            ci_treatment = self.compute_confidence_interval(metric, "treatment")

            all_p_values.append(sig["p_value"])

            metric_results.append(
                {
                    "metric": metric,
                    "control": {
                        "mean": sig["control_mean"],
                        "n": sig["n_control"],
                        "ci_95": list(ci_control),
                    },
                    "treatment": {
                        "mean": sig["treatment_mean"],
                        "n": sig["n_treatment"],
                        "ci_95": list(ci_treatment),
                    },
                    "difference": {
                        "mean_diff": ci_diff["mean_diff"],
                        "ci_95": [ci_diff["ci_lower"], ci_diff["ci_upper"]],
                        "lift_pct": sig["lift_pct"],
                    },
                    "significance": {
                        "p_value": sig["p_value"],
                        "significant": sig["significant"],
                        "method": sig["method"],
                        "test_statistic": sig["test_statistic"],
                    },
                    "effect_size": {
                        "d": es["effect_size"],
                        "method": es["method"],
                        "interpretation": es["interpretation"],
                        "direction": es["direction"],
                    },
                }
            )

        # ---- 多重比较校正 ----
        corrected_alpha = alpha
        bonferroni_results = None
        if bonferroni and n_metrics > 1:
            corrected_alpha, significant_after_correction = _bonferroni_correct(
                all_p_values, alpha
            )
            bonferroni_results = {
                "corrected_alpha": corrected_alpha,
                "significant_after_correction": significant_after_correction,
                "n_tests": n_metrics,
            }
            # 更新每个指标的显著状态
            for i, mr in enumerate(metric_results):
                mr["significance"]["significant_bonferroni"] = significant_after_correction[i]

        # ---- 汇总 ----
        n_significant = sum(
            1 for mr in metric_results if mr["significance"]["significant"]
        )
        n_significant_corrected = (
            sum(bonferroni_results["significant_after_correction"])
            if bonferroni_results
            else n_significant
        )

        # 获取样本量
        control, treatment = self._get_data(metrics[0]) if metrics else ([], [])
        n_control_total = len(control) if metrics else 0
        n_treatment_total = len(treatment) if metrics else 0

        # 尝试从 cc 获取总样本量
        try:
            total_samples = self.cc._count_samples()
        except Exception:
            total_samples = n_control_total + n_treatment_total

        # 综合判定胜者
        if total_samples < self.config.min_samples:
            winner = "insufficient_samples"
            winner_reason = (
                f"总样本量 {total_samples} 未达到最低要求 {self.config.min_samples}"
            )
        elif n_significant_corrected > n_metrics / 2:
            winner = "treatment"
            winner_reason = f"挑战者在 {n_significant_corrected}/{n_metrics} 个指标上显著优胜（Bonferroni 校正后）"
        elif n_significant_corrected > 0:
            winner = "partial"
            winner_reason = f"挑战者在 {n_significant_corrected}/{n_metrics} 个指标上显著，但未过半"
        else:
            winner = "control"
            winner_reason = f"挑战者在任何指标上均未达到统计显著（α={alpha}）"

        report_dict = self._to_native({
            "experiment_id": experiment_id,
            "experiment_name": self.config.name,
            "description": self.config.description,
            "control_model": self.config.control_model,
            "treatment_model": self.config.treatment_model,
            "traffic_split": self.config.traffic_split,
            "min_samples_required": self.config.min_samples,
            "total_samples": total_samples,
            "n_control": n_control_total,
            "n_treatment": n_treatment_total,
            "alpha": alpha,
            "bonferroni_correction": bonferroni_results,
            "winner": winner,
            "winner_reason": winner_reason,
            "metrics": metric_results,
            "summary": {
                "n_metrics": n_metrics,
                "n_significant": n_significant,
                "n_significant_bonferroni": n_significant_corrected,
                "overall_winner": winner,
            },
        })

        return report_dict

    # ---- 汇总统计 -----------------------------------------------------------

    def summary(self) -> dict:
        """快速汇总所有指标的基本统计。"""
        results = {}
        for metric in self.config.metrics:
            control, treatment = self._get_data(metric)
            results[metric] = {
                "control": {
                    "mean": round(statistics.mean(control), 6) if control else None,
                    "std": round(statistics.stdev(control), 6) if len(control) > 1 else None,
                    "n": len(control),
                    "min": min(control) if control else None,
                    "max": max(control) if control else None,
                },
                "treatment": {
                    "mean": round(statistics.mean(treatment), 6) if treatment else None,
                    "std": round(statistics.stdev(treatment), 6) if len(treatment) > 1 else None,
                    "n": len(treatment),
                    "min": min(treatment) if treatment else None,
                    "max": max(treatment) if treatment else None,
                },
            }
        return results


# ===========================================================================
# 辅助: t 分布临界值近似（小样本）
# ===========================================================================


def _t_approx_critical(p: float, df: float) -> float:
    """t 分布临界值近似（Hill & Davis 算法）。

    当 scipy 不可用且 df 较小时使用。
    """
    if df <= 0:
        return _normal_quantile(p)
    if df > 100:
        return _normal_quantile(p)

    # 粗略近似: 用正态分位数加校正
    z = _normal_quantile(p)
    # Hill & Davis 近似
    g1 = (z**3 + z) / 4.0
    g2 = (5 * z**5 + 16 * z**3 + 3 * z) / 96.0
    g3 = (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / 384.0
    t = z + g1 / df + g2 / (df**2) + g3 / (df**3)
    return t


# ===========================================================================
# ReportGenerator
# ===========================================================================


class ReportGenerator:
    """报告生成器。

    将 ExperimentAnalyzer.report() 的输出转换为多种格式。
    """

    @staticmethod
    def generate_markdown(analyzer_report: dict) -> str:
        """生成 Markdown 格式的分析报告。

        Args:
            analyzer_report: ExperimentAnalyzer.report() 的输出。

        Returns:
            Markdown 格式的字符串。
        """
        lines = []
        r = analyzer_report

        # ---- 标题 ----
        lines.append(f"# A/B 实验分析报告: {r['experiment_name']}")
        lines.append("")
        lines.append(f"- **实验 ID:** `{r['experiment_id']}`")
        lines.append(f"- **描述:** {r['description']}")
        lines.append(f"- **对照组:** `{r['control_model']}`")
        lines.append(f"- **实验组:** `{r['treatment_model']}`")
        lines.append(f"- **流量分配:** 对照组 {r['traffic_split']*100:.0f}% / 实验组 {(1-r['traffic_split'])*100:.0f}%")
        lines.append(f"- **显著性水平 (α):** {r['alpha']}")
        if r["bonferroni_correction"]:
            lines.append(
                f"- **Bonferroni 校正:** 是 (校正后 α = {r['bonferroni_correction']['corrected_alpha']:.6f}, "
                f"{r['bonferroni_correction']['n_tests']} 个指标)"
            )
        else:
            lines.append("- **Bonferroni 校正:** 否")
        lines.append("")

        # ---- 样本量 ----
        lines.append("## 样本量信息")
        lines.append("")
        lines.append(f"| 项目 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 总样本量 | {r['total_samples']} |")
        lines.append(f"| 对照组 | {r['n_control']} |")
        lines.append(f"| 实验组 | {r['n_treatment']} |")
        lines.append(f"| 最低要求 | {r['min_samples_required']} |")
        lines.append("")

        # ---- 胜者判定 ----
        winner_emoji = {
            "treatment": "🏆",
            "control": "✅",
            "partial": "⚠️",
            "insufficient_samples": "❌",
        }
        emoji = winner_emoji.get(r["winner"], "❓")
        lines.append(f"## 胜者判定: {emoji} **{r['winner'].upper()}**")
        lines.append("")
        lines.append(f"> {r['winner_reason']}")
        lines.append("")

        # ---- 各指标详细分析 ----
        lines.append("## 各指标分析")
        lines.append("")

        for mr in r["metrics"]:
            metric = mr["metric"]
            lines.append(f"### {metric}")
            lines.append("")

            # 基本统计
            lines.append("**基本统计:**")
            lines.append("")
            lines.append(f"| 统计量 | 对照组 | 实验组 |")
            lines.append(f"|--------|--------|--------|")
            lines.append(
                f"| 均值 | {mr['control']['mean']:.6f} | {mr['treatment']['mean']:.6f} |"
            )
            lines.append(
                f"| 样本量 | {mr['control']['n']} | {mr['treatment']['n']} |"
            )
            lines.append(
                f"| 95% CI | [{mr['control']['ci_95'][0]:.6f}, {mr['control']['ci_95'][1]:.6f}] | "
                f"[{mr['treatment']['ci_95'][0]:.6f}, {mr['treatment']['ci_95'][1]:.6f}] |"
            )
            lines.append("")

            # 差异
            lines.append("**组间差异:**")
            lines.append("")
            lines.append(f"| 指标 | 值 |")
            lines.append(f"|------|-----|")
            lines.append(f"| 均值差 (实验 - 对照) | {mr['difference']['mean_diff']:.6f} |")
            lines.append(f"| 提升百分比 | {mr['difference']['lift_pct']:+.4f}% |")
            lines.append(
                f"| 95% CI 均值差 | [{mr['difference']['ci_95'][0]:.6f}, {mr['difference']['ci_95'][1]:.6f}] |"
            )
            lines.append("")

            # 显著检验
            sig = mr["significance"]
            sig_text = "✅ **显著**" if sig["significant"] else "❌ **不显著**"
            if sig.get("significant_bonferroni") is not None:
                sig_bonf = (
                    "✅ 显著"
                    if sig["significant_bonferroni"]
                    else "❌ 不显著"
                )
                sig_text += f" (Bonferroni 校正: {sig_bonf})"

            lines.append("**显著性检验:**")
            lines.append("")
            lines.append(f"| 指标 | 值 |")
            lines.append(f"|------|-----|")
            lines.append(f"| 检验方法 | {sig['method']} |")
            lines.append(f"| 检验统计量 | {sig['test_statistic']:.4f} |")
            lines.append(f"| p-value | {sig['p_value']:.6f} |")
            lines.append(f"| 结论 | {sig_text} |")
            lines.append("")

            # 效应量
            es = mr["effect_size"]
            interp_map = {
                "very_small": "非常小",
                "small": "小",
                "medium": "中",
                "large": "大",
                "insufficient_data": "数据不足",
            }
            interp_cn = interp_map.get(es["interpretation"], es["interpretation"])
            dir_cn = "实验组 > 对照组" if es["direction"] == "treatment_higher" else "对照组 > 实验组"

            lines.append("**效应量:**")
            lines.append("")
            lines.append(f"| 指标 | 值 |")
            lines.append(f"|------|-----|")
            lines.append(f"| {es['method']} | {es['d']:.6f} |")
            lines.append(f"| 解释 | {interp_cn} 效应量 |")
            lines.append(f"| 方向 | {dir_cn} |")
            lines.append("")
            lines.append("---")
            lines.append("")

        # ---- 汇总 ----
        lines.append("## 汇总")
        lines.append("")
        lines.append(f"- 分析指标数: {r['summary']['n_metrics']}")
        lines.append(f"- 显著指标数 (未校正): {r['summary']['n_significant']}")
        lines.append(f"- 显著指标数 (Bonferroni 校正): {r['summary']['n_significant_bonferroni']}")
        lines.append(f"- 最终判定: **{r['summary']['overall_winner']}**")
        lines.append("")
        lines.append("---")
        lines.append(f"*报告生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(lines)

    @staticmethod
    def generate_json(analyzer_report: dict, indent: int = 2) -> str:
        """生成 JSON 格式的分析报告。

        Args:
            analyzer_report: ExperimentAnalyzer.report() 的输出。
            indent: JSON 缩进空格数。

        Returns:
            JSON 格式的字符串。
        """
        # 处理不可序列化类型
        def _serialize(obj):
            if isinstance(obj, (float, int)):
                if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
                    return str(obj)
                return obj
            return obj

        return json.dumps(analyzer_report, indent=indent, default=_serialize, ensure_ascii=False)

    @staticmethod
    def generate_html(analyzer_report: dict) -> str:
        """生成内嵌 HTML 看板。

        Args:
            analyzer_report: ExperimentAnalyzer.report() 的输出。

        Returns:
            自包含的 HTML 字符串（简单看板风格）。
        """
        r = analyzer_report

        # 构建指标行
        rows_html = ""
        for mr in r["metrics"]:
            sig = mr["significance"]
            es = mr["effect_size"]

            sig_color = "#27ae60" if sig["significant"] else "#e74c3c"
            sig_text = "显著" if sig["significant"] else "不显著"

            if sig.get("significant_bonferroni") is not None:
                bonf_color = "#27ae60" if sig["significant_bonferroni"] else "#e74c3c"
                bonf_text = "显著" if sig["significant_bonferroni"] else "不显著"
                bonf_html = f'<span style="color:{bonf_color};font-size:0.85em">(Bonferroni: {bonf_text})</span>'
            else:
                bonf_html = ""

            rows_html += f"""
            <div class="metric-card">
                <h3>{mr['metric']}</h3>
                <table>
                    <tr><th>统计量</th><th>对照组</th><th>实验组</th></tr>
                    <tr><td>均值</td><td>{mr['control']['mean']:.6f}</td><td>{mr['treatment']['mean']:.6f}</td></tr>
                    <tr><td>样本量</td><td>{mr['control']['n']}</td><td>{mr['treatment']['n']}</td></tr>
                    <tr><td>95% CI</td><td>[{mr['control']['ci_95'][0]:.6f}, {mr['control']['ci_95'][1]:.6f}]</td>
                        <td>[{mr['treatment']['ci_95'][0]:.6f}, {mr['treatment']['ci_95'][1]:.6f}]</td></tr>
                </table>
                <div class="diff-section">
                    <strong>均值差:</strong> {mr['difference']['mean_diff']:.6f} &nbsp;
                    <strong>提升:</strong> <span class="{'positive' if mr['difference']['lift_pct'] > 0 else 'negative'}">{mr['difference']['lift_pct']:+.4f}%</span><br>
                    <strong>95% CI 差:</strong> [{mr['difference']['ci_95'][0]:.6f}, {mr['difference']['ci_95'][1]:.6f}]
                </div>
                <div class="test-section">
                    <strong>检验:</strong> {sig['method']} &nbsp;
                    <strong>p-value:</strong> {sig['p_value']:.6f} &nbsp;
                    <strong>结论:</strong> <span style="color:{sig_color};font-weight:bold">{sig_text}</span> {bonf_html}<br>
                    <strong>效应量 ({es['method']}):</strong> {es['d']:.6f} &nbsp;
                    <strong>解释:</strong> {es['interpretation']} &nbsp;
                    <strong>方向:</strong> {es['direction']}
                </div>
            </div>
            """

        # 胜者颜色
        winner_colors = {
            "treatment": "#27ae60",
            "control": "#2980b9",
            "partial": "#f39c12",
            "insufficient_samples": "#e74c3c",
        }
        wc = winner_colors.get(r["winner"], "#95a5a6")

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A/B 实验分析报告 - {r['experiment_name']}</title>
<style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: #f5f6fa; color: #2c3e50; padding: 20px; }}
    .container {{ max-width: 1000px; margin: 0 auto; }}
    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
               color: white; padding: 30px; border-radius: 12px; margin-bottom: 20px; }}
    .header h1 {{ font-size: 1.8em; margin-bottom: 10px; }}
    .header .meta {{ font-size: 0.9em; opacity: 0.9; }}
    .winner-banner {{ padding: 15px 20px; border-radius: 8px; margin-bottom: 20px;
                     color: white; font-size: 1.2em; font-weight: bold; text-align: center;
                     background-color: {wc}; }}
    .winner-banner small {{ font-weight: normal; font-size: 0.7em; display: block; margin-top: 5px; opacity: 0.85; }}
    .summary-box {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
    .summary-box table {{ width: 100%; border-collapse: collapse; }}
    .summary-box th, .summary-box td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #ecf0f1; }}
    .metric-card {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 15px;
                   box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
    .metric-card h3 {{ color: #2c3e50; border-bottom: 2px solid #667eea; padding-bottom: 8px; margin-bottom: 12px; }}
    .metric-card table {{ width: 100%; border-collapse: collapse; margin-bottom: 12px; }}
    .metric-card th, .metric-card td {{ padding: 6px 10px; text-align: left; border-bottom: 1px solid #ecf0f1; font-size: 0.9em; }}
    .metric-card th {{ background: #f8f9fa; font-weight: 600; }}
    .diff-section, .test-section {{ background: #f8f9fa; padding: 10px; border-radius: 6px; margin-top: 8px; font-size: 0.9em; line-height: 1.8; }}
    .positive {{ color: #27ae60; }}
    .negative {{ color: #e74c3c; }}
    .footer {{ text-align: center; color: #95a5a6; font-size: 0.85em; margin-top: 30px; padding: 20px; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>📊 A/B 实验分析报告</h1>
        <div class="meta">
            <strong>{r['experiment_name']}</strong> ({r['experiment_id']})<br>
            对照组: {r['control_model']} | 实验组: {r['treatment_model']}<br>
            流量: 对照 {r['traffic_split']*100:.0f}% / 实验 {(1-r['traffic_split'])*100:.0f}% |
            α = {r['alpha']} |
            Bonferroni: {'是' if r['bonferroni_correction'] else '否'}
        </div>
    </div>

    <div class="winner-banner">
        🏆 {r['winner'].upper()}
        <small>{r['winner_reason']}</small>
    </div>

    <div class="summary-box">
        <h2>📋 样本量信息</h2>
        <table>
            <tr><td>总样本量</td><td>{r['total_samples']}</td></tr>
            <tr><td>对照组</td><td>{r['n_control']}</td></tr>
            <tr><td>实验组</td><td>{r['n_treatment']}</td></tr>
            <tr><td>最低要求</td><td>{r['min_samples_required']}</td></tr>
            <tr><td>显著指标 (未校正)</td><td>{r['summary']['n_significant']} / {r['summary']['n_metrics']}</td></tr>
            <tr><td>显著指标 (Bonferroni校正)</td><td>{r['summary']['n_significant_bonferroni']} / {r['summary']['n_metrics']}</td></tr>
        </table>
    </div>

    <h2>📈 各指标详细分析</h2>
    {rows_html}
    <div class="footer">
        <p>链客宝 A/B 实验分析报告引擎 · {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
</div>
</body>
</html>"""
        return html


# ===========================================================================
# __init__ 辅助
# ===========================================================================

__all__ = [
    "ExperimentAnalyzer",
    "ReportGenerator",
]
