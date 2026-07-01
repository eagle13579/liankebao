"""测试盖娅数据表创建"""
import asyncio
from app.database import engine, Base
from app.models.gaia import GaiaKnowledge, GaiaEvolutionEvent, GaiaTrainingRun, GaiaModelWeights

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("✅ 盖娅数据表创建成功")
        # 验证表存在
        tables = [GaiaKnowledge.__tablename__, GaiaEvolutionEvent.__tablename__,
                  GaiaTrainingRun.__tablename__, GaiaModelWeights.__tablename__]
        print(f"   表: {tables}")

asyncio.run(main())
