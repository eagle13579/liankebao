# Search Service - P3 microservice (port 8008)
import os, sys, json, sqlite3, hashlib, re
sys.path.insert(0, '/var/www/liankebao/backend')

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Search Service", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
DB_PATH = "/var/www/liankebao/backend/data/chainke.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/search")
def search(q: str = "", page: int = 1, limit: int = 20):
    conn = get_db()
    like = f"%{q}%"
    products = conn.execute("SELECT id, name, description, price, category FROM products WHERE name LIKE ? OR description LIKE ? LIMIT ? OFFSET ?", (like, like, limit, (page-1)*limit)).fetchall()
    needs = conn.execute("SELECT id, title, description FROM business_needs WHERE title LIKE ? OR description LIKE ? LIMIT 5", (like, like)).fetchall()
    conn.close()
    return {"code": 200, "data": {"products": [dict(r) for r in products], "needs": [dict(r) for r in needs]}}

@app.get("/api/search/categories")
def categories():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != ''").fetchall()
    conn.close()
    return {"code": 200, "data": [r["category"] for r in rows]}

@app.get("/api/search/suggestions")
def suggestions(q: str = ""):
    conn = get_db()
    like = f"%{q}%"
    products = conn.execute("SELECT name FROM products WHERE name LIKE ? LIMIT 5", (like,)).fetchall()
    conn.close()
    return {"code": 200, "data": {"products": [r["name"] for r in products]}}

@app.get("/api/search/stats")
def stats():
    conn = get_db()
    total_p = conn.execute("SELECT COUNT(*) as c FROM products").fetchone()["c"]
    total_n = conn.execute("SELECT COUNT(*) as c FROM business_needs").fetchone()["c"]
    conn.close()
    return {"code": 200, "data": {"total_products": total_p, "total_needs": total_n, "indexed": total_p + total_n}}

@app.get("/api/search/vector")
def vector_search(q: str = "", limit: int = 10):
    conn = get_db()
    rows = conn.execute("SELECT id, name, description, price FROM products LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"code": 200, "data": [dict(r) for r in rows]}

@app.get("/api/contacts/search")
def search_contacts(q: str = ""):
    conn = get_db()
    like = f"%{q}%"
    rows = conn.execute("SELECT id, name, company, phone FROM contacts WHERE name LIKE ? OR company LIKE ? LIMIT 20", (like, like)).fetchall()
    conn.close()
    return {"code": 200, "data": [dict(r) for r in rows]}

@app.get("/api/enterprise/search")
def search_enterprises(q: str = ""):
    conn = get_db()
    like = f"%{q}%"
    rows = conn.execute("SELECT id, name, industry FROM enterprises WHERE name LIKE ? LIMIT 20", (like, like)).fetchall()
    conn.close()
    return {"code": 200, "data": [dict(r) for r in rows]}

@app.get("/health")
def health():
    return {"status": "ok", "service": "search-service", "port": 8008}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
