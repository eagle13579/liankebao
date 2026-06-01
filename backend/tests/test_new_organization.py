"""Test organization routes"""

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


def test_orgs_list():
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/orgs")
    assert resp.status_code in (200, 401)


def test_org_create():
    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/orgs", json={"name": "测试组织"})
    assert resp.status_code in (200, 401, 422)
