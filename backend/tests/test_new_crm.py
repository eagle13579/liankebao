"""Test CRM pipeline routes"""

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


def test_pipeline_overview():
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/crm/pipeline")
    assert resp.status_code in (200, 401)


def test_leads_list():
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/crm/leads")
    assert resp.status_code in (200, 401)


def test_lead_detail():
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/crm/leads/1")
    assert resp.status_code in (200, 401, 404)


def test_my_leads():
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/crm/leads/my")
    assert resp.status_code in (200, 401)
