"""
链客宝 - 审美评估编排器
========================
统筹调度各检查器进行审美评估，整合结果并生成报告。

架构：
1. 使用 UiConsistencyChecker 检查UI一致性
2. 使用 BrandConsistencyChecker 检查品牌一致性
3. 使用 CardDesignEvaluator 评估名片设计质量
4. 使用 ReviewReportGenerator 生成综合报告
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from .ui_checker import UiConsistencyChecker, UiCheckResult
from .brand_checker import BrandConsistencyChecker, BrandCheckResult
from .card_design_evaluator import CardDesignEvaluator, CardDesignScore
from .report_generator import (
    ReviewReportGenerator,
    ReportFormat,
    generate_review_report,
)

logger = logging.getLogger(__name__)


class ScoreLevel(Enum):
    """评分等级"""
    EXCELLENT = 'excellent'
    GOOD = 'good'
    FAIR = 'fair'
    POOR = 'poor'
    FAIL = 'fail'

    @classmethod
    def from_score(cls, score: int) -> 'ScoreLevel':
        """根据分数返回等级"""
        if score >= 90:
            return cls.EXCELLENT
        elif score >= 80:
            return cls.GOOD
        elif score >= 70:
            return cls.FAIR
        elif score >= 60:
            return cls.POOR
        else:
            return cls.FAIL


@dataclass
class ReviewConfig:
    """
    审美评估配置
    """
    # 源码目录
    src_dir: str = 'D:/chainke-full/src'
    # 名片页面目录
    card_dir: str = 'D:/chainke-full/src/pages/business-card'
    # 通用组件目录
    components_dir: str = 'D:/chainke-full/src/components'
    # 是否启用严格模式
    strict_mode: bool = False
    # 是否启用所有检查器
    enable_ui_check: bool = True
    enable_brand_check: bool = True
    enable_card_eval: bool = True
    # 日志级别
    log_level: str = 'INFO'
    # 输出格式
    output_format: str = 'text'

    @classmethod
    def default(cls) -> 'ReviewConfig':
        """返回默认配置"""
        return cls()

    def validate(self) -> list[str]:
        """校验配置有效性"""
        issues: list[str] = []
        src = Path(self.src_dir)
        if not src.exists():
            issues.append(f'源码目录不存在: {self.src_dir}')

        card = Path(self.card_dir)
        if not card.exists():
            issues.append(f'名片目录不存在: {self.card_dir}')

        if self.output_format not in ('dict', 'text', 'markdown', 'json'):
            issues.append(f'不支持的输出格式: {self.output_format}')

        return issues


@dataclass
class ReviewReport:
    """
    审美评估报告

    包含各检查器的结果和综合评分。
    """
    # 元数据
    project_name: str = '链客宝'
    started_at: str = ''
    finished_at: str = ''
    elapsed_seconds: float = 0.0

    # 各检查器结果
    ui_result: Optional[UiCheckResult] = None
    brand_result: Optional[BrandCheckResult] = None
    card_score: Optional[CardDesignScore] = None

    # 综合评分
    overall_score: int = 0
    score_level: ScoreLevel = ScoreLevel.FAIR

    # 状态
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # 原始报告输出
    raw_output: Any = None

    @property
    def success(self) -> bool:
        """评估是否成功完成"""
        return len(self.errors) == 0

    @property
    def has_issues(self) -> bool:
        """是否存在待处理问题"""
        total = 0
        if self.ui_result:
            total += self.ui_result.issue_count
        if self.brand_result:
            total += self.brand_result.issue_count
        return total > 0


# ---------------------------------------------------------------------------
# 审美评估编排器
# ---------------------------------------------------------------------------


class DesignReviewEngine:
    """
    审美评估编排器

    统筹调度审美评估系统各模块，执行完整评估流程。

    使用方式:
        engine = DesignReviewEngine()
        report = engine.run()
        print(f"综合评分: {report.overall_score}")
        print(report.raw_output)

    Args:
        config: 评估配置（可选，使用默认配置）
    """

    def __init__(self, config: Optional[ReviewConfig] = None) -> None:
        self.config = config or ReviewConfig.default()
        self._setup_logging()

        # 检查器实例（延迟初始化）
        self._ui_checker: Optional[UiConsistencyChecker] = None
        self._brand_checker: Optional[BrandConsistencyChecker] = None
        self._card_evaluator: Optional[CardDesignEvaluator] = None

    def _setup_logging(self) -> None:
        """配置日志"""
        level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=level,
            format='[design_review] %(levelname)s %(message)s',
            force=False,
        )

    def _initialize_checkers(self) -> list[str]:
        """
        初始化所有检查器

        Returns:
            初始化过程中的警告列表
        """
        warnings: list[str] = []
        src_dir = self.config.src_dir
        card_dir = self.config.card_dir
        components_dir = self.config.components_dir

        # 验证路径
        for name, path_str in [('src', src_dir), ('card', card_dir), ('components', components_dir)]:
            if not Path(path_str).exists():
                warnings.append(f'{name} 目录不存在: {path_str}')

        if self.config.enable_ui_check:
            try:
                self._ui_checker = UiConsistencyChecker(
                    source_dir=src_dir,
                )
                logger.info("UI一致性检查器初始化完成")
            except Exception as e:
                msg = f'UI一致性检查器初始化失败: {e}'
                warnings.append(msg)
                logger.warning(msg)

        if self.config.enable_brand_check:
            try:
                self._brand_checker = BrandConsistencyChecker(
                    source_dir=src_dir,
                )
                logger.info("品牌一致性检查器初始化完成")
            except Exception as e:
                msg = f'品牌一致性检查器初始化失败: {e}'
                warnings.append(msg)
                logger.warning(msg)

        if self.config.enable_card_eval:
            try:
                self._card_evaluator = CardDesignEvaluator(
                    card_dir=card_dir,
                    components_dir=components_dir,
                )
                logger.info("名片设计评估器初始化完成")
            except Exception as e:
                msg = f'名片设计评估器初始化失败: {e}'
                warnings.append(msg)
                logger.warning(msg)

        return warnings

    # ------------------------------------------------------------------
    # 各阶段执行
    # ------------------------------------------------------------------

    def _run_ui_check(self) -> UiCheckResult:
        """执行UI一致性检查"""
        logger.info("=== 阶段: UI一致性检查 ===")
        if self._ui_checker is None:
            raise RuntimeError('UI一致性检查器未初始化')
        return self._ui_checker.check()

    def _run_brand_check(self) -> BrandCheckResult:
        """执行品牌一致性检查"""
        logger.info("=== 阶段: 品牌一致性检查 ===")
        if self._brand_checker is None:
            raise RuntimeError('品牌一致性检查器未初始化')
        return self._brand_checker.check()

    def _run_card_eval(self) -> CardDesignScore:
        """执行名片设计评估"""
        logger.info("=== 阶段: 名片设计评估 ===")
        if self._card_evaluator is None:
            raise RuntimeError('名片设计评估器未初始化')
        return self._card_evaluator.evaluate()

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def run(self) -> ReviewReport:
        """
        执行完整的审美评估流程

        依次执行：
        1. UI一致性检查（可选）
        2. 品牌一致性检查（可选）
        3. 名片设计评估（可选）
        4. 生成综合报告

        Returns:
            ReviewReport 包含所有检查结果和综合评分
        """
        report = ReviewReport()
        report.started_at = datetime.now().isoformat()
        start_time = time.perf_counter()

        logger.info("====== 链客宝审美评估启动 ======")
        logger.info("源码目录: %s", self.config.src_dir)

        # 配置校验
        config_issues = self.config.validate()
        if config_issues:
            for issue in config_issues:
                logger.warning("配置警告: %s", issue)
                report.warnings.append(issue)
            if self.config.strict_mode:
                report.errors.extend(config_issues)
                report.finished_at = datetime.now().isoformat()
                report.elapsed_seconds = round(time.perf_counter() - start_time, 3)
                return report

        # 初始化检查器
        init_warnings = self._initialize_checkers()
        report.warnings.extend(init_warnings)

        # 阶段1: UI一致性检查
        if self.config.enable_ui_check and self._ui_checker:
            try:
                ui_result = self._run_ui_check()
                report.ui_result = ui_result
                logger.info("UI一致性检查完成: 得分 %d", ui_result.score)
            except Exception as e:
                msg = f'UI一致性检查失败: {e}'
                logger.error(msg)
                report.errors.append(msg)
                if self.config.strict_mode:
                    report.finished_at = datetime.now().isoformat()
                    report.elapsed_seconds = round(time.perf_counter() - start_time, 3)
                    return report
        else:
            logger.info("跳过UI一致性检查")

        # 阶段2: 品牌一致性检查
        if self.config.enable_brand_check and self._brand_checker:
            try:
                brand_result = self._run_brand_check()
                report.brand_result = brand_result
                logger.info("品牌一致性检查完成: 得分 %d", brand_result.score)
            except Exception as e:
                msg = f'品牌一致性检查失败: {e}'
                logger.error(msg)
                report.errors.append(msg)
                if self.config.strict_mode:
                    report.finished_at = datetime.now().isoformat()
                    report.elapsed_seconds = round(time.perf_counter() - start_time, 3)
                    return report
        else:
            logger.info("跳过品牌一致性检查")

        # 阶段3: 名片设计评估
        if self.config.enable_card_eval and self._card_evaluator:
            try:
                card_score = self._run_card_eval()
                report.card_score = card_score
                logger.info("名片设计评估完成: 得分 %d", card_score.overall_score)
            except Exception as e:
                msg = f'名片设计评估失败: {e}'
                logger.error(msg)
                report.errors.append(msg)
                if self.config.strict_mode:
                    report.finished_at = datetime.now().isoformat()
                    report.elapsed_seconds = round(time.perf_counter() - start_time, 3)
                    return report
        else:
            logger.info("跳过名片设计评估")

        # 阶段4: 计算综合评分
        report.overall_score = self._calculate_overall(report)
        report.score_level = ScoreLevel.from_score(report.overall_score)
        logger.info(
            "综合评分: %d (%s)",
            report.overall_score,
            report.score_level.value,
        )

        # 阶段5: 生成报告
        try:
            generator = ReviewReportGenerator(
                project_name=report.project_name,
                ui_result=report.ui_result,
                brand_result=report.brand_result,
                card_score=report.card_score,
            )
            report.raw_output = generator.generate(
                fmt=ReportFormat(self.config.output_format)
                if self.config.output_format != 'json'
                else ReportFormat.TEXT,
            )
            if self.config.output_format == 'json':
                report.raw_output = generator.generate_json()
            logger.info("评估报告生成完成")
        except Exception as e:
            msg = f'报告生成失败: {e}'
            logger.error(msg)
            report.errors.append(msg)

        # 完成
        report.finished_at = datetime.now().isoformat()
        report.elapsed_seconds = round(time.perf_counter() - start_time, 3)

        logger.info(
            "====== 审美评估完成, 耗时 %.2fs, 综合评分 %d ======",
            report.elapsed_seconds,
            report.overall_score,
        )

        return report

    def _calculate_overall(self, report: ReviewReport) -> int:
        """
        计算综合评分

        从各检查器结果计算加权综合评分。
        如果某个检查器未运行，则基于其他可用维度评分。

        Args:
            report: 当前报告（包含各检查器结果）

        Returns:
            综合评分 (0-100)
        """
        has_ui = report.ui_result is not None
        has_brand = report.brand_result is not None
        has_card = report.card_score is not None

        available_count = sum([has_ui, has_brand, has_card])
        if available_count == 0:
            return 0

        total_weight = 0.0
        weighted_score = 0.0

        # 各维度默认权重
        weights = {
            'ui': 0.30,
            'brand': 0.30,
            'card': 0.40,
        }

        if has_ui:
            weighted_score += report.ui_result.score * weights['ui']
            total_weight += weights['ui']

        if has_brand:
            weighted_score += report.brand_result.score * weights['brand']
            total_weight += weights['brand']

        if has_card:
            weighted_score += report.card_score.overall_score * weights['card']
            total_weight += weights['card']

        if total_weight > 0:
            result = int(weighted_score / total_weight)
        else:
            result = 0

        return max(0, min(100, result))

    def run_async(self) -> ReviewReport:
        """
        异步运行占位符

        当前为同步版本，返回与 run() 相同结果。
        后续可接入 Celery 或 asyncio。

        Returns:
            与 run() 相同的报告
        """
        logger.info("[design_review] 异步模式未启用，回退为同步执行")
        return self.run()


# ---------------------------------------------------------------------------
# 便捷入口
# ---------------------------------------------------------------------------


def run_review(
    config: Optional[ReviewConfig] = None,
) -> ReviewReport:
    """
    快速执行审美评估

    Args:
        config: 评估配置（可选）

    Returns:
        评估报告
    """
    engine = DesignReviewEngine(config or ReviewConfig.default())
    return engine.run()


def run_review_simple(src_dir: str = 'src/') -> dict[str, Any]:
    """
    极简方式运行审美评估

    自动检测路径并执行所有检查器，返回结果 dict。

    Args:
        src_dir: 前端源码目录

    Returns:
        评估摘要 dict
    """
    config = ReviewConfig(src_dir=src_dir)
    report = run_review(config)

    return {
        'success': report.success,
        'overall_score': report.overall_score,
        'score_level': report.score_level.value,
        'ui_score': report.ui_result.score if report.ui_result else None,
        'brand_score': report.brand_result.score if report.brand_result else None,
        'card_score': report.card_score.overall_score if report.card_score else None,
        'errors': report.errors,
        'warnings': report.warnings,
        'elapsed_seconds': report.elapsed_seconds,
    }
