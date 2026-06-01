"""Test recommend routes"""

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


def test_recommend_hot():
    """Test hot products recommendation"""
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/recommend/hot")
    assert resp.status_code in (200, 404)


def test_recommend_products():
    """Test products recommendation"""
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/recommend/products")
    assert resp.status_code in (200, 404)


def test_recommend_feedback():
    """Test recommendation feedback"""
    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/recommend/feedback", json={"product_id": 1, "action": "like"})
    assert resp.status_code in (200, 401, 422)
