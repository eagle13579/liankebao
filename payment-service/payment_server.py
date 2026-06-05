'''Payment Service - P3 microservice (port 8006)'''
import os, sys
sys.path.insert(0, '/var/www/liankebao/backend')

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Payment Service", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

from app.routers.payment import router as payment_router
from app.routers.orders import router as orders_router

app.include_router(payment_router)
app.include_router(orders_router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "payment-service", "port": 8006}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
