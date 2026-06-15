"""Seed contact data to the live server via SSH-tunneled localhost:8000"""

import urllib.request
import json

API = "http://127.0.0.1:8000"

# Register
reg = json.dumps(
    {
        "username": "test_contacts",
        "password": "Test123456!",
        "name": "测试联系人",
        "company": "链客宝AI测试",
    }
).encode()
try:
    req = urllib.request.Request(
        f"{API}/api/auth/register",
        data=reg,
        headers={"Content-Type": "application/json"},
    )
    r = urllib.request.urlopen(req, timeout=5)
    print("注册:", r.status, r.read().decode()[:100])
except Exception:
    print("注册(可能已存在): OK")

# Login
login = json.dumps({"username": "test_contacts", "password": "Test123456!"}).encode()
req = urllib.request.Request(
    f"{API}/api/auth/login", data=login, headers={"Content-Type": "application/json"}
)
r = urllib.request.urlopen(req, timeout=5)
res = json.loads(r.read())
token = res.get("data", {}).get("access_token", "")
print(f"登录成功, token: {token[:30]}...")

# Seed contacts
seed = json.dumps({"count": 15}).encode()
req = urllib.request.Request(
    f"{API}/api/contacts/seed",
    data=seed,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
)
r = urllib.request.urlopen(req, timeout=5)
d = json.loads(r.read())
print(
    f"seed结果: {d.get('message', '')}, created: {d.get('data', {}).get('created', 0)}"
)

# Verify
req2 = urllib.request.Request(
    f"{API}/api/contacts", headers={"Authorization": f"Bearer {token}"}
)
r2 = urllib.request.urlopen(req2, timeout=5)
d2 = json.loads(r2.read())
total = d2.get("data", {}).get("total", 0)
items = d2.get("data", {}).get("items", [])
print(f"线上联系人总数: {total}")
for c in items[:5]:
    print(f"  {c['name']} - {c.get('company', '')} - {c.get('phone', '')}")
