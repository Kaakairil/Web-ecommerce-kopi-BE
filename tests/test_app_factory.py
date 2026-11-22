"""Tests for app factory, response envelope, security headers, TTLCache."""
import time

import pytest

from app import create_app
from app.utils.cache import TTLCache


@pytest.fixture()
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_unknown_route_returns_envelope_with_request_id(client):
    resp = client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["status"] == "error"
    assert "request_id" in body
    assert resp.headers.get("X-Request-ID")


def test_security_headers_present(client):
    resp = client.get("/api/v1/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"


def test_health_route_exists(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "success"


class TestTTLCache:
    def test_set_get_roundtrip(self):
        cache = TTLCache(ttl_seconds=60)
        cache.set("k", {"a": 1})
        assert cache.get("k") == {"a": 1}

    def test_expiry(self):
        cache = TTLCache(ttl_seconds=0.05)
        cache.set("k", "v")
        time.sleep(0.06)
        assert cache.get("k") is None

    def test_invalidate_prefix(self):
        cache = TTLCache(ttl_seconds=60)
        cache.set("products:all", [1, 2])
        cache.set("products:5", {"id": 5})
        cache.set("dashboard:admin", {"x": 1})
        cache.invalidate("products")
        assert cache.get("products:all") is None
        assert cache.get("products:5") is None
        assert cache.get("dashboard:admin") == {"x": 1}
