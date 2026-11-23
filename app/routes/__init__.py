"""API v1 blueprint aggregation."""
from flask import Blueprint

from app.routes.auth import bp as auth_bp
from app.routes.cart import bp as cart_bp
from app.routes.dashboards import bp as dashboards_bp
from app.routes.products import bp as products_bp
from app.routes.system import bp as system_bp

bp = Blueprint("api", __name__)
bp.register_blueprint(auth_bp)
bp.register_blueprint(cart_bp)
bp.register_blueprint(dashboards_bp)
bp.register_blueprint(products_bp)
bp.register_blueprint(system_bp)


@bp.route("/")
def index():
    return {
        "status": "success",
        "message": "KoMa Coffee API v1",
        "data": {"version": "1.0.0"},
    }
