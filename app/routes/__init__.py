"""API v1 blueprint aggregation."""
from flask import Blueprint

from app.routes.auth import bp as auth_bp
from app.routes.system import bp as system_bp

bp = Blueprint("api", __name__)
bp.register_blueprint(auth_bp)
bp.register_blueprint(system_bp)


@bp.route("/")
def index():
    return {
        "status": "success",
        "message": "KoMa Coffee API v1",
        "data": {"version": "1.0.0"},
    }
