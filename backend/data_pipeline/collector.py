"""
链客宝 - 数据采集器
======================
统一数据采集层，整合散落在各个路由模块的数据源。
将 retention_insights / learning_center / unit_economics
等模块的内存数据统一提取为标准化的 DataSource 对象。

设计原则：
1. 每个采集器只关注一个数据源，职责单一
2. 采集结果统一为标准 DataSource 结构
3. 通过配置控制哪些源启用/禁用
4. 支持重试和超时
"""

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, Optional, TypeVar, Union

from .config import CollectorConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 标准数据类型（统一采集输出格式）
# ---------------------------------------------------------------------------

T = TypeVar("T")


@dataclass
class DataRecord:
    """采集数据记录（标准化单条数据）"""

    id: Optional[Union[int, str]]
    source: str  # 来源标识 e.g. "retention", "learning"
    record_type: str  # 记录类型 e.g. "cohort", "course"
    data: dict[str, Any]  # 原始数据字典
    collected_at: str = ""  # 采集时间戳

    def __post_init__(self) -> None:
        if not self.collected_at:
            self.collected_at = datetime.utcnow().isoformat() + "Z"


@dataclass
class DataSource(Generic[T]):
    """数据源采集结果（每个数据源对应一个实例）"""

    name: str  # 数据源名称
    records: list[T] = field(default_factory=list)
    total_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    collected_at: str = ""

    def __post_init__(self) -> None:
        if not self.collected_at:
            self.collected_at = datetime.utcnow().isoformat() + "Z"

    @property
    def success(self) -> bool:
        """是否采集成功（无错误）"""
        return self.error_count == 0

    def merge(self, other: "DataSource") -> "DataSource":
        """合并另一个数据源（用于相同类型的数据源聚合）"""
        self.records.extend(other.records)
        self.total_count += other.total_count
        self.error_count += other.error_count
        self.errors.extend(other.errors)
        self.elapsed_seconds += other.elapsed_seconds
        return self


# ---------------------------------------------------------------------------
# 采集器基类
# ---------------------------------------------------------------------------


class BaseCollector(ABC):
    """数据采集器基类，所有采集器必须继承此类"""

    def __init__(self, config: Optional[CollectorConfig] = None) -> None:
        self.config = config or CollectorConfig()
        self._start_time: float = 0.0

    @property
    @abstractmethod
    def source_name(self) -> str:
        """采集器名称，用于标识数据来源"""
        ...

    @abstractmethod
    def collect(self) -> DataSource:
        """执行数据采集，返回标准化数据源"""
        ...

    def _start_timer(self) -> None:
        """开始计时"""
        self._start_time = time.perf_counter()

    def _end_timer(self) -> float:
        """结束计时并返回耗时"""
        return round(time.perf_counter() - self._start_time, 3)

    def _make_result(
        self,
        records: list,
        errors: Optional[list[str]] = None,
        error_count: Optional[int] = None,
    ) -> DataSource:
        """构造标准化返回结果"""
        elapsed = self._end_timer()
        return DataSource(
            name=self.source_name,
            records=records,
            total_count=len(records),
            error_count=error_count or (len(errors) if errors else 0),
            errors=errors or [],
            elapsed_seconds=elapsed,
        )

    def _safe_collect(self, fn, *args, **kwargs) -> Any:
        """安全执行采集函数，带重试机制"""
        last_error: Optional[Exception] = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(
                    "[%s] 采集失败 (attempt=%d/%d): %s",
                    self.source_name, attempt, self.config.max_retries, e,
                )
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_backoff_seconds * attempt)
        raise RuntimeError(
            f"[{self.source_name}] 采集失败，已重试 {self.config.max_retries} 次: {last_error}"
        )


# ---------------------------------------------------------------------------
# 具体采集器实现
# ---------------------------------------------------------------------------


class BaseDataCollector(BaseCollector):
    """带通用采集方法的基类，为子类提供 try-block 模板"""

    def _collect_records(
        self,
        items,
        record_type: str,
        fields: list[str],
        errors: list[str],
        records: list,
        err_label: str,
    ) -> None:
        """采集一组相同类型的记录，异常时追加错误"""
        try:
            for item in items:
                data = {}
                for f in fields:
                    data[f] = getattr(item, f, None)
                records.append(DataRecord(
                    id=getattr(item, "id", None),
                    source=self.source_name,
                    record_type=record_type,
                    data=data,
                ))
        except Exception as e:
            errors.append(f"{err_label} 采集失败: {e}")


