"""
Online Learning Engine — 在线学习引擎 (反馈→自动模型参数调整)
==============================================================

构建从用户反馈到推荐模型参数自动调整的在线学习闭环。

架构:
  ┌──────────────┐   feedback   ┌──────────────────┐  每N条触发   ┌──────────────────────┐
  │ FeedbackLoop │ ──────────→  │ OnlineLearning   │ ──────────→  │ RecommendEngine      │
  │  (SQLite)    │              │ Engine           │              │ 权重调整             │
  └──────────────┘              │                  │              └──────────────────────┘
                                │ 1. 累计反馈检查   │
                                │ 2. 全局权重计算   │
                                │ 3. 日志记录      │
                                └──────────────────┘
                                        │
                                        ▼
                                ┌──────────────┐
                                │ learning_log │
                                │  .jsonl      │
                                └──────────────┘

调整策略 (batch = 100条反馈):
  - LIKE  (rating>0):    全局权重 +0.05
  - DISLIKE(rating<0):   全局权重 -0.05
  - SKIP  (rating==0):   无变化
  最终权重 clamp 到 [0.5, 1.5] 范围。

在线学习影响 RecommendEngine 的三个维度权重系数 (WEIGHT_TAG_MATCH,
WEIGHT_GRAPH, WEIGHT_SEMANTIC)，通过模块级全局变量 + JSON 持久化共享。
"""

import json
import logging
import os
import threading
import time
from collections import deque
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ======================================================================
# 全局权重共享 — OnlineLearningEngine 和 RecommendEngine 共享
# ======================================================================

# 默认基础权重 (与 RecommendEngine 默认值保持一致)
_DEFAULT_WEIGHTS = {
    "tag_match": 0.40,
    "graph": 0.30,
    "semantic": 0.30,
}

# 当前生效的在线学习权重 (模块级, 线程安全)
_online_weights: dict[str, float] = dict(_DEFAULT_WEIGHTS)
_weights_lock = threading.Lock()

# 在线学习全局调整系数 (由 OnlineLearningEngine 计算)
# 初始1.0, 随正/负反馈比例增减
_global_adjustment: float = 1.0
_global_adjustment_lock = threading.Lock()

# 持久化路径
_WEIGHTS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "data",
    "online_weights.json",
)


