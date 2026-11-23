import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request, redirect

load_dotenv()

from app.config import Config

try:
    from flask_cors import CORS
except Exception:
    CORS = None

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config())

    os.environ["SUPABASE_URL"] = app.config.get("SUPABASE_URL")
    os.environ["SUPABASE_KEY"] = app.config.get("SUPABASE_KEY")

    if CORS:
        CORS(app, resources={r"/api/*": {"origins": app.config["FE_ORIGINS"]}})

    from app.access_log import register_observability
    from app.routes import bp

    app.register_blueprint(bp, url_prefix="/api/v1")
    register_observability(app)

    # Event outbox worker: only in prod (not when FLASK_DEBUG/testing),
    # and only when a webhook target is configured.
    if (
        os.environ.get("WEBHOOK_URL")
        and not app.config.get("TESTING")
        and os.environ.get("FLASK_DEBUG") != "1"
        and not app.debug
    ):
        from app.services.event_worker import start_worker_thread

        from app.supabase_client import db as supa_db
        start_worker_thread(supa_db)

    @app.after_request
    def add_security_headers(resp):
        from flask import g

        for k, v in SECURITY_HEADERS.items():
            resp.headers.setdefault(k, v)
        resp.headers.setdefault("X-Request-ID", g.get("request_id", ""))
        return resp

    @app.errorhandler(404)
    def not_found(_e):
        from flask import g

        if request.path.startswith("/api/"):
            body = {"status": "error", "message": "Not found", "data": None}
            request_id = g.get("request_id")
            if request_id:
                body["request_id"] = request_id
            return jsonify(body), 404
        return redirect("/api/v1/")

    @app.route("/")
    def root_redirect():
        return redirect("/api/v1/")

    return app
