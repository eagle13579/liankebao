"""
创新发现引擎 — Smoke Test
========================
快速验证模块导入和基本运行正常。
执行：python -m pytest tests/test_innovation_engine.py -v
或：python tests/test_innovation_engine.py
"""

import sys
from pathlib import Path

# 添加 backend 目录到 Python 路径
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from features.innovation_engine import (
    ActionStep,
    EngineConfig,
    EngineResult,
    InnovationEngine,
    MOCK_ENTERPRISES,
    MOCK_MATCHING_EVENTS,
    MOCK_NEEDS,
    MOCK_SEARCHES,
    OpportunityRecommender,
    OpportunityScanner,
    OpportunitySignal,
    PipelineStage,
    RecommendationReport,
    RecommendedOpportunity,
    ScanResult,
    TrendAnalyzer,
    TrendInsight,
    TrendReport,
)


def test_module_imports() -> None:
    """验证所有模块可正常导入"""
    # 验证所有导入的对象都是正确的类型
    assert InnovationEngine is not None
    assert OpportunityScanner is not None
    assert TrendAnalyzer is not None
    assert OpportunityRecommender is not None

    # 验证数据类型
    assert OpportunitySignal is not None
    assert ScanResult is not None
    assert TrendInsight is not None
    assert TrendReport is not None
    assert RecommendedOpportunity is not None
    assert RecommendationReport is not None
    assert ActionStep is not None
    assert EngineConfig is not None
    assert EngineResult is not None
    assert PipelineStage is not None

    # 验证模拟数据存在
    assert len(MOCK_NEEDS) > 0
    assert len(MOCK_MATCHING_EVENTS) > 0
    assert len(MOCK_SEARCHES) > 0
    assert len(MOCK_ENTERPRISES) > 0

    print("[PASS] 所有模块导入成功")


def test_opportunity_scanner() -> None:
    """验证扫描器各项功能"""
    scanner = OpportunityScanner()

    # 测试未满足需求扫描
    result = scanner.scan_unmet_needs()
    assert result.success
    assert isinstance(result.signals, list)
    for sig in result.signals:
        assert sig.signal_type == "unmet_need"
        assert sig.signal_id.startswith("unmet_")
    print(f"  unmet_needs: {len(result.signals)} 条信号")

    # 测试匹配失败扫描
    result = scanner.scan_match_failures()
    assert result.success
    for sig in result.signals:
        assert sig.signal_type == "match_failure"
        assert sig.signal_id.startswith("match_")
    print(f"  match_failures: {len(result.signals)} 条信号")

    # 测试搜索真空扫描
    result = scanner.scan_search_voids()
    assert result.success
    for sig in result.signals:
        assert sig.signal_type == "search_void"
        assert sig.signal_id.startswith("void_")
    print(f"  search_voids: {len(result.signals)} 条信号")

    # 测试全量扫描
    result = scanner.scan_all()
    assert result.success
    assert result.total_signals > 0
    assert result.scanner_name == "opportunity_scanner.scan_all"
    print(f"  scan_all: {result.total_signals} 条信号合计")

    print("[PASS] 机会扫描器工作正常")


def test_trend_analyzer() -> None:
    """验证趋势分析器各项功能"""
    scanner = OpportunityScanner()
    analyzer = TrendAnalyzer()

    scan_result = scanner.scan_all()

    # 测试基于信号的分析
    report = analyzer.analyze_signals(scan_result)
    assert report.success
    print(f"  趋势洞察: {report.total_insights} 条")
    for ins in report.insights:
        assert ins.insight_id
        assert ins.title
        assert ins.description

    # 测试品类热度分析
    heat_report = analyzer.analyze_category_heat(
        signals=scan_result.signals,
        needs=None,
        searches=None,
    )
    assert heat_report.success
    if heat_report.insights:
        top = heat_report.insights[0]
        assert "heat_score" in top.metrics
        assert top.metrics["heat_score"] > 0
    print(f"  品类热度: {len(heat_report.insights)} 条")

    # 测试供需缺口分析
    gap_report = analyzer.analyze_supply_demand_gap(
        signals=scan_result.signals
    )
    assert gap_report.success
    if gap_report.insights:
        top = gap_report.insights[0]
        assert "gap_score" in top.metrics
    print(f"  供需缺口: {len(gap_report.insights)} 条")

    # 测试完整分析
    full_report = analyzer.analyze_full(scan_result=scan_result)
    assert full_report.success
    assert full_report.summary
    print(f"  完整分析: {full_report.total_insights} 条")

    print("[PASS] 趋势分析器工作正常")


