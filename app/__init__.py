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

    from app.routes import bp

    app.register_blueprint(bp, url_prefix="/api/v1")

    @app.before_request
    def assign_request_id():
        from flask import g
        import uuid

        g.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

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
