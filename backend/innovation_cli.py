#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
由 Feature 总线适配器引擎 v0.1 自动生成
源: FastAPI Router (router)
路由数: 16
"""

import argparse
import importlib
import json
import sys
import os
from pathlib import Path
from typing import Any

# 源模块导入
try:
    # 尝试直接导入（如果模块在 sys.path 中）
    source_module = importlib.import_module('innovation_engine')
except ImportError:
    # 尝试通过文件路径导入
    spec = importlib.util.spec_from_file_location('innovation_engine', r'D:\\链客宝\\backend\\innovation_engine.py')
    source_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(source_module)

def _error_exit(status_code: int, detail: str):
    """输出错误并退出。"""
    print(json.dumps({"code": status_code, "message": detail, "data": None}, ensure_ascii=False))
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# CLI 处理函数
# ═══════════════════════════════════════════════════════════════

def cmd_create_hypothesis(args):
    """创建新假设"""
    # 构建函数调用参数
    call_kwargs = {}
    # 请求体: HypothesisCreate
    if args.json_input:
        try:
            body_data = json.loads(args.json_input)
        except json.JSONDecodeError as e:
            _error_exit(400, f"JSON 解析失败: {e}")
        call_kwargs["req"] = body_data
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.create_hypothesis(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 create_hypothesis 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_list_hypotheses(args):
    """获取假设列表"""
    # 构建函数调用参数
    call_kwargs = {}
    if hasattr(args, "status") and args.status is not None:
        call_kwargs["status"] = args.status
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.list_hypotheses(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 list_hypotheses 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_get_hypothesis(args):
    """获取假设详情"""
    # 构建函数调用参数
    call_kwargs = {}
    call_kwargs["hypothesis_id"] = args.hypothesis_id
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.get_hypothesis(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 get_hypothesis 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_update_hypothesis(args):
    """更新假设"""
    # 构建函数调用参数
    call_kwargs = {}
    call_kwargs["hypothesis_id"] = args.hypothesis_id
    # 请求体: HypothesisUpdate
    if args.json_input:
        try:
            body_data = json.loads(args.json_input)
        except json.JSONDecodeError as e:
            _error_exit(400, f"JSON 解析失败: {e}")
        call_kwargs["req"] = body_data
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.update_hypothesis(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 update_hypothesis 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_create_experiment(args):
    """为假设设计实验"""
    # 构建函数调用参数
    call_kwargs = {}
    call_kwargs["hypothesis_id"] = args.hypothesis_id
    # 请求体: ExperimentDesign
    if args.json_input:
        try:
            body_data = json.loads(args.json_input)
        except json.JSONDecodeError as e:
            _error_exit(400, f"JSON 解析失败: {e}")
        call_kwargs["req"] = body_data
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.create_experiment(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 create_experiment 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_list_experiments(args):
    """获取实验列表"""
    # 构建函数调用参数
    call_kwargs = {}
    if hasattr(args, "hypothesis_id") and args.hypothesis_id is not None:
        call_kwargs["hypothesis_id"] = args.hypothesis_id
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.list_experiments(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 list_experiments 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_verify_hypothesis(args):
    """提交验证结果"""
    # 构建函数调用参数
    call_kwargs = {}
    call_kwargs["hypothesis_id"] = args.hypothesis_id
    # 请求体: VerifyResult
    if args.json_input:
        try:
            body_data = json.loads(args.json_input)
        except json.JSONDecodeError as e:
            _error_exit(400, f"JSON 解析失败: {e}")
        call_kwargs["req"] = body_data
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.verify_hypothesis(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 verify_hypothesis 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_gate_check(args):
    """手动触发门禁检查"""
    # 构建函数调用参数
    call_kwargs = {}
    call_kwargs["hypothesis_id"] = args.hypothesis_id
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.gate_check(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 gate_check 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_scan_opportunities(args):
    """执行机会扫描"""
    # 构建函数调用参数
    call_kwargs = {}
    # 请求体: ScanRequest
    if args.json_input:
        try:
            body_data = json.loads(args.json_input)
        except json.JSONDecodeError as e:
            _error_exit(400, f"JSON 解析失败: {e}")
        call_kwargs["req"] = body_data
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.scan_opportunities(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 scan_opportunities 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_analyze_trends(args):
    """执行趋势分析"""
    # 构建函数调用参数
    call_kwargs = {}
    # 请求体: AnalyzeRequest
    if args.json_input:
        try:
            body_data = json.loads(args.json_input)
        except json.JSONDecodeError as e:
            _error_exit(400, f"JSON 解析失败: {e}")
        call_kwargs["req"] = body_data
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.analyze_trends(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 analyze_trends 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_list_opportunities(args):
    """获取推荐机会列表"""
    # 构建函数调用参数
    call_kwargs = {}
    if hasattr(args, "limit") and args.limit is not None:
        call_kwargs["limit"] = args.limit
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.list_opportunities(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 list_opportunities 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_run_full_pipeline(args):
    """执行完整创新引擎管道"""
    # 构建函数调用参数
    call_kwargs = {}
    # 请求体: ScanRequest
    if args.json_input:
        try:
            body_data = json.loads(args.json_input)
        except json.JSONDecodeError as e:
            _error_exit(400, f"JSON 解析失败: {e}")
        call_kwargs["req"] = body_data
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.run_full_pipeline(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 run_full_pipeline 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_get_growth_cycle(args):
    """获取增长周期状态"""
    # 构建函数调用参数
    call_kwargs = {}
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.get_growth_cycle(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 get_growth_cycle 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_switch_growth_cycle(args):
    """切换增长周期阶段"""
    # 构建函数调用参数
    call_kwargs = {}
    if hasattr(args, "phase") and args.phase is not None:
        call_kwargs["phase"] = args.phase
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.switch_growth_cycle(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 switch_growth_cycle 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_get_innovation_metrics(args):
    """获取引擎监控指标"""
    # 构建函数调用参数
    call_kwargs = {}
    # 模拟 DB 会话传入
    call_kwargs["db"] = getattr(args, "db", None)

    # 调用原始函数
    try:
        result = source_module.get_innovation_metrics(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 get_innovation_metrics 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))

def cmd_clear_innovation_cache(args):
    """清除缓存"""
    # 构建函数调用参数
    call_kwargs = {}

    # 调用原始函数
    try:
        result = source_module.clear_innovation_cache(**call_kwargs)
    except Exception as e:
        _error_exit(500, f"调用 clear_innovation_cache 失败: {e}")

    # 输出结果
    print(json.dumps(result, ensure_ascii=False, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="innovation_cli",
        description="FastAPI CLI 适配 — 由 Feature 总线适配器引擎自动生成",
        epilog="由 Feature 总线适配器引擎自动生成",
    )
    parser.add_argument("--db", default="sqlite:///innovation.db",
                        help="数据库连接 (默认: sqlite:///innovation.db)")
    sub = parser.add_subparsers(dest="command", help="子命令")

    # ── POST /hypotheses ──
    p_create_hypothesis = sub.add_parser(
        "create-hypothesis",
        help="创建新假设",
        description="创建新假设",
    )
    p_create_hypothesis.add_argument(
        "--json-input",
        help=f"请求体 JSON. 字段: title:str; description:str; category:HypothesisCategory; evidence_level:EvidenceLevel; risk_score:int",
    )
    p_create_hypothesis.set_defaults(func=cmd_create_hypothesis)

    # ── GET /hypotheses ──
    p_list_hypotheses = sub.add_parser(
        "list-hypotheses",
        help="获取假设列表",
        description="获取假设列表",
    )
    p_list_hypotheses.add_argument(
        "--status",
        help="status (查询参数)",
    )
    p_list_hypotheses.set_defaults(func=cmd_list_hypotheses)

    # ── GET /hypotheses/{hypothesis_id} ──
    p_get_hypothesis = sub.add_parser(
        "get-hypothesis",
        help="获取假设详情",
        description="获取假设详情",
    )
    p_get_hypothesis.add_argument(
        "hypothesis_id",
        help="hypothesis_id (路径参数)",
    )
    p_get_hypothesis.set_defaults(func=cmd_get_hypothesis)

    # ── PUT /hypotheses/{hypothesis_id} ──
    p_update_hypothesis = sub.add_parser(
        "update-hypothesis",
        help="更新假设",
        description="更新假设",
    )
    p_update_hypothesis.add_argument(
        "hypothesis_id",
        help="hypothesis_id (路径参数)",
    )
    p_update_hypothesis.add_argument(
        "--json-input",
        help=f"请求体 JSON. 字段: title:str | None; description:str | None; category:HypothesisCategory | None; evidence_level:EvidenceLevel | None; risk_score:int | None",
    )
    p_update_hypothesis.set_defaults(func=cmd_update_hypothesis)

    # ── POST /hypotheses/{hypothesis_id}/experiments ──
    p_create_experiment = sub.add_parser(
        "create-experiment",
        help="为假设设计实验",
        description="为假设设计实验",
    )
    p_create_experiment.add_argument(
        "hypothesis_id",
        help="hypothesis_id (路径参数)",
    )
    p_create_experiment.add_argument(
        "--json-input",
        help=f"请求体 JSON. 字段: method:ExperimentMethod; sample_size:int | None; success_criteria:str; control_group_desc:str; experiment_group_desc:str",
    )
    p_create_experiment.set_defaults(func=cmd_create_experiment)

    # ── GET /experiments ──
    p_list_experiments = sub.add_parser(
        "list-experiments",
        help="获取实验列表",
        description="获取实验列表",
    )
    p_list_experiments.add_argument(
        "--hypothesis_id",
        help="hypothesis_id (查询参数)",
    )
    p_list_experiments.set_defaults(func=cmd_list_experiments)

    # ── POST /hypotheses/{hypothesis_id}/verify ──
    p_verify_hypothesis = sub.add_parser(
        "verify-hypothesis",
        help="提交验证结果",
        description="提交验证结果",
    )
    p_verify_hypothesis.add_argument(
        "hypothesis_id",
        help="hypothesis_id (路径参数)",
    )
    p_verify_hypothesis.add_argument(
        "--json-input",
        help=f"请求体 JSON. 字段: passed:bool; confidence:float; metrics:dict[str, Any]; notes:str",
    )
    p_verify_hypothesis.set_defaults(func=cmd_verify_hypothesis)

    # ── POST /hypotheses/{hypothesis_id}/gate-check ──
    p_gate_check = sub.add_parser(
        "gate-check",
        help="手动触发门禁检查",
        description="手动触发门禁检查",
    )
    p_gate_check.add_argument(
        "hypothesis_id",
        help="hypothesis_id (路径参数)",
    )
    p_gate_check.set_defaults(func=cmd_gate_check)

    # ── POST /scan ──
    p_scan_opportunities = sub.add_parser(
        "scan-opportunities",
        help="执行机会扫描",
        description="执行机会扫描",
    )
    p_scan_opportunities.add_argument(
        "--json-input",
        help=f"请求体 JSON. 字段: data_sources:list[str]; max_signals:int; context:dict[str, Any]",
    )
    p_scan_opportunities.set_defaults(func=cmd_scan_opportunities)

    # ── POST /analyze ──
    p_analyze_trends = sub.add_parser(
        "analyze-trends",
        help="执行趋势分析",
        description="执行趋势分析",
    )
    p_analyze_trends.add_argument(
        "--json-input",
        help=f"请求体 JSON. 字段: signals:list[OpportunitySignal]; context:dict[str, Any]",
    )
    p_analyze_trends.set_defaults(func=cmd_analyze_trends)

    # ── GET /opportunities ──
    p_list_opportunities = sub.add_parser(
        "list-opportunities",
        help="获取推荐机会列表",
        description="获取推荐机会列表",
    )
    p_list_opportunities.add_argument(
        "--limit",
        type=int,
        default=20,
        help="limit (查询参数)",
    )
    p_list_opportunities.set_defaults(func=cmd_list_opportunities)

    # ── POST /pipeline/run ──
    p_run_full_pipeline = sub.add_parser(
        "run-full-pipeline",
        help="执行完整创新引擎管道",
        description="执行完整创新引擎管道",
    )
    p_run_full_pipeline.add_argument(
        "--json-input",
        help=f"请求体 JSON. 字段: data_sources:list[str]; max_signals:int; context:dict[str, Any]",
    )
    p_run_full_pipeline.set_defaults(func=cmd_run_full_pipeline)

    # ── GET /growth-cycle ──
    p_get_growth_cycle = sub.add_parser(
        "get-growth-cycle",
        help="获取增长周期状态",
        description="获取增长周期状态",
    )
    p_get_growth_cycle.set_defaults(func=cmd_get_growth_cycle)

    # ── POST /growth-cycle/switch ──
    p_switch_growth_cycle = sub.add_parser(
        "switch-growth-cycle",
        help="切换增长周期阶段",
        description="切换增长周期阶段",
    )
    p_switch_growth_cycle.add_argument(
        "--phase",
        help="phase (查询参数)",
    )
    p_switch_growth_cycle.set_defaults(func=cmd_switch_growth_cycle)

    # ── GET /metrics ──
    p_get_innovation_metrics = sub.add_parser(
        "get-innovation-metrics",
        help="获取引擎监控指标",
        description="获取引擎监控指标",
    )
    p_get_innovation_metrics.set_defaults(func=cmd_get_innovation_metrics)

    # ── POST /cache/clear ──
    p_clear_innovation_cache = sub.add_parser(
        "clear-innovation-cache",
        help="清除缓存",
        description="清除缓存",
    )
    p_clear_innovation_cache.set_defaults(func=cmd_clear_innovation_cache)

    return parser

def main():
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except Exception as e:
        import traceback
        _error_exit(500, f"{e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
