"""JWT auth: token issuance/verification + route decorators.

Replaces the old X-User-ID trust model. Tokens are HS256, 15-min TTL,
claims: sub (user id), username, is_admin.
"""
import secrets
import time
from datetime import datetime, timezone
from functools import wraps

import jwt as pyjwt
from flask import g, request

from app.utils import responses

TOKEN_TTL_SECONDS = 900  # 15 minutes
REFRESH_TTL_SECONDS = 30 * 24 * 3600  # 30 days


class AuthError(Exception):
    """Raised when a token is missing, expired, or invalid."""


def _secret() -> str:
    import os

    return os.environ.get("SECRET_KEY", "dev-secret-change-me")


def make_token(user: dict) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user["id"]),
        "username": user.get("username"),
        "is_admin": bool(user.get("is_admin")),
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
    return pyjwt.encode(payload, _secret(), algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        claims = pyjwt.decode(token, _secret(), algorithms=["HS256"])
    except pyjwt.ExpiredSignatureError as e:
        raise AuthError("Token expired") from e
    except pyjwt.InvalidTokenError as e:
        raise AuthError("Invalid token") from e
    return claims


def _bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[len("Bearer ") :].strip() or None
    return None


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _bearer_token()
        if not token:
            return responses.unauthorized("Authorization Bearer token required")
        try:
            claims = decode_token(token)
        except AuthError as e:
            return responses.unauthorized(str(e))
        g.user = {
            "id": int(claims["sub"]),
            "username": claims.get("username"),
            "is_admin": bool(claims.get("is_admin")),
        }
        return fn(*args, **kwargs)

    return wrapper


def require_admin(fn):
    @wraps(fn)
    @require_auth
    def wrapper(*args, **kwargs):
        if not g.user.get("is_admin"):
            return responses.forbidden("Admin access required")
        return fn(*args, **kwargs)

    return wrapper


# --- refresh tokens ---------------------------------------------------------

def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def refresh_token_hash(token: str) -> str:
    from werkzeug.security import generate_password_hash

    return generate_password_hash(token)


def refresh_token_expires_at() -> str:
    from datetime import timedelta

    return (
        datetime.now(timezone.utc) + timedelta(seconds=REFRESH_TTL_SECONDS)
    ).isoformat()
