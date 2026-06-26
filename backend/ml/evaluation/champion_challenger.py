"""
链客宝 - 离线A/B冠军挑战者实验框架
======================================
提供 ExperimentConfig, ChampionChallenger, MetricsTracker 三类核心组件，
支持基于 SQLite 持久化的确定性分流、评估记录、显著性检验与冠军提升。
"""

import hashlib
import json
import math
import random
import sqlite3
import statistics
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

# ---------------------------------------------------------------------------
# 默认评估指标
# ---------------------------------------------------------------------------
DEFAULT_METRICS = ["auc", "precision@10", "recall@20", "diversity@10"]


def _hash_user(user_id: str, experiment_id: str, salt: str = "") -> float:
    """对 user_id + experiment_id 做确定性哈希，返回 [0.0, 1.0) 的浮点数."""
    raw = f"{experiment_id}:{user_id}:{salt}"
    h = int(hashlib.md5(raw.encode()).hexdigest()[:8], 16)
    return h / (2 ** 32)


def _bootstrap_ci(a, b, n_resamples: int = 5000, ci: float = 0.95):
    """Bootstrap 置信区间比较：检验 A 是否显著优于 B."""
    alpha = 1.0 - ci
    combined = a + b
    n_a, n_b = len(a), len(b)
    diffs = []
    for _ in range(n_resamples):
        sample_a = [random.choice(combined) for _ in range(n_a)]
        sample_b = [random.choice(combined) for _ in range(n_b)]
        diffs.append(statistics.mean(sample_a) - statistics.mean(sample_b))
    diffs.sort()
    lower = diffs[int(n_resamples * alpha / 2)]
    upper = diffs[int(n_resamples * (1 - alpha / 2))]
    # 如果置信区间整体 > 0，则 A 显著优于 B
    return lower, upper