def _get_weights_path() -> str:
    """获取权重文件路径"""
    path = os.path.abspath(_WEIGHTS_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def load_online_weights() -> dict[str, float]:
    """加载持久化的在线学习权重"""
    global _online_weights
    path = _get_weights_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            with _weights_lock:
                _online_weights.update({k: v for k, v in data.items() if k in _DEFAULT_WEIGHTS})
                if "global_adjustment" in data:
                    global _global_adjustment
                    with _global_adjustment_lock:
                        _global_adjustment = float(data["global_adjustment"])
            logger.info("在线学习权重已加载: %s", _online_weights)
        except Exception as e:
            logger.warning("在线学习权重加载失败, 使用默认值: %s", e)
    return dict(_online_weights)


def save_online_weights(weights: dict[str, float], global_adj: float = 1.0):
    """持久化在线学习权重到 JSON 文件"""
    path = _get_weights_path()
    try:
        data = dict(weights)
        data["global_adjustment"] = global_adj
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug("在线学习权重已保存: %s", data)
    except Exception as e:
        logger.error("在线学习权重保存失败: %s", e)


def get_online_weight(name: str) -> float:
    """获取指定维度的在线学习调整后权重

    Args:
        name: 权重名称 (tag_match | graph | semantic)

    Returns:
        调整后的权重值, 如未调整则返回默认值
    """
    with _weights_lock:
        return _online_weights.get(name, _DEFAULT_WEIGHTS.get(name, 0.0))


def get_all_online_weights() -> dict[str, float]:
    """获取所有在线学习调整后的权重"""
    with _weights_lock:
        result = dict(_DEFAULT_WEIGHTS)
        result.update(_online_weights)
        result["global_adjustment"] = _global_adjustment
        return result


def get_global_adjustment() -> float:
    """获取全局调整系数"""
    with _global_adjustment_lock:
        return _global_adjustment


# ======================================================================
# OnlineLearningPipeline (已有 — 纯内存交互记录, 保持不变)
# ======================================================================


class OnlineLearningPipeline:
    """在线学习管道: 记录交互、获取热门趋势、查询用户历史。纯内存+线程安全。"""

    VALID_ACTIONS = {"view", "click", "share", "save"}

    def __init__(self):
        self._lock = threading.Lock()
        # {user_id: deque([(timestamp, item_id, action), ...])}
        self._user_history: dict[str, deque] = {}
        # {item_id: deque([(timestamp, action, user_id), ...])}
        self._item_events: dict[str, deque] = {}

    def _ensure_user(self, user_id: str) -> deque:
        """线程安全地获取或创建用户历史 deque."""
        if user_id not in self._user_history:
            self._user_history[user_id] = deque(maxlen=10000)
        return self._user_history[user_id]

    def _ensure_item(self, item_id: str) -> deque:
        """线程安全地获取或创建 item 事件 deque."""
        if item_id not in self._item_events:
            self._item_events[item_id] = deque(maxlen=100000)
        return self._item_events[item_id]

    def record_interaction(
        self,
        user_id: str,
        item_id: str,
        action: str,
        timestamp: float | None = None,
    ) -> None:
        """记录一条用户交互。action 必须为 view/click/share/save 之一。"""
        if action not in self.VALID_ACTIONS:
            raise ValueError(f"无效 action: {action}，必须为 {self.VALID_ACTIONS}")
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            self._ensure_user(user_id).append((ts, item_id, action))
            self._ensure_item(item_id).append((ts, action, user_id))

    def get_trending(self, hours: int = 24, limit: int = 50) -> list[dict]:
        """返回指定小时内按交互量降序排列的热门 item 列表。"""
        cutoff = time.time() - hours * 3600
        counts: dict[str, int] = {}

        with self._lock:
            for item_id, events in self._item_events.items():
                c = 0
                for ts, action, uid in events:
                    if ts >= cutoff:
                        c += 1
                if c:
                    counts[item_id] = c

        sorted_items = sorted(counts.items(), key=lambda x: -x[1])
        return [{"item_id": item_id, "count": count} for item_id, count in sorted_items[:limit]]

    def get_user_history(self, user_id: str, limit: int = 100) -> list[dict]:
        """返回用户历史交互（按时间倒序）。"""
        with self._lock:
            history = list(self._user_history.get(user_id, []))
        # 按时间戳倒序
        history.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "timestamp": ts,
                "item_id": item_id,
                "action": action,
            }
            for ts, item_id, action in history[:limit]
        ]


# ======================================================================
# OnlineLearningEngine — 在线学习引擎 (反馈→模型参数调整)
# ======================================================================


