#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
异常评分引擎 (Anomaly Scoring Engine)
=======================================
五维联合异常检测，修复「规则可绕过」问题。
使用纯统计学方法，无外部ML依赖。

维度设计:
  D1 - 频率异常:     写入频率 + 增量突变检测 (中位数+3*MAD)
  D2 - 分布异常:     字段值分布 + 长度分布 + 特殊字符比例
  D3 - 类型偏移:     字段类型 + 语义类型偏移检测
  D4 - 约束违反率:   总体违反率 + 新字段 vs 老字段违反分布
  D5 - 跨模块一致性: 外键引用 + 循环引用检测

模块：向海容知識庫 · 記憶宮殿 · 数据安全层
"""

import json
import os
import re
import statistics
import time
import math
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple, Union

__version__ = "1.0.0"

# ===================================================================
#  全局配置
# ===================================================================

# 冷启动阈值：写入次数少于该值则降级评分
COLD_START_THRESHOLD = 100

# 基线存储根目录
BASELINES_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "baselines",
)

# 默认灵敏度配置
DEFAULT_SENSITIVITY: Dict[str, float] = {
    "d1_frequency": 1.0,
    "d2_distribution": 1.0,
    "d3_type_shift": 1.0,
    "d4_violation": 1.0,
    "d5_consistency": 1.0,
}

# 动态阈值倍数 (baseline_mean + Z_SCORE * baseline_stddev)
Z_SCORE_FACTOR = 2.0

# 最大历史保留窗口 (秒)
HISTORY_WINDOW_SEC = 3600  # 1 小时

# ===================================================================
#  统计工具函数
# ===================================================================


def _robust_mad(data: List[float]) -> float:
    """稳健中位数绝对偏差 (MAD)，对异常值不敏感"""
    if not data:
        return 0.0
    median = statistics.median(data)
    abs_devs = [abs(x - median) for x in data]
    return statistics.median(abs_devs) * 1.4826  # 缩放因子以对齐正态分布标准差


def _dynamic_threshold(
    data: List[float], factor: float = Z_SCORE_FACTOR
) -> Tuple[float, float]:
    """计算动态阈值 (mean + factor * stddev)，数据不足时返回默认值"""
    if len(data) < 3:
        return float("inf"), 0.0
    mean = statistics.mean(data)
    stdev = statistics.stdev(data) if len(data) > 1 else 0.0
    return mean + factor * stdev, stdev


def _kl_divergence_smoothed(p: Counter, q: Counter, alpha: float = 0.01) -> float:
    """带拉普拉斯平滑的 KL 散度近似，衡量两个分布的距离"""
    all_keys = set(p.keys()) | set(q.keys())
    total_p = sum(p.values())
    total_q = sum(q.values())
    if total_p == 0 or total_q == 0:
        return 0.0
    kl = 0.0
    vocab_size = len(all_keys)
    for k in all_keys:
        prob_p = p.get(k, 0) / total_p
        prob_q = (q.get(k, 0) + alpha) / (total_q + alpha * (vocab_size + 1))
        prob_p_smooth = (prob_p * total_p + alpha) / (total_p + alpha * (vocab_size + 1))
        if prob_p_smooth > 0 and prob_q > 0:
            kl += prob_p_smooth * math.log(prob_p_smooth / prob_q)
    return kl


# ===================================================================
#  基线管理器
# ===================================================================


class BaselineManager:
    """管理 per-(module, table) 的统计基线，存储在 JSON 文件中"""

    def __init__(self, root_dir: str = BASELINES_ROOT):
        self.root_dir = root_dir
        os.makedirs(self.root_dir, exist_ok=True)
        self._cache: Dict[str, dict] = {}

    def _path(self, module: str, table: str) -> str:
        """基线文件路径"""
        safe = f"{module}.{table}".replace("/", "_").replace("\\", "_")
        return os.path.join(self.root_dir, f"{safe}.json")

    def load(self, module: str, table: str) -> dict:
        """加载基线，不存在则返回空基线"""
        cache_key = f"{module}.{table}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        p = self._path(module, table)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._cache[cache_key] = data
                return data
            except (json.JSONDecodeError, OSError):
                pass
        return self._empty_baseline()

    def save(self, module: str, table: str, baseline: dict) -> None:
        """保存基线到磁盘并刷新缓存"""
        cache_key = f"{module}.{table}"
        p = self._path(module, table)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(baseline, f, ensure_ascii=False, indent=2, default=str)
        self._cache[cache_key] = baseline

    @staticmethod
    def _empty_baseline() -> dict:
        """返回一个空基线结构"""
        return {
            "version": 1,
            "created_at": time.time(),
            "updated_at": time.time(),
            "write_count": 0,
            "frequencies": [],          # 时间戳列表 (秒级时间戳)
            "field_stats": {},           # field -> {"types": {...}, "lengths": [...], "special_char_ratios": [...], "values": {...}}
            "semantic_types": {},       # field -> {"phone": count, "email": count, "url": count, "plain": count}
            "violation_history": [],     # 每批次的违反比例
            "violation_field_dist": {},  # field -> violation_count
            "foreign_keys": {},          # field -> [(ref_module, ref_table), ...]
            "total_writes": 0,
        }

    def update(self, module: str, table: str, data: dict,
               write_rate: Optional[int] = None,
               violations: Optional[Dict[str, int]] = None) -> None:
        """用新数据更新基线"""
        baseline = self.load(module, table)
        now = time.time()

        # 更新写入计数 & 频率
        baseline["write_count"] += 1
        baseline["total_writes"] = baseline.get("total_writes", 0) + 1
        baseline["updated_at"] = now

        freq_list: list = baseline.get("frequencies", [])
        freq_list.append(now)
        # 只保留最近 HISTORY_WINDOW_SEC 的数据
        cutoff = now - HISTORY_WINDOW_SEC
        baseline["frequencies"] = [t for t in freq_list if t >= cutoff]

        # 更新字段统计
        field_stats: dict = baseline.get("field_stats", {})
        for field, value in data.items():
            if field.startswith("_"):
                continue  # 跳过内部字段
            if field not in field_stats:
                field_stats[field] = {
                    "types": {},
                    "lengths": [],
                    "special_char_ratios": [],
                    "values": {},
                }
            fs = field_stats[field]
            val_str = str(value)
            val_type = type(value).__name__
            fs["types"][val_type] = fs["types"].get(val_type, 0) + 1
            fs["lengths"].append(len(val_str))
            # 裁剪长度列表，避免无限膨胀
            if len(fs["lengths"]) > 1000:
                fs["lengths"] = fs["lengths"][-500:]
            # 特殊字符比例
            special_count = sum(1 for c in val_str if not c.isalnum() and not c.isspace())
            ratio = special_count / max(len(val_str), 1)
            fs["special_char_ratios"].append(ratio)
            if len(fs["special_char_ratios"]) > 1000:
                fs["special_char_ratios"] = fs["special_char_ratios"][-500:]
            # 值分布（只保留最近200个不同值）
            if isinstance(value, (str, int, float, bool)):
                val_key = str(value)
                fs["values"][val_key] = fs["values"].get(val_key, 0) + 1
            if len(fs["values"]) > 200:
                # 保留前200高频
                fs["values"] = dict(
                    Counter(fs["values"]).most_common(200))

        baseline["field_stats"] = field_stats

        # 更新语义类型
        sem_types: dict = baseline.get("semantic_types", {})
        for field, value in data.items():
            if field not in sem_types:
                sem_types[field] = {"phone": 0, "email": 0, "url": 0, "ip": 0, "plain": 0}
            st = _infer_semantic_type(str(value))
            sem_types[field][st] = sem_types[field].get(st, 0) + 1
        baseline["semantic_types"] = sem_types

        # 更新违反历史
        if violations is not None:
            if violations:
                v_total = sum(violations.values())
                v_count = len(violations)
                # 总体违反比例
                violation_ratio = v_count / max(len(data), 1)
                v_hist: list = baseline.get("violation_history", [])
                v_hist.append(violation_ratio)
                if len(v_hist) > 500:
                    v_hist = v_hist[-250:]
                baseline["violation_history"] = v_hist
                # 按字段分布
                vfd: dict = baseline.get("violation_field_dist", {})
                for fld, cnt in violations.items():
                    vfd[fld] = vfd.get(fld, 0) + cnt
                baseline["violation_field_dist"] = vfd

        self.save(module, table, baseline)


# ===================================================================
#  语义类型推断
# ===================================================================

_SEMANTIC_PATTERNS = {
    "phone": re.compile(
        r"^\+?[1-9]\d{6,14}$"
    ),
    "email": re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    ),
    "url": re.compile(
        r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE
    ),
    "ip": re.compile(
        r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
    ),
}


def _infer_semantic_type(value: str) -> str:
    """推断一个字符串值的语义类型"""
    for stype, pattern in _SEMANTIC_PATTERNS.items():
        if pattern.match(value):
            return stype
    return "plain"


# ===================================================================
#  各维度评分器
# ===================================================================


class D1FrequencyScorer:
    """维度1：频率异常检测"""

    def __init__(self, baseline_mgr: BaselineManager, sensitivity: float = 1.0):
        self.bm = baseline_mgr
        self.sensitivity = sensitivity

    def score(self, module: str, table: str, data: dict,
              write_rate: Optional[int] = None) -> Dict[str, Any]:
        """
        检测写入频率异常：
        - 频率异常：当前频次 vs 基线中位数+3*MAD
        - 增量突变：写入量趋势 vs 历史趋势
        """
        baseline = self.bm.load(module, table)
        timestamps: list = baseline.get("frequencies", [])
        total_writes = baseline.get("write_count", 0)

        if total_writes < COLD_START_THRESHOLD or len(timestamps) < 10:
            return {"score": 0.0, "reason": "冷启动/数据不足，跳过频率检测"}

        now = time.time()
        window_start = now - HISTORY_WINDOW_SEC

        # 计算当前1小时的写入频率
        recent_timestamps = [t for t in timestamps if t >= window_start]
        current_freq = len(recent_timestamps) / (HISTORY_WINDOW_SEC / 3600)  # 次/小时

        # 计算历史频率（按相同窗口滑动取中位数）
        if len(timestamps) >= 20:
            # 按小时划分历史窗口
            min_ts = min(timestamps)
            max_ts = max(timestamps)
            hourly_counts = []
            ts = min_ts
            while ts < max_ts:
                count = sum(1 for t in timestamps if ts <= t < ts + 3600)
                hourly_counts.append(count)
                ts += 3600
            if hourly_counts:
                baseline_freq = statistics.median(hourly_counts)
                mad = _robust_mad(hourly_counts)
                threshold = baseline_freq + 3 * mad
            else:
                baseline_freq = 0
                threshold = float("inf")
        else:
            baseline_freq = len(timestamps) / (HISTORY_WINDOW_SEC / 3600)
            threshold = baseline_freq * 3

        # 频率异常分
        freq_score = 0.0
        freq_reason_parts = []
        if threshold > 0 and current_freq > threshold:
            excess_ratio = (current_freq - threshold) / max(threshold, 1)
            freq_score = min(1.0, excess_ratio * self.sensitivity)
            freq_reason_parts.append(
                f"频率 {current_freq:.1f}次/h 超过阈值 {threshold:.1f}次/h"
            )

        # 增量突变检测: 比较最近N条与之前N条的数据量趋势
        if total_writes >= 30:
            # 使用写入时间间隔的变化
            if len(timestamps) >= 10:
                sorted_ts = sorted(timestamps)
                # 分成最近一半和历史一半
                mid = len(sorted_ts) // 2
                recent_intervals = [
                    sorted_ts[i] - sorted_ts[i - 1]
                    for i in range(mid, len(sorted_ts))
                    if i > 0
                ]
                old_intervals = [
                    sorted_ts[i] - sorted_ts[i - 1]
                    for i in range(1, mid)
                ]
                if recent_intervals and old_intervals:
                    recent_median = statistics.median(recent_intervals)
                    old_median = statistics.median(old_intervals)
                    if old_median > 0 and recent_median < old_median * 0.5:
                        # 间隔缩短50%以上 -> 写入加速
                        speedup = old_median / max(recent_median, 0.001)
                        delta_score = min(0.8, (speedup - 1) * 0.1 * self.sensitivity)
                        freq_score = max(freq_score, delta_score)
                        freq_reason_parts.append(
                            f"写入间隔缩短 {speedup:.1f}倍 (历史中位数{old_median:.1f}s->当前{recent_median:.1f}s)"
                        )

        freq_score = min(1.0, freq_score)

        reason = "; ".join(freq_reason_parts) if freq_reason_parts else "频率正常"

        return {
            "dimension": "频率",
            "score": freq_score,
            "reason": reason,
            "details": {
                "current_freq": current_freq,
                "baseline_freq": baseline_freq,
                "threshold": threshold,
            },
        }


class D2DistributionScorer:
    """维度2：分布异常检测"""

    def __init__(self, baseline_mgr: BaselineManager, sensitivity: float = 1.0):
        self.bm = baseline_mgr
        self.sensitivity = sensitivity

    def score(self, module: str, table: str, data: dict) -> Dict[str, Any]:
        """检测字段值分布、长度分布、特殊字符比例的异常"""
        baseline = self.bm.load(module, table)
        field_stats: dict = baseline.get("field_stats", {})
        total_writes = baseline.get("write_count", 0)

        if total_writes < COLD_START_THRESHOLD or not field_stats:
            return {"score": 0.0, "reason": "冷启动/数据不足，跳过分布检测"}

        max_field_score = 0.0
        field_reasons = []

        for field, value in data.items():
            if field.startswith("_") or field not in field_stats:
                continue

            fs = field_stats[field]
            val_str = str(value)
            field_score = 0.0

            # --- 类型分布偏移 ---
            type_dist: dict = fs.get("types", {})
            if type_dist:
                cur_type = type(value).__name__
                total_types = sum(type_dist.values())
                type_ratio = type_dist.get(cur_type, 0) / max(total_types, 1)
                if type_ratio < 0.01 and total_types > 10:
                    # 类型从未出现或极少出现
                    field_score += 0.4 * self.sensitivity
                    field_reasons.append(
                        f"字段[{field}]类型'{cur_type}'罕见 (占比{type_ratio:.1%})"
                    )

            # --- 长度分布偏移 ---
            lengths: list = fs.get("lengths", [])
            if len(lengths) >= 10:
                cur_len = len(val_str)
                len_median = statistics.median(lengths)
                len_mad = _robust_mad(lengths)
                if len_mad > 0:
                    len_z = (cur_len - len_median) / len_mad
                    if abs(len_z) > 3:
                        deviation = min(1.0, (abs(len_z) - 3) * 0.15 * self.sensitivity)
                        field_score = max(field_score, deviation)
                        field_reasons.append(
                            f"字段[{field}]长度 {cur_len} 偏离中位数 {len_median} (z-score={len_z:.1f})"
                        )

            # --- 特殊字符比例偏移 ---
            ratios: list = fs.get("special_char_ratios", [])
            if len(ratios) >= 10:
                cur_ratio = sum(1 for c in val_str if not c.isalnum() and not c.isspace()) / max(len(val_str), 1)
                ratio_mean = statistics.mean(ratios)
                ratio_stdev = statistics.stdev(ratios) if len(ratios) > 1 else 0.0
                if ratio_stdev > 0:
                    ratio_z = (cur_ratio - ratio_mean) / ratio_stdev
                    if abs(ratio_z) > 2.5:
                        deviation = min(1.0, (abs(ratio_z) - 2.5) * 0.12 * self.sensitivity)
                        field_score = max(field_score, deviation)
                        field_reasons.append(
                            f"字段[{field}]特殊字符比例 {cur_ratio:.2%} 偏离均值 {ratio_mean:.2%} (z={ratio_z:.1f})"
                        )

            # --- 值分布 KL 散度 ---
            values_hist: dict = fs.get("values", {})
            if len(values_hist) >= 20:
                val_key = str(value)
                hist_counter = Counter(values_hist)
                current_counter = Counter({val_key: 1})
                kl = _kl_divergence_smoothed(current_counter, hist_counter)
                if kl > 0.5:
                    kl_contrib = min(0.6, kl * 0.2 * self.sensitivity)
                    field_score = max(field_score, kl_contrib)
                    field_reasons.append(
                        f"字段[{field}]值'{val_key[:30]}'分布偏移 (KL={kl:.2f})"
                    )

            max_field_score = max(max_field_score, field_score)

        max_field_score = min(1.0, max_field_score)
        reason = "; ".join(field_reasons) if field_reasons else "分布正常"

        return {
            "dimension": "分布",
            "score": max_field_score,
            "reason": reason,
        }


class D3TypeShiftScorer:
    """维度3：类型偏移检测（字段类型 + 语义类型）"""

    def __init__(self, baseline_mgr: BaselineManager, sensitivity: float = 1.0):
        self.bm = baseline_mgr
        self.sensitivity = sensitivity

    def score(self, module: str, table: str, data: dict) -> Dict[str, Any]:
        """检测字段类型和语义类型是否发生偏移"""
        baseline = self.bm.load(module, table)
        sem_types: dict = baseline.get("semantic_types", {})
        total_writes = baseline.get("write_count", 0)

        if total_writes < COLD_START_THRESHOLD or not sem_types:
            return {"score": 0.0, "reason": "冷启动/数据不足，跳过类型偏移检测"}

        max_shift_score = 0.0
        shift_reasons = []

        for field, value in data.items():
            if field.startswith("_"):
                continue

            val_str = str(value)
            inferred = _infer_semantic_type(val_str)

            # 检查语义类型偏移
            if field in sem_types:
                type_dist = sem_types[field]
                total = sum(type_dist.values())
                expected_ratio = type_dist.get(inferred, 0) / max(total, 1)

                if expected_ratio < 0.05 and total >= 20:
                    # 语义类型极少出现
                    dominant_type = max(type_dist, key=type_dist.get)
                    dominant_ratio = type_dist[dominant_type] / max(total, 1)

                    shift_score = (1.0 - expected_ratio) * 0.5 * self.sensitivity
                    # 如果主类型占比极高，说明数据格式非常固定，偏移更可疑
                    if dominant_ratio > 0.9:
                        shift_score = min(1.0, shift_score * 1.5)

                    if shift_score > 0.1:
                        max_shift_score = max(max_shift_score, shift_score)
                        shift_reasons.append(
                            f"字段[{field}]语义类型从'{dominant_type}'偏移至'{inferred}' "
                            f"(历史占比{expected_ratio:.1%}, 主类型占比{dominant_ratio:.1%})"
                        )
            else:
                # 新字段出现
                shift_score = 0.3 * self.sensitivity
                max_shift_score = max(max_shift_score, shift_score)
                shift_reasons.append(
                    f"字段[{field}]为全新字段 (语义类型:{inferred})"
                )

            # 正则格式检测：如果历史主类型是phone/email/url/ip，新值格式不匹配
            if field in sem_types:
                type_dist = sem_types[field]
                dominant = max(type_dist, key=type_dist.get)
                if dominant != "plain" and dominant != inferred:
                    # 字段原本有特定语义格式，现在格式不匹配
                    format_bonus = 0.2 * self.sensitivity
                    max_shift_score = min(1.0, max_shift_score + format_bonus)
                    shift_reasons.append(
                        f"字段[{field}]历史格式'{dominant}'，当前值'{inferred}'不匹配"
                    )

        max_shift_score = min(1.0, max_shift_score)
        reason = "; ".join(shift_reasons) if shift_reasons else "类型一致"

        return {
            "dimension": "类型偏移",
            "score": max_shift_score,
            "reason": reason,
        }


class D4ViolationScorer:
    """维度4：约束违反率检测"""

    def __init__(self, baseline_mgr: BaselineManager, sensitivity: float = 1.0):
        self.bm = baseline_mgr
        self.sensitivity = sensitivity

    def score(self, module: str, table: str, data: dict,
              violations: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """检测约束违反比例及分布异常"""
        baseline = self.bm.load(module, table)
        total_writes = baseline.get("write_count", 0)

        if total_writes < COLD_START_THRESHOLD:
            return {"score": 0.0, "reason": "冷启动，跳过约束违反检测"}

        if not violations:
            return {"score": 0.0, "reason": "无约束违反"}

        v_hist: list = baseline.get("violation_history", [])
        vfd: dict = baseline.get("violation_field_dist", {})

        # --- 总体违反比例 ---
        v_total = sum(violations.values())
        v_count = len(violations)
        current_ratio = v_count / max(len(data), 1)

        field_violation_score = 0.0
        v_reasons = []

        if v_hist and len(v_hist) >= 5:
            baseline_mean = statistics.mean(v_hist)
            baseline_stdev = statistics.stdev(v_hist) if len(v_hist) > 1 else 0.0
            threshold = baseline_mean + Z_SCORE_FACTOR * baseline_stdev
            if threshold > 0 and current_ratio > threshold:
                ratio_score = min(
                    1.0, ((current_ratio - threshold) / max(threshold, 0.01)) * self.sensitivity
                )
                field_violation_score = max(field_violation_score, ratio_score)
                v_reasons.append(
                    f"违反比例 {current_ratio:.1%} 超过基线阈值 {threshold:.1%}"
                )

        # --- 新字段上的违反 vs 老字段 ---
        known_fields = set(vfd.keys())
        violating_fields = set(violations.keys())
        new_violations = violating_fields - known_fields
        old_violations = violating_fields & known_fields

        if new_violations and known_fields:
            # 新字段违反比例
            new_v_ratio = len(new_violations) / max(len(violating_fields), 1)
            if new_v_ratio > 0.3:
                new_field_score = min(1.0, new_v_ratio * self.sensitivity)
                field_violation_score = max(field_violation_score, new_field_score)
                v_reasons.append(
                    f"违反集中在新增字段: {', '.join(sorted(new_violations)[:5])}"
                )

        # --- 历史高违反字段的持续违反 ---
        if old_violations and vfd:
            for fld in old_violations:
                hist_count = vfd.get(fld, 0)
                cur_count = violations.get(fld, 0)
                if hist_count > 0 and cur_count > hist_count * 2:
                    repeat_score = min(0.5, cur_count / max(hist_count, 1) * 0.1 * self.sensitivity)
                    field_violation_score = max(field_violation_score, repeat_score)
                    v_reasons.append(
                        f"字段[{fld}]违反次数 {cur_count} 为历史 {hist_count} 的2倍以上"
                    )

        field_violation_score = min(1.0, field_violation_score)
        reason = "; ".join(v_reasons) if v_reasons else "约束违反率正常"

        return {
            "dimension": "约束违反",
            "score": field_violation_score,
            "reason": reason,
            "details": {
                "current_ratio": current_ratio,
                "total_violations": v_total,
                "new_fields_violating": len(new_violations),
            },
        }


class D5ConsistencyScorer:
    """维度5：跨模块一致性检测"""

    def __init__(self, baseline_mgr: BaselineManager, sensitivity: float = 1.0):
        self.bm = baseline_mgr
        self.sensitivity = sensitivity
        # 用于循环引用检测的访问跟踪集
        self._visited: Set[Tuple[str, str]] = set()

    def _resolve_foreign_keys(self, module: str, table: str) -> dict:
        """解析某个模块/表的已知外键引用关系"""
        baseline = self.bm.load(module, table)
        return baseline.get("foreign_keys", {})

    def score(self, module: str, table: str, data: dict,
              context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        检测外键引用一致性 + 循环引用。
        context 可传入 {"known_modules": {"module_a": {...}, ...}} 供交叉引用。
        """
        baseline = self.bm.load(module, table)
        total_writes = baseline.get("write_count", 0)

        if total_writes < COLD_START_THRESHOLD:
            return {"score": 0.0, "reason": "冷启动，跳过一致性检测"}

        consistency_score = 0.0
        consistency_reasons = []
        known_fks: dict = baseline.get("foreign_keys", {})

        # 从 context 获取已知模块
        known_modules: dict = context.get("known_modules", {}) if context else {}
        known_tables: Set[str] = set()
        for mod, tables in known_modules.items():
            if isinstance(tables, dict):
                known_tables.update(tables.keys())
            elif isinstance(tables, list):
                known_tables.update(tables)

        # --- 外键引用检查 ---
        for field, value in data.items():
            if field.endswith("_id") or field.endswith("_key"):
                ref_val = str(value)
                # 检查基线中是否有此引用
                if field in known_fks:
                    expected_refs: list = known_fks[field]
                    # 检查引用值是否在预期范围内
                    ref_found = False
                    for ref_mod, ref_tbl in expected_refs:
                        ref_baseline = self.bm.load(ref_mod, ref_tbl)
                        ref_values = ref_baseline.get("field_stats", {}).get(field, {}).get("values", {})
                        if ref_val in ref_values or ref_val == "":
                            ref_found = True
                            break
                    if not ref_found and ref_val:
                        # 引用值不存在于目标模块
                        ref_score = 0.3 * self.sensitivity
                        consistency_score = max(consistency_score, ref_score)
                        consistency_reasons.append(
                            f"字段[{field}]值'{ref_val[:20]}'在引用目标中不存在"
                        )

        # --- 循环引用检测 ---
        if context and "call_chain" in context:
            call_chain: List[Tuple[str, str]] = context["call_chain"]
            current = (module, table)
            if current in call_chain:
                # 发现循环引用
                cycle_length = len(call_chain) - call_chain.index(current)
                cycle_score = min(0.8, (cycle_length / 10) * self.sensitivity)
                consistency_score = max(consistency_score, cycle_score)
                chain_str = " -> ".join(
                    [f"{m}.{t}" for m, t in call_chain] + [f"{module}.{table}"]
                )
                consistency_reasons.append(
                    f"循环引用检测: {chain_str} (长度{cycle_length})"
                )

        # --- 跨模块交叉引用统计 ---
        if known_modules:
            missing_tables = 0
            total_refs = 0
            for field, refs in known_fks.items():
                total_refs += len(refs)
                for ref_mod, ref_tbl in refs:
                    if ref_mod in known_modules:
                        if isinstance(known_modules[ref_mod], dict):
                            if ref_tbl not in known_modules[ref_mod]:
                                missing_tables += 1
                        elif isinstance(known_modules[ref_mod], list):
                            if ref_tbl not in known_modules[ref_mod]:
                                missing_tables += 1

            if total_refs > 0:
                missing_ratio = missing_tables / max(total_refs, 1)
                if missing_ratio > 0.2:
                    miss_score = min(0.5, missing_ratio * self.sensitivity)
                    consistency_score = max(consistency_score, miss_score)
                    consistency_reasons.append(
                        f"外键引用中 {missing_tables}/{total_refs} 目标表缺失"
                    )

        consistency_score = min(1.0, consistency_score)
        reason = "; ".join(consistency_reasons) if consistency_reasons else "跨模块一致性正常"

        return {
            "dimension": "跨模块一致",
            "score": consistency_score,
            "reason": reason,
        }


