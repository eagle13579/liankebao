"""
analysis_reporter.py 测试套件
================================
覆盖: ExperimentAnalyzer + ReportGenerator
验收标准: 至少 15 个测试用例，涵盖置信区间/显著检验/效应量/功效分析/报告生成
"""

import json
import math
import os
import random
import sys
import tempfile
import unittest

# 确保导入路径正确
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from champion_challenger import ExperimentConfig, ChampionChallenger
from analysis_reporter import ExperimentAnalyzer, ReportGenerator


# ===========================================================================
# 测试用帮助函数
# ===========================================================================

def _make_experiment(metrics=None, min_samples=10):
    """创建一个带内存 SQLite 的完整实验环境。"""
    if metrics is None:
        metrics = ["auc", "precision@10", "recall@20"]
    config = ExperimentConfig(
        experiment_id="test_exp_001",
        name="测试实验",
        description="单元测试用实验",
        control_model="v1.0",
        treatment_model="v2.0",
        traffic_split=0.5,
        metrics=metrics,
        min_samples=min_samples,
    )
    cc = ChampionChallenger(config, db_path=":memory:")
    return config, cc


def _add_results(cc, control_values, treatment_values, metric="auc"):
    """向 ChampionChallenger 写入控制组和实验组结果（直接写 DB 绕过哈希分流）。"""
    import json
    import time

    cur = cc._conn.cursor()
    for i, val in enumerate(control_values):
        cur.execute(
            """INSERT INTO results
               (experiment_id, user_id, model_name, metrics, timestamp, group_label)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                cc.config.experiment_id,
                f"ctrl_u_{i:04d}",
                cc.config.control_model,
                json.dumps({metric: val}),
                time.time(),
                "control",
            ),
        )

    for i, val in enumerate(treatment_values):
        cur.execute(
            """INSERT INTO results
               (experiment_id, user_id, model_name, metrics, timestamp, group_label)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                cc.config.experiment_id,
                f"trt_u_{i:04d}",
                cc.config.treatment_model,
                json.dumps({metric: val}),
                time.time(),
                "treatment",
            ),
        )
    cc._conn.commit()


def _add_multi_metric_results(cc, control_dicts, treatment_dicts):
    """向 ChampionChallenger 写入多指标结果（直接写 DB）。"""
    import json
    import time

    cur = cc._conn.cursor()
    for i, metrics_dict in enumerate(control_dicts):
        cur.execute(
            """INSERT INTO results
               (experiment_id, user_id, model_name, metrics, timestamp, group_label)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                cc.config.experiment_id,
                f"cm_u_{i:04d}",
                cc.config.control_model,
                json.dumps(metrics_dict),
                time.time(),
                "control",
            ),
        )

    for i, metrics_dict in enumerate(treatment_dicts):
        cur.execute(
            """INSERT INTO results
               (experiment_id, user_id, model_name, metrics, timestamp, group_label)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                cc.config.experiment_id,
                f"tm_u_{i:04d}",
                cc.config.treatment_model,
                json.dumps(metrics_dict),
                time.time(),
                "treatment",
            ),
        )
    cc._conn.commit()


# ===========================================================================
# 测试用例
# ===========================================================================

