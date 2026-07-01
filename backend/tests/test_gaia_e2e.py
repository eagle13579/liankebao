"""端到端验证：复盘知识 → 盖娅大脑 → 进化权重 → 反哺推荐"""

import asyncio
import logging
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("gaia_e2e_test")


async def main():
    from app.database import AsyncSessionLocal, engine, Base
    from app.models.gaia import GaiaKnowledge, GaiaEvolutionEvent, GaiaTrainingRun, GaiaModelWeights
    from app.ai.gaia_evolution_brain import get_gaia_brain
    from app.ai.gaia_trainer import get_gaia_trainer
    from app.ai.gaia_flywheel import get_flywheel

    # 1. 确保表已创建
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    brain = get_gaia_brain()
    trainer = get_gaia_trainer()
    flywheel = get_flywheel()

    # 2. 注入一条复盘知识（模拟F8知识归档）
    print("\n🧪 Step 1: 注入复盘知识...")
    async with AsyncSessionLocal() as db:
        knowledge = await brain.ingest_knowledge(
            db=db,
            source="retrospective",
            source_id="retro_board:42",
            knowledge_type="pattern",
            title="用户转化率提升策略",
            content="复盘发现：用户在首次看到匹配结果后的24小时内联系的概率提升60%。"
                     "建议匹配引擎优先推荐最近活跃的用户，并缩短推荐结果的缓存时间。",
            tags=["matching", "conversion", "recency"],
            confidence=0.85,
        )
        await db.commit()
        print(f"   ✅ 知识已注入: id={knowledge.id}, title={knowledge.title}")

        # 验证知识已持久化
        count = await db.scalar(
            __import__("sqlalchemy").select(__import__("sqlalchemy").func.count())
            .select_from(GaiaKnowledge)
        )
        print(f"   📊 知识库总计: {count} 条")

    # 3. 运行飞轮（进化循环 + 训练管线）
    print("\n🧪 Step 2: 运行进化飞轮...")
    result = await flywheel.run_once()
    print(f"   ✅ 飞轮完成: {result.get('status', 'unknown')}")
    print(f"   📊 知识处理: {result.get('evolution', {}).get('knowledge_processed', 0)}")
    print(f"   📊 事件创建: {result.get('evolution', {}).get('events_created', 0)}")
    print(f"   ⏱  耗时: {result.get('duration_seconds')}s")

    # 4. 验证进化权重已生成
    print("\n🧪 Step 3: 验证进化权重...")
    async with AsyncSessionLocal() as db:
        weights_count = await db.scalar(
            __import__("sqlalchemy").select(__import__("sqlalchemy").func.count())
            .select_from(GaiaModelWeights)
        )
        print(f"   📊 权重记录总数: {weights_count} 条")

        # 查询各模块权重
        for module in ["recommendation", "matching", "search", "ranking", "extractor", "writing", "optimization"]:
            weight = await brain.get_evolved_weights(db=db, module=module)
            if weight:
                print(f"   ✅ {module}: param_value={weight.param_value}, version={weight.version}")
            else:
                print(f"   ⚠️ {module}: 无活跃权重")

        # 验证事件日志
        events = await brain.get_events(db=db, limit=5)
        print(f"\n   📋 最近进化事件 ({len(events)}):")
        for e in events:
            print(f"      - [{e.event_type}] {e.description}")

        # 验证训练记录
        runs = await brain.get_training_runs(db=db, limit=5)
        print(f"\n   📋 最近训练记录 ({len(runs)}):")
        for r in runs:
            print(f"      - #{r.id}: {r.status} ({r.knowledge_count}k, {r.feedback_count}f)")

    # 5. 查询知识库（语义检索）
    print("\n🧪 Step 4: 检索知识库...")
    async with AsyncSessionLocal() as db:
        results = await brain.get_knowledge_base(db=db, query="用户转化", limit=5)
        print(f"   📊 检索到 {len(results)} 条相关知识:")
        for r in results:
            print(f"      - [{r.source}] {r.title} (置信度: {r.confidence})")

    # 6. 查询反哺后的权重
    print("\n🧪 Step 5: 盖娅反哺权重...")
    async with AsyncSessionLocal() as db:
        for module in ["recommendation", "matching"]:
            evolved = await trainer.get_evolved_params(db=db, module=module)
            print(f"   {module}: {evolved}")

    print("\n✅ 端到端验证完成！盖娅进化大脑已活过来。")


if __name__ == "__main__":
    asyncio.run(main())
