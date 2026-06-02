# Notification Service - P3 microservice (port 8007)
import os, sys, json, sqlite3
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Notification Service", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
DB_PATH = "/var/www/liankebao/backend/data/chainke.db"
WF_DB = "/var/www/liankebao/backend/data/workflow.db"

def get_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/notifications")
def list_notifications(page: int = 1, limit: int = 20):
    conn = get_db()
    rows = conn.execute("SELECT * FROM notifications ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, (page-1)*limit)).fetchall()
    conn.close()
    return {"code": 200, "data": {"items": [dict(r) for r in rows], "total": len(rows)}}

@app.get("/api/notifications/unread-count")
def unread_count():
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) as c FROM notifications WHERE is_read=0 OR is_read IS NULL").fetchone()["c"]
    except:
        total = 0
    conn.close()
    return {"code": 200, "data": {"unread": total}}

@app.post("/api/notifications/{notification_id}/read")
def mark_read(notification_id: int):
    conn = get_db()
    conn.execute("UPDATE notifications SET is_read=1 WHERE id=?", (notification_id,))
    conn.commit()
    conn.close()
    return {"code": 200, "message": "ok"}

@app.get("/api/v1/workflow/notifications/{user_id}")
def workflow_notifications(user_id: int):
    conn = get_db(WF_DB)
    try:
        rows = conn.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (user_id,)).fetchall()
        conn.close()
        return {"code": 200, "data": [dict(r) for r in rows]}
    except:
        conn.close()
        return {"code": 200, "data": []}

@app.get("/health")
def health():
    return {"status": "ok", "service": "notification-service", "port": 8007}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
