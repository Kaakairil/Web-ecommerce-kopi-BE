"""Uniform response envelope: {"status", "message", "data"[, "request_id"]}."""
from flask import g, jsonify


def _envelope(status: str, message: str, data, code: int):
    body = {"status": status, "message": message, "data": data}
    request_id = g.get("request_id")
    if request_id:
        body["request_id"] = request_id
    return jsonify(body), code


def ok(data=None, message: str = "Success"):
    return _envelope("success", message, data, 200)


def created(data=None, message: str = "Created"):
    return _envelope("success", message, data, 201)


def bad_request(message: str = "Bad request", data=None):
    return _envelope("error", message, data, 400)


def unauthorized(message: str = "Unauthorized", data=None):
    return _envelope("error", message, data, 401)


def forbidden(message: str = "Forbidden", data=None):
    return _envelope("error", message, data, 403)


def not_found(message: str = "Not found", data=None):
    return _envelope("error", message, data, 404)


def conflict(message: str = "Conflict", data=None):
    return _envelope("error", message, data, 409)


def too_many(message: str = "Too many requests", retry_after: int = 60, data=None):
    resp, code = _envelope("error", message, data, 429)
    resp.headers["Retry-After"] = str(retry_after)
    return resp, code


def server_error(message: str = "Internal server error", data=None):
    return _envelope("error", message, data, 500)
