"""Dashboard + transaction routes.

Admin dashboard aggregates are cached 30s. Customer dashboard and
transaction detail batch product fetches via Product.get_by_ids (N+1
fix). Shapes match the legacy routes the FE was built against.
"""
from datetime import datetime

from flask import Blueprint, g

from app.config import Config
from app.middleware.auth import require_admin, require_auth
from app.middleware.rate_limit import limit
from app.models.cart import Cart, CartItem
from app.models.product import Product
from app.models.stock import Stock
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User
from app.utils import responses
from app.utils.cache import TTLCache

bp = Blueprint("dashboards", __name__)
_cache = TTLCache(ttl_seconds=Config.CACHE_DASHBOARD_TTL)


@bp.route("/admin/dashboard", methods=["GET"])
@limit("read")
@require_admin
def admin_dashboard():
    cached = _cache.get("admin_dashboard")
    if cached is not None:
        return responses.ok(cached)

    transactions = Transaction.get_all()
    today = datetime.utcnow().date().isoformat()
    stats = {
        "total_users": len(User.get_all()),
        "total_products": len(Product.get_all()),
        "total_transactions": len(transactions),
        "today_transactions": len(
            [t for t in transactions if (t.get("created_at") or "").startswith(today)]
        ),
        "low_stock_products": len(
            [
                s
                for s in Stock.get_all()
                if s.get("quantity", 0) <= s.get("min_stock", 10)
            ]
        ),
        "total_revenue": Transaction.sum_total_all(),
        "admin": {
            "id": g.user["id"],
            "username": g.user.get("username"),
        },
        "dashboard_updated": datetime.utcnow().isoformat(),
    }
    _cache.set("admin_dashboard", stats)
    return responses.ok(stats, "Admin dashboard data")


@bp.route("/admin/transactions", methods=["GET"])
@limit("read")
@require_admin
def admin_transactions():
    transactions = Transaction.get_all()
    users = {u["id"]: u for u in User.get_all()}
    data = [
        {
            "id": t.get("id"),
            "transaction_code": t.get("transaction_code"),
            "user_id": t.get("user_id"),
            "username": users.get(t.get("user_id"), {}).get("username", "Unknown"),
            "total_amount": float(t.get("total_amount", 0) or 0),
            "status": t.get("status"),
            "payment_method": t.get("payment_method"),
            "shipping_address": t.get("shipping_address"),
            "created_at": t.get("created_at"),
        }
        for t in transactions
    ]
    return responses.ok(data, f"Found {len(data)} transactions")


@bp.route("/customer/dashboard", methods=["GET"])
@limit("read")
@require_auth
def customer_dashboard():
    if g.user.get("is_admin"):
        return responses.forbidden("Customer access required")

    user_id = g.user["id"]
    cart = Cart.get_by_user_id(user_id)
    item_count = 0
    cart_total = 0
    product_ids = []
    items = CartItem.get_by_cart_id(cart["id"]) if cart else []
    for i in items:
        item_count += i.get("quantity", 0)
        product_ids.append(i["product_id"])

    products = {p["id"]: p for p in Product.get_by_ids(product_ids)} if product_ids else {}
    for i in items:
        p = products.get(i["product_id"])
        if p and p.get("price"):
            cart_total += float(p["price"]) * i.get("quantity", 0)

    recent = Transaction.get_recent_by_user(user_id, limit=5)
    data = {
        "customer": {
            "id": user_id,
            "username": g.user.get("username"),
        },
        "total_orders": Transaction.count_by_user(user_id),
        "total_spent": Transaction.sum_total_by_user(user_id),
        "recent_transactions": [
            {
                "id": t.get("id"),
                "transaction_code": t.get("transaction_code"),
                "total_amount": float(t.get("total_amount", 0) or 0),
                "status": t.get("status"),
                "created_at": t.get("created_at"),
            }
            for t in recent
        ],
        "cart": {"item_count": item_count, "cart_total": cart_total},
        "dashboard_updated": datetime.utcnow().isoformat(),
    }
    return responses.ok(data, "Customer dashboard data")


@bp.route("/transactions/<int:transaction_id>", methods=["GET"])
@limit("read")
@require_auth
def transaction_detail(transaction_id):
    txn = Transaction.get_by_id(transaction_id)
    if not txn:
        return responses.not_found("Transaction not found")
    if not g.user.get("is_admin") and txn.get("user_id") != g.user["id"]:
        return responses.forbidden("Unauthorized")

    items = TransactionItem.get_by_transaction_id(transaction_id)
    products = {
        p["id"]: p
        for p in Product.get_by_ids([i["product_id"] for i in items])
    } if items else {}
    item_data = [
        {
            "id": it.get("id"),
            "product_id": it.get("product_id"),
            "product_name": products.get(it.get("product_id"), {}).get("name"),
            "image_url": products.get(it.get("product_id"), {}).get("image_url"),
            "quantity": it.get("quantity"),
            "price": float(it.get("price", 0) or 0),
            "subtotal": float(it.get("subtotal", 0) or 0),
        }
        for it in items
    ]
    txn_data = {
        "id": txn.get("id"),
        "transaction_code": txn.get("transaction_code"),
        "user_id": txn.get("user_id"),
        "total_amount": float(txn.get("total_amount", 0) or 0),
        "status": txn.get("status"),
        "payment_method": txn.get("payment_method"),
        "shipping_address": txn.get("shipping_address"),
        "notes": txn.get("notes"),
        "created_at": txn.get("created_at"),
        "items": item_data,
    }
    return responses.ok(txn_data, "Transaction found")
