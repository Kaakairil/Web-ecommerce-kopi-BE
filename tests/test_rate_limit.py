"""Rate limiting tests: token bucket per (ip, class)."""
from unittest.mock import patch

import pytest

from app.middleware.rate_limit import limit, reset_buckets


@pytest.fixture(autouse=True)
def _clean_buckets():
    reset_buckets()
    yield
    reset_buckets()


def test_sixth_login_from_same_ip_is_429_with_retry_after(client, mock_db):
    from werkzeug.security import generate_password_hash
    from app.models.user import User

    row = {
        "id": 1, "username": "budi", "email": "budi@example.com",
        "password_hash": generate_password_hash("password123"),
        "is_admin": False,
    }
    with patch.object(User, "get_by_username", return_value=row), patch.object(
        User, "check_password", return_value=True
    ), patch.object(User, "store_refresh_token", return_value={"id": 1}):
        last = None
        for _ in range(6):
            last = client.post(
                "/api/v1/login", json={"username": "budi", "password": "password123"}
            )
    assert last.status_code == 429
    assert "Retry-After" in last.headers
    body = last.get_json()
    assert body["status"] == "error"


def test_different_ip_unaffected(client, mock_db):
    from werkzeug.security import generate_password_hash
    from app.models.user import User

    row = {
        "id": 1, "username": "budi", "email": "budi@example.com",
        "password_hash": generate_password_hash("password123"),
        "is_admin": False,
    }
    with patch.object(User, "get_by_username", return_value=row), patch.object(
        User, "check_password", return_value=True
    ), patch.object(User, "store_refresh_token", return_value={"id": 1}):
        for _ in range(5):
            client.post(
                "/api/v1/login",
                json={"username": "budi", "password": "password123"},
                environ_base={"REMOTE_ADDR": "10.0.0.1"},
            )
        other = client.post(
            "/api/v1/login",
            json={"username": "budi", "password": "password123"},
            environ_base={"REMOTE_ADDR": "10.0.0.2"},
        )
    assert other.status_code == 200


def test_limit_decorator_returns_429_after_capacity():
    from flask import Flask

    app = Flask(__name__)
    reset_buckets()

    @app.route("/probe")
    @limit("auth")
    def probe():
        return {"status": "success"}

    with app.test_client() as c:
        for _ in range(5):
            assert c.get("/probe").status_code == 200
        r6 = c.get("/probe")
        assert r6.status_code == 429
        assert "Retry-After" in r6.headers
