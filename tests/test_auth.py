"""JWT auth flow tests (Supabase mocked)."""
import time
from unittest.mock import patch

import jwt as pyjwt
import pytest


def _mock_user_row(**over):
    row = {
        "id": 1,
        "username": "budi",
        "email": "budi@example.com",
        "phone": None,
        "full_name": "Budi",
        "address": None,
        "city": None,
        "postal_code": None,
        "province": None,
        "password_hash": "hashed",
        "is_admin": False,
        "is_verified": False,
        "email_verified": False,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }
    row.update(over)
    return row


@pytest.fixture()
def auth_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    from app.middleware import auth as auth_mod

    yield auth_mod


# --- middleware unit tests -------------------------------------------------

def test_decode_token_roundtrip(auth_env):
    token = auth_env.make_token({"id": 1, "username": "budi", "is_admin": False})
    claims = auth_env.decode_token(token)
    # PyJWT 2.13 requires sub to be a string on the wire
    assert claims["sub"] == "1"
    assert claims["username"] == "budi"
    assert claims["is_admin"] is False


def test_decode_expired_token_raises(auth_env):
    # PyJWT 2.13 checks expiry against datetime.now(), so patching
    # time.time does not affect it: encode with a past exp directly.
    now = int(time.time())
    token = pyjwt.encode(
        {"sub": "1", "iat": now - 7200, "exp": now - 3600},
        auth_env._secret(),
        algorithm="HS256",
    )
    with pytest.raises(auth_env.AuthError):
        auth_env.decode_token(token)


def test_decode_tampered_token_raises(auth_env):
    token = auth_env.make_token({"id": 1, "username": "budi", "is_admin": False})
    with pytest.raises(auth_env.AuthError):
        auth_env.decode_token(token[:-3] + "abc")


# --- route tests (mocked db) ------------------------------------------------

def test_register_strips_is_admin(client, mock_db):
    stored = {}

    def fake_create(data):
        stored.update(data)
        return _mock_user_row(id=7, username="budi", email="budi@example.com")

    monkey_target = "app.models.user.User.create"
    with patch(monkey_target, side_effect=fake_create), patch(
        "app.models.user.User.get_by_email", return_value=None
    ), patch("app.models.user.User.get_by_username", return_value=None):
        resp = client.post(
            "/api/v1/register",
            json={
                "username": "budi",
                "email": "budi@example.com",
                "password": "password123",
                "is_admin": True,  # must be ignored
            },
        )
    assert resp.status_code == 201
    assert stored.get("is_admin") is False


def test_login_success_returns_decodable_token(client, mock_db, auth_env):
    from werkzeug.security import generate_password_hash
    from app.models.user import User

    row = _mock_user_row(
        password_hash=generate_password_hash("password123")
    )
    with patch.object(User, "get_by_username", return_value=row), patch.object(
        User, "check_password", return_value=True
    ), patch.object(User, "store_refresh_token", return_value={"id": 1}):
        resp = client.post(
            "/api/v1/login", json={"username": "budi", "password": "password123"}
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "success"
    claims = auth_env.decode_token(body["data"]["access_token"])
    assert claims["sub"] == "1"
    assert body["data"]["user"]["id"] == 1


def test_login_wrong_password_401(client, mock_db):
    from app.models.user import User

    row = _mock_user_row()
    with patch.object(User, "get_by_username", return_value=row), patch.object(
        User, "check_password", return_value=False
    ):
        resp = client.post(
            "/api/v1/login", json={"username": "budi", "password": "wrong"}
        )
    assert resp.status_code == 401


def test_login_unknown_user_401(client, mock_db):
    from app.models.user import User

    with patch.object(User, "get_by_username", return_value=None):
        resp = client.post(
            "/api/v1/login", json={"username": "ghost", "password": "x"}
        )
    assert resp.status_code == 401


def test_missing_bearer_401(app, client):
    # any protected probe: register a temporary protected route
    from app.middleware.auth import require_auth
    from app.utils.responses import ok

    @app.route("/api/v1/_probe")
    @require_auth
    def probe():
        return ok({"user": None})

    resp = client.get("/api/v1/_probe")
    assert resp.status_code == 401


def test_forged_token_401(app, client):
    from app.middleware.auth import require_auth
    from app.utils.responses import ok

    @app.route("/api/v1/_probe2")
    @require_auth
    def probe2():
        return ok({})

    resp = client.get(
        "/api/v1/_probe2", headers={"Authorization": "Bearer not.a.jwt"}
    )
    assert resp.status_code == 401


def test_valid_token_sets_g_user(app, client):
    from app.middleware.auth import require_auth, make_token
    from flask import g
    from app.utils.responses import ok

    @app.route("/api/v1/_probe3")
    @require_auth
    def probe3():
        return ok({"uid": g.user["id"], "admin": g.user["is_admin"]})

    token = make_token({"id": 42, "username": "siti", "is_admin": True})
    resp = client.get("/api/v1/_probe3", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.get_json()["data"] == {"uid": 42, "admin": True}


def test_non_admin_blocked_from_admin_route(app, client):
    from app.middleware.auth import require_admin, make_token
    from app.utils.responses import ok

    @app.route("/api/v1/_probe4")
    @require_admin
    def probe4():
        return ok({})

    token = make_token({"id": 42, "username": "siti", "is_admin": False})
    resp = client.get("/api/v1/_probe4", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
