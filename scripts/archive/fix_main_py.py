"""Fix main.py syntax error on server"""
import os

path = "/opt/chainke/backend/app/main.py"

with open(path, "r") as f:
    content = f.read()

# Full correct main.py
fixed = '''"""FastAPI 应用入口"""
from app.security_middleware_injection import init_security_middleware, close_security_middleware

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.routers import auth, products, orders, promoter, admin, analytics, user, crm

# 创建应用
app = FastAPI(
    title="企盟 · 后端 API",
    description="企业家供需匹配平台 MVP 后端服务",
    version="0.1.0",
)

# Initialize security middleware
init_security_middleware(app)

# CORS 配置（让 Lovable 小程序前端可以跨域访问）
origins = ["*"]
if settings.CORS_ORIGINS and settings.CORS_ORIGINS != "*":
    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    """应用启动时初始化数据库"""
    init_db()


@app.get("/api/health", tags=["系统"])
def health_check():
    """健康检查"""
    return {"status": "ok", "version": "0.1.0"}


# 注册路由
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(promoter.router)
app.include_router(admin.router)
app.include_router(analytics.router)
app.include_router(user.router)
app.include_router(crm.router)
'''

with open(path, "w") as f:
    f.write(fixed)

import ast
ast.parse(fixed)
print("Syntax OK")
print(f"Written {len(fixed)} bytes")
