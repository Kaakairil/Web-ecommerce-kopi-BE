"""Products routes: index/show/store/update/delete/activate.

Index is cached (60s TTL) and revalidated with an ETag; writes bust the
cache. Stock is joined with one batch fetch, not per-product queries.
"""
import hashlib

from flask import Blueprint, request

from app.config import Config
from app.middleware.auth import require_admin
from app.middleware.rate_limit import limit
from app.models.product import Product
from app.models.stock import Stock
from app.utils import responses
from app.utils.cache import TTLCache
from app.utils.serialize import single_transform, transform

bp = Blueprint("products", __name__)
_cache = TTLCache(ttl_seconds=Config.CACHE_PRODUCTS_TTL)


def _invalidate() -> None:
    _cache.invalidate("products")


def _stock_map() -> dict:
    return {s["product_id"]: s for s in Stock.get_all()}


@bp.route("/products", methods=["GET"])
@limit("read")
def index():
    cached = _cache.get("products")
    if cached is not None:
        payload = cached
    else:
        products = Product.get_available()
        payload = transform(products, _stock_map())
        _cache.set("products", payload)

    etag = f'"{hashlib.md5(str(payload).encode()).hexdigest()}"'
    if request.headers.get("If-None-Match") == etag:
        resp = responses.not_modified()
    else:
        body, code = responses.ok(payload)
        resp = body
        resp.status_code = code
    resp.headers["ETag"] = etag
    return resp


@bp.route("/products/<int:product_id>", methods=["GET"])
@limit("read")
def show(product_id):
    product = Product.get_by_id(product_id)
    if not product:
        return responses.not_found("Product not found")
    return responses.ok(single_transform(product, Stock.get_by_product_id(product_id)))


@bp.route("/products", methods=["POST"])
@limit("write")
@require_admin
def store():
    data = request.get_json(silent=True) or {}
    product = Product.create(data)
    if not product:
        return responses.server_error("Failed to create product")
    if data.get("stock") is not None:
        Stock.create({"product_id": product["id"], "quantity": int(data["stock"])})
    _invalidate()
    return responses.created(single_transform(product, Stock.get_by_product_id(product["id"])))


@bp.route("/products/<int:product_id>", methods=["PUT"])
@limit("write")
@require_admin
def update(product_id):
    data = request.get_json(silent=True) or {}
    product = Product.update(product_id, data)
    if not product:
        return responses.not_found("Product not found")
    _invalidate()
    return responses.ok(single_transform(product, Stock.get_by_product_id(product_id)))


@bp.route("/products/<int:product_id>", methods=["DELETE"])
@limit("write")
@require_admin
def delete(product_id):
    product = Product.get_by_id(product_id)
    if not product:
        return responses.not_found("Product not found")
    Stock.delete_by_product_id(product_id)
    Product.delete(product_id)
    _invalidate()
    return responses.ok(None, "Product deleted")


@bp.route("/products/<int:product_id>/activate", methods=["PUT"])
@limit("write")
@require_admin
def activate(product_id):
    product = Product.get_by_id(product_id)
    if not product:
        return responses.not_found("Product not found")
    if product.get("is_available"):
        return responses.ok(
            {"id": product_id, "name": product["name"], "status": "active"},
            "Product is already active",
        )
    Product.update(product_id, {"is_available": True})
    _invalidate()
    return responses.ok(
        {"id": product_id, "name": product["name"], "status": "active"},
        "Product reactivated",
    )
