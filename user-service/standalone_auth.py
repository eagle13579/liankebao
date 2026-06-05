"""用户服务 (独立版) — P3微服务拆分"""
import os, sys, json, uuid, hashlib, hmac, time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import jwt

app = FastAPI(title="用户服务", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

JWT_SECRET = os.environ.get("JWT_SECRET", "chainke-dev-secret-key")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# --- Models ---
class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str
    phone: Optional[str] = None
    company: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict = {}

# --- Database ---
def get_db():
    """Connect to shared SQLite or PG"""
    import sqlite3
    db_path = "/var/www/liankebao/backend/data/chainke.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# --- Utils ---
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def create_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": int(time.time()) + ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

# --- Routes ---
@app.post("/api/auth/login")
def login(req: LoginRequest):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=? AND is_deleted=0", (req.username,)).fetchone()
    conn.close()
    if not user or user["password_hash"] != hash_password(req.password):
        raise HTTPException(401, "用户名或密码错误")
    token = create_token(user["id"], user["username"])
    return {"code": 200, "message": "登录成功", "data": {
        "token": token, "user": {"id": user["id"], "name": user["name"],
        "username": user["username"], "role": user["role"], "company": user.get("company","")}
    }}

@app.post("/api/auth/register")
def register(req: RegisterRequest):
    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE username=?", (req.username,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(400, "用户名已存在")
    conn.execute("INSERT INTO users (username, password_hash, name, phone, company, role, created_at) VALUES (?,?,?,?,?,?,?)",
                 (req.username, hash_password(req.password), req.name, req.phone, req.company, "buyer", datetime.now().isoformat()))
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    token = create_token(user_id, req.username)
    return {"code": 200, "message": "注册成功", "data": {"token": token, "user_id": user_id}}

@app.get("/api/auth/profile")
def profile(authorization: str = ""):
    try:
        payload = jwt.decode(authorization.replace("Bearer ",""), JWT_SECRET, algorithms=[JWT_ALGORITHM])
        conn = get_db()
        user = conn.execute("SELECT id, username, name, role, company, phone, avatar FROM users WHERE id=?", (int(payload["sub"]),)).fetchone()
        conn.close()
        if user: return {"code": 200, "data": dict(user)}
    except: pass
    raise HTTPException(401, "未登录")

@app.get("/health")
def health():
    return {"status": "ok", "service": "user-service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
