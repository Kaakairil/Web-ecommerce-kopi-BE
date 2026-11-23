"""Auth routes: register, login, refresh, logout."""
from flask import Blueprint, request

from app.middleware import auth as auth_mod
from app.models.user import User
from app.utils import responses

bp = Blueprint("auth", __name__)

MIN_PASSWORD_LEN = 8


@bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not email or not password:
        return responses.bad_request("username, email, and password are required")
    if len(password) < MIN_PASSWORD_LEN:
        return responses.bad_request("Password must be at least 8 characters")
    if User.get_by_email(email):
        return responses.conflict("Email already registered")
    if User.get_by_username(username):
        return responses.conflict("Username already taken")

    # Security: is_admin is NEVER accepted from the client. Admins are
    # promoted via scripts/seed_admin.py.
    user = User.create({**data, "username": username, "email": email, "is_admin": False})
    if not user:
        return responses.server_error("Failed to create user")
    return responses.created(
        {"id": user["id"], "username": user["username"], "email": user["email"]},
        "Registration successful",
    )


@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    if not password:
        return responses.bad_request("Password is required")

    user = None
    if data.get("email"):
        user = User.get_by_email(data["email"].strip().lower())
    elif data.get("username"):
        user = User.get_by_username(data["username"].strip())
    if not user or not User.check_password(user, password):
        return responses.unauthorized("Invalid credentials")

    token = auth_mod.make_token(user)
    refresh = auth_mod.generate_refresh_token()
    stored = User.store_refresh_token(user["id"], refresh)
    if not stored:
        return responses.server_error("Failed to create session")
    return responses.ok(
        {
            "access_token": token,
            "refresh_token": refresh,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "is_admin": bool(user.get("is_admin")),
            },
        },
        "Login successful",
    )


@bp.route("/refresh", methods=["POST"])
def refresh():
    data = request.get_json(silent=True) or {}
    presented = data.get("refresh_token")
    if not presented:
        return responses.bad_request("refresh_token is required")
    result = User.rotate_refresh_token(presented)
    if not result:
        return responses.unauthorized("Invalid or expired refresh token")
    user, new_refresh = result
    return responses.ok(
        {
            "access_token": auth_mod.make_token(user),
            "refresh_token": new_refresh,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "is_admin": bool(user.get("is_admin")),
            },
        },
        "Token refreshed",
    )


@bp.route("/logout", methods=["POST"])
def logout():
    data = request.get_json(silent=True) or {}
    presented = data.get("refresh_token")
    if presented:
        User.revoke_refresh_token(presented)
    return responses.ok(None, "Logged out")