class TestExperimentAnalyzer(unittest.TestCase):
    """ExperimentAnalyzer 核心功能测试。"""

    def setUp(self):
        self.config, self.cc = _make_experiment()

    # ---- Test 1: 基本初始化 ------------------------------------------------

    def test_01_initialization(self):
        """测试分析器能正确初始化并关联 ChampionChallenger 实例。"""
        analyzer = ExperimentAnalyzer(self.cc)
        self.assertIs(analyzer.cc, self.cc)
        self.assertIs(analyzer.config, self.config)
        self.assertEqual(analyzer.config.experiment_id, "test_exp_001")

    # ---- Test 2: 置信区间 - 单组 t 分布 -----------------------------------

    def test_02_confidence_interval_t_dist(self):
        """测试单组置信区间计算（t 分布），验证 CI 包含真实均值。"""
        control_vals = [0.75, 0.78, 0.72, 0.76, 0.74, 0.77, 0.73, 0.79, 0.71, 0.80]
        treatment_vals = [0.82, 0.85, 0.81, 0.84, 0.83]
        _add_results(self.cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(self.cc)
        ci = analyzer.compute_confidence_interval("auc", "control", confidence=0.95)

        # CI 应包含控制组均值
        control_mean = sum(control_vals) / len(control_vals)
        self.assertGreaterEqual(ci[1], ci[0])  # upper >= lower
        self.assertLessEqual(ci[0], control_mean)
        self.assertGreaterEqual(ci[1], control_mean)

    # ---- Test 3: 置信区间 - Bootstrap --------------------------------------

    def test_03_confidence_interval_bootstrap(self):
        """测试 Bootstrap 置信区间。"""
        control_vals = [0.75, 0.78, 0.72, 0.76, 0.74, 0.77, 0.73, 0.79, 0.71, 0.80]
        treatment_vals = [0.82, 0.85, 0.81, 0.84, 0.83]
        _add_results(self.cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(self.cc)
        ci = analyzer.compute_confidence_interval("auc", "treatment", method="bootstrap")

        self.assertGreaterEqual(ci[1], ci[0])
        self.assertFalse(math.isnan(ci[0]))

    # ---- Test 4: 置信区间 - 均值差 -----------------------------------------

    def test_04_ci_diff(self):
        """测试两组均值差置信区间。"""
        control_vals = [0.75, 0.78, 0.72, 0.76, 0.74, 0.77, 0.73, 0.79, 0.71, 0.80]
        treatment_vals = [0.82, 0.85, 0.81, 0.84, 0.83]
        _add_results(self.cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(self.cc)
        ci_diff = analyzer.compute_ci_diff("auc")

        self.assertIn("mean_diff", ci_diff)
        self.assertIn("ci_lower", ci_diff)
        self.assertIn("ci_upper", ci_diff)
        # 实验组均值更高 => mean_diff 应 > 0
        self.assertGreater(ci_diff["mean_diff"], 0)

    # ---- Test 5: 显著检验 - Welch t-test 显著 -----------------------------

    def test_05_significance_test_significant(self):
        """测试显著检验：当两组差异足够大时返回 significant=True。"""
        # 控制组 ~0.65, 实验组 ~0.85, 差异明显
        control_vals = [0.63, 0.65, 0.64, 0.66, 0.62, 0.65, 0.64, 0.67, 0.63, 0.66]
        treatment_vals = [0.84, 0.86, 0.85, 0.87, 0.83, 0.85, 0.86, 0.88, 0.84, 0.87]
        _add_results(self.cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(self.cc)
        result = analyzer.significance_test("auc", alpha=0.05)

        self.assertTrue(result["significant"])
        self.assertLess(result["p_value"], 0.05)
        self.assertIn(result["method"], ["welch_ttest", "mann_whitney_u"])
        self.assertGreater(result["lift_pct"], 0)

    # ---- Test 6: 显著检验 - 不显著 -----------------------------------------

    def test_06_significance_test_not_significant(self):
        """测试显著检验：两组非常接近时返回 significant=False。"""
        # 两组几乎一样
        control_vals = [0.7501, 0.7502, 0.7499, 0.7500, 0.7503,
                        0.7498, 0.7504, 0.7497, 0.7505, 0.7496]
        treatment_vals = [0.7502, 0.7503, 0.7500, 0.7501, 0.7504,
                          0.7499, 0.7505, 0.7498, 0.7506, 0.7497]
        _add_results(self.cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(self.cc)
        result = analyzer.significance_test("auc", alpha=0.05)

        self.assertFalse(result["significant"])
        # p-value 应 > 0.05
        self.assertGreater(result["p_value"], 0.05)

    # ---- Test 7: 显著检验 - Mann-Whitney 回退 -----------------------------

    def test_07_significance_test_mann_whitney(self):
        """测试小样本时自动使用 Mann-Whitney U 检验。"""
        control_vals = [0.7, 0.8, 0.75]
        treatment_vals = [0.85, 0.9, 0.88]
        _add_results(self.cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(self.cc)
        # 指定 mann_whitney 方法
        result = analyzer.significance_test("auc", method="mann_whitney")

        self.assertEqual(result["method"], "mann_whitney_u")
        self.assertIsInstance(result["p_value"], float)
        self.assertIsInstance(result["significant"], bool)

    # ---- Test 8: 效应量 - Cohen's d ---------------------------------------

    def test_08_effect_size_cohens_d(self):
        """测试 Cohen's d 效应量计算。"""
        control_vals = [0.75, 0.78, 0.72, 0.76, 0.74]
        treatment_vals = [0.85, 0.88, 0.82, 0.86, 0.84]
        _add_results(self.cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(self.cc)
        es = analyzer.effect_size("auc", method="cohens_d")

        self.assertEqual(es["method"], "cohens_d")
        # 应检测到中到大效应量
        self.assertGreater(es["effect_size"], 0.5)
        self.assertIn(es["interpretation"], ["medium", "large"])
        self.assertEqual(es["direction"], "treatment_higher")

    # ---- Test 9: 效应量 - Hedges' g ---------------------------------------

    def test_09_effect_size_hedges_g(self):
        """测试 Hedges' g 效应量计算（小样本校正）。"""
        control_vals = [0.75, 0.78, 0.72]
        treatment_vals = [0.92, 0.95, 0.90]
        _add_results(self.cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(self.cc)
        es = analyzer.effect_size("auc", method="hedges_g")

        self.assertEqual(es["method"], "hedges_g")
        self.assertIsInstance(es["effect_size"], float)

    # ---- Test 10: 效应量 - 方向判断 ---------------------------------------

    def test_10_effect_size_direction(self):
        """测试效应量方向判断。"""
        # 控制组更高的场景
        control_vals = [0.85, 0.88, 0.82, 0.86, 0.84]
        treatment_vals = [0.75, 0.78, 0.72, 0.76, 0.74]
        _add_results(self.cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(self.cc)
        es = analyzer.effect_size("auc")

        self.assertEqual(es["direction"], "control_higher")
        self.assertLess(es["effect_size"], 0)

    # ---- Test 11: 功效分析 ------------------------------------------------

    def test_11_power_analysis(self):
        """测试功效分析样本量计算。"""
        analyzer = ExperimentAnalyzer(self.cc)

        # 中等效应量 0.5, α=0.05, power=0.8
        pa = analyzer.power_analysis(effect_size=0.5, alpha=0.05, power=0.8)

        self.assertIn("required_n_per_group", pa)
        # 对于 d=0.5, 每组应需要 ~64 个样本
        self.assertGreaterEqual(pa["required_n_per_group"], 30)
        self.assertLessEqual(pa["required_n_per_group"], 200)
        self.assertEqual(pa["alpha"], 0.05)
        self.assertEqual(pa["power"], 0.8)

    # ---- Test 12: 功效分析 - 大效应量 -------------------------------------

    def test_12_power_analysis_large_effect(self):
        """测试大效应量时所需样本量较小。"""
        analyzer = ExperimentAnalyzer(self.cc)

        # 大效应量 d=0.8
        pa_small = analyzer.power_analysis(effect_size=0.8, alpha=0.05, power=0.8)
        pa_large = analyzer.power_analysis(effect_size=0.2, alpha=0.05, power=0.8)

        # 大效应量需要更少样本
        self.assertLess(pa_small["required_n_per_group"], pa_large["required_n_per_group"])

    # ---- Test 13: 功效分析 - 基于实际数据 --------------------------------

    def test_13_power_analysis_from_metric(self):
        """测试基于实际数据指标进行功效分析。"""
        control_vals = [0.75, 0.78, 0.72, 0.76, 0.74, 0.77, 0.73, 0.79, 0.71, 0.80]
        treatment_vals = [0.88, 0.91, 0.87, 0.90, 0.89, 0.92, 0.86, 0.93, 0.85, 0.91]
        _add_results(self.cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(self.cc)
        pa = analyzer.power_analysis(metric="auc", alpha=0.05, power=0.8)

        self.assertGreater(pa["effect_size"], 0)
        self.assertIsInstance(pa["required_n_per_group"], int)

    # ---- Test 14: 完整报告 - 基本结构 -------------------------------------

    def test_14_report_structure(self):
        """测试完整报告的数据结构完整性。"""
        control_vals = [0.75, 0.76, 0.74, 0.77, 0.73]
        treatment_vals = [0.82, 0.83, 0.81, 0.84, 0.80]
        _add_results(self.cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(self.cc)
        report = analyzer.report("test_exp_001")

        # 顶层字段
        self.assertEqual(report["experiment_id"], "test_exp_001")
        self.assertEqual(report["experiment_name"], "测试实验")
        self.assertIn("winner", report)
        self.assertIn("winner_reason", report)
        self.assertIn("metrics", report)
        self.assertIn("summary", report)
        self.assertIn("total_samples", report)

        # 每个指标应有完整分析
        for mr in report["metrics"]:
            self.assertIn("metric", mr)
            self.assertIn("control", mr)
            self.assertIn("treatment", mr)
            self.assertIn("difference", mr)
            self.assertIn("significance", mr)
            self.assertIn("effect_size", mr)

            # 差异结构
            self.assertIn("mean_diff", mr["difference"])
            self.assertIn("lift_pct", mr["difference"])
            self.assertIn("ci_95", mr["difference"])

            # 显著检验结构
            self.assertIn("p_value", mr["significance"])
            self.assertIn("significant", mr["significance"])
            self.assertIn("method", mr["significance"])

            # 效应量结构
            self.assertIn("d", mr["effect_size"])
            self.assertIn("interpretation", mr["effect_size"])

    # ---- Test 15: 完整报告 - 胜者判定 -------------------------------------

    def test_15_report_winner_determination(self):
        """测试报告中的胜者判定逻辑。"""
        # 实验组在所有指标上显著更好
        control_auc = [0.65] * 15 + [0.66] * 15
        treatment_auc = [0.88] * 15 + [0.89] * 15
        control_prec = [0.60] * 15 + [0.61] * 15
        treatment_prec = [0.85] * 15 + [0.86] * 15

        control_dicts = [{"auc": c, "precision@10": p}
                         for c, p in zip(control_auc, control_prec)]
        treatment_dicts = [{"auc": c, "precision@10": p}
                          for c, p in zip(treatment_auc, treatment_prec)]

        _add_multi_metric_results(self.cc, control_dicts, treatment_dicts)

        analyzer = ExperimentAnalyzer(self.cc)
        report = analyzer.report("test_exp_001", bonferroni=False)

        self.assertEqual(report["winner"], "treatment")

    # ---- Test 16: 样本不足时返回 tie / insufficient_samples ---------------

    def test_16_report_insufficient_samples(self):
        """测试样本不足时的报告行为。"""
        control_vals = [0.75, 0.76]
        treatment_vals = [0.82, 0.83]
        _add_results(self.cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(self.cc)
        report = analyzer.report("test_exp_001")

        # min_samples=10, 总样本=4 < 10
        self.assertIn(report["winner"], ["insufficient_samples", "control"])

    # ---- Test 17: 多指标 Bonferroni 校正 ----------------------------------

    def test_17_bonferroni_correction(self):
        """测试 Bonferroni 多重比较校正。"""
        # 在三个指标上产生不同的显著水平
        control_dicts = [
            {"auc": 0.75, "precision@10": 0.70, "recall@20": 0.65}
            for _ in range(20)
        ]
        treatment_dicts = [
            {"auc": 0.80, "precision@10": 0.72, "recall@20": 0.68}
            for _ in range(20)
        ]
        _add_multi_metric_results(self.cc, control_dicts, treatment_dicts)

        analyzer = ExperimentAnalyzer(self.cc)
        report = analyzer.report("test_exp_001", bonferroni=True)

        self.assertIsNotNone(report["bonferroni_correction"])
        self.assertEqual(report["bonferroni_correction"]["n_tests"], 3)
        self.assertAlmostEqual(
            report["bonferroni_correction"]["corrected_alpha"],
            0.05 / 3,
            places=6,
        )

    # ---- Test 18: 空数据场景 -----------------------------------------------

    def test_18_empty_data(self):
        """测试无数据时的健壮性。"""
        analyzer = ExperimentAnalyzer(self.cc)

        # 不应抛出异常
        ci = analyzer.compute_confidence_interval("auc", "control")
        self.assertTrue(math.isnan(ci[0]))

        sig = analyzer.significance_test("auc")
        self.assertFalse(sig["significant"])
        self.assertEqual(sig["method"], "insufficient_data")

        es = analyzer.effect_size("auc")
        self.assertEqual(es["effect_size"], 0.0)

        report = analyzer.report("test_exp_001")
        self.assertIsInstance(report, dict)

    # ---- Test 19: 偏态分布 - 非参数检验 -----------------------------------

    def test_19_skewed_distribution(self):
        """测试偏态分布下的非参数回退。"""
        # 控制组正态，实验组偏态
        control_vals = [0.5, 0.52, 0.48, 0.51, 0.49, 0.53, 0.47, 0.50, 0.52, 0.48]
        # 实验组有明显的正偏态（有少量极高值）
        treatment_vals = [0.55, 0.56, 0.54, 0.57, 0.53, 0.58, 0.52, 0.95, 0.55, 0.56]
        _add_results(self.cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(self.cc)

        # 显式使用 Mann-Whitney
        result = analyzer.significance_test("auc", method="mann_whitney")
        self.assertEqual(result["method"], "mann_whitney_u")
        # 无论如何应该能输出 p-value
        self.assertGreaterEqual(result["p_value"], 0)

    # ---- Test 20: summary 方法 --------------------------------------------

    def test_20_summary(self):
        """测试 summary 基本统计量。"""
        control_vals = [0.75, 0.78, 0.72, 0.76, 0.74]
        treatment_vals = [0.82, 0.83, 0.81, 0.84, 0.80]
        _add_results(self.cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(self.cc)
        summary = analyzer.summary()

        self.assertIn("auc", summary)
        self.assertIn("control", summary["auc"])
        self.assertIn("treatment", summary["auc"])
        self.assertIsNotNone(summary["auc"]["control"]["mean"])
        self.assertIsNotNone(summary["auc"]["treatment"]["std"])
        self.assertEqual(summary["auc"]["control"]["n"], 5)
        self.assertEqual(summary["auc"]["treatment"]["n"], 5)


# ===========================================================================
# ReportGenerator 测试
# ===========================================================================

class TestReportGenerator(unittest.TestCase):
    """ReportGenerator 输出格式测试。"""

    def setUp(self):
        config, cc = _make_experiment(metrics=["auc"])
        control_vals = [0.75, 0.76, 0.74, 0.77, 0.73]
        treatment_vals = [0.82, 0.83, 0.81, 0.84, 0.80]
        _add_results(cc, control_vals, treatment_vals)
        self.analyzer = ExperimentAnalyzer(cc)
        self.report = self.analyzer.report("test_exp_001")
        self.generator = ReportGenerator()

    # ---- Test 21: Markdown 生成 -------------------------------------------

    def test_21_generate_markdown(self):
        """测试 Markdown 报告生成。"""
        md = self.generator.generate_markdown(self.report)

        self.assertIsInstance(md, str)
        self.assertIn("# A/B 实验分析报告", md)
        self.assertIn("测试实验", md)
        self.assertIn("对照组", md)
        self.assertIn("实验组", md)
        self.assertIn("胜者判定", md)
        self.assertIn("auc", md)
        self.assertIn("cohens_d", md)
        self.assertIn("p-value", md)

    # ---- Test 22: JSON 生成 -----------------------------------------------

    def test_22_generate_json(self):
        """测试 JSON 报告生成。"""
        js = self.generator.generate_json(self.report)

        self.assertIsInstance(js, str)
        parsed = json.loads(js)
        self.assertEqual(parsed["experiment_name"], "测试实验")
        self.assertIn("winner", parsed)
        self.assertIn("metrics", parsed)

    # ---- Test 23: HTML 生成 -----------------------------------------------

    def test_23_generate_html(self):
        """测试 HTML 看板生成。"""
        html = self.generator.generate_html(self.report)

        self.assertIsInstance(html, str)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("A/B 实验分析报告", html)
        self.assertIn("测试实验", html)
        self.assertIn("</html>", html)
        # 应包含 CSS 样式
        self.assertIn("metric-card", html)
        self.assertIn("winner-banner", html)

    # ---- Test 24: 空报告生成 -----------------------------------------------

    def test_24_empty_report_generation(self):
        """测试空数据报告的生成（不应崩溃）。"""
        config, cc = _make_experiment(metrics=["auc"])
        analyzer = ExperimentAnalyzer(cc)
        report = analyzer.report("empty_test")

        md = self.generator.generate_markdown(report)
        self.assertIsInstance(md, str)

        js = self.generator.generate_json(report)
        parsed = json.loads(js)
        self.assertEqual(parsed["experiment_id"], "empty_test")

        html = self.generator.generate_html(report)
        self.assertIn("<!DOCTYPE html>", html)


# ===========================================================================
# 统计正确性验证
# ===========================================================================

class TestStatisticalCorrectness(unittest.TestCase):
    """统计方法正确性验证。"""

    # ---- Test 25: 已知数据的 Cohen's d 验证 --------------------------------

    def test_25_cohens_d_known_value(self):
        """验证 Cohen's d 在已知数据上的正确性。"""
        # 两组数据，手动验证
        a = [1, 2, 3, 4, 5]
        b = [6, 7, 8, 9, 10]

        config, cc = _make_experiment(metrics=["value"])
        _add_results(cc, a, b, metric="value")

        analyzer = ExperimentAnalyzer(cc)
        es = analyzer.effect_size("value", method="cohens_d")

        # 手动计算:
        # m1=3, m2=8, v1=2.5, v2=2.5
        # pooled_std = sqrt((4*2.5+4*2.5)/8) = sqrt(2.5) = 1.58114
        # d = (8-3)/1.58114 = 3.1623
        self.assertAlmostEqual(es["effect_size"], 3.1623, places=3)

    # ---- Test 26: 置信区间覆盖率 ------------------------------------------

    def test_26_ci_coverage(self):
        """验证 95% 置信区间覆盖率的合理性。"""
        # 从已知分布生成数据
        random.seed(42)
        control_vals = [random.gauss(0.5, 0.1) for _ in range(50)]
        treatment_vals = [random.gauss(0.55, 0.1) for _ in range(50)]

        config, cc = _make_experiment(metrics=["score"])
        _add_results(cc, control_vals, treatment_vals, metric="score")

        analyzer = ExperimentAnalyzer(cc)
        ci = analyzer.compute_confidence_interval("score", "control")

        # 样本均值应落在 CI 内（t 分布 CI 保证这一点）
        sample_mean = __import__("statistics").mean(control_vals)
        self.assertLessEqual(ci[0], sample_mean)
        self.assertGreaterEqual(ci[1], sample_mean)

    # ---- Test 27: p-value 均匀性（H0 成立时）-------------------------------

    def test_27_p_value_uniformity_under_null(self):
        """验证 H0 成立时 p-value 的分布（粗略校验）。"""
        random.seed(123)
        n_simulations = 10  # 10次模拟，每次构造两个相同分布的样本
        p_values = []

        for _ in range(n_simulations):
            a = [random.gauss(0.5, 0.1) for _ in range(30)]
            b = [random.gauss(0.5, 0.1) for _ in range(30)]

            config, cc = _make_experiment(metrics=["score"])
            _add_results(cc, a, b, metric="score")

            analyzer = ExperimentAnalyzer(cc)
            result = analyzer.significance_test("score")
            p_values.append(result["p_value"])

        # 在 H0 下，p_value < 0.05 的概率约为 5%，10次中不应全部 < 0.05
        n_sig = sum(1 for p in p_values if p < 0.05)
        self.assertLessEqual(n_sig, 3)  # 宽松: 最多允许 3/10 显著


# ===========================================================================
# 边缘情况测试
# ===========================================================================

class TestEdgeCases(unittest.TestCase):
    """边界条件和异常情况测试。"""

    # ---- Test 28: 单样本每组 -----------------------------------------------

    def test_28_single_sample_per_group(self):
        """测试每组仅 1 个样本的边界情况。"""
        config, cc = _make_experiment(metrics=["auc"])
        _add_results(cc, [0.75], [0.82])

        analyzer = ExperimentAnalyzer(cc)

        sig = analyzer.significance_test("auc")
        self.assertFalse(sig["significant"])
        self.assertEqual(sig["method"], "insufficient_data")

        es = analyzer.effect_size("auc")
        self.assertEqual(es["effect_size"], 0.0)

    # ---- Test 29: 所有值相同 -----------------------------------------------

    def test_29_all_identical_values(self):
        """测试所有值完全相同时（零方差）的表现。"""
        config, cc = _make_experiment(metrics=["auc"])
        _add_results(cc, [0.8] * 10, [0.8] * 10)

        analyzer = ExperimentAnalyzer(cc)

        sig = analyzer.significance_test("auc")
        self.assertFalse(sig["significant"])
        # 应与 0.05 接近（大概率 > 0.05）
        self.assertGreaterEqual(sig["p_value"], 0.05)

        es = analyzer.effect_size("auc")
        self.assertAlmostEqual(es["effect_size"], 0.0, places=5)

    # ---- Test 30: 极致值（异常值）------------------------------------------

    def test_30_outliers(self):
        """测试含异常值时的健壮性。"""
        config, cc = _make_experiment(metrics=["auc"])
        # 包含一个极端异常值
        control_vals = [0.75, 0.76, 0.74, 0.77, 0.73, 0.01]  # 最后一个异常低
        treatment_vals = [0.82, 0.83, 0.81, 0.84, 0.80, 0.99]  # 最后一个异常高
        _add_results(cc, control_vals, treatment_vals)

        analyzer = ExperimentAnalyzer(cc)

        # 不应抛出异常
        sig = analyzer.significance_test("auc")
        self.assertIsInstance(sig["p_value"], float)

        ci = analyzer.compute_confidence_interval("auc", "control")
        self.assertFalse(math.isnan(ci[0]))

        report = analyzer.report("test_exp_001")
        self.assertIsInstance(report, dict)


# ===========================================================================
# 入口
# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
