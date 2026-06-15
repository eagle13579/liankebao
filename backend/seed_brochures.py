#!/usr/bin/env python3
"""为所有主后端用户创建brochure名片记录（数据真实化同步）
运行: python seed_brochures.py
"""
import os, sys, json, urllib.request, logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)

CHAINKE_DB = os.path.join(BACKEND, "data", "chainke.db")
BROCHURE_API = os.environ.get("BROCHURE_API", "http://localhost:8003")

def get_users_from_chainke():
    """从chainke.db读取所有用户"""
    import sqlite3
    conn = sqlite3.connect(CHAINKE_DB)
    conn.row_factory = sqlite3.Row
    users = conn.execute("SELECT id, username, name, phone, company, position, avatar FROM users WHERE is_deleted = 0").fetchall()
    conn.close()
    return [dict(u) for u in users]

def brochure_exists(user_id):
    """检查brochure是否已存在"""
    try:
        req = urllib.request.Request(f"{BROCHURE_API}/api/v1/brochures/{user_id}")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except:
        return False

def create_brochure(user):
    """为指定用户创建brochure"""
    data = json.dumps({
        "user_id": str(user["id"]),
        "name": user.get("name") or user.get("username") or "",
        "company": user.get("company") or "",
        "position": user.get("position") or "",
        "phone": user.get("phone") or "",
        "avatar": user.get("avatar") or "",
        "title": f"{user.get('name') or user.get('username') or ''} 的数字名片",
        "bio": "", "tags": [], "email": "", "wechat": "",
    }).encode()
    req = urllib.request.Request(
        f"{BROCHURE_API}/api/v1/brochures",
        data=data, headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 201
    except urllib.error.HTTPError as e:
        if e.code == 409:  # already exists
            return True
        log.warning(f"  HTTP {e.code}: {user.get('name')}")
        return False
    except Exception as e:
        log.warning(f"  Error: {e}")
        return False

def main():
    if not os.path.isfile(CHAINKE_DB):
        log.error(f"chainke.db not found at {CHAINKE_DB}")
        sys.exit(1)

    users = get_users_from_chainke()
    log.info(f"Found {len(users)} users in chainke.db")

    ok, skip, fail = 0, 0, 0
    for u in users:
        uid = str(u["id"])
        if brochure_exists(uid):
            log.info(f"  SKIP {u.get('name'):12s} (brochure exists)")
            skip += 1
            continue
        if create_brochure(u):
            log.info(f"  OK   {u.get('name'):12s} -> brochure created")
            ok += 1
        else:
            log.warning(f"  FAIL {u.get('name'):12s}")
            fail += 1

    log.info(f"\nDone: {ok} created, {skip} skipped, {fail} failed")

if __name__ == "__main__":
    main()
