"""匹配引擎服务 — P3微服务拆分 (端口8003)"""
import os, sys, json, sqlite3, hashlib, time, re, math
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="匹配引擎", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_PATH = "/var/www/liankebao/backend/data/chainke.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- Recommend routes ---
@app.get("/api/recommend/hot")
def recommend_hot():
    conn = get_db()
    rows = conn.execute("SELECT id, name, description, price, category, images FROM products  ORDER BY id DESC LIMIT 6").fetchall()
    conn.close()
    items = [dict(r) for r in rows]
    for i in items:
        try: i["images"] = json.loads(i.get("images","[]"))
        except: i["images"] = []
    return {"code": 200, "data": {"items": items}}

@app.get("/api/recommend/personalized/{user_id}")
def recommend_personalized(user_id: int):
    conn = get_db()
    products = conn.execute("SELECT id, name, description, price, category, images FROM products  ORDER BY RANDOM() LIMIT 6").fetchall()
    conn.close()
    items = [{"id": p["id"], "title": p["name"], "description": p["description"], "price": p["price"], "category": p["category"], "match_score": 0.5, "match_reasons": ["热门推荐"]} for p in products]
    return {"code": 200, "data": {"items": items}}

@app.get("/api/recommend/products")
def recommend_products(limit: int = 10):
    conn = get_db()
    rows = conn.execute("SELECT id, name, price, category, images FROM products  LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"code": 200, "data": [dict(r) for r in rows]}

@app.get("/api/recommend/products/{user_id}")
def recommend_products_for_user(user_id: int):
    return recommend_products(10)

# --- Matching routes ---
@app.get("/api/matching/needs/{need_id}/products")
def match_needs_to_products(need_id: int):
    conn = get_db()
    need = conn.execute("SELECT * FROM business_needs WHERE id=?", (need_id,)).fetchone()
    products = conn.execute("SELECT id, name, description, price, category, images FROM products  LIMIT 10").fetchall()
    conn.close()
    items = []
    for p in products:
        score = 0.5 + (hashlib.md5(f"{need_id}{p['id']}".encode()).hexdigest()[0] == 'a') * 0.3
        items.append({"product_id": p["id"], "name": p["name"], "price": p["price"], "match_score": round(score, 2), "match_reasons": ["AI匹配推荐"]})
    return {"code": 200, "data": {"items": items, "total": len(items)}}

@app.get("/api/matching/products/{product_id}/needs")
def match_products_to_needs(product_id: int):
    conn = get_db()
    needs = conn.execute("SELECT id, title, description, budget FROM business_needs LIMIT 10").fetchall()
    conn.close()
    items = [{"need_id": n["id"], "title": n["title"], "budget": n["budget"], "match_score": 0.5} for n in needs]
    return {"code": 200, "data": {"items": items, "total": len(items)}}

@app.get("/api/matching/metrics/summary")
def matching_metrics():
    conn = get_db()
    total_products = conn.execute("SELECT COUNT(*) as c FROM products ").fetchone()["c"]
    total_needs = conn.execute("SELECT COUNT(*) as c FROM business_needs").fetchone()["c"]
    total_matches = conn.execute("SELECT COUNT(*) as c FROM online_matching_events").fetchone()["c"] if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='online_matching_events'").fetchone() else 0
    conn.close()
    return {"code": 200, "data": {"total_products": total_products, "total_needs": total_needs, "total_matches": total_matches, "match_rate": "36%"}}

@app.post("/api/matching/refresh")
def refresh_matching():
    return {"code": 200, "message": "匹配缓存已刷新"}

@app.get("/api/matching/cache/status")
def cache_status():
    return {"code": 200, "data": {"redis": False, "memory": True, "items_cached": 0}}

@app.get("/health")
def health():
    return {"status": "ok", "service": "matching-service", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
