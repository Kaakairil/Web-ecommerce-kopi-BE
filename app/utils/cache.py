"""Minimal in-process TTL cache with prefix invalidation."""
import time
from threading import Lock


class TTLCache:
    def __init__(self, ttl_seconds: float):
        self.ttl = ttl_seconds
        self._store: dict = {}
        self._lock = Lock()

    def set(self, key: str, value) -> None:
        with self._lock:
            self._store[key] = (value, time.monotonic() + self.ttl)

    def get(self, key: str):
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def invalidate(self, prefix: str) -> None:
        with self._lock:
            self._store = {
                k: v for k, v in self._store.items() if not k.startswith(prefix)
            }
