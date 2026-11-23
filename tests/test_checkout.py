"""Idempotent checkout service tests (RPC mocked; SQL lives in Task 12 CI)."""
from unittest.mock import patch

import pytest

from app import supabase_client

RPC_OK = {
    "ok": True,
    "shipping_fee": 15000,
    "transaction": {
        "id": 55,
        "transaction_code": "TRX-20261123-ABC123",
        "user_id": 7,
        "total_amount": 100000,
        "status": "pending",
    },
}

RPC_REPLAY = {
    "ok": True,
    "idempotent_replay": True,
    "transaction": RPC_OK["transaction"],
}

RPC_NO_STOCK = {
    "ok": False,
    "error": "INSUFFICIENT_STOCK",
    "product": "Gayo Honey",
    "available": 1,
}


@pytest.fixture()
def user_token():
    from app.middleware import auth as auth_mod

    token = auth_mod.make_token({"id": 7, "username": "budi", "is_admin": False})
    return {"Authorization": f"Bearer {token}"}


def test_checkout_with_key_creates_transaction_via_rpc(client, mock_db, user_token):
    with patch.object(supabase_client.db, "rpc", return_value=RPC_OK) as rpc_spy:
        resp = client.post(
            "/api/v1/cart/checkout",
            json={"payment_method": "Bank Transfer", "shipping_address": "Jl. Mawar 1"},
            headers={**user_token, "Idempotency-Key": "key-1"},
        )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["status"] == "success"
    data = body["data"]
    assert data["transaction_code"] == "TRX-20261123-ABC123"
    assert data["transaction_id"] == 55
    assert data["total_amount"] == 100000  # RPC number verbatim (incl. shipping)
    assert data["shipping_fee"] == 15000
    assert data["status"] == "pending"
    assert "idempotent_replay" not in data or data.get("idempotent_replay") is not True
    rpc_spy.assert_called_once_with(
        "checkout_transaction",
        {"payload": {
            "user_id": 7,
            "idempotency_key": "key-1",
            "payment_method": "Bank Transfer",
            "shipping_address": "Jl. Mawar 1",
            "notes": None,
        }},
    )


def test_second_call_same_key_replays_without_rpc(client, mock_db, user_token):
    with patch.object(supabase_client.db, "rpc", return_value=RPC_OK) as rpc_spy:
        r1 = client.post(
            "/api/v1/cart/checkout",
            json={},
            headers={**user_token, "Idempotency-Key": "key-2"},
        )
        r2 = client.post(
            "/api/v1/cart/checkout",
            json={},
            headers={**user_token, "Idempotency-Key": "key-2"},
        )
    assert r1.status_code == 201
    rpc_spy.assert_called_once()  # replay must not re-call the RPC
    assert r2.status_code == 200
    body = r2.get_json()
    assert body["data"]["idempotent_replay"] is True
    assert body["data"]["transaction_code"] == "TRX-20261123-ABC123"


def test_missing_idempotency_key_400(client, mock_db, user_token):
    resp = client.post(
        "/api/v1/cart/checkout", json={}, headers=user_token
    )
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"


def test_insufficient_stock_409_and_rpc_payload_untouched(client, mock_db, user_token):
    with patch.object(supabase_client.db, "rpc", return_value=RPC_NO_STOCK) as rpc_spy:
        resp = client.post(
            "/api/v1/cart/checkout",
            json={},
            headers={**user_token, "Idempotency-Key": "key-3"},
        )
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["status"] == "error"
    assert body["data"]["error"] == "INSUFFICIENT_STOCK"
    assert body["data"]["product"] == "Gayo Honey"
    rpc_spy.assert_called_once()  # no retry, no mutation


def test_rpc_error_500(client, mock_db, user_token):
    with patch.object(supabase_client.db, "rpc", side_effect=RuntimeError("db down")):
        resp = client.post(
            "/api/v1/cart/checkout",
            json={},
            headers={**user_token, "Idempotency-Key": "key-4"},
        )
    assert resp.status_code == 500
    assert resp.get_json()["status"] == "error"
