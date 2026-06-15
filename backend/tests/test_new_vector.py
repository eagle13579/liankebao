"""Test vector search routes"""

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


def test_vector_search():
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/search/vector?q=test")
    assert resp.status_code in (200, 404)


def test_vector_rebuild():
    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/search/vector/rebuild")
    assert resp.status_code in (200, 401, 405)
