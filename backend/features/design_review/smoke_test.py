"""
链客宝 - 审美评估系统 Smoke Test
==================================
快速验证所有模块的导入和基本功能正常。
"""

import json
import os
import sys

# 添加 backend 到路径
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..')
))

# 顶层导入
from backend.features.design_review import (
    DesignReviewEngine,
    ReviewConfig,
    ReviewReport,
    ScoreLevel,
    run_review,
    UiConsistencyChecker,
    BrandConsistencyChecker,
    CardDesignEvaluator,
    ReviewReportGenerator,
    generate_review_report,
    __version__,
    __author__,
)
from backend.features.design_review.report_generator import ReportFormat
from backend.features.design_review.engine import run_review_simple

SRC_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'src'
))
CARD_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..',
    'src', 'pages', 'business-card',
))
COMPONENTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'src', 'components',
))


def test_imports():
    """测试所有模块导入"""
    print("=== 测试模块导入 ===")
    print(f"  ✓ 导入成功 (v{__version__})")
    print(f"  ✓ 作者: {__author__}")
    for cls in [
        DesignReviewEngine, ReviewConfig, ReviewReport, ScoreLevel, run_review,
        UiConsistencyChecker, BrandConsistencyChecker, CardDesignEvaluator,
        ReviewReportGenerator, generate_review_report,
    ]:
        assert cls is not None, f"{cls} 导入失败"
    print("  ✓ 所有关键类导入正确")
    return True


def test_ui_checker():
    """测试 UI 一致性检查器"""
    print("\n=== 测试 UI一致性检查器 ===")
    checker = UiConsistencyChecker(source_dir=SRC_DIR)
    result = checker.check()
    print(f"  ✓ 扫描 {result.total_files_checked} 个文件")
    print(f"  ✓ 总类名数: {result.total_classes_checked}")
    print(f"  ✓ 命名问题: {len(result.component_naming_issues)}")
    print(f"  ✓ 样式问题: {len(result.style_inconsistencies)}")
    print(f"  ✓ 响应式问题: {len(result.responsive_layout_issues)}")
    print(f"  ✓ UI 评分: {result.score}/100")
    assert 0 <= result.score <= 100
    return True


def test_brand_checker():
    """测试品牌一致性检查器"""
    print("\n=== 测试品牌一致性检查器 ===")
    checker = BrandConsistencyChecker(source_dir=SRC_DIR)
    result = checker.check()
    print(f"  ✓ 扫描 {result.total_files_checked} 个文件")
    print(f"  ✓ 颜色品牌一致率: {result.brand_alignment_ratio:.1%}")
    print(f"  ✓ 颜色问题: {len(result.color_issues)}")
    print(f"  ✓ 字体问题: {len(result.font_issues)}")
    print(f"  ✓ 间距问题: {len(result.spacing_issues)}")
    print(f"  ✓ 品牌评分: {result.score}/100")
    assert 0 <= result.score <= 100
    return True


def test_card_evaluator():
    """测试名片设计评估器"""
    print("\n=== 测试名片设计评估器 ===")
    evaluator = CardDesignEvaluator(card_dir=CARD_DIR, components_dir=COMPONENTS_DIR)
    score = evaluator.evaluate()
    print(f"  ✓ 页面结构分: {score.structure_score}/100")
    print(f"  ✓ 字段覆盖分: {score.field_coverage_score}/100")
    print(f"  ✓ 组件架构分: {score.component_score}/100")
    print(f"  ✓ 主题使用分: {score.theme_score}/100")
    print(f"  ✓ 总评分: {score.overall_score}/100")
    if score.structure:
        print(f"  ✓ 相册页面类型: {score.structure.page_types_found or '(未发现)'}")
        print(f"  ✓ 缺失页面类型: {score.structure.page_types_missing or '(无)'}")
    if score.field_coverage:
        print(f"  ✓ 字段覆盖率: {score.field_coverage.coverage_ratio:.0%}")
        print(f"  ✓ 缺失字段: {score.field_coverage.fields_missing or '(无)'}")
    if score.missing_components:
        print(f"  ⚠ 缺失组件: {score.missing_components}")
    assert 0 <= score.overall_score <= 100
    return True


def test_report_generator():
    """测试报告生成器"""
    print("\n=== 测试报告生成器 ===")
    generator = ReviewReportGenerator(project_name='链客宝测试')
    # 设置一些模拟数据
    ui_result = UiConsistencyChecker(source_dir=SRC_DIR).check()
    brand_result = BrandConsistencyChecker(source_dir=SRC_DIR).check()
    card_score = CardDesignEvaluator(card_dir=CARD_DIR, components_dir=COMPONENTS_DIR).evaluate()

    generator.ui_result = ui_result
    generator.brand_result = brand_result
    generator.card_score = card_score

    text_report = generator.generate(fmt=ReportFormat.TEXT)
    assert isinstance(text_report, str) and len(text_report) > 50
    print(f"  ✓ 文本报告 ({len(text_report)} 字符)")

    dict_report = generator.generate(fmt=ReportFormat.DICT)
    assert isinstance(dict_report, dict) and 'overall' in dict_report
    print(f"  ✓ Dict 报告")

    md_report = generator.generate(fmt=ReportFormat.MARKDOWN)
    assert isinstance(md_report, str) and md_report.startswith('#')
    print(f"  ✓ Markdown 报告 ({len(md_report)} 字符)")

    json_str = generator.generate_json()
    json.loads(json_str)  # 验证 JSON 有效
    print(f"  ✓ JSON 报告 ({len(json_str)} 字符)")
    return True


def test_engine():
    """测试编排器"""
    print("\n=== 测试编排器 ===")
    config = ReviewConfig.default()
    engine = DesignReviewEngine(config)
    report = engine.run()

    print(f"  ✓ 耗时: {report.elapsed_seconds:.2f}s")
    print(f"  ✓ 综合评分: {report.overall_score}/100 ({report.score_level.value})")
    print(f"  ✓ 错误数: {len(report.errors)}, 警告数: {len(report.warnings)}")
    if report.ui_result:
        print(f"  ✓ UI评分: {report.ui_result.score}/100")
    if report.brand_result:
        print(f"  ✓ 品牌评分: {report.brand_result.score}/100")
    if report.card_score:
        print(f"  ✓ 名片评分: {report.card_score.overall_score}/100")

    assert 0 <= report.overall_score <= 100
    assert report.raw_output is not None
    return True


def test_run_review_simple():
    """测试便捷入口"""
    print("\n=== 测试便捷入口 ===")
    summary = run_review_simple(src_dir=SRC_DIR)
    print(f"  ✓ 综合评分: {summary['overall_score']}, 等级: {summary['score_level']}")
    print(f"  ✓ UI评分: {summary['ui_score']}, 品牌评分: {summary['brand_score']}, 名片评分: {summary['card_score']}")
    assert summary['overall_score'] is not None
    assert 0 <= summary['overall_score'] <= 100
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("  链客宝 - 审美评估系统 Smoke Test")
    print("=" * 60)
    print()

    tests = [
        ("模块导入", test_imports),
        ("UI一致性检查器", test_ui_checker),
        ("品牌一致性检查器", test_brand_checker),
        ("名片设计评估器", test_card_evaluator),
        ("报告生成器", test_report_generator),
        ("编排器", test_engine),
        ("便捷入口", test_run_review_simple),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  ✅ {name} 通过")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  ❌ {name} 失败: {e}")
            traceback.print_exc()
            failed += 1
        print()

    print("=" * 60)
    print(f"  测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