class RetentionCollector(BaseCollector):
    """
    留存分析数据采集器

    从 retention_insights.py 模块采集：
        - Cohort（用户群组）
        - CohortRetention（留存率序列）
        - UserActivity（用户行为日志）
        - ChurnSignal（流失信号）
        - RetentionStrategy（留存策略）

    向后兼容：直接引用 retention_insights 的内存数据，
    不修改现有模块。
    """

    @property
    def source_name(self) -> str:
        return "retention"

    def collect(self) -> DataSource[DataRecord]:
        """采集留存分析模块的所有数据"""
        self._start_timer()
        errors: list[str] = []

        try:
            from app.routers.retention_insights import (
                COHORTS,
                COHORT_RETENTION,
                ACTIVITIES,
                CHURN_SIGNALS,
                RETENTION_STRATEGIES,
            )
        except ImportError as e:
            errors.append(f"无法导入 retention_insights 模块: {e}")
            return self._make_result([], errors=errors)

        records: list[DataRecord] = []
        self._collect_cohorts(COHORTS, records, errors)
        self._collect_retentions(COHORT_RETENTION, records, errors)
        self._collect_activities(ACTIVITIES, records, errors)
        self._collect_churn_signals(CHURN_SIGNALS, records, errors)
        self._collect_strategies(RETENTION_STRATEGIES, records, errors)

        return self._make_result(records, errors=errors or None)

    # ------------------------------------------------------------------
    # 子方法
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_cohorts(cohorts, records, errors):
        try:
            for c in cohorts:
                records.append(DataRecord(
                    id=c.id,
                    source="retention",
                    record_type="cohort",
                    data={
                        "name": c.name, "period": c.period,
                        "cohort_type": c.cohort_type, "user_count": c.user_count,
                        "source": c.source, "plan": c.plan, "tags": c.tags,
                        "created_at": c.created_at,
                    },
                ))
        except Exception as e:
            errors.append(f"Cohort 采集失败: {e}")

    @staticmethod
    def _collect_retentions(retentions, records, errors):
        try:
            for r in retentions:
                records.append(DataRecord(
                    id=r.id, source="retention",
                    record_type="cohort_retention",
                    data={
                        "cohort_id": r.cohort_id, "period_offset": r.period_offset,
                        "period_label": r.period_label, "active_users": r.active_users,
                        "retention_rate": r.retention_rate, "calculated_at": r.calculated_at,
                    },
                ))
        except Exception as e:
            errors.append(f"CohortRetention 采集失败: {e}")

    @staticmethod
    def _collect_activities(activities, records, errors):
        try:
            for a in activities:
                records.append(DataRecord(
                    id=a.id, source="retention",
                    record_type="user_activity",
                    data={
                        "user_id": a.user_id, "username": a.username,
                        "cohort_period": a.cohort_period, "activity_period": a.activity_period,
                        "actions": a.actions, "is_active": a.is_active,
                        "last_active_at": a.last_active_at,
                    },
                ))
        except Exception as e:
            errors.append(f"UserActivity 采集失败: {e}")

    @staticmethod
    def _collect_churn_signals(signals, records, errors):
        try:
            for s in signals:
                records.append(DataRecord(
                    id=s.id, source="retention",
                    record_type="churn_signal",
                    data={
                        "user_id": s.user_id, "username": s.username,
                        "signal_type": s.signal_type, "severity": s.severity,
                        "description": s.description, "detected_at": s.detected_at,
                        "days_since_last_active": s.days_since_last_active,
                        "recommended_action": s.recommended_action, "resolved": s.resolved,
                    },
                ))
        except Exception as e:
            errors.append(f"ChurnSignal 采集失败: {e}")

    @staticmethod
    def _collect_strategies(strategies, records, errors):
        try:
            for st in strategies:
                records.append(DataRecord(
                    id=st.id, source="retention",
                    record_type="retention_strategy",
                    data={
                        "segment": st.segment, "title": st.title,
                        "description": st.description, "actions": st.actions,
                        "expected_impact": st.expected_impact, "priority": st.priority,
                        "status": st.status,
                    },
                ))
        except Exception as e:
            errors.append(f"RetentionStrategy 采集失败: {e}")