def test_recommender() -> None:
    """验证推荐器各项功能"""
    scanner = OpportunityScanner()
    analyzer = TrendAnalyzer()
    recommender = OpportunityRecommender()

    scan_result = scanner.scan_all()
    trend_report = analyzer.analyze_signals(scan_result)

    # 测试去重
    deduped = recommender.deduplicate_and_merge(scan_result.signals)
    assert len(deduped) <= len(scan_result.signals)
    print(f"  去重: {len(scan_result.signals)} -> {len(deduped)}")

    # 测试评分
    if scan_result.signals:
        sig = scan_result.signals[0]
        score = recommender.score_opportunity(sig)
        assert 0 <= score <= 100
        print(f"  评分示例: {sig.title[:20]}... = {score}")

    # 测试基于信号的推荐
    report = recommender.recommend_from_signals(scan_result)
    assert report.success
    assert report.total_opportunities > 0
    print(f"  推荐机会: {report.total_opportunities} 个")

    # 验证推荐的内容完整性
    if report.opportunities:
        opp = report.opportunities[0]
        assert opp.opportunity_id.startswith("opp_")
        assert opp.score > 0
        assert opp.action_steps
        assert opp.priority in ("高", "中", "低")
        print(f"  最优机会: {opp.title} (评分: {opp.score}, 优先级: {opp.priority})")
        print(f"  操作步骤: {len(opp.action_steps)} 个")

    # 测试完整推荐（含趋势分析）
    full_report = recommender.recommend_full(
        scan_result=scan_result,
        trend_report=trend_report,
    )
    assert full_report.success
    assert full_report.summary
    print(f"  完整推荐: {full_report.total_opportunities} 个")

    print("[PASS] 机会推荐器工作正常")


def test_engine_full_pipeline() -> None:
    """验证引擎完整管道运行"""
    engine = InnovationEngine()
    result = engine.run()

    # 验证结果结构
    assert result.success, f"引擎运行失败: {result.error}"
    assert result.run_at
    assert result.total_elapsed_seconds >= 0

    # 验证各阶段
    stage_names = [s.name for s in result.stages]
    assert "scan" in stage_names
    assert "analyze" in stage_names
    assert "recommend" in stage_names

    for stage in result.stages:
        assert stage.success, f"阶段 {stage.name} 失败: {stage.error}"
        assert stage.elapsed_seconds >= 0

    # 验证输出数据
    assert result.scan_result is not None
    assert result.scan_result.total_signals > 0
    assert result.trend_report is not None
    assert result.trend_report.total_insights > 0
    assert result.recommendation is not None
    assert result.recommendation.total_opportunities > 0

    # 验证推荐排序
    opps = result.recommendation.opportunities
    for i in range(len(opps) - 1):
        assert opps[i].score >= opps[i + 1].score, "推荐未按评分降序排列"

    print(f"  阶段: {', '.join(stage_names)}")
    print(f"  信号: {result.scan_result.total_signals}")
    print(f"  洞察: {result.trend_report.total_insights}")
    print(f"  推荐: {result.recommendation.total_opportunities}")
    print(f"  总耗时: {result.total_elapsed_seconds}s")

    # 打印 Top 3 推荐
    print("  Top 推荐:")
    for opp in result.recommendation.opportunities[:3]:
        print(f"    [{opp.priority}] {opp.title} (评分: {opp.score})")

    print("[PASS] 引擎完整管道运行正常")


def test_custom_data() -> None:
    """验证使用自定义数据运行"""
    engine = InnovationEngine()

    custom_needs = [
        {
            "id": "test_001",
            "enterprise_name": "测试企业",
            "title": "寻找量子计算服务商",
            "category": "前沿科技",
            "status": "unmatched",
            "created_at": "2026-06-01T00:00:00Z",
            "days_unmatched": 10,
            "urgency": "high",
            "budget_range": "500万以上",
        }
    ]

    custom_searches = [
        {
            "id": "test_s_001",
            "keyword": "量子计算云平台",
            "category": "前沿科技",
            "search_count": 100,
            "result_count": 0,
            "last_searched_at": "2026-06-07T00:00:00Z",
            "user_segments": ["科研机构", "金融"],
        }
    ]

    result = engine.run(
        needs=custom_needs,
        searches=custom_searches,
    )

    assert result.success
    assert result.recommendation is not None
    assert result.recommendation.total_opportunities > 0

    # 验证自定义数据出现在推荐中
    titles = [opp.title for opp in result.recommendation.opportunities]
    has_custom = any("量子" in t for t in titles)
    assert has_custom, "自定义数据应出现在推荐结果中"

    print("[PASS] 自定义数据运行正常")


def test_error_handling() -> None:
    """验证错误处理"""
    scanner = OpportunityScanner()

    # 传入异常数据
    bad_data = [{"id": "bad", "category": "测试"}]
    result = scanner.scan_unmet_needs(needs=bad_data)
    assert result.success  # 应优雅处理，不崩溃
    assert isinstance(result.signals, list)

    # 空数据
    result = scanner.scan_unmet_needs(needs=[])
    assert result.success
    assert len(result.signals) == 0

    # 验证 ScanResult 错误状态
    result_with_errors = ScanResult(
        scanner_name="test",
        errors=["模拟错误1", "模拟错误2"],
    )
    assert not result_with_errors.success
    assert len(result_with_errors.errors) == 2

    print("[PASS] 错误处理正常")


if __name__ == "__main__":
    print("=" * 50)
    print("创新发现引擎 Smoke Test")
    print("=" * 50)

    tests = [
        ("模块导入", test_module_imports),
        ("机会扫描器", test_opportunity_scanner),
        ("趋势分析器", test_trend_analyzer),
        ("机会推荐器", test_recommender),
        ("引擎完整管道", test_engine_full_pipeline),
        ("自定义数据", test_custom_data),
        ("错误处理", test_error_handling),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        print(f"\n▶  测试: {name}")
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 50)
    print(f"结果: {passed} 通过, {failed} 失败 / 共 {len(tests)} 项")
    print("=" * 50)

    sys.exit(0 if failed == 0 else 1)
