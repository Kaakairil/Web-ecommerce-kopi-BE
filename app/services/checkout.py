"""Idempotent checkout: calls the checkout_transaction RPC, stores the
first result per idempotency key, replays it on retries.

The RPC (db/migrations/0005) owns stock locking, shipping (15k < 250k,
free above), transaction + items + order.created outbox insert, and cart
clearing — atomically.
"""
from app import supabase_client

# In-process idempotency store: key -> (body, status). Single-process
# scope; the DB-side unique index on transactions.idempotency_key is the
# durable guarantee (ponytail: swap for a redis/table-backed store when
# this runs multi-process).
_stored = {}


def get_stored_result(key: str):
    return _stored.get(key)


def run_checkout(user: dict, key: str, form: dict):
    """Returns (response_body, status_code)."""
    stored = _stored.get(key)
    if stored is not None:
        body, status = stored
        replay = dict(body)
        replay["data"] = {**body["data"], "idempotent_replay": True}
        return replay, 200

    payload = {
        "user_id": user["id"],
        "idempotency_key": key,
        "payment_method": form.get("payment_method"),
        "shipping_address": form.get("shipping_address"),
        "notes": form.get("notes"),
    }
    try:
        result = supabase_client.db.rpc("checkout_transaction", {"payload": payload})
    except Exception:
        return (
            {"status": "error", "message": "Checkout failed", "data": None},
            500,
        )

    if not result.get("ok"):
        err = result.get("error", "CHECKOUT_FAILED")
        data = {k: v for k, v in result.items() if k != "ok"}
        return (
            {
                "status": "error",
                "message": f"Checkout failed: {err}",
                "data": data,
            },
            409,
        )

    txn = result.get("transaction", {})
    shipping = result.get("shipping_fee", 0)
    data = {
        "transaction_id": txn.get("id"),
        "transaction_code": txn.get("transaction_code"),
        "total_amount": txn.get("total_amount"),
        "shipping_fee": shipping,
        "status": txn.get("status"),
        "item_count": txn.get("item_count"),
    }
    if result.get("idempotent_replay"):
        data["idempotent_replay"] = True
    body = {"status": "success", "message": "Checkout successful", "data": data}
    status = 200 if result.get("idempotent_replay") else 201
    _stored[key] = (body, status)
    return body, status
