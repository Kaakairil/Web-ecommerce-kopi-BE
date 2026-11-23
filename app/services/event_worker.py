"""Event outbox worker: delivers pending events to the webhook URL.

Retry with linear-ish backoff (30s x attempts via next_attempt_at);
5 failed attempts -> status='dead'. Runs as a background thread when
WEBHOOK_URL is set (wired in the app factory).
"""
import hashlib
import hmac
import json
import os
import threading
import time

POLL_INTERVAL_SECONDS = 5
BACKOFF_SECONDS = 30


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _update_event(db, event_id: str, fields: dict) -> None:
    db.table("events").update(fields).eq("id", event_id).execute()


def fetch_pending(db) -> list:
    result = (
        db.table("events")
        .select("*")
        .eq("status", "pending")
        .execute()
    )
    return result.data or []


def deliver_pending_events(db, requests_post, stop_event, max_attempts=5,
                           max_cycles=1, webhook_url=None, webhook_secret=None,
                           poll_seconds=POLL_INTERVAL_SECONDS) -> dict:
    """Deliver pending events until stop_event is set or max_cycles done.

    Returns stats {delivered, dead, failed}. Pure-ish: tests inject
    requests_post; the real worker passes requests.post.
    """
    webhook_url = webhook_url if webhook_url is not None else os.environ.get("WEBHOOK_URL")
    webhook_secret = webhook_secret if webhook_secret is not None else os.environ.get("WEBHOOK_SECRET", "")

    stats = {"delivered": 0, "dead": 0, "failed": 0}
    cycles = 0
    while stop_event is None or not stop_event.is_set():
        cycles += 1
        if max_cycles and cycles > max_cycles:
            break
        for event in fetch_pending(db):
            if stop_event is not None and stop_event.is_set():
                break
            if event.get("attempts", 0) >= max_attempts:
                _update_event(db, event["id"], {"status": "dead"})
                stats["dead"] += 1
                continue
            body = json.dumps(
                {"event_type": event["event_type"], "payload": event["payload"]}
            ).encode()
            headers = {"X-KoMa-Signature": _sign(webhook_secret, body)}
            try:
                requests_post(webhook_url, json=json.loads(body), headers=headers,
                              timeout=10)
            except Exception as exc:
                attempts = event.get("attempts", 0) + 1
                fields = {
                    "attempts": attempts,
                    "last_error": str(exc)[:500],
                }
                if attempts >= max_attempts:
                    fields["status"] = "dead"
                    stats["dead"] += 1
                else:
                    fields["next_attempt_at"] = (
                        time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ",
                            time.gmtime(time.time() + BACKOFF_SECONDS * attempts),
                        )
                    )
                    stats["failed"] += 1
                _update_event(db, event["id"], fields)
                continue
            _update_event(
                db, event["id"],
                {"status": "delivered", "delivered_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
            )
            stats["delivered"] += 1
        if stop_event is not None:
            if max_cycles and cycles >= max_cycles:
                break
            stop_event.wait(poll_seconds)
        else:
            # no stop Event: max_cycles is the only budget
            if not max_cycles:
                break  # safety: avoid an unbounded loop
    return stats


def start_worker_thread(db) -> threading.Event:
    """Start the delivery loop in a daemon thread; returns its stop Event."""
    stop = threading.Event()

    def run():
        import requests

        deliver_pending_events(db, requests.post, stop, max_cycles=None)

    thread = threading.Thread(target=run, daemon=True, name="event-worker")
    thread.start()
    return stop
