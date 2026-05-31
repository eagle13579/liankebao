"""Rewrite main.py with correct route order"""
content = '''"""FastAPI 应用入口"""
from app.security_middleware_injection import init_security_middleware, close_security_middleware

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.routers import auth, contacts, products, orders, promoter, admin, analytics, user, crm

# 创建应用
app = FastAPI(
    title="企盟 · 后端 API",
    description="企业家供需匹配平台 MVP 后端服务",
    version="0.1.0",
)

# Initialize security middleware
init_security_middleware(app)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/health", tags=["系统"])
def health_check():
    return {"status": "ok", "version": "0.1.0"}


# 注册路由 — 特定路由先注册，避免被通用 catch-all 拦截
app.include_router(auth.router)
app.include_router(contacts.router)     # 特定 /api/contacts/* 路由先注册
app.include_router(products.router)      # BaseRouter 生成 /api/{id}
app.include_router(orders.router)        # BaseRouter 生成 /api/{id}
app.include_router(promoter.router)      # BaseRouter 生成 /api/{id} ← ⚠️ 会在 /api/{id} 拦截未匹配路由
app.include_router(admin.router)
app.include_router(analytics.router)
app.include_router(user.router)
app.include_router(crm.router)
'''

import ast
ast.parse(content)
print("Syntax OK")
with open("/opt/chainke/backend/app/main.py", "w") as f:
    f.write(content)
print("Rewritten with contacts before promoter")