def _ttest_ind(a, b):
    """
    独立样本 t 检验。
    优先尝试 scipy，回退到纯 Python 实现（基于 t 分布近似）。
    返回 (t_statistic, p_value)。
    """
    try:
        from scipy import stats as scipy_stats
        return scipy_stats.ttest_ind(a, b, equal_var=False)
    except ImportError:
        pass

    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return 0.0, 1.0

    m1, m2 = statistics.mean(a), statistics.mean(b)
    v1, v2 = statistics.variance(a), statistics.variance(b)

    # Welch's t-test
    se = math.sqrt(v1 / n1 + v2 / n2)
    if se == 0:
        return 0.0, 1.0
    t = (m1 - m2) / se

    # Welch-Satterthwaite degrees of freedom
    df_num = (v1 / n1 + v2 / n2) ** 2
    df_den = (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
    df = df_num / df_den if df_den > 0 else 1.0

    # 使用近似计算 p-value (对于大样本足够精确)
    from numpy import inf as np_inf
    try:
        from scipy.special import betainc
        x = df / (df + t * t)
        p = betainc(df / 2, 0.5, x)
        p_value = min(p, 1 - p) * 2  # two-tailed
    except ImportError:
        # 最简备选：查正态分布表近似
        p_value = _normal_approx_p(t)

    return t, max(p_value, 1e-300)


def _normal_approx_p(z):
    """标准正态分布双尾 p-value 近似（Polya  approximation）. """
    import math
    x = abs(z)
    b0, b1, b2, b3, b4, b5, b6, b7, b8 = (
        0.319381530, -0.356563782, 1.781477937,
        -1.821255978, 1.330274429, 0.2316419,
    )
    t = 1.0 / (1.0 + b5 * x)
    phi = math.exp(-x * x / 2) / math.sqrt(2 * math.pi)
    poly = ((b4 * t + b3) * t + b2) * t + b1 * t + b0
    p = phi * poly * t
    return min(p * 2, 1.0)


# ============================================================================
# ExperimentConfig
# ============================================================================


@dataclass
class ExperimentConfig:
    """实验配置。

    Attributes:
        experiment_id: 实验唯一标识符。
        name: 实验名称。
        description: 实验描述。
        control_model: 当前生产模型名（对照组）。
        treatment_model: 挑战者模型名（实验组）。
        traffic_split: 控制组流量占比，默认 0.5（即 50%）。
        metrics: 评估指标列表。
        duration_days: 实验周期（天），默认 7。
        min_samples: 最小样本数门禁，默认 1000。
    """
    experiment_id: str
    name: str
    description: str
    control_model: str
    treatment_model: str
    traffic_split: float = 0.5
    metrics: list = field(default_factory=lambda: list(DEFAULT_METRICS))
    duration_days: int = 7
    min_samples: int = 1000

    def __post_init__(self):
        if not 0 < self.traffic_split < 1:
            raise ValueError("traffic_split 必须在 (0, 1) 之间")
        if self.duration_days < 1:
            raise ValueError("duration_days 必须 >= 1")
        if self.min_samples < 10:
            raise ValueError("min_samples 至少为 10")


# ============================================================================
# ChampionChallenger
# ============================================================================


class ChampionChallenger:
    """冠军挑战者实验管理器。

    负责用户分组、结果记录、聚合分析、显著性检验和模型提升。
    使用 SQLite 持久化所有实验结果。
    """

    def __init__(self, config: ExperimentConfig, db_path: str = ":memory:"):
        self.config = config
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    # ---- 数据库初始化 -------------------------------------------------------

    def _init_db(self):
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                control_model TEXT,
                treatment_model TEXT,
                traffic_split REAL,
                metrics TEXT,
                duration_days INTEGER,
                min_samples INTEGER,
                created_at REAL,
                promoted_model TEXT
            );
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT,
                user_id TEXT,
                model_name TEXT,
                metrics TEXT,
                timestamp REAL,
                group_label TEXT
            );
            CREATE TABLE IF NOT EXISTS metrics_series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT,
                model_name TEXT,
                metric_name TEXT,
                value REAL,
                timestamp REAL
            );
            CREATE INDEX IF NOT EXISTS idx_results_exp
                ON results(experiment_id);
            CREATE INDEX IF NOT EXISTS idx_metrics_exp_model
                ON metrics_series(experiment_id, model_name, metric_name);
        """)
        self._conn.commit()
        # 持久化实验配置
        self._save_config()

    def _save_config(self):
        cur = self._conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO experiments
               (experiment_id, name, description, control_model, treatment_model,
                traffic_split, metrics, duration_days, min_samples, created_at, promoted_model)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                self.config.experiment_id,
                self.config.name,
                self.config.description,
                self.config.control_model,
                self.config.treatment_model,
                self.config.traffic_split,
                json.dumps(self.config.metrics),
                self.config.duration_days,
                self.config.min_samples,
                time.time(),
                None,
            ),
        )
        self._conn.commit()

    @property
    def db_path(self):
        return self._db_path

    # ---- 分流逻辑 -----------------------------------------------------------

    def assign_group(self, user_id: str) -> str:
        """基于 user_id 确定性哈希分流。

        同一个 user_id 在同一个 experiment_id 下始终分配到同一组。
        """
        ratio = _hash_user(user_id, self.config.experiment_id)
        return "control" if ratio < self.config.traffic_split else "treatment"

    # ---- 结果记录 -----------------------------------------------------------

    def record_result(self, user_id: str, model_name: str,
                      metrics_dict: dict) -> None:
        """记录一条实验结果。

        Args:
            user_id: 用户标识。
            model_name: 模型名（应与 control_model 或 treatment_model 一致）。
            metrics_dict: 指标字典，如 {'auc': 0.85, 'precision@10': 0.72}。
        """
        group = self.assign_group(user_id)
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO results
               (experiment_id, user_id, model_name, metrics, timestamp, group_label)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                self.config.experiment_id,
                str(user_id),
                model_name,
                json.dumps(metrics_dict),
                time.time(),
                group,
            ),
        )
        self._conn.commit()

    # ---- 聚合结果 -----------------------------------------------------------

    def get_results(self) -> dict:
        """获取控制组和实验组的聚合指标均值。

        Returns:
            {'control': {metric: mean_value, ...},
             'treatment': {metric: mean_value, ...}}
        """
        control_metrics, treatment_metrics = self._aggregate_metrics()
        return {"control": control_metrics, "treatment": treatment_metrics}

    def _aggregate_metrics(self) -> tuple:
        """聚合两组指标，返回 (control_metrics_dict, treatment_metrics_dict)."""
        cur = self._conn.cursor()
        cur.execute(
            """SELECT group_label, metrics FROM results
               WHERE experiment_id = ?""",
            (self.config.experiment_id,),
        )
        rows = cur.fetchall()

        groups = {"control": [], "treatment": []}
        for group_label, metrics_json in rows:
            m = json.loads(metrics_json)
            groups[group_label].append(m)

        def _mean_dict(records):
            if not records:
                return {m: 0.0 for m in self.config.metrics}
            result = {}
            keys = records[0].keys()
            for k in keys:
                values = [r.get(k, 0.0) for r in records]
                result[k] = statistics.mean(values)
            return result

        return _mean_dict(groups["control"]), _mean_dict(groups["treatment"])

    def _get_raw_values(self, metric: str) -> dict:
        """获取某个指标在两组中的原始值列表。

        Returns:
            {'control': [v1, v2, ...], 'treatment': [v1, v2, ...]}
        """
        cur = self._conn.cursor()
        cur.execute(
            """SELECT group_label, metrics FROM results
               WHERE experiment_id = ?""",
            (self.config.experiment_id,),
        )
        rows = cur.fetchall()
        groups = {"control": [], "treatment": []}
        for group_label, metrics_json in rows:
            m = json.loads(metrics_json)
            if metric in m:
                groups[group_label].append(m[metric])
        return groups

    # ---- 显著性检验 ---------------------------------------------------------

    def is_significant(self, metric: str, confidence: float = 0.95) -> bool:
        """检验治疗组在指定指标上是否显著优于对照组。

        使用独立样本 t-test（优先 scipy，否则纯 Python 实现）。
        当 scipy 不可用时自动回退到 bootstrap 置信区间法。

        Args:
            metric: 指标名。
            confidence: 置信水平，默认 0.95。

        Returns:
            True 如果治疗组显著优于对照组。
        """
        raw = self._get_raw_values(metric)
        control_vals = raw.get("control", [])
        treatment_vals = raw.get("treatment", [])

        # 样本量门禁检查
        min_req = max(5, self.config.min_samples // 10)
        if len(control_vals) < min_req or len(treatment_vals) < min_req:
            return False

        control_mean = statistics.mean(control_vals) if control_vals else 0.0
        treatment_mean = statistics.mean(treatment_vals) if treatment_vals else 0.0

        # 治疗组均值必须大于对照组才有意义
        if treatment_mean <= control_mean:
            return False

        try:
            # 优先 t-test
            _, p_value = _ttest_ind(treatment_vals, control_vals)
            return p_value < (1 - confidence)
        except Exception:
            # 回退 bootstrap
            lower, _ = _bootstrap_ci(treatment_vals, control_vals,
                                     ci=confidence)
            return lower > 0

    # ---- 胜者判定 -----------------------------------------------------------

    def declare_winner(self, confidence: float = 0.95) -> dict:
        """综合所有指标判定实验胜者。

        Returns:
            dict with keys: winner, details, control_metrics, treatment_metrics.
        """
        control_metrics, treatment_metrics = self._aggregate_metrics()
        results = self.get_results()

        significant_wins = 0
        total_metrics = len(self.config.metrics)
        details = {}

        for metric in self.config.metrics:
            c_val = control_metrics.get(metric, 0.0)
            t_val = treatment_metrics.get(metric, 0.0)
            sig = self.is_significant(metric, confidence)
            lift = ((t_val - c_val) / c_val * 100) if c_val != 0 else 0.0
            details[metric] = {
                "control_mean": c_val,
                "treatment_mean": t_val,
                "lift_pct": round(lift, 4),
                "significant": sig,
            }
            if sig and t_val > c_val:
                significant_wins += 1

        # 样本量门禁
        total_samples = self._count_samples()
        if total_samples < self.config.min_samples:
            winner = "tie"
            details["_reason"] = f"样本不足: {total_samples} < {self.config.min_samples}"
        elif significant_wins > total_metrics / 2:
            winner = "treatment"
            details["_reason"] = f"挑战者在 {significant_wins}/{total_metrics} 个指标上显著优胜"
        else:
            winner = "control"
            details["_reason"] = f"挑战者在 {significant_wins}/{total_metrics} 个指标上未达显著"

        return {
            "winner": winner,
            "details": details,
            "control_metrics": control_metrics,
            "treatment_metrics": treatment_metrics,
        }

    def _count_samples(self) -> int:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM results WHERE experiment_id = ?",
            (self.config.experiment_id,),
        )
        return cur.fetchone()[0]

    # ---- 冠军提升 -----------------------------------------------------------

    def promote(self) -> Optional[str]:
        """如果挑战者胜出，将其提升为新的冠军模型。

        Returns:
            新的冠军模型名，如果未胜出则返回 None。
        """
        verdict = self.declare_winner()
        if verdict["winner"] == "treatment":
            new_champion = self.config.treatment_model
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE experiments SET promoted_model = ? WHERE experiment_id = ?",
                (new_champion, self.config.experiment_id),
            )
            self._conn.commit()
            # 更新配置
            old_control = self.config.control_model
            self.config.control_model = new_champion
            return new_champion
        elif verdict["winner"] == "control":
            # 对照组胜出，记录但不变更
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE experiments SET promoted_model = ? WHERE experiment_id = ?",
                (self.config.control_model, self.config.experiment_id),
            )
            self._conn.commit()
            return None
        return None

    def close(self):
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ============================================================================
# MetricsTracker
# ============================================================================


class MetricsTracker:
    """指标跟踪器，记录和查询模型指标的时间序列。"""

    def __init__(self, db_path: str = ":memory:"):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        cur = self._conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS metrics_series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT,
                model_name TEXT,
                metric_name TEXT,
                value REAL,
                timestamp REAL
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_ms_exp_model_metric
            ON metrics_series(experiment_id, model_name, metric_name)
        """)
        self._conn.commit()

    def log_metric(self, experiment_id: str, model_name: str,
                   metric_name: str, value: float,
                   timestamp: Optional[float] = None) -> None:
        """记录一个指标点。

        Args:
            experiment_id: 实验ID。
            model_name: 模型名。
            metric_name: 指标名（如 'auc'）。
            value: 指标值。
            timestamp: Unix 时间戳，默认当前时间。
        """
        ts = timestamp if timestamp is not None else time.time()
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO metrics_series
               (experiment_id, model_name, metric_name, value, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (experiment_id, model_name, metric_name, value, ts),
        )
        self._conn.commit()

    def get_series(self, experiment_id: str, model_name: str,
                   metric_name: str) -> list:
        """获取某模型在某指标上的时间序列。

        Returns:
            [(timestamp, value), ...] 按时间升序排列。
        """
        cur = self._conn.cursor()
        cur.execute(
            """SELECT timestamp, value FROM metrics_series
               WHERE experiment_id = ? AND model_name = ? AND metric_name = ?
               ORDER BY timestamp ASC""",
            (experiment_id, model_name, metric_name),
        )
        return [(row[0], row[1]) for row in cur.fetchall()]

    def summary(self, experiment_id: str) -> dict:
        """获取某实验的聚合报告。

        Returns:
            {model_name: {metric_name: {mean, min, max, count, last}}, ...}
        """
        cur = self._conn.cursor()
        cur.execute(
            """SELECT DISTINCT model_name, metric_name FROM metrics_series
               WHERE experiment_id = ?""",
            (experiment_id,),
        )
        pairs = cur.fetchall()
        report = {}
        for model_name, metric_name in pairs:
            if model_name not in report:
                report[model_name] = {}
            cur.execute(
                """SELECT value FROM metrics_series
                   WHERE experiment_id = ? AND model_name = ? AND metric_name = ?
                   ORDER BY timestamp ASC""",
                (experiment_id, model_name, metric_name),
            )
            values = [row[0] for row in cur.fetchall()]
            if values:
                report[model_name][metric_name] = {
                    "mean": round(statistics.mean(values), 6),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                    "last": values[-1],
                }
        return report

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