class LearningCollector(BaseCollector):
    """
    学习中心数据采集器

    从 learning_center.py 模块采集：
        - Course（课程）
        - Module（模块）
        - Lesson（课时）
        - LearningProgress（学习进度）
        - AiTutorMessage（AI导师对话）
        - Certification（认证记录）
    """

    @property
    def source_name(self) -> str:
        return "learning"

    def collect(self) -> DataSource[DataRecord]:
        """采集学习中心模块的所有数据"""
        self._start_timer()
        errors: list[str] = []

        try:
            from app.routers.learning_center import (
                COURSES,
                MODULES,
                LESSONS,
                PROGRESSES,
                AI_TUTOR_MESSAGES,
                CERTIFICATIONS,
            )
        except ImportError as e:
            errors.append(f"无法导入 learning_center 模块: {e}")
            return self._make_result([], errors=errors)

        records: list[DataRecord] = []
        self._collect_courses(COURSES, records, errors)
        self._collect_modules(MODULES, records, errors)
        self._collect_lessons(LESSONS, records, errors)
        self._collect_progresses(PROGRESSES, records, errors)
        self._collect_tutor_messages(AI_TUTOR_MESSAGES, records, errors)
        self._collect_certifications(CERTIFICATIONS, records, errors)

        return self._make_result(records, errors=errors or None)

    # ------------------------------------------------------------------
    # 子方法
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_courses(courses, records, errors):
        try:
            for c in courses:
                records.append(DataRecord(
                    id=c.id, source="learning", record_type="course",
                    data={
                        "title": c.title, "description": c.description,
                        "category": c.category, "level": c.level,
                        "duration_minutes": c.duration_minutes, "modules_count": c.modules_count,
                        "instructor": c.instructor, "tags": c.tags,
                        "rating": c.rating, "enrolled_count": c.enrolled_count,
                        "completion_rate": c.completion_rate, "status": c.status,
                        "created_at": c.created_at,
                    },
                ))
        except Exception as e:
            errors.append(f"Course 采集失败: {e}")

    @staticmethod
    def _collect_modules(modules, records, errors):
        try:
            for m in modules:
                records.append(DataRecord(
                    id=m.id, source="learning", record_type="module",
                    data={
                        "course_id": m.course_id, "module_code": m.module_code,
                        "title": m.title, "description": m.description,
                        "content_type": m.content_type, "duration_minutes": m.duration_minutes,
                        "order": m.order, "is_required": m.is_required,
                    },
                ))
        except Exception as e:
            errors.append(f"Module 采集失败: {e}")

    @staticmethod
    def _collect_lessons(lessons, records, errors):
        try:
            for l in lessons:
                records.append(DataRecord(
                    id=l.id, source="learning", record_type="lesson",
                    data={
                        "module_id": l.module_id, "title": l.title,
                        "content_type": l.content_type, "duration_minutes": l.duration_minutes,
                        "order": l.order,
                    },
                ))
        except Exception as e:
            errors.append(f"Lesson 采集失败: {e}")

    @staticmethod
    def _collect_progresses(progresses, records, errors):
        try:
            for p in progresses:
                records.append(DataRecord(
                    id=p.id, source="learning", record_type="learning_progress",
                    data={
                        "user_id": p.user_id, "course_id": p.course_id,
                        "progress_pct": p.progress_pct, "completed_lessons": p.completed_lessons,
                        "total_lessons": p.total_lessons, "time_spent_minutes": p.time_spent_minutes,
                        "quiz_score": p.quiz_score, "status": p.status,
                        "started_at": p.started_at, "completed_at": p.completed_at,
                    },
                ))
        except Exception as e:
            errors.append(f"LearningProgress 采集失败: {e}")

    @staticmethod
    def _collect_tutor_messages(messages, records, errors):
        try:
            for msg in messages:
                records.append(DataRecord(
                    id=msg.id, source="learning", record_type="ai_tutor_message",
                    data={
                        "user_id": msg.user_id, "course_id": msg.course_id,
                        "role": msg.role, "content": msg.content,
                    },
                ))
        except Exception as e:
            errors.append(f"AiTutorMessage 采集失败: {e}")

    @staticmethod
    def _collect_certifications(certifications, records, errors):
        try:
            for cert in certifications:
                records.append(DataRecord(
                    id=cert.id, source="learning", record_type="certification",
                    data={
                        "user_id": cert.user_id, "user_name": cert.user_name,
                        "course_id": cert.course_id, "course_title": cert.course_title,
                        "score": cert.score, "passed": cert.passed,
                        "skills": cert.skills, "issued_at": cert.issued_at,
                    },
                ))
        except Exception as e:
            errors.append(f"Certification 采集失败: {e}")