class OnlineLearningEngine:
    """在线学习引擎

    监视 FeedbackLoop 的累计反馈量, 每达到 LEARN_THRESHOLD 条反馈,
    自动触发一次全局模型参数调整:

    1. 从 FeedbackLoop 读取反馈统计 (正/负/总)
    2. 计算净调整量: like+0.05, dislike-0.05, skip+0
    3. 更新 RecommendEngine 的全局权重系数
    4. 记录学习日志到 learning_log.jsonl
    5. 持久化新权重到 JSON 文件
    """

    # 学习触发阈值: 每累积 100 条反馈触发一次
    LEARN_THRESHOLD = 100

    # 每次调整幅度
    ADJUST_LIKE = 0.05  # 👍 积极反馈
    ADJUST_DISLIKE = -0.05  # 👎 消极反馈
    ADJUST_SKIP = 0.0  # 跳过无影响

    # 权重范围限制
    MIN_GLOBAL_ADJUSTMENT = 0.5
    MAX_GLOBAL_ADJUSTMENT = 1.5

    # ── 类级单例 ──────────────────────────────────────────────
    _instance: Optional["OnlineLearningEngine"] = None
    _last_learn_time: float = 0.0
    _last_feedback_count: int = 0
    _total_learning_cycles: int = 0
    _last_learn_result: dict | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 日志文件路径
        data_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "..",
            "data",
        )
        os.makedirs(data_dir, exist_ok=True)
        self._log_path = os.path.join(data_dir, "learning_log.jsonl")

        # 加载持久化的在线学习权重
        load_online_weights()

        logger.info(
            "OnlineLearningEngine 初始化完成: threshold=%d, log=%s",
            self.LEARN_THRESHOLD,
            self._log_path,
        )

    # ── 日志记录 ──────────────────────────────────────────────

    def _append_log(self, entry: dict):
        """追加一条学习日志到 JSONL 文件"""
        try:
            line = json.dumps(entry, ensure_ascii=False)
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            logger.error("学习日志写入失败: %s", e)

    def get_recent_logs(self, limit: int = 50) -> list[dict]:
        """获取最近的学习日志

        Args:
            limit: 返回最新日志条数

        Returns:
            list[dict]: 日志条目列表, 按时间倒序
        """
        logs = []
        try:
            if not os.path.exists(self._log_path):
                return []
            with open(self._log_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            logs.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            # 按时间戳倒序
            logs.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return logs[:limit]
        except Exception as e:
            logger.error("学习日志读取失败: %s", e)
            return []

    # ── 反馈数据获取 ──────────────────────────────────────────

    def _get_feedback_stats(self) -> dict[str, Any]:
        """从 FeedbackLoop 获取反馈统计数据

        Returns:
            dict: 包含 total, positive, negative 等统计
        """
        try:
            from app.ai.feedback_loop import get_feedback_loop

            loop = get_feedback_loop()
            return loop.get_global_stats()
        except Exception as e:
            logger.warning("获取反馈统计失败: %s", e)
            return {
                "total_feedback": 0,
                "positive_feedback": 0,
                "negative_feedback": 0,
                "unique_users": 0,
                "weight_cache_entries": 0,
            }

    # ── 核心学习逻辑 ──────────────────────────────────────────

    def run_learning_cycle(self) -> dict[str, Any]:
        """执行一轮在线学习

        读取反馈统计 → 计算全局调整 → 更新权重 → 记录日志

        Returns:
            dict: 学习结果报告
        """
        start_time = time.time()
        stats = self._get_feedback_stats()
        total = stats.get("total_feedback", 0)
        positive = stats.get("positive_feedback", 0)
        negative = stats.get("negative_feedback", 0)

        # 计算本周期新增反馈
        prev_count = self._last_feedback_count
        new_feedback = total - prev_count

        # 计算正负反馈比例
        if total > 0:
            like_ratio = positive / total
            dislike_ratio = negative / total
        else:
            like_ratio = 0.0
            dislike_ratio = 0.0

        # 计算净调整量
        # 用本周期新增反馈的比例来计算调整
        if new_feedback > 0:
            # 估算本周期新增的正/负反馈 (按整体比例)
            batch_likes = new_feedback * like_ratio
            batch_dislikes = new_feedback * dislike_ratio
            net_adjust = batch_likes * self.ADJUST_LIKE + batch_dislikes * self.ADJUST_DISLIKE
        else:
            net_adjust = 0.0

        # 更新全局调整系数
        global _global_adjustment
        with _global_adjustment_lock:
            new_adjustment = _global_adjustment + net_adjust
            new_adjustment = max(
                self.MIN_GLOBAL_ADJUSTMENT,
                min(self.MAX_GLOBAL_ADJUSTMENT, new_adjustment),
            )
            old_adjustment = _global_adjustment
            _global_adjustment = new_adjustment

        # 更新各维度权重: 等比例应用全局调整
        with _weights_lock:
            old_weights = dict(_online_weights)
            for key in _DEFAULT_WEIGHTS:
                base = _DEFAULT_WEIGHTS[key]
                # 等比例缩放, 不加归一化 — 权重绝对值变化代表推荐策略偏移
                adjusted = base * new_adjustment
                _online_weights[key] = round(adjusted, 4)

            # 保持三个权重的比例关系, 不做强制归一化到1.0
            # 这样 RecommendEngine 的 final_score = sum(weight * score) 会整体放大/缩小
            # 影响推荐排序: 权重绝对值高的维度获得更大话语权
            new_weights = dict(_online_weights)

        # 持久化
        save_online_weights(new_weights, new_adjustment)

        # 热更新 RecommendEngine 权重
        try:
            from app.ai.recommendation import RecommendEngine

            RecommendEngine.refresh_online_weights()
        except Exception as e:
            logger.debug("RecommendEngine 权重热更新跳过: %s", e)

        # 更新状态
        self._last_learn_time = time.time()
        self._last_feedback_count = total
        self._total_learning_cycles += 1

        # 构建结果报告
        elapsed = time.time() - start_time
        result = {
            "timestamp": self._last_learn_time,
            "cycle": self._total_learning_cycles,
            "duration_seconds": round(elapsed, 3),
            "feedback_stats": {
                "total": total,
                "positive": positive,
                "negative": negative,
                "new_since_last": new_feedback,
                "like_ratio": round(like_ratio, 4),
                "dislike_ratio": round(dislike_ratio, 4),
            },
            "weight_changes": {
                "old_global_adjustment": old_adjustment,
                "new_global_adjustment": new_adjustment,
                "net_adjust": round(net_adjust, 4),
                "old_weights": old_weights,
                "new_weights": new_weights,
            },
            "status": "completed",
        }

        # 记录日志
        self._append_log(result)
        self._last_learn_result = result

        logger.info(
            "在线学习周期 #%d 完成: total_feedback=%d, adjustment=%.4f→%.4f, weights=%s, 耗时=%.3fs",
            self._total_learning_cycles,
            total,
            old_adjustment,
            new_adjustment,
            new_weights,
            elapsed,
        )

        return result

    def check_and_learn(self) -> dict | None:
        """检查反馈量是否达到阈值, 是则触发学习

        Returns:
            Optional[dict]: 如果触发了学习返回结果, 否则返回 None
        """
        stats = self._get_feedback_stats()
        total = stats.get("total_feedback", 0)

        # 计算从上次学习后新增的反馈数
        new_count = total - self._last_feedback_count

        if new_count >= self.LEARN_THRESHOLD:
            logger.info(
                "反馈累积达阈值: 新增 %d 条 (>=%d), 触发在线学习",
                new_count,
                self.LEARN_THRESHOLD,
            )
            return self.run_learning_cycle()

        logger.debug(
            "未达学习阈值: 新增 %d / %d (总反馈 %d)",
            new_count,
            self.LEARN_THRESHOLD,
            total,
        )
        return None

    # ── 状态查询 ──────────────────────────────────────────────

    def get_learning_status(self) -> dict[str, Any]:
        """获取在线学习引擎当前状态

        Returns:
            dict: 包含反馈统计、学习时间、参数变化等
        """
        stats = self._get_feedback_stats()
        total = stats.get("total_feedback", 0)

        # 计算距下次学习的进度
        new_since_last = total - self._last_feedback_count
        progress = min(100.0, (new_since_last / self.LEARN_THRESHOLD) * 100.0)

        all_weights = get_all_online_weights()

        # 获取最近一次学习结果
        last_result = None
        if self._last_learn_result:
            last_result = {
                "time": self._last_learn_result.get("timestamp"),
                "cycle": self._last_learn_result.get("cycle"),
                "adjustment_before": self._last_learn_result.get("weight_changes", {}).get("old_global_adjustment"),
                "adjustment_after": self._last_learn_result.get("weight_changes", {}).get("new_global_adjustment"),
            }

        return {
            "status": "active" if self._initialized else "inactive",
            "feedback": {
                "total": total,
                "positive": stats.get("positive_feedback", 0),
                "negative": stats.get("negative_feedback", 0),
                "unique_users": stats.get("unique_users", 0),
            },
            "learning": {
                "threshold": self.LEARN_THRESHOLD,
                "new_since_last_learn": new_since_last,
                "progress_percent": round(progress, 1),
                "total_cycles": self._total_learning_cycles,
                "last_learn_time": self._last_learn_time,
                "last_learn_result": last_result,
            },
            "current_weights": {
                "global_adjustment": all_weights.get("global_adjustment", 1.0),
                "tag_match": all_weights.get("tag_match", 0.40),
                "graph": all_weights.get("graph", 0.30),
                "semantic": all_weights.get("semantic", 0.30),
                "default_weights": dict(_DEFAULT_WEIGHTS),
            },
        }


# ── 单例快捷函数 ──────────────────────────────────────────────

_engine: OnlineLearningEngine | None = None


def get_online_learning_engine() -> OnlineLearningEngine:
    """获取全局 OnlineLearningEngine 单例"""
    global _engine
    if _engine is None:
        _engine = OnlineLearningEngine()
    return _engine


def trigger_learning() -> dict[str, Any]:
    """手动触发一次在线学习"""
    engine = get_online_learning_engine()
    return engine.run_learning_cycle()


def get_learning_status() -> dict[str, Any]:
    """获取在线学习状态"""
    engine = get_online_learning_engine()
    return engine.get_learning_status()