# ===================================================================
#  主评分引擎
# ===================================================================


class AnomalyScorer:
    """
    多维异常评分引擎
    
    对写入数据进行五维联合异常评分，返回综合异常分数和每个维度的详情。
    支持动态阈值（基于统计学的均值+2*标准差，替代固定阈值）。
    支持冷启动降级（写入小于 COLD_START_THRESHOLD 条时仅做部分检测）。
    """

    def __init__(self, db_url: Optional[str] = None):
        """
        Args:
            db_url: 可选的数据库连接字符串。如果提供，可以查询 DB 中的历史数据。
                    当前版本使用文件基线存储，db_url 保留用于未来扩展。
        """
        self.db_url = db_url
        self.baseline_mgr = BaselineManager()
        self.sensitivities: Dict[str, Dict[str, float]] = {}

        # 初始化各维度评分器，使用默认灵敏度
        self.d1 = D1FrequencyScorer(self.baseline_mgr)
        self.d2 = D2DistributionScorer(self.baseline_mgr)
        self.d3 = D3TypeShiftScorer(self.baseline_mgr)
        self.d4 = D4ViolationScorer(self.baseline_mgr)
        self.d5 = D5ConsistencyScorer(self.baseline_mgr)

    def set_sensitivity(self, module: str, table: str,
                        config: Optional[Dict[str, float]] = None) -> None:
        """
        设置特定模块/表的灵敏度配置
        
        Args:
            module: 模块名
            table: 表名
            config: 灵敏度字典，如 {"d1_frequency": 0.8, "d3_type_shift": 1.5}
                     不传则重置为默认值
        """
        key = f"{module}.{table}"
        if config is None:
            self.sensitivities.pop(key, None)
        else:
            merged = dict(DEFAULT_SENSITIVITY)
            merged.update(config)
            self.sensitivities[key] = merged

    def _get_sensitivity(self, module: str, table: str) -> Dict[str, float]:
        """获取模块/表的灵敏度配置"""
        key = f"{module}.{table}"
        config = self.sensitivities.get(key)
        if config is None:
            return dict(DEFAULT_SENSITIVITY)
        return config

    def score(self, module: str, table: str, data: dict,
              write_rate: Optional[int] = None,
              context: Optional[dict] = None,
              violations: Optional[Dict[str, int]] = None) -> dict:
        """
        多维异常评分

        Args:
            module: 来源模块名
            table: 目标表名
            data: 写入数据字典
            write_rate: 可选的写入速率（次/秒）
            context: 上下文信息，可包含:
                - known_modules: 已知模块列表/字典，用于交叉引用
                - call_chain: 调用链 [(mod, table), ...]，用于循环引用检测
            violations: 可选的数据契约违反统计 {field: count}

        Returns:
            dict: {
                "score": 0.0-1.0 综合异常评分,
                "details": [
                    {"dimension": "频率", "score": 0.1, "reason": "..."},
                    ...
                ],
                "cold_start": bool,
                "threshold": 动态阈值,
            }
        """
        if context is None:
            context = {}
        if violations is None:
            violations = {}

        baseline = self.baseline_mgr.load(module, table)
        total_writes = baseline.get("write_count", 0)
        cold_start = total_writes < COLD_START_THRESHOLD

        sens = self._get_sensitivity(module, table)

        # 更新各维度评分器的灵敏度
        self.d1.sensitivity = sens["d1_frequency"]
        self.d2.sensitivity = sens["d2_distribution"]
        self.d3.sensitivity = sens["d3_type_shift"]
        self.d4.sensitivity = sens["d4_violation"]
        self.d5.sensitivity = sens["d5_consistency"]

        # 各维度评分
        details = []
        d1_result = self.d1.score(module, table, data, write_rate)
        d2_result = self.d2.score(module, table, data)
        d3_result = self.d3.score(module, table, data)
        d4_result = self.d4.score(module, table, data, violations)
        d5_result = self.d5.score(module, table, data, context)

        details.append(d1_result)
        details.append(d2_result)
        details.append(d3_result)
        details.append(d4_result)
        details.append(d5_result)

        # 综合评分：最大值加权 + 叠加惩罚
        scores = [d["score"] for d in details]
        max_score = max(scores)

        # 如果有两个以上维度同时异常，叠加惩罚
        high_dims = [s for s in scores if s > 0.3]
        if len(high_dims) >= 2:
            # 多维联合异常惩罚
            joint_penalty = (len(high_dims) - 1) * 0.15
            combined_score = min(1.0, max_score + joint_penalty)
        else:
            combined_score = max_score

        # 计算动态阈值
        hist_scores = baseline.get("history_scores", [])
        threshold, stdev = _dynamic_threshold(hist_scores) if hist_scores else (0.5, 0.0)

        # 更新历史评分
        hist_scores.append(combined_score)
        if len(hist_scores) > 500:
            hist_scores = hist_scores[-250:]
        baseline["history_scores"] = hist_scores

        # 保存更新后的基线（包括评分历史）
        self.baseline_mgr.save(module, table, baseline)

        # 更新基线数据（频率、分布等）
        self.baseline_mgr.update(module, table, data, write_rate, violations)

        result = {
            "score": round(combined_score, 4),
            "details": details,
            "cold_start": cold_start,
            "threshold": round(threshold, 4),
            "threshold_stddev": round(stdev, 4),
        }

        return result

    def get_baseline_summary(self, module: str, table: str) -> dict:
        """获取基线摘要信息"""
        baseline = self.baseline_mgr.load(module, table)
        return {
            "module": module,
            "table": table,
            "total_writes": baseline.get("write_count", 0),
            "last_updated": baseline.get("updated_at", 0),
            "fields_tracked": list(baseline.get("field_stats", {}).keys()),
            "frequency_samples": len(baseline.get("frequencies", [])),
            "violation_history_length": len(baseline.get("violation_history", [])),
        }

    def clear_baselines(self, module: Optional[str] = None,
                        table: Optional[str] = None) -> int:
        """
        清除基线数据
        
        Args:
            module: 如果指定，只清除该模块的基线
            table: 如果指定（需同时指定module），清除特定表

        Returns:
            清除的基线文件数量
        """
        cleared = 0
        if module and table:
            self.baseline_mgr.save(module, table, self.baseline_mgr._empty_baseline())
            cleared = 1
        elif module:
            pattern = f"{module}."
            for fname in os.listdir(self.baseline_mgr.root_dir):
                if fname.startswith(pattern) and fname.endswith(".json"):
                    os.remove(os.path.join(self.baseline_mgr.root_dir, fname))
                    cleared += 1
        else:
            for fname in os.listdir(self.baseline_mgr.root_dir):
                if fname.endswith(".json"):
                    os.remove(os.path.join(self.baseline_mgr.root_dir, fname))
                    cleared += 1
        self.baseline_mgr._cache.clear()
        return cleared


# ===================================================================
#  便捷入口
# ===================================================================


def quick_score(module: str, table: str, data: dict,
                violations: Optional[Dict[str, int]] = None,
                context: Optional[dict] = None) -> dict:
    """快速单次评分，使用默认配置"""
    scorer = AnomalyScorer()
    return scorer.score(module, table, data, context=context, violations=violations)