class EconomicsCollector(BaseCollector):
    """
    单位经济数据采集器

    从 unit_economics.py 模块采集：
        - CostEntry（成本条目）
        - RevenueEntry（收入条目）
        - UnitEconomicsSnapshot（单位经济快照）
        - ChannelEconomics（渠道经济分析）
    """

    @property
    def source_name(self) -> str:
        return "economics"

    def collect(self) -> DataSource[DataRecord]:
        """采集单位经济模块的所有数据"""
        self._start_timer()
        errors: list[str] = []

        try:
            from app.routers.unit_economics import (
                COST_ENTRIES,
                REVENUE_ENTRIES,
                SNAPSHOTS,
                CHANNEL_ECONOMICS,
            )
        except ImportError as e:
            errors.append(f"无法导入 unit_economics 模块: {e}")
            return self._make_result([], errors=errors)

        records: list[DataRecord] = []
        self._collect_cost_entries(COST_ENTRIES, records, errors)
        self._collect_revenue_entries(REVENUE_ENTRIES, records, errors)
        self._collect_snapshots(SNAPSHOTS, records, errors)
        self._collect_channel_economics(CHANNEL_ECONOMICS, records, errors)

        return self._make_result(records, errors=errors or None)

    # ------------------------------------------------------------------
    # 子方法
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_cost_entries(entries, records, errors):
        try:
            for c in entries:
                records.append(DataRecord(
                    id=c.id, source="economics", record_type="cost_entry",
                    data={
                        "name": c.name, "category": c.category,
                        "amount": c.amount, "period": c.period,
                        "description": c.description,
                    },
                ))
        except Exception as e:
            errors.append(f"CostEntry 采集失败: {e}")

    @staticmethod
    def _collect_revenue_entries(entries, records, errors):
        try:
            for r in entries:
                records.append(DataRecord(
                    id=r.id, source="economics", record_type="revenue_entry",
                    data={
                        "customer_id": r.customer_id, "customer_name": r.customer_name,
                        "plan": r.plan, "revenue": r.revenue,
                        "period": r.period, "acquisition_channel": r.acquisition_channel,
                        "contract_months": r.contract_months,
                    },
                ))
        except Exception as e:
            errors.append(f"RevenueEntry 采集失败: {e}")

    @staticmethod
    def _collect_snapshots(snapshots, records, errors):
        try:
            for s in snapshots:
                records.append(DataRecord(
                    id=s.id, source="economics", record_type="economics_snapshot",
                    data={
                        "period": s.period, "cac": s.cac, "ltv": s.ltv,
                        "ltv_cac_ratio": s.ltv_cac_ratio,
                        "avg_revenue_per_customer": s.avg_revenue_per_customer,
                        "avg_gross_margin": s.avg_gross_margin,
                        "payback_months": s.payback_months,
                        "new_customers": s.new_customers,
                        "churned_customers": s.churned_customers,
                        "total_active_customers": s.total_active_customers,
                    },
                ))
        except Exception as e:
            errors.append(f"Snapshot 采集失败: {e}")

    @staticmethod
    def _collect_channel_economics(channels, records, errors):
        try:
            for ch in channels:
                records.append(DataRecord(
                    id=None, source="economics", record_type="channel_economics",
                    data={
                        "channel": ch.channel, "period": ch.period,
                        "spend": ch.spend, "leads": ch.leads,
                        "conversions": ch.conversions, "cac": ch.cac,
                        "revenue_from_channel": ch.revenue_from_channel, "roi": ch.roi,
                    },
                ))
        except Exception as e:
            errors.append(f"ChannelEconomics 采集失败: {e}")


