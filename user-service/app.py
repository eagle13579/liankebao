"""用户服务 — 独立微服务 (P3拆分)"""
import os, sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="用户服务", version="1.0.0", docs_url="/docs")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Import auth routes from main backend
sys.path.insert(0, '/var/www/liankebao/backend')
from app.routers.auth import router as auth_router
app.include_router(auth_router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "user-service", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
