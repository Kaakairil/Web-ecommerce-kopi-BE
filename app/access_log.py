"""Request-ID assignment, access logging, and in-process metrics.

One before/after hook pair drives all three: g.request_id (accepts an
inbound X-Request-ID), one JSON log line per request on the
"koma.access" logger, and Prometheus-style counters/histogram.
"""
import json
import logging
import threading
import time
from collections import defaultdict

from flask import g, request

logger = logging.getLogger("koma.access")

# --- in-process metrics (Prometheus text format) ----------------------------

_metrics_lock = threading.Lock()
_request_counts = defaultdict(int)  # (route, method, status) -> count
_duration_buckets = defaultdict(int)  # (le) -> count
_duration_sum = 0.0
_duration_count = 0
BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, "+Inf"]


def record_request(route: str, method: str, status: int, duration_s: float) -> None:
    global _duration_sum, _duration_count
    with _metrics_lock:
        _request_counts[(route, method, status)] += 1
        for b in BUCKETS:
            if duration_s <= float(b):
                _duration_buckets[b] += 1
                break
        else:
            _duration_buckets["+Inf"] += 1
        _duration_sum += duration_s
        _duration_count += 1


def render_metrics() -> str:
    with _metrics_lock:
        lines = [
            "# HELP http_requests_total Total HTTP requests.",
            "# TYPE http_requests_total counter",
        ]
        for (route, method, status), n in sorted(_request_counts.items()):
            lines.append(
                f'http_requests_total{{route="{route}",method="{method}",'
                f'status="{status}"}} {n}'
            )
        lines += [
            "# HELP http_request_duration_seconds Request duration in seconds.",
            "# TYPE http_request_duration_seconds histogram",
        ]
        cumulative = 0
        for b in BUCKETS:
            if b == "+Inf":
                cumulative = _duration_count
            else:
                cumulative += _duration_buckets[b]
            lines.append(
                f'http_request_duration_seconds_bucket{{le="{b}"}} {cumulative}'
            )
        lines.append(
            f"http_request_duration_seconds_sum {_duration_sum:.6f}"
        )
        lines.append(
            f"http_request_duration_seconds_count {_duration_count}"
        )
        return "\n".join(lines) + "\n"


def route_label() -> str:
    """Path with the matched rule (normalizes IDs, e.g. /products/<id>)."""
    rule = request.url_rule.rule if request.url_rule else "unmatched"
    return rule


def register_observability(app) -> None:
    @app.before_request
    def assign_request_id():
        import uuid

        g.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        g.request_started = time.perf_counter()

    @app.after_request
    def observe_request(resp):
        duration_ms = (time.perf_counter() - g.get("request_started", time.perf_counter())) * 1000
        user = g.get("user")
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": "INFO" if resp.status_code < 500 else "ERROR",
            "request_id": g.get("request_id", ""),
            "method": request.method,
            "path": request.path,
            "status": resp.status_code,
            "duration_ms": round(duration_ms, 2),
            "user_id": user["id"] if user else None,
        }
        logger.info(json.dumps(entry))
        record_request(route_label(), request.method, resp.status_code, duration_ms / 1000)
        return resp
