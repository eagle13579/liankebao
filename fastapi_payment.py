"""
FastAPI Payment Microservice — Unified entry point.

Integrates:
  - payment/router.py        (9 payment routes)
  - crm_engine/router.py     (6 CRM customer routes)
  - crm_engine/nps_router.py (4 CRM NPS/renewal routes)
  - permission_guard.py      (6 RBAC/permission routes)

Total: 25 API routes + 1 health endpoint + OpenAPI docs.

Usage:
    uvicorn fastapi_payment:app --host 0.0.0.0 --port 8000 --reload
"""

import sys
import os

# ── Path setup: ensure project root is on sys.path ──────────────
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Router imports ──────────────────────────────────────────────
from payment.router import router as payment_router
from crm_engine.router import router as crm_router
from crm_engine.nps_router import nps_router as crm_nps_router
from permission_guard import router as permission_router

# ── 会员体系路由 ──────────────────────────────────────────────────────────
from trust_api import _membership_router as membership_router

# ── App metadata ────────────────────────────────────────────────
APP_TITLE = "内容自动化工厂 — FastAPI 支付微服务"
APP_DESCRIPTION = """
统一 FastAPI 微服务，整合以下子系统：

| 模块 | 路由前缀 | 端点数 | 说明 |
|------|---------|-------|------|
| 💳 支付 | `/api/payment` | 9 | 订单、发票、交易、退款 |
| 👥 CRM | `/api/crm` | 6 | 客户管理 (CRUD) |
| 📊 NPS/续费 | `/api/crm` | 4 | NPS 调查、续费提醒 |
| 🔒 权限守卫 | `/api/permissions` | 6 | RBAC 角色权限管理 |

**总计**: 25 个业务端点 + `/health` 健康检查
**协议**: RESTful JSON
**文档**: `/docs` (Swagger) | `/redoc` (ReDoc)
"""

# ── Create FastAPI app ──────────────────────────────────────────
app = FastAPI(
    title=APP_TITLE,
    description=APP_DESCRIPTION,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "内容自动化工厂团队",
        "url": "https://content-factory.example.com",
        "email": "dev@content-factory.example.com",
    },
    license_info={
        "name": "Proprietary",
    },
)

# ── CORS middleware ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include all routers ─────────────────────────────────────────
app.include_router(payment_router)
app.include_router(crm_router)
app.include_router(crm_nps_router)
app.include_router(permission_router)
app.include_router(membership_router)


# ── Health endpoint ─────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    """
    Unified health check endpoint.

    Returns overall system status, subsystem health, and uptime info.
    """
    from payment.router import _orders, _invoices, _transactions
    from crm_engine.router import _customers

    return {
        "status": "ok",
        "service": "内容自动化工厂 · FastAPI 支付微服务",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "subsystems": {
            "payment": {
                "status": "healthy",
                "orders": len(_orders),
                "invoices": len(_invoices),
                "transactions": len(_transactions),
            },
            "crm": {
                "status": "healthy",
                "customers": len(_customers),
            },
            "permissions": {
                "status": "healthy",
                "roles": len(permission_guard_role_store()),
            },
        },
        "endpoints": _enumerate_routes(),
    }


def permission_guard_role_store():
    """Borrow the role store from permission_guard without side effects."""
    from permission_guard import _roles
    return _roles


def _enumerate_routes() -> list[dict]:
    """List all registered routes with method and path."""
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    routes.append({
                        "method": method,
                        "path": route.path,
                        "name": route.name if hasattr(route, "name") else "",
                    })
    routes.sort(key=lambda r: r["path"])
    return routes


# ── Root info endpoint ──────────────────────────────────────────
@app.get("/", tags=["System"])
async def root():
    """API root — returns service overview and links to documentation."""
    return {
        "service": APP_TITLE,
        "version": "1.0.0",
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
        },
        "health": "/health",
        "routes_count": len([r for r in app.routes if hasattr(r, "methods")]),
    }


# ── Standalone entry point ──────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print(f"🚀 {APP_TITLE}")
    print(f"📄 Docs:      http://127.0.0.1:8000/docs")
    print(f"📄 ReDoc:     http://127.0.0.1:8000/redoc")
    print(f"❤️  Health:    http://127.0.0.1:8000/health")
    uvicorn.run("fastapi_payment:app", host="0.0.0.0", port=8000, reload=True)
