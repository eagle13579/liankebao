"""Test enrichment routes"""

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


def test_enrich_company():
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/enrich/company?name=字节跳动")
    assert resp.status_code in (200, 401)


def test_enrich_contacts():
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/enrich/contacts?company=阿里巴巴")
    assert resp.status_code in (200, 401)
