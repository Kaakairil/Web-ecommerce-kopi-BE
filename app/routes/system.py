"""System routes: /health, /ready, /metrics."""
from flask import Blueprint, Response, jsonify

from app.access_log import render_metrics
from app import supabase_client

bp = Blueprint("system", __name__)


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "success", "message": "Healthy", "data": None})


@bp.route("/ready", methods=["GET"])
def ready():
    try:
        supabase_client.db.table("users").select("id").limit(1).execute()
        return jsonify(
            {"status": "success", "message": "Ready", "data": {"supabase": "ok"}}
        )
    except Exception:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Dependency check failed",
                    "data": {"supabase": "unreachable"},
                }
            ),
            503,
        )


@bp.route("/metrics", methods=["GET"])
def metrics():
    return Response(render_metrics(), mimetype="text/plain")
