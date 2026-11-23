"""Observability tests: request IDs, JSON access logs, /health /ready /metrics."""
import json
import logging
from unittest.mock import patch


def test_two_requests_get_distinct_request_ids(client):
    r1 = client.get("/api/v1/")
    r2 = client.get("/api/v1/")
    id1 = r1.headers.get("X-Request-ID")
    id2 = r2.headers.get("X-Request-ID")
    assert id1 and id2
    assert id1 != id2


def test_inbound_request_id_is_echoed(client):
    resp = client.get("/api/v1/", headers={"X-Request-ID": "my-trace-42"})
    assert resp.headers.get("X-Request-ID") == "my-trace-42"


def test_access_log_is_one_parseable_json_line(client, caplog):
    with caplog.at_level(logging.INFO, logger="koma.access"):
        client.get("/api/v1/")
    json_lines = [
        rec.getMessage()
        for rec in caplog.records
        if rec.name == "koma.access"
    ]
    assert json_lines, "no access-log record emitted"
    entry = json.loads(json_lines[-1])
    for key in (
        "ts", "level", "request_id", "method", "path", "status",
        "duration_ms", "user_id",
    ):
        assert key in entry, f"missing log key {key}"
    assert entry["method"] == "GET"
    assert entry["path"] == "/api/v1/"
    assert entry["status"] == 200
    assert isinstance(entry["duration_ms"], (int, float))


def test_access_log_carries_user_id_when_authed(app, client, mock_db):
    from app.middleware import auth as auth_mod
    from app.middleware.auth import require_auth

    @app.route("/api/v1/_probe_auth")
    @require_auth
    def probe_auth():
        return {"status": "success", "data": None}

    token = auth_mod.make_token({"id": 7, "username": "budi", "is_admin": False})
    with patch("app.access_log.logger") as spy:
        client.get("/api/v1/_probe_auth", headers={"Authorization": f"Bearer {token}"})
    assert spy.info.called
    entry = json.loads(spy.info.call_args[0][0])
    assert entry["user_id"] == 7


class TestSystemRoutes:
    def test_health_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"

    def test_ready_ok_when_supabase_reachable(self, client, mock_db):
        resp = client.get("/api/v1/ready")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        assert body["data"]["supabase"] == "ok"

    def test_ready_503_when_supabase_raises(self, client, mock_db):
        with patch("app.supabase_client.db") as broken_db:
            broken_db.table.side_effect = RuntimeError("boom")
            resp = client.get("/api/v1/ready")
        assert resp.status_code == 503
        body = resp.get_json()
        assert body["status"] == "error"

    def test_metrics_contains_request_counters(self, client):
        client.get("/api/v1/health")
        resp = client.get("/api/v1/metrics")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/plain")
        text = resp.get_data(as_text=True)
        assert "http_requests_total" in text
        assert "http_request_duration_seconds" in text
