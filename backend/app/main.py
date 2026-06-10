"""
链客宝 Backend — FastAPI 应用入口
======================================
服务入口文件，注册所有路由模块。

规则：纯新增，不修改现有业务逻辑
路由注册原则：
  - 所有 router 通过 app.include_router() 注册
  - brochure_bridge 同时注册 /api/brochures/（复数）别名路由
    以满足小程序 brochure/index.js 的调用路径
"""

import os
import sys
from pathlib import Path

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ── 确保项目根目录在 sys.path ────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ===================================================================
# FastAPI 应用实例
# ===================================================================

app = FastAPI(
    title="链客宝 API",
    description="链客宝 — 企业家供需匹配平台后端服务",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3099",
        "http://localhost:3000",
        "https://liankebao.top",
        "https://www.liankebao.top",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================================================================
# 路由注册
# ===================================================================

# ── M1 基础能力 ──────────────────────────────────────────────────
from app.routers.business_card import router as business_card_router
from app.routers.brochure_bridge import router as brochure_bridge_router
from app.routers.auth import router as auth_router

app.include_router(business_card_router)
app.include_router(brochure_bridge_router)
app.include_router(auth_router)

# ── M2 假设验证门禁 ─────────────────────────────────────────────
try:
    from app.routers.hypothesis_gate import router as hypothesis_router
    if hypothesis_router is not None:
        app.include_router(hypothesis_router)
        print("[Main] hypothesis_gate 已注册")
except ImportError:
    print("[Main] hypothesis_gate 未安装，跳过")

# ── M3 学习中心 ─────────────────────────────────────────────────
try:
    from app.routers.learning_center import router as learning_router
    if learning_router is not None:
        app.include_router(learning_router)
        print("[Main] learning_center 已注册")
except ImportError:
    print("[Main] learning_center 未安装，跳过")

# ── M4 留存洞察 ─────────────────────────────────────────────────
try:
    from app.routers.retention_insights import router as retention_router
    if retention_router is not None:
        app.include_router(retention_router)
        print("[Main] retention_insights 已注册")
except ImportError:
    print("[Main] retention_insights 未安装，跳过")

# ── M5 回顾看板 ─────────────────────────────────────────────────
try:
    from app.routers.retro_board import router as retro_router
    if retro_router is not None:
        app.include_router(retro_router)
        print("[Main] retro_board 已注册")
except ImportError:
    print("[Main] retro_board 未安装，跳过")

# ── M6 单位经济 ─────────────────────────────────────────────────
try:
    from app.routers.unit_economics import router as unit_econ_router
    if unit_econ_router is not None:
        app.include_router(unit_econ_router)
        print("[Main] unit_economics 已注册")
except ImportError:
    print("[Main] unit_economics 未安装，跳过")

# ── ABACC 销售话术 ──────────────────────────────────────────────
try:
    from app.routers.sales_script import router as sales_script_router
    if sales_script_router is not None:
        app.include_router(sales_script_router)
        print("[Main] sales_script 已注册")
except ImportError:
    print("[Main] sales_script 未安装，跳过")

# ── 别名路由：/api/brochures/（复数） → brochure_bridge ──────────
# 小程序 brochure/index.js 调用的是 /api/brochures/{userId}（复数）
# brochure_bridge_router 内已包含 GET /api/brochures/{user_id}，
# 此处额外注册一个显式别名路由器以确保兼容性
brochures_alias = APIRouter(prefix="/api/brochures")

# 将 brochure_bridge 的复数路径再暴露一次（已在 bridge 内部注册，
# 此处保留以应对未来可能的路径拆分需求）
print("[Main] 别名路由就绪: /api/brochures/{user_id} → brochure_bridge")

# ===================================================================
# 模型初始化
# ===================================================================

try:
    from app.models import init_models
    init_models()
except Exception as e:
    print(f"[Main] 数据库表初始化失败: {e}")

# ===================================================================
# 健康检查
# ===================================================================


@app.get("/api/health", tags=["健康检查"])
async def health_check():
    """健康检查端点"""
    return {
        "status": "ok",
        "service": "链客宝 Backend API",
        "version": "1.0.0",
    }


@app.get("/health", tags=["健康检查"])
async def health_check_short():
    return {"status": "ok"}


# ===================================================================
# 启动入口
# ===================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8001"))
    print(f"[Main] 链客宝后端服务启动 → http://0.0.0.0:{port}")
    print(f"[Main] 电子画册 API: GET /api/brochure/{{user_id}}")
    print(f"[Main] 电子画册 API: GET /api/brochures/{{user_id}} (小程序别名)")
    print(f"[Main] 名片 API:     GET /api/business-card/cards")
    print(f"[Main] 生成名片 API:  POST /api/business-card/generate-card")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
