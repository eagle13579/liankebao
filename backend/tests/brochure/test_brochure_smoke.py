"""AI数字名片 brochure API smoke test"""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from digital_brochure_api import init_db; init_db()
os.environ["BROCHURE_DB_DIR"] = tempfile.mkdtemp()
os.environ["SENTRY_DSN"] = ""
from digital_brochure_api import app
from fastapi.testclient import TestClient
client = TestClient(app)

def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200

def test_trace_id():
    r = client.get("/api/v1/health")
    assert "X-Trace-Id" in r.headers

def test_rate_limit():
    r = client.get("/api/v1/health")
    assert "X-RateLimit-Limit" in r.headers

def test_register():
    r = client.post("/api/v1/auth/register", json={"phone":"13800138000","password":"Test123456","name":"u"})
    assert r.status_code == 201

def test_dup():
    r = client.post("/api/v1/auth/register", json={"phone":"13800138000","password":"Test123456","name":"u"})
    assert r.status_code == 409

def test_login():
    r = client.post("/api/v1/auth/login", json={"phone":"13800138000","password":"Test123456"})
    assert r.status_code == 200
    assert "access_token" in r.json()

def test_wrong():
    r = client.post("/api/v1/auth/login", json={"phone":"13800138000","password":"x"})
    assert r.status_code == 401

def test_me_ok():
    r = client.post("/api/v1/auth/login", json={"phone":"13800138000","password":"Test123456"})
    t = r.json()["access_token"]
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {t}"})
    assert r.status_code == 200

def test_me_denied():
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 403

def test_i18n():
    r = client.post("/api/v1/auth/login", json={"phone":"9","password":"x"}, headers={"Accept-Language":"en"})
    assert r.status_code == 401

def test_error_trace():
    r = client.post("/api/v1/auth/login", json={"phone":"9","password":"x"})
    assert "X-Trace-Id" in r.headers
