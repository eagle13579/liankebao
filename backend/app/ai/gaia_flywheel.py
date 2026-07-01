"""盖娅进化飞轮 — 微任务并行引擎

自动运行的进化周期脚本，供 cron/scheduler 定期调用。
每次运行完成一轮完整的：
  1. 知识聚合（从复盘 F8 摄取新增知识）
  2. 反馈消化（处理极端反馈模式）
  3. 进化循环（计算新权重 → 更新向量索引 → 部署）
  4. 状态记录

用法:
  python -m app.ai.gaia_flywheel              # 单次运行
  python -m app.ai.gaia_flywheel --watch      # 持续监视模式 (每30分钟)
"""

import asyncio
import logging
import os
import sys
import time

# 确保项目路径在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("gaia_flywheel")

# ── 飞轮状态 ──────────────────────────────────────────────────────────────


class GaiaFlywheel:
    """盖娅进化飞轮 — 微任务并行引擎"""

    def __init__(self):
        self._cycle_count = 0
        self._last_duration = 0.0
        self._total_duration = 0.0
        self._errors = 0

    async def run_once(self) -> dict:
        """执行一轮完整的进化周期"""
        from app.ai.gaia_evolution_brain import get_gaia_brain
        from app.ai.gaia_trainer import get_gaia_trainer
        from app.database import AsyncSessionLocal, engine
        from app.models.gaia import GaiaKnowledge, GaiaEvolutionEvent, GaiaTrainingRun, GaiaModelWeights
        from app.database import Base

        # 确保盖娅数据表已创建
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        brain = get_gaia_brain()
        trainer = get_gaia_trainer()

        start = time.time()
        self._cycle_count += 1
        cycle_id = self._cycle_count

        logger.info("[飞轮 #%d] ⚙️ 进化周期启动", cycle_id)

        try:
            # 创建数据库会话
            async with AsyncSessionLocal() as db:
                # ── 阶段 1: 运行进化循环（知识聚合+事件处理）──
                logger.info("[飞轮 #%d] 📡 运行进化循环...", cycle_id)
                evolution_result = await brain.process_evolution_cycle(db=db)
                await db.commit()
                logger.info(
                    "[飞轮 #%d] ✅ 进化循环完成: knowledge=%d, events=%d",
                    cycle_id,
                    evolution_result.get("knowledge_processed", 0),
                    evolution_result.get("events_created", 0),
                )

                # ── 阶段 2: 运行模型训练管线 ──
                logger.info("[飞轮 #%d] 🧠 运行训练管线...", cycle_id)
                training_result = await trainer.run_training_cycle(db=db)
                await db.commit()
                if training_result.get("status") == "completed":
                    logger.info(
                        "[飞轮 #%d] ✅ 训练完成: module=%s, weights=%d",
                        cycle_id,
                        training_result.get("module", "unknown"),
                        training_result.get("weights_updated", 0),
                    )
                else:
                    logger.warning(
                        "[飞轮 #%d] ⚠️ 训练未完成: status=%s",
                        cycle_id,
                        training_result.get("status", "unknown"),
                    )

                # ── 阶段 3: 统计报告 ──
                status = await brain.get_status(db=db)
                elapsed = time.time() - start
                self._last_duration = elapsed
                self._total_duration += elapsed

                report = {
                    "cycle_id": cycle_id,
                    "duration_seconds": round(elapsed, 2),
                    "evolution": evolution_result,
                    "training": training_result,
                    "brain_status": status,
                }

                logger.info(
                    "[飞轮 #%d] ✅ 周期完成 (%.2fs) — "
                    "知识库: %d条, 事件: %d条, 权重: %d模块",
                    cycle_id,
                    elapsed,
                    status.get("knowledge_count", 0),
                    status.get("event_count", 0),
                    status.get("weight_count", 0),
                )

                return report

        except Exception as e:
            self._errors += 1
            elapsed = time.time() - start
            logger.error(
                "[飞轮 #%d] ❌ 周期失败 (%.2fs): %s",
                cycle_id,
                elapsed,
                str(e),
                exc_info=True,
            )
            return {
                "cycle_id": cycle_id,
                "duration_seconds": round(elapsed, 2),
                "status": "failed",
                "error": str(e),
            }

    def get_stats(self) -> dict:
        """获取飞轮运行统计"""
        return {
            "cycle_count": self._cycle_count,
            "last_duration_seconds": round(self._last_duration, 2),
            "avg_duration_seconds": (
                round(self._total_duration / self._cycle_count, 2)
                if self._cycle_count > 0
                else 0
            ),
            "total_duration_seconds": round(self._total_duration, 2),
            "errors": self._errors,
        }


# ── 单例 ─────────────────────────────────────────────────────────────────

_flywheel: GaiaFlywheel | None = None


def get_flywheel() -> GaiaFlywheel:
    global _flywheel
    if _flywheel is None:
        _flywheel = GaiaFlywheel()
    return _flywheel


# ── CLI ──────────────────────────────────────────────────────────────────


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="盖娅进化飞轮 — 微任务并行引擎")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="持续监视模式（每30分钟自动运行）",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="监视模式的间隔分钟数（默认: 30）",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="仅运行一次（默认行为）",
    )

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    flywheel = get_flywheel()

    if args.watch:
        logger.info(
            "🔁 盖娅进化飞轮 — 监视模式启动 (间隔=%d分钟)",
            args.interval,
        )
        while True:
            try:
                result = await flywheel.run_once()
                logger.info("📊 本轮结果: %s", result)
            except Exception as e:
                logger.error("飞轮运行异常: %s", e)
            logger.info("💤 休眠 %d 分钟...", args.interval)
            await asyncio.sleep(args.interval * 60)
    else:
        # 单次运行
        logger.info("⚡ 盖娅进化飞轮 — 单次运行")
        result = await flywheel.run_once()
        print(f"\n📊 进化报告:\n")
        print(f"  周期: #{result.get('cycle_id')}")
        print(f"  耗时: {result.get('duration_seconds')}s")
        print(f"  知识处理: {result.get('evolution', {}).get('knowledge_processed', 0)} 条")
        print(f"  事件创建: {result.get('evolution', {}).get('events_created', 0)} 条")
        print(f"  状态: {result.get('training', {}).get('status', 'unknown')}")


if __name__ == "__main__":
    asyncio.run(main())
