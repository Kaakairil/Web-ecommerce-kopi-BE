"""Cart routes: get/add(upsert)/update/remove/clear."""
from unittest.mock import patch

import pytest


@pytest.fixture()
def user_token():
    from app.middleware import auth as auth_mod

    token = auth_mod.make_token({"id": 7, "username": "budi", "is_admin": False})
    return {"Authorization": f"Bearer {token}"}


def test_get_cart_empty_creates_nothing_returns_items(client, mock_db, user_token):
    from app.models.cart import Cart, CartItem

    with patch.object(Cart, "get_by_user_id", return_value=None), \
         patch.object(CartItem, "get_by_cart_id", return_value=[]):
        resp = client.get("/api/v1/cart", headers=user_token)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["data"]["items"] == []


def test_add_item_upserts_quantity(client, mock_db, user_token):
    from app.models.cart import Cart, CartItem

    cart = {"id": 10, "user_id": 7}
    with patch.object(Cart, "get_by_user_id", return_value=cart), \
         patch.object(CartItem, "upsert", return_value={"id": 3, "quantity": 2}) as up:
        resp = client.post(
            "/api/v1/cart/add",
            json={"product_id": 1, "quantity": 2},
            headers=user_token,
        )
    assert resp.status_code == 200
    up.assert_called_once_with(10, 1, 2)


def test_add_item_creates_cart_if_missing(client, mock_db, user_token):
    from app.models.cart import Cart, CartItem

    with patch.object(Cart, "get_by_user_id", return_value=None), \
         patch.object(Cart, "create", return_value={"id": 11, "user_id": 7}) as mk, \
         patch.object(CartItem, "upsert", return_value={"id": 1, "quantity": 1}):
        resp = client.post(
            "/api/v1/cart/add",
            json={"product_id": 1, "quantity": 1},
            headers=user_token,
        )
    assert resp.status_code == 200
    mk.assert_called_once_with({"user_id": 7})


def test_update_item_quantity(client, mock_db, user_token):
    from app.models.cart import Cart, CartItem

    cart = {"id": 10, "user_id": 7}
    item = {"id": 3, "cart_id": 10, "product_id": 1, "quantity": 1}
    with patch.object(Cart, "get_by_user_id", return_value=cart), \
         patch.object(CartItem, "get_by_id", return_value=item), \
         patch.object(CartItem, "update", return_value={**item, "quantity": 5}) as upd:
        resp = client.put(
            "/api/v1/cart/items/3", json={"quantity": 5}, headers=user_token
        )
    assert resp.status_code == 200
    upd.assert_called_once_with(3, {"quantity": 5})


def test_update_item_of_other_user_404(client, mock_db, user_token):
    from app.models.cart import Cart, CartItem

    with patch.object(Cart, "get_by_user_id", return_value={"id": 10, "user_id": 7}), \
         patch.object(CartItem, "get_by_id", return_value={"id": 3, "cart_id": 99}):
        resp = client.put(
            "/api/v1/cart/items/3", json={"quantity": 5}, headers=user_token
        )
    assert resp.status_code == 404


def test_remove_item(client, mock_db, user_token):
    from app.models.cart import Cart, CartItem

    with patch.object(Cart, "get_by_user_id", return_value={"id": 10, "user_id": 7}), \
         patch.object(CartItem, "get_by_id", return_value={"id": 3, "cart_id": 10}), \
         patch.object(CartItem, "delete", return_value={"id": 3}) as dele:
        resp = client.delete("/api/v1/cart/items/3", headers=user_token)
    assert resp.status_code == 200
    dele.assert_called_once_with(3)


def test_clear_cart(client, mock_db, user_token):
    from app.models.cart import Cart, CartItem

    with patch.object(Cart, "get_by_user_id", return_value={"id": 10, "user_id": 7}), \
         patch.object(CartItem, "delete_by_cart_id", return_value=[]) as dele:
        resp = client.delete("/api/v1/cart", headers=user_token)
    assert resp.status_code == 200
    dele.assert_called_once_with(10)


def test_cart_requires_auth(client, mock_db):
    resp = client.get("/api/v1/cart")
    assert resp.status_code == 401
