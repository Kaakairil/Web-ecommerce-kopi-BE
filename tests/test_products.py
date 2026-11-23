"""Products routes: batch stock fetch, TTL cache, ETag, admin guard."""
from unittest.mock import patch

import pytest

from app.utils.cache import TTLCache

PRODUCT_ROW = {
    "id": 1,
    "name": "Gayo Honey",
    "description": "Sweet Gayo process honey",
    "price": 85000.0,
    "original_price": None,
    "category": "beans",
    "image_url": None,
    "is_available": True,
    "is_featured": False,
    "is_discounted": False,
    "discount_percentage": 0,
    "rating": 4.5,
    "specifications": None,
    "weight": "200g",
    "type": "beans",
    "origin": "Aceh",
    "process": "honey",
    "roast_level": "medium",
    "flavor_notes": "caramel, orange",
    "brewing_methods": None,
    "grade": None,
    "certification": None,
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
}

STOCK_ROW = {"id": 1, "product_id": 1, "quantity": 12, "min_stock": 5}


def _admin_token(app):
    from app.middleware import auth as auth_mod

    return auth_mod.make_token({"id": 1, "username": "admin", "is_admin": True})


@pytest.fixture()
def fresh_cache(monkeypatch):
    """Give each test an empty products cache."""
    c = TTLCache(ttl_seconds=60)
    monkeypatch.setattr("app.routes.products._cache", c)
    return c


def test_get_products_joins_stock_with_one_batch_call(client, mock_db, fresh_cache):
    from app.models.product import Product
    from app.models.stock import Stock

    with patch.object(Product, "get_available", return_value=[PRODUCT_ROW]),          patch.object(Stock, "get_all", return_value=[STOCK_ROW]) as stock_spy:
        resp = client.get("/api/v1/products")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "success"
    item = body["data"][0]
    assert item["id"] == 1
    assert item["stock"] == 12
    assert item["specs"] == []
    assert item["spec_meta"] == {}
    assert stock_spy.call_count == 1  # one batch call, not N


def test_second_get_within_ttl_hits_cache(client, mock_db, fresh_cache):
    from app.models.product import Product
    from app.models.stock import Stock

    with patch.object(
        Product, "get_available", return_value=[PRODUCT_ROW]
    ) as prod_spy, patch.object(Stock, "get_all", return_value=[STOCK_ROW]) as stock_spy:
        r1 = client.get("/api/v1/products")
        r2 = client.get("/api/v1/products")
    assert r1.status_code == 200 and r2.status_code == 200
    assert prod_spy.call_count == 1  # second GET served from cache
    assert stock_spy.call_count == 1
    assert r1.get_json()["data"] == r2.get_json()["data"]


def test_etag_revalidate_returns_304(client, mock_db, fresh_cache):
    from app.models.product import Product
    from app.models.stock import Stock

    with patch.object(Product, "get_available", return_value=[PRODUCT_ROW]), \
         patch.object(Stock, "get_all", return_value=[STOCK_ROW]):
        r1 = client.get("/api/v1/products")
    etag = r1.headers.get("ETag")
    assert etag
    r2 = client.get("/api/v1/products", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.get_data() == b""


def test_store_without_admin_is_403(client, mock_db):
    from app.middleware import auth as auth_mod

    token = auth_mod.make_token({"id": 2, "username": "budi", "is_admin": False})
    resp = client.post(
        "/api/v1/products",
        json={"name": "X", "price": 10000},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_store_with_admin_creates_and_invalidates_cache(client, mock_db, fresh_cache):
    from app.models.product import Product
    from app.models.stock import Stock

    fresh_cache.set("products", [{"id": 999}])
    token = _admin_token(client)
    created = {**PRODUCT_ROW, "id": 2, "name": "New"}
    with patch.object(Product, "create", return_value=created), \
         patch.object(Stock, "create", return_value={**STOCK_ROW, "product_id": 2}) as stock_create, \
         patch.object(Stock, "get_by_product_id", return_value={**STOCK_ROW, "product_id": 2}):
        resp = client.post(
            "/api/v1/products",
            json={"name": "New", "price": 50000, "stock": 3},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    assert resp.get_json()["data"]["id"] == 2
    stock_create.assert_called_once()
    assert fresh_cache.get("products") is None  # cache invalidated


def test_show_single_product(client, mock_db, fresh_cache):
    from app.models.product import Product
    from app.models.stock import Stock

    with patch.object(Product, "get_by_id", return_value=PRODUCT_ROW), \
         patch.object(Stock, "get_by_product_id", return_value=STOCK_ROW):
        resp = client.get("/api/v1/products/1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["data"]["id"] == 1
    assert body["data"]["stock"] == 12
    assert body["data"]["min_stock"] == 5


def test_show_missing_product_404(client, mock_db, fresh_cache):
    from app.models.product import Product

    with patch.object(Product, "get_by_id", return_value=None):
        resp = client.get("/api/v1/products/999")
    assert resp.status_code == 404


def test_activate_reactivates_product(client, mock_db, fresh_cache):
    from app.models.product import Product

    fresh_cache.set("products", [{"id": 999}])
    token = _admin_token(client)
    row = {**PRODUCT_ROW, "is_available": False}
    with patch.object(Product, "get_by_id", return_value=row), \
         patch.object(Product, "update", return_value={**row, "is_available": True}) as upd:
        resp = client.put(
            "/api/v1/products/1/activate",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    upd.assert_called_once_with(1, {"is_available": True})
    assert fresh_cache.get("products") is None
