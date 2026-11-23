"""Cart routes: get/add/update/remove/clear/checkout (all authed)."""
from flask import Blueprint, g, request

from app.middleware.auth import require_auth
from app.middleware.rate_limit import limit
from app.models.cart import Cart, CartItem
from app.models.product import Product
from app.services import checkout as checkout_service
from app.utils import responses
from app.utils.serialize import single_transform

bp = Blueprint("cart", __name__)


def _get_or_create_cart():
    cart = Cart.get_by_user_id(g.user["id"])
    if not cart:
        cart = Cart.create({"user_id": g.user["id"]})
    return cart


def _cart_payload(cart):
    items = CartItem.get_by_cart_id(cart["id"])
    enriched = []
    total = 0
    for item in items:
        product = Product.get_by_id(item["product_id"])
        data = single_transform(product, {"quantity": item["quantity"]}) if product else {
            "id": item["product_id"], "name": None, "price": 0,
        }
        data["quantity"] = item["quantity"]
        data["cart_item_id"] = item["id"]
        data["subtotal"] = (data.get("price") or 0) * item["quantity"]
        total += data["subtotal"]
        enriched.append(data)
    return {"cart_id": cart["id"], "items": enriched, "subtotal": total}


@bp.route("/cart", methods=["GET"])
@limit("read")
@require_auth
def get_cart():
    cart = Cart.get_by_user_id(g.user["id"])
    if not cart:
        return responses.ok({"cart_id": None, "items": [], "subtotal": 0})
    return responses.ok(_cart_payload(cart))


@bp.route("/cart/add", methods=["POST"])
@limit("write")
@require_auth
def add_item():
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    quantity = data.get("quantity", 1)
    if not product_id or int(quantity) < 1:
        return responses.bad_request("product_id and positive quantity are required")
    cart = _get_or_create_cart()
    item = CartItem.upsert(cart["id"], int(product_id), int(quantity))
    return responses.ok({"cart_item": item}, "Added to cart")


@bp.route("/cart/items/<int:item_id>", methods=["PUT"])
@limit("write")
@require_auth
def update_item(item_id):
    data = request.get_json(silent=True) or {}
    quantity = data.get("quantity")
    if quantity is None or int(quantity) < 1:
        return responses.bad_request("positive quantity is required")
    cart = Cart.get_by_user_id(g.user["id"])
    item = CartItem.get_by_id(item_id)
    if not cart or not item or item["cart_id"] != cart["id"]:
        return responses.not_found("Cart item not found")
    return responses.ok({"cart_item": CartItem.update(item_id, {"quantity": int(quantity)})})


@bp.route("/cart/items/<int:item_id>", methods=["DELETE"])
@limit("write")
@require_auth
def remove_item(item_id):
    cart = Cart.get_by_user_id(g.user["id"])
    item = CartItem.get_by_id(item_id)
    if not cart or not item or item["cart_id"] != cart["id"]:
        return responses.not_found("Cart item not found")
    CartItem.delete(item_id)
    return responses.ok(None, "Item removed")


@bp.route("/cart", methods=["DELETE"])
@limit("write")
@require_auth
def clear_cart():
    cart = Cart.get_by_user_id(g.user["id"])
    if cart:
        CartItem.delete_by_cart_id(cart["id"])
    return responses.ok(None, "Cart cleared")


@bp.route("/cart/checkout", methods=["POST"])
@limit("write")
@require_auth
def checkout():
    idem_key = request.headers.get("Idempotency-Key")
    if not idem_key:
        return responses.bad_request("Idempotency-Key header is required")
    form = request.get_json(silent=True) or {}
    body, status = checkout_service.run_checkout(g.user, idem_key, form)
    return responses._envelope(
        body["status"], body["message"], body["data"], status
    )
