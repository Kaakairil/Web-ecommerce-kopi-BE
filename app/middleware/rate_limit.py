"""Rate limiting: stdlib token bucket per (ip, class).

Classes: auth 5/min, write 30/min, read 120/min. 429 responses carry a
Retry-After header. Buckets refill continuously from the last request.
"""
import threading
import time
from functools import wraps

from flask import g, jsonify, request

CLASSES = {
    "auth": (5, 60),      # 5 requests per 60s
    "write": (30, 60),    # 30 per 60s
    "read": (120, 60),    # 120 per 60s
}

_lock = threading.Lock()
_buckets = {}  # (ip, class) -> (tokens, last_refill_ts)


def reset_buckets() -> None:
    """Test helper: clear all buckets."""
    with _lock:
        _buckets.clear()


def _take(ip: str, bucket_class: str) -> tuple[bool, int]:
    """Try to take one token. Returns (allowed, retry_after_seconds)."""
    capacity, window = CLASSES[bucket_class]
    key = (ip, bucket_class)
    now = time.monotonic()
    with _lock:
        tokens, last = _buckets.get(key, (float(capacity), now))
        elapsed = now - last
        tokens = min(float(capacity), tokens + elapsed * (capacity / window))
        if tokens >= 1:
            _buckets[key] = (tokens - 1, now)
            return True, 0
        # time until one token refills
        retry_after = int((1 - tokens) / (capacity / window)) + 1
        _buckets[key] = (tokens, now)
        return False, retry_after


def limit(bucket_class: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            allowed, retry_after = _take(request.remote_addr or "unknown", bucket_class)
            if not allowed:
                resp = jsonify(
                    {
                        "status": "error",
                        "message": "Too many requests",
                        "data": None,
                        "request_id": g.get("request_id", ""),
                    }
                )
                resp.status_code = 429
                resp.headers["Retry-After"] = str(retry_after)
                return resp
            return fn(*args, **kwargs)

        return wrapper

    return decorator
