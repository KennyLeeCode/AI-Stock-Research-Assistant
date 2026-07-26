"""A small thread-safe in-process TTL cache.

Why this exists:
  1. The free Alpha Vantage tier allows only ~25 requests/day. Without caching,
     a single dashboard load (quote + history + overview + news) would burn four
     of them.
  2. AI research reports are expensive to generate and stable over short
     windows, so identical requests should not be re-billed.

It is deliberately a plain dict behind a lock rather than Redis: the interface
(`get` / `set` / `invalidate`) is narrow enough that swapping in a shared cache
later means rewriting only this file.

Entries carry a monotonic expiry so a system clock change cannot resurrect or
prematurely kill them.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class _Entry:
    """A cached value together with the monotonic time at which it expires."""

    value: Any
    expires_at: float


class TTLCache:
    """A thread-safe mapping whose entries expire after a per-key TTL."""

    def __init__(self, *, max_entries: int = 512) -> None:
        self._store: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries

    # -- reads ------------------------------------------------------------
    def get(self, key: str) -> Any | None:
        """Return the cached value for `key`, or None if absent or expired."""
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                # Expired: drop it so the dict does not grow unbounded.
                del self._store[key]
                return None
            return entry.value

    # -- writes -----------------------------------------------------------
    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store `value` under `key` for `ttl_seconds`.

        A non-positive TTL is treated as "do not cache", which lets callers
        disable caching by configuration without branching at the call site.
        """
        if ttl_seconds <= 0:
            return
        expires_at = time.monotonic() + ttl_seconds
        with self._lock:
            if len(self._store) >= self._max_entries and key not in self._store:
                self._evict_locked(now=time.monotonic())
            self._store[key] = _Entry(value=value, expires_at=expires_at)

    def invalidate(self, key: str) -> None:
        """Remove a single key if present."""
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> int:
        """Remove every key starting with `prefix`. Returns the count removed."""
        with self._lock:
            doomed = [key for key in self._store if key.startswith(prefix)]
            for key in doomed:
                del self._store[key]
            return len(doomed)

    def clear(self) -> None:
        """Drop every entry. Used by tests and on configuration reload."""
        with self._lock:
            self._store.clear()

    # -- introspection ----------------------------------------------------
    def size(self) -> int:
        """Number of entries currently held, including any not yet reaped."""
        with self._lock:
            return len(self._store)

    # -- internals --------------------------------------------------------
    def _evict_locked(self, *, now: float) -> None:
        """Reap expired entries; if none, drop the soonest-to-expire entry.

        Caller must already hold `self._lock`.
        """
        expired = [key for key, entry in self._store.items() if entry.expires_at <= now]
        for key in expired:
            del self._store[key]
        if expired or not self._store:
            return
        oldest = min(self._store, key=lambda key: self._store[key].expires_at)
        del self._store[oldest]


def make_key(namespace: str, *parts: object) -> str:
    """Build a stable cache key.

    Example:
        make_key("quote", "AAPL")            -> "quote:AAPL"
        make_key("history", "AAPL", 90)      -> "history:AAPL:90"
    """
    return ":".join([namespace, *(str(part) for part in parts)])


# Process-wide cache shared by all services.
cache = TTLCache()
