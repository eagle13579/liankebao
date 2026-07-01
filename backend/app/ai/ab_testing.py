"""
AI数字名片 A/B测试引擎
──────────────────────────────────────────
功能：创建实验 / 分发版本 / 收集指标 / 统计显著性检验
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime
from typing import Any

# ─── 统计工具 ─────────────────────────────────────────────


def z_score(alpha: float = 0.05, two_tailed: bool = True) -> float:
    """近似 Z 临界值（标准正态分布分位数）。"""
    # 使用 Abramowitz & Stegun 近似
    if two_tailed:
        p = 1.0 - alpha / 2.0
    else:
        p = 1.0 - alpha
    t = math.sqrt(-2.0 * math.log(1.0 - p))
    return t - (2.515517 + 0.802853 * t + 0.010328 * t * t) / (
        1.0 + 1.432788 * t + 0.189269 * t * t + 0.001308 * t * t * t
    )


def chi_square_pvalue(observed: list[list[int]]) -> float:
    """
    卡方检验 p-value（2x2 列联表）。
    observed = [[control_success, control_fail], [variant_success, variant_fail]]
    返回双侧 p-value。
    """
    # 自由度 df = 1
    n = [[float(v) for v in row] for row in observed]
    row_totals = [sum(n[0]), sum(n[1])]
    col_totals = [n[0][0] + n[1][0], n[0][1] + n[1][1]]
    total = sum(row_totals)

    if total == 0 or any(c == 0 for c in col_totals):
        return 1.0

    # 期望频率
    expected = [
        [row_totals[0] * col_totals[0] / total, row_totals[0] * col_totals[1] / total],
        [row_totals[1] * col_totals[0] / total, row_totals[1] * col_totals[1] / total],
    ]

    chi2 = 0.0
    for i in range(2):
        for j in range(2):
            if expected[i][j] > 0:
                chi2 += (n[i][j] - expected[i][j]) ** 2 / expected[i][j]

    # 自由度 1 的卡方分布近似 p-value
    from math import erfc

    if chi2 <= 0:
        return 1.0
    # 对于 df=1: p = erfc(sqrt(chi2/2))
    p = erfc(math.sqrt(chi2 / 2.0))
    return min(p, 1.0)


def bayesian_win_probability(
    control_success: int,
    control_total: int,
    variant_success: int,
    variant_total: int,
    simulations: int = 100_000,
) -> tuple[float, float]:
    """
    贝叶斯方法估算 variant 胜过 control 的概率。
    使用 Beta 分布蒙特卡洛模拟。
    返回 (win_probability, expected_lift).
    """
    if control_total <= 0 or variant_total <= 0:
        return 0.5, 0.0

    # Beta 先验 Beta(1,1) = 均匀分布
    alpha_c = control_success + 1
    beta_c = control_total - control_success + 1
    alpha_v = variant_success + 1
    beta_v = variant_total - variant_success + 1

    wins = 0
    total_lift = 0.0
    for _ in range(simulations):
        # 从 Beta 分布采样
        c_rate = random.betavariate(alpha_c, beta_c)
        v_rate = random.betavariate(alpha_v, beta_v)
        if v_rate > c_rate:
            wins += 1
        total_lift += (v_rate - c_rate) / (c_rate if c_rate > 0 else 0.01)

    win_prob = wins / simulations
    expected_lift = total_lift / simulations
    return win_prob, expected_lift


# ─── 实验状态常量 ─────────────────────────────────────────

EXPERIMENT_STATUS_DRAFT = "draft"
EXPERIMENT_STATUS_RUNNING = "running"
EXPERIMENT_STATUS_PAUSED = "paused"
EXPERIMENT_STATUS_COMPLETED = "completed"

# ─── 实验配置 ─────────────────────────────────────────────


class ExperimentConfig:
    """实验配置参数。"""

    def __init__(
        self,
        name: str,
        description: str = "",
        traffic_fraction: float = 1.0,  # 0.0 ~ 1.0
        control_name: str = "对照组",
        variants: list[dict[str, Any]] | None = None,
        min_sample_size: int = 100,  # 每组最小样本量
        significance_level: float = 0.05,  # α
        metric: str = "click_rate",  # click_rate | view_count | conversion
    ):
        self.name = name
        self.description = description
        self.traffic_fraction = max(0.01, min(1.0, traffic_fraction))
        self.control_name = control_name
        self.variants = variants or []
        self.min_sample_size = min_sample_size
        self.significance_level = significance_level
        self.metric = metric


# ─── 实验状态 ─────────────────────────────────────────────


class ExperimentState:
    """实验运行时状态。"""

    def __init__(
        self,
        experiment_id: int,
        config: ExperimentConfig,
    ):
        self.experiment_id = experiment_id
        self.config = config
        self.status: str = EXPERIMENT_STATUS_DRAFT
        self.created_at: datetime = datetime.now(UTC)
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.results: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "name": self.config.name,
            "description": self.config.description,
            "status": self.status,
            "traffic_fraction": self.config.traffic_fraction,
            "control_name": self.config.control_name,
            "variants": self.config.variants,
            "min_sample_size": self.config.min_sample_size,
            "significance_level": self.config.significance_level,
            "metric": self.config.metric,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "results": self.results,
        }


# ─── 版本分发器 ───────────────────────────────────────────


class VariantDistributor:
    """
    根据流量分配规则将用户分派到不同版本。
    支持：用户 ID 哈希、随机分配、权重分配。
    """

    @staticmethod
    def assign_by_user_id(
        user_id: int,
        variants: list[dict[str, Any]],
        seed: int = 42,
    ) -> int:
        """基于用户 ID 确定性的哈希分派，保证同一用户始终看到同一版本。"""
        raw = hash(f"{seed}:{user_id}")
        idx = abs(raw) % len(variants) if variants else 0
        return idx

    @staticmethod
    def assign_random(
        variants: list[dict[str, Any]],
        weights: list[float] | None = None,
    ) -> int:
        """随机分派，支持权重（weights 长度应与 variants 相同）。"""
        if not variants:
            return 0
        if weights and len(weights) == len(variants):
            total = sum(weights)
            r = random.uniform(0, total)
            cumulative = 0.0
            for i, w in enumerate(weights):
                cumulative += w
                if r <= cumulative:
                    return i
            return len(variants) - 1
        return random.randint(0, len(variants) - 1)


# ─── 指标收集器 ───────────────────────────────────────────


class MetricsCollector:
    """收集并聚合 A/B 测试指标数据。"""

    @staticmethod
    def aggregate_events(
        events: list[dict[str, Any]],
        metric: str = "click_rate",
    ) -> dict[int, dict[str, Any]]:
        """
        按 variant_id 聚合事件，计算各指标。
        返回 {variant_id: {impressions, clicks, conversions, rate, ...}}
        """
        from collections import defaultdict

        agg: dict[int, dict[str, Any]] = defaultdict(
            lambda: {"impressions": 0, "clicks": 0, "conversions": 0, "views": 0}
        )

        for ev in events:
            vid = ev.get("variant_id", 0)
            evt_type = ev.get("event_type", "")
            agg[vid]["impressions"] += 1
            if evt_type == "click":
                agg[vid]["clicks"] += 1
            elif evt_type == "conversion":
                agg[vid]["conversions"] += 1
            elif evt_type == "view":
                agg[vid]["views"] += 1

        results: dict[int, dict[str, Any]] = {}
        for vid, data in agg.items():
            imp = data["impressions"]
            data["click_rate"] = data["clicks"] / imp if imp > 0 else 0.0
            data["conversion_rate"] = data["conversions"] / imp if imp > 0 else 0.0
            data["view_rate"] = data["views"] / imp if imp > 0 else 0.0
            if metric == "click_rate":
                data["rate"] = data["click_rate"]
            elif metric == "conversion":
                data["rate"] = data["conversion_rate"]
            else:
                data["rate"] = data["view_rate"]
            results[vid] = data

        return results


# ─── 统计显著性检验 ───────────────────────────────────────


class SignificanceTester:
    """
    统计显著性检验引擎。
    支持：卡方检验、贝叶斯概率估算。
    """

    def __init__(self, alpha: float = 0.05):
        self.alpha = alpha

    def chi_square_test(
        self,
        control_impressions: int,
        control_success: int,
        variant_impressions: int,
        variant_success: int,
    ) -> dict[str, Any]:
        """
        卡方检验判断 variant 是否显著优于 control。
        """
        observed = [
            [control_success, control_impressions - control_success],
            [variant_success, variant_impressions - variant_success],
        ]
        p_value = chi_square_pvalue(observed)

        control_rate = control_success / control_impressions if control_impressions > 0 else 0.0
        variant_rate = variant_success / variant_impressions if variant_impressions > 0 else 0.0
        lift = variant_rate - control_rate
        relative_lift = (lift / control_rate * 100.0) if control_rate > 0 else 0.0

        is_significant = p_value < self.alpha

        return {
            "method": "chi_square",
            "control_rate": round(control_rate, 6),
            "variant_rate": round(variant_rate, 6),
            "lift": round(lift, 6),
            "relative_lift_pct": round(relative_lift, 4),
            "p_value": round(p_value, 6),
            "alpha": self.alpha,
            "is_significant": is_significant,
            "control_sample": control_impressions,
            "variant_sample": variant_impressions,
        }

    def bayesian_test(
        self,
        control_success: int,
        control_total: int,
        variant_success: int,
        variant_total: int,
    ) -> dict[str, Any]:
        """
        贝叶斯检验：估算 variant 优于 control 的概率和预期提升。
        """
        win_prob, expected_lift = bayesian_win_probability(
            control_success,
            control_total,
            variant_success,
            variant_total,
        )

        control_rate = control_success / control_total if control_total > 0 else 0.0
        variant_rate = variant_success / variant_total if variant_total > 0 else 0.0

        return {
            "method": "bayesian",
            "control_rate": round(control_rate, 6),
            "variant_rate": round(variant_rate, 6),
            "win_probability": round(win_prob, 6),
            "expected_lift": round(expected_lift, 6),
            "control_sample": control_total,
            "variant_sample": variant_total,
        }


# ─── 主引擎 ───────────────────────────────────────────────


class ABTestingEngine:
    """
    A/B 测试主引擎。封装实验全生命周期。
    """

    def __init__(self):
        self._experiments: dict[int, ExperimentState] = {}
        self._distributor = VariantDistributor()
        self._collector = MetricsCollector()
        self._tester = SignificanceTester()
        self._decision_logs: dict[int, list[dict]] = {}

    # ── 实验管理 ───────────────────────────────────────────

    def create_experiment(
        self,
        experiment_id: int,
        name: str,
        description: str = "",
        traffic_fraction: float = 1.0,
        control_name: str = "对照组",
        variants: list[dict[str, Any]] | None = None,
        min_sample_size: int = 100,
        significance_level: float = 0.05,
        metric: str = "click_rate",
    ) -> ExperimentState:
        """创建新实验。"""
        config = ExperimentConfig(
            name=name,
            description=description,
            traffic_fraction=traffic_fraction,
            control_name=control_name,
            variants=variants or [],
            min_sample_size=min_sample_size,
            significance_level=significance_level,
            metric=metric,
        )
        state = ExperimentState(experiment_id, config)
        state.status = EXPERIMENT_STATUS_DRAFT
        self._experiments[experiment_id] = state
        return state

    def get_experiment(self, experiment_id: int) -> ExperimentState | None:
        """获取实验状态。"""
        return self._experiments.get(experiment_id)

    def start_experiment(self, experiment_id: int) -> ExperimentState | None:
        """启动实验。"""
        state = self._experiments.get(experiment_id)
        if state and state.status == EXPERIMENT_STATUS_DRAFT:
            state.status = EXPERIMENT_STATUS_RUNNING
            state.started_at = datetime.now(UTC)
        return state

    def pause_experiment(self, experiment_id: int) -> ExperimentState | None:
        """暂停实验。"""
        state = self._experiments.get(experiment_id)
        if state and state.status == EXPERIMENT_STATUS_RUNNING:
            state.status = EXPERIMENT_STATUS_PAUSED
        return state

    def resume_experiment(self, experiment_id: int) -> ExperimentState | None:
        """恢复暂停的实验。"""
        state = self._experiments.get(experiment_id)
        if state and state.status == EXPERIMENT_STATUS_PAUSED:
            state.status = EXPERIMENT_STATUS_RUNNING
        return state

    def stop_experiment(self, experiment_id: int) -> ExperimentState | None:
        """停止实验并计算结果。"""
        state = self._experiments.get(experiment_id)
        if state and state.status in (EXPERIMENT_STATUS_RUNNING, EXPERIMENT_STATUS_PAUSED):
            state.status = EXPERIMENT_STATUS_COMPLETED
            state.completed_at = datetime.now(UTC)
        return state

    def delete_experiment(self, experiment_id: int) -> bool:
        """删除实验。"""
        return self._experiments.pop(experiment_id, None) is not None

    def list_experiments(self) -> list[ExperimentState]:
        """列出所有实验。"""
        return list(self._experiments.values())

    # ── 版本分发 ───────────────────────────────────────────

    def assign_variant(
        self,
        experiment_id: int,
        user_id: int | None = None,
        method: str = "random",
    ) -> int | None:
        """
        为用户分派实验版本。
        method: "random" | "user_hash"
        返回 variant_index（从 0 开始），或 None 如果实验未运行。
        """
        state = self._experiments.get(experiment_id)
        if not state or state.status != EXPERIMENT_STATUS_RUNNING:
            return None

        variants = state.config.variants
        if not variants:
            return None

        # 流量采样
        if random.random() > state.config.traffic_fraction:
            return None  # 未被选入实验

        if method == "user_hash" and user_id is not None:
            return VariantDistributor.assign_by_user_id(user_id, variants)

        return VariantDistributor.assign_random(variants)

    # ── 指标收集 ───────────────────────────────────────────

    def record_event(
        self,
        experiment_id: int,
        variant_id: int,
        user_id: int | None = None,
        event_type: str = "impression",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        记录实验事件（impression / click / conversion / view）。
        返回事件字典。
        """
        event = {
            "experiment_id": experiment_id,
            "variant_id": variant_id,
            "user_id": user_id,
            "event_type": event_type,
            "metadata": metadata or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return event

    def compute_results(
        self,
        experiment_id: int,
        events: list[dict[str, Any]],
        method: str = "chi_square",
    ) -> dict[str, Any]:
        """
        计算实验结果的统计显著性。
        method: "chi_square" | "bayesian"
        返回包含所有变体对比结果。
        """
        state = self._experiments.get(experiment_id)
        if not state:
            return {"error": "实验不存在"}

        metric = state.config.metric
        alpha = state.config.significance_level

        # 聚合事件
        aggregated = self._collector.aggregate_events(events, metric)

        variants = state.config.variants
        if not variants:
            return {"error": "没有变体配置"}

        # control = variants[0], variants[1:] = 实验组
        control_vid = 0  # 第一个 variant 作为对照组
        control_data = aggregated.get(control_vid, {"impressions": 0, "rate": 0.0})
        control_imp = control_data["impressions"]
        control_success = int(control_data["rate"] * control_imp)

        variant_results = []
        for idx, variant in enumerate(variants):
            if idx == 0:
                continue  # 跳过对照组
            vdata = aggregated.get(idx, {"impressions": 0, "rate": 0.0})
            vimp = vdata["impressions"]
            vsuccess = int(vdata["rate"] * vimp)

            if method == "bayesian":
                test_result = self._tester.bayesian_test(
                    control_success,
                    control_imp,
                    vsuccess,
                    vimp,
                )
            else:
                test_result = self._tester.chi_square_test(
                    control_imp,
                    control_success,
                    vimp,
                    vsuccess,
                )

            variant_results.append(
                {
                    "variant_id": idx,
                    "variant_name": variant.get("name", f"变体 {idx}"),
                    "variant_config": variant,
                    "impressions": vimp,
                    "success_count": vsuccess,
                    "rate": round(vdata["rate"], 6),
                    "test_result": test_result,
                }
            )

        results = {
            "experiment_id": experiment_id,
            "experiment_name": state.config.name,
            "status": state.status,
            "metric": metric,
            "alpha": alpha,
            "test_method": method,
            "control": {
                "variant_id": 0,
                "variant_name": state.config.control_name,
                "impressions": control_imp,
                "success_count": control_success,
                "rate": round(control_data["rate"], 6),
            },
            "variants": variant_results,
            "computed_at": datetime.now(UTC).isoformat(),
        }

        # 缓存结果
        state.results = results
        return results

    # ── 自动决策 ───────────────────────────────────────────

    def auto_decision(
        self,
        experiment_id: int,
        results: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        自动分析实验结果并做出决策。

        决策规则:
          - p_value < 0.05  → 'rollout'（发布胜出变体）
          - p_value > 0.3   → 'continue'（继续实验）
          - 运行 >30 天无显著差异 → 'stop'（停止，无差异）

        参数:
          experiment_id: 实验 ID
          results: compute_results() 的输出；若为 None 则使用缓存的 state.results

        返回:
          决策字典 {decision, variant_name, p_value, reason, ...}
        """
        state = self._experiments.get(experiment_id)
        if not state:
            return {"error": "实验不存在", "decision": "error"}

        if state.status not in (EXPERIMENT_STATUS_RUNNING, EXPERIMENT_STATUS_PAUSED, EXPERIMENT_STATUS_COMPLETED):
            return {"error": f"当前状态不允许自动决策: {state.status}", "decision": "error"}

        # 使用传入或缓存的实验结果
        res = results or state.results
        if not res or "variants" not in res:
            return {"error": "尚无实验结果，请先 compute_results", "decision": "error"}

        variants = res.get("variants", [])
        if not variants:
            return {"decision": "continue", "reason": "无变体结果，继续实验"}

        # 提取所有变体的 p_value，取最小（最显著）
        p_values = []
        best_variant = None
        lowest_p = 1.0
        for v in variants:
            tr = v.get("test_result", {})
            pv = tr.get("p_value", 1.0)
            p_values.append(pv)
            if pv < lowest_p:
                lowest_p = pv
                best_variant = v.get("variant_name", str(v.get("variant_id", "")))

        # 计算实验运行天数
        days_running = 0
        if state.started_at:
            delta = datetime.now(UTC) - state.started_at
            days_running = delta.days

        # 决策逻辑
        decision_entry: dict[str, Any] = {
            "experiment_id": experiment_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "p_value": round(lowest_p, 6),
            "days_running": days_running,
            "variant_count": len(variants),
        }

        if lowest_p < 0.05 and best_variant:
            # 显著差异 → 发布胜出变体
            decision_entry["decision"] = "rollout"
            decision_entry["variant_name"] = best_variant
            decision_entry["reason"] = f"p_value={lowest_p:.4f} < 0.05，变体「{best_variant}」显著优于对照组，自动发布"
            # 自动执行 rollout
            rollout_result = self.rollout_winner(experiment_id, best_variant)
            decision_entry["rollout_result"] = rollout_result
        elif days_running > 30:
            # 运行超过 30 天无显著差异 → 停止
            decision_entry["decision"] = "stop"
            decision_entry["variant_name"] = None
            decision_entry["reason"] = (
                f"实验已运行 {days_running} 天 > 30 天，p_value={lowest_p:.4f} ≥ 0.05，无显著差异，停止实验"
            )
            # 自动停止实验
            self.stop_experiment(experiment_id)
        else:
            # 无显著差异，继续实验
            decision_entry["decision"] = "continue"
            decision_entry["variant_name"] = None
            decision_entry["reason"] = (
                f"p_value={lowest_p:.4f} ≥ 0.05 且实验仅运行 {days_running} 天 ≤ 30 天，继续收集数据"
            )

        decision_entry["details"] = {
            "control_rate": res.get("control", {}).get("rate"),
            "variants": [
                {
                    "name": v.get("variant_name"),
                    "rate": v.get("rate"),
                    "p_value": v.get("test_result", {}).get("p_value"),
                }
                for v in variants
            ],
        }

        # 记录到内存日志
        self._decision_logs.setdefault(experiment_id, []).append(decision_entry)

        return decision_entry

    def rollout_winner(
        self,
        experiment_id: int,
        variant_name: str,
    ) -> dict[str, Any]:
        """
        自动发布胜出变体。
        - 将胜出变体标记为 default
        - 记录决策日志
        """
        state = self._experiments.get(experiment_id)
        if not state:
            return {"error": "实验不存在"}

        # 在实验配置中标记胜出变体
        for idx, v in enumerate(state.config.variants):
            if v.get("name") == variant_name:
                v["is_default"] = True
                v["rolled_out_at"] = datetime.now(UTC).isoformat()
                # 停止实验（发布即代表实验结束）
                self.stop_experiment(experiment_id)
                return {
                    "success": True,
                    "variant_id": idx,
                    "variant_name": variant_name,
                    "message": f"变体「{variant_name}」已成功发布为默认版本",
                }

        return {"error": f"未找到变体: {variant_name}"}

    def get_decision_logs(
        self,
        experiment_id: int,
    ) -> list[dict[str, Any]]:
        """获取指定实验的决策历史。"""
        return self._decision_logs.get(experiment_id, [])


# ─── 单例 ─────────────────────────────────────────────────

_engine: ABTestingEngine | None = None


def get_ab_testing_engine() -> ABTestingEngine:
    """获取全局 A/B 测试引擎单例。"""
    global _engine
    if _engine is None:
        _engine = ABTestingEngine()
    return _engine
