"""Dashboards + transactions routes: RBAC, batch fetch, ownership guard."""
from unittest.mock import patch

import pytest

from app.utils.cache import TTLCache

TXN = {
    "id": 55,
    "transaction_code": "TRX-20261123-ABC123",
    "user_id": 7,
    "total_amount": 100000,
    "status": "pending",
    "payment_method": "Bank Transfer",
    "shipping_address": "Jl. Mawar 1",
    "notes": None,
    "created_at": "2026-11-23T10:00:00",
}

ITEM = {
    "id": 9,
    "transaction_id": 55,
    "product_id": 1,
    "quantity": 2,
    "price": 50000,
    "subtotal": 100000,
}

PRODUCT = {"id": 1, "name": "Gayo Honey", "image_url": None, "price": 50000}


def _token(app, user_id, is_admin):
    from app.middleware import auth as auth_mod

    t = auth_mod.make_token({"id": user_id, "username": "u", "is_admin": is_admin})
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture()
def fresh_cache(monkeypatch):
    c = TTLCache(ttl_seconds=30)
    monkeypatch.setattr("app.routes.dashboards._cache", c)
    return c


# --- customer dashboard -----------------------------------------------------

def test_customer_dashboard_batches_product_fetch(client, mock_db, fresh_cache):
    from app.models.cart import Cart, CartItem
    from app.models.product import Product
    from app.models.transaction import Transaction

    with patch.object(Transaction, "count_by_user", return_value=2), \
         patch.object(Transaction, "sum_total_by_user", return_value=200000), \
         patch.object(Transaction, "get_recent_by_user", return_value=[TXN]), \
         patch.object(Cart, "get_by_user_id", return_value={"id": 10, "user_id": 7}), \
         patch.object(CartItem, "get_by_cart_id",
                      return_value=[{"id": 3, "product_id": 1, "quantity": 2},
                                    {"id": 4, "product_id": 2, "quantity": 1}]), \
         patch.object(Product, "get_by_ids", return_value=[PRODUCT]) as batch_spy:
        resp = client.get(
            "/api/v1/customer/dashboard",
            headers=_token(client, 7, False),
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["data"]["total_orders"] == 2
    assert body["data"]["cart"]["item_count"] == 3
    batch_spy.assert_called_once()  # one batch call, not N


def test_admin_blocked_from_customer_dashboard(client, mock_db, fresh_cache):
    resp = client.get(
        "/api/v1/customer/dashboard", headers=_token(client, 1, True)
    )
    assert resp.status_code == 403


# --- admin dashboard --------------------------------------------------------

def test_admin_dashboard_stats_keys(client, mock_db, fresh_cache):
    from app.models.product import Product
    from app.models.stock import Stock
    from app.models.transaction import Transaction
    from app.models.user import User

    with patch.object(User, "get_all", return_value=[{}, {}, {}]), \
         patch.object(Product, "get_all", return_value=[PRODUCT]), \
         patch.object(Transaction, "get_all", return_value=[TXN]), \
         patch.object(Transaction, "sum_total_all", return_value=100000), \
         patch.object(Stock, "get_all",
                      return_value=[{"quantity": 2, "min_stock": 5},
                                    {"quantity": 20, "min_stock": 10}]):
        resp = client.get(
            "/api/v1/admin/dashboard", headers=_token(client, 1, True)
        )
    assert resp.status_code == 200
    stats = resp.get_json()["data"]
    for key in (
        "total_users", "total_products", "total_transactions",
        "today_transactions", "low_stock_products", "total_revenue",
    ):
        assert key in stats, f"missing {key}"
    assert stats["total_users"] == 3
    assert stats["low_stock_products"] == 1
    assert stats["total_revenue"] == 100000


def test_second_admin_dashboard_within_ttl_uses_cache(client, mock_db, fresh_cache):
    from app.models.product import Product
    from app.models.stock import Stock
    from app.models.transaction import Transaction
    from app.models.user import User

    with patch.object(User, "get_all", return_value=[]), \
         patch.object(Product, "get_all", return_value=[]), \
         patch.object(Transaction, "get_all", return_value=[]), \
         patch.object(Transaction, "sum_total_all", return_value=0), \
         patch.object(Stock, "get_all", return_value=[]) as stock_spy:
        r1 = client.get("/api/v1/admin/dashboard", headers=_token(client, 1, True))
        r2 = client.get("/api/v1/admin/dashboard", headers=_token(client, 1, True))
    assert r1.status_code == 200 and r2.status_code == 200
    assert stock_spy.call_count == 1  # second served from cache


def test_non_admin_on_admin_dashboard_403(client, mock_db, fresh_cache):
    resp = client.get(
        "/api/v1/admin/dashboard", headers=_token(client, 2, False)
    )
    assert resp.status_code == 403


def test_non_admin_on_admin_transactions_403(client, mock_db, fresh_cache):
    resp = client.get(
        "/api/v1/admin/transactions", headers=_token(client, 2, False)
    )
    assert resp.status_code == 403


# --- transactions -----------------------------------------------------------

def test_admin_transactions_lists_with_usernames(client, mock_db, fresh_cache):
    from app.models.transaction import Transaction
    from app.models.user import User

    with patch.object(Transaction, "get_all", return_value=[TXN]), \
         patch.object(User, "get_all", return_value=[{"id": 7, "username": "budi"}]):
        resp = client.get(
            "/api/v1/admin/transactions", headers=_token(client, 1, True)
        )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data[0]["username"] == "budi"
    assert data[0]["transaction_code"] == "TRX-20261123-ABC123"


def test_transaction_detail_owner_ok_with_batch_products(client, mock_db, fresh_cache):
    from app.models.product import Product
    from app.models.transaction import Transaction, TransactionItem

    with patch.object(Transaction, "get_by_id", return_value=TXN), \
         patch.object(TransactionItem, "get_by_transaction_id",
                      return_value=[ITEM]), \
         patch.object(Product, "get_by_ids", return_value=[PRODUCT]) as batch_spy:
        resp = client.get(
            "/api/v1/transactions/55", headers=_token(client, 7, False)
        )
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["items"][0]["product_name"] == "Gayo Honey"
    batch_spy.assert_called_once()


def test_transaction_detail_hidden_from_other_user_403(client, mock_db, fresh_cache):
    from app.models.transaction import Transaction

    with patch.object(Transaction, "get_by_id", return_value=TXN):
        resp = client.get(
            "/api/v1/transactions/55", headers=_token(client, 8, False)
        )
    assert resp.status_code == 403


def test_transaction_detail_missing_404(client, mock_db, fresh_cache):
    from app.models.transaction import Transaction

    with patch.object(Transaction, "get_by_id", return_value=None):
        resp = client.get(
            "/api/v1/transactions/55", headers=_token(client, 7, False)
        )
    assert resp.status_code == 404