class HypothesisCollector(BaseCollector):
    """
    假设验证数据采集器

    从 hypothesis_gate.py 模块采集：
        - Hypothesis（商业假设）
        - ExperimentDesign（实验设计）
    """

    @property
    def source_name(self) -> str:
        return "hypothesis"

    def collect(self) -> DataSource[DataRecord]:
        """采集假设验证模块的所有数据"""
        self._start_timer()
        errors: list[str] = []

        try:
            from app.routers.hypothesis_gate import HYPOTHESES, EXPERIMENTS
        except ImportError as e:
            errors.append(f"无法导入 hypothesis_gate 模块: {e}")
            return self._make_result([], errors=errors)

        records: list[DataRecord] = []

        try:
            for h in HYPOTHESES:
                records.append(DataRecord(
                    id=h.id,
                    source="hypothesis",
                    record_type="hypothesis",
                    data={
                        "title": h.title,
                        "description": h.description,
                        "category": h.category,
                        "assumptions": h.assumptions,
                        "evidence_level": h.evidence_level,
                        "risk_score": h.risk_score,
                        "status": h.status,
                        "tags": h.tags,
                        "created_at": h.created_at,
                    },
                ))
        except Exception as e:
            errors.append(f"Hypothesis 采集失败: {e}")

        try:
            for exp in EXPERIMENTS:
                records.append(DataRecord(
                    id=exp.id,
                    source="hypothesis",
                    record_type="experiment",
                    data={
                        "hypothesis_id": exp.hypothesis_id,
                        "name": exp.name,
                        "method": exp.method,
                        "sample_size": exp.sample_size,
                        "success_criteria": exp.success_criteria,
                        "duration_days": exp.duration_days,
                        "variables": exp.variables,
                        "created_at": exp.created_at,
                    },
                ))
        except Exception as e:
            errors.append(f"Experiment 采集失败: {e}")

        return self._make_result(records, errors=errors or None)


# ---------------------------------------------------------------------------
# 采集器注册表 & 工厂
# ---------------------------------------------------------------------------

_COLLECTOR_REGISTRY: dict[str, type[BaseCollector]] = {
    "retention": RetentionCollector,
    "learning": LearningCollector,
    "economics": EconomicsCollector,
    "hypothesis": HypothesisCollector,
}


def get_collector(name: str, config: Optional[CollectorConfig] = None) -> BaseCollector:
    """获取指定名称的采集器实例"""
    collector_cls = _COLLECTOR_REGISTRY.get(name)
    if collector_cls is None:
        raise ValueError(
            f"未知采集器: '{name}'。可用采集器: {list(_COLLECTOR_REGISTRY.keys())}"
        )
    return collector_cls(config=config)


def list_available_collectors() -> list[str]:
    """列出所有可用的采集器名称"""
    return list(_COLLECTOR_REGISTRY.keys())


def collect_all(config: Optional[CollectorConfig] = None) -> dict[str, DataSource]:
    """
    采集所有启用的数据源

    Args:
        config: 采集器配置（可选）

    Returns:
        数据源名称 -> DataSource 的映射字典
    """
    cfg = config or CollectorConfig()
    results: dict[str, DataSource] = {}

    enabled_sources = [
        ("retention", cfg.enable_retention_source),
        ("learning", cfg.enable_learning_source),
        ("economics", cfg.enable_economics_source),
        ("hypothesis", cfg.enable_hypothesis_source),
    ]

    for name, enabled in enabled_sources:
        if not enabled:
            logger.info("[collector] 跳过数据源: %s (已禁用)", name)
            continue
        try:
            collector = get_collector(name, config=cfg)
            result = collector.collect()
            results[name] = result
            logger.info(
                "[collector] %s: 采集 %d 条记录, 耗时 %.2fs",
                name, result.total_count, result.elapsed_seconds,
            )
            if result.errors:
                for err in result.errors:
                    logger.warning("[collector] %s 错误: %s", name, err)
        except Exception as e:
            logger.error("[collector] %s 采集异常: %s", name, e)
            results[name] = DataSource(
                name=name,
                records=[],
                error_count=1,
                errors=[str(e)],
            )

    return results
