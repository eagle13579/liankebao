#!/usr/bin/env python
"""
链客宝 - 数据管道健康检查 CLI
==============================
Usage:
    python scripts/health_check.py --check all
    python scripts/health_check.py --check health
    python scripts/health_check.py --check freshness
    python scripts/health_check.py --check error-rate
    python scripts/health_check.py --check alert
    python scripts/health_check.py --check report
    python scripts/health_check.py --data-dir /path/to/data

选项：
    --check      检查类型: all | health | freshness | error-rate | alert | report
    --data-dir   状态数据目录（可选，默认自动检测）
    --webhook    飞书 Webhook URL（可选，默认从环境变量读取）
    --verbose    详细日志输出
"""

import argparse
import json
import logging
import os
import sys

# 添加项目根到 sys.path（从 backend/scripts/health_check.py → D:\chainke-full）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.scripts.monitor_setup import (
    PipelineMonitor,
    AlertManager,
    create_monitor,
    create_alert_manager,
)

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """配置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_health(monitor: PipelineMonitor) -> None:
    """健康检查"""
    health = monitor.check_health()
    print("=" * 60)
    print("  管道健康状态")
    print("=" * 60)

    full = health.get("full_sync", {})
    incr = health.get("incremental_sync", {})
    overall = health.get("overall", {})

    print(f"\n全量同步:")
    print(f"  最后同步: {full.get('last_sync') or '从未运行'}")
    print(f"  距现在:   {full.get('hours_since') or 'N/A'}h")
    print(f"  状态:     {full.get('status', 'unknown')}")

    print(f"\n增量同步:")
    print(f"  最后同步: {incr.get('last_sync') or '从未运行'}")
    print(f"  距现在:   {incr.get('hours_since') or 'N/A'}h")
    print(f"  状态:     {incr.get('status', 'unknown')}")

    print(f"\n整体:")
    print(f"  状态:        {overall.get('status', 'unknown')}")
    print(f"  总同步次数:  {overall.get('total_syncs', 0)}")
    print(f"  总错误数:    {overall.get('total_errors', 0)}")
    print(f"  正在运行:    {'是' if overall.get('is_running') else '否'}")
    print()


def cmd_freshness(monitor: PipelineMonitor) -> None:
    """数据新鲜度检查"""
    freshness = monitor.check_data_freshness()
    print("=" * 60)
    print("  数据新鲜度")
    print("=" * 60)
    print(f"\n  全量同步: {freshness.get('full_sync_hours') or 'N/A'}h")
    print(f"  增量同步: {freshness.get('incremental_sync_hours') or 'N/A'}h")
    print(f"  有效新鲜度: {freshness.get('max_hours') or 'N/A'}h")
    print(f"  级别:       {freshness.get('level', 'unknown')}")

    level = freshness.get("level")
    if level == "healthy":
        print("  ✅ 数据新鲜，无需处理。")
    elif level == "info":
        print("  ℹ️ 数据新鲜度超过4小时，建议关注。")
    elif level == "warn":
        print("  ⚠️ 数据新鲜度超过12小时，建议尽快同步。")
    elif level == "critical":
        print("  🚨 数据严重过期（超过24小时），请立即处理！")
    print()


def cmd_error_rate(monitor: PipelineMonitor) -> None:
    """错误率检查"""
    error_info = monitor.check_error_rate(hours=24)
    print("=" * 60)
    print("  错误率统计（最近24h）")
    print("=" * 60)
    print(f"\n  统计窗口: {error_info.get('window_hours', 24)}h")
    print(f"  同步次数: {error_info.get('total_syncs', 0)}")
    print(f"  错误次数: {error_info.get('total_errors', 0)}")
    print(f"  错误率:   {error_info.get('error_rate', 0) * 100:.2f}%")
    print(f"  状态:     {error_info.get('status', 'healthy')}")

    if error_info.get("status") == "critical":
        print("  🚨 错误率超过10%，请立即检查管道！")
    print()


def cmd_alert(monitor: PipelineMonitor, alert_mgr: AlertManager) -> None:
    """阈值检查并推送告警"""
    health = monitor.check_health()
    triggered = alert_mgr.check_thresholds(health)

    if not triggered:
        print("=" * 60)
        print("  阈值检查: ✅ 所有指标正常")
        print("=" * 60)
        return

    print("=" * 60)
    print(f"  阈值检查: 触发 {len(triggered)} 条告警")
    print("=" * 60)

    for item in triggered:
        print(f"\n  [{item['level']}] {item['metric']} = {item['value']}")
        print(f"  {item['message']}")

        # 推送飞书 + 本地日志
        alert_mgr.send_feishu(item["message"])
        alert_mgr.send_log(item["message"])

    print()


def cmd_report(monitor: PipelineMonitor) -> None:
    """生成健康报告（Markdown）"""
    report = monitor.generate_report()
    print(report)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="链客宝 - 数据管道健康检查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/health_check.py --check all
  python scripts/health_check.py --check report
  python scripts/health_check.py --check alert --webhook https://open.feishu.cn/open-apis/bot/v2/hook/xxx
        """,
    )
    parser.add_argument(
        "--check",
        choices=["all", "health", "freshness", "error-rate", "alert", "report"],
        default="all",
        help="检查类型（默认: all）",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="状态数据目录（可选，默认自动检测）",
    )
    parser.add_argument(
        "--webhook",
        default=None,
        help="飞书 Webhook URL（可选，默认从环境变量 FEISHU_WEBHOOK_URL 读取）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="详细日志输出",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    monitor = create_monitor(data_dir=args.data_dir)
    alert_mgr = create_alert_manager(webhook_url=args.webhook)

    check = args.check

    if check in ("all", "health"):
        cmd_health(monitor)

    if check in ("all", "freshness"):
        cmd_freshness(monitor)

    if check in ("all", "error-rate"):
        cmd_error_rate(monitor)

    if check in ("all", "alert"):
        cmd_alert(monitor, alert_mgr)

    if check in ("all", "report"):
        if check == "all":
            print("\n" + "=" * 60)
            print("  健康报告 (Markdown)")
            print("=" * 60 + "\n")
        cmd_report(monitor)


if __name__ == "__main__":
    main()
