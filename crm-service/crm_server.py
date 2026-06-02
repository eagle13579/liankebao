'''CRM Service - P3 microservice (port 8005)'''
import os, sys
sys.path.insert(0, '/var/www/liankebao/backend')

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CRM Service", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Import existing CRM routes
from app.routers.contacts import router as contacts_router
from app.routers.crm import router as crm_router
from app.routers.crm_pipeline import router as crm_pipeline_router
from app.routers.enterprise import router as enterprise_router

app.include_router(contacts_router)
app.include_router(crm_router)
app.include_router(crm_pipeline_router)
app.include_router(enterprise_router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "crm-service", "port": 8005}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
