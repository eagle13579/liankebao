"""
在线学习定时触发脚本 — 供 cron / scheduler 定期调用

用法:
  python -m app.ai.cron.learning_cron             # 单次检查(自动)
  python -m app.ai.cron.learning_cron --watch     # 持续监视(每30分钟)
  python -m app.ai.cron.learning_cron --force     # 强制学习一次
"""

import argparse
import asyncio
import logging
import os
import sys

# 确保项目路径在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logger = logging.getLogger("learning_cron")


async def check_and_learn() -> dict:
    """检查反馈数据量, 达到阈值则触发一次在线学习

    Returns:
        dict: 学习结果 (如果触发了学习) 或状态报告 (如果未触发)
    """
    from app.ai.online_learning import get_online_learning_engine

    engine = get_online_learning_engine()
    result = engine.check_and_learn()

    if result:
        logger.info(
            "✅ 在线学习已触发: cycle=%d, adjustment=%.4f, weights=%s",
            result.get("cycle"),
            result.get("weight_changes", {}).get("new_global_adjustment", 1.0),
            result.get("weight_changes", {}).get("new_weights", {}),
        )
    else:
        status = engine.get_learning_status()
        progress = status.get("learning", {}).get("progress_percent", 0)
        total = status.get("feedback", {}).get("total", 0)
        logger.info(
            "⏳ 未达阈值: 总反馈 %d 条, 距下次学习进度 %.1f%%",
            total,
            progress,
        )

    return result or {"triggered": False, "status": "skipped"}


async def force_learn() -> dict:
    """强制执行一次在线学习 (无论是否达到阈值)"""
    from app.ai.online_learning import trigger_learning

    logger.info("⚡ 强制触发在线学习...")
    result = trigger_learning()
    logger.info(
        "✅ 在线学习完成: cycle=%d, adjustment=%.4f",
        result.get("cycle"),
        result.get("weight_changes", {}).get("new_global_adjustment", 1.0),
    )
    return result


async def main():
    parser = argparse.ArgumentParser(description="在线学习定时触发脚本")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="持续监视模式 (每30分钟自动检查)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="监视模式的间隔分钟数 (默认: 30)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制学习一次 (忽略阈值)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="单次检查 (默认行为)",
    )

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if args.force:
        # 强制学习 (无论是否达到阈值)
        logger.info("⚡ 强制在线学习模式")
        result = await force_learn()
        print("\n📊 在线学习结果:")
        print(f"  周期: #{result.get('cycle', 'N/A')}")
        print(f"  耗时: {result.get('duration_seconds', 0):.3f}s")
        print(f"  反馈: {result.get('feedback_stats', {}).get('total', 0)} 条")
        print(
            f"  调整: {result.get('weight_changes', {}).get('old_global_adjustment', 1.0):.4f} → "
            f"{result.get('weight_changes', {}).get('new_global_adjustment', 1.0):.4f}"
        )
        print(f"  新权重: {result.get('weight_changes', {}).get('new_weights', {})}")

    elif args.watch:
        # 持续监视模式
        logger.info(
            "🔁 在线学习监视模式启动 (检查间隔=%d分钟)",
            args.interval,
        )
        while True:
            try:
                result = await check_and_learn()
                if result.get("triggered") is False:
                    pass  # 正常未触发, 日志已记录
            except Exception as e:
                logger.error("在线学习检查异常: %s", e, exc_info=True)

            logger.info("💤 休眠 %d 分钟...", args.interval)
            await asyncio.sleep(args.interval * 60)
    else:
        # 单次检查
        logger.info("🔍 单次检查模式")
        result = await check_and_learn()
        if result.get("triggered") is not False:
            print("\n📊 在线学习完成:")
            print(f"  周期: #{result.get('cycle', 'N/A')}")
            print(f"  耗时: {result.get('duration_seconds', 0):.3f}s")
            print(f"  反馈: {result.get('feedback_stats', {}).get('total', 0)} 条")
            print(
                f"  调整: {result.get('weight_changes', {}).get('old_global_adjustment', 1.0):.4f} → "
                f"{result.get('weight_changes', {}).get('new_global_adjustment', 1.0):.4f}"
            )
            print(f"  新权重: {result.get('weight_changes', {}).get('new_weights', {})}")
        else:
            status = result.get("status", {})
            if isinstance(result, dict) and "triggered" in result:
                print(f"\n⏳ 未触发学习: {result}")
            else:
                print("\n⏳ 未触发学习")


if __name__ == "__main__":
    asyncio.run(main())
