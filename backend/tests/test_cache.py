"""TTL cache behaviour.

The cache is what keeps the application inside a 25-request-per-day quota, so
its expiry, eviction, and key isolation are worth pinning down.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from app.core.cache import TTLCache, make_key


class TestBasicOperations:
    def test_stores_and_returns(self) -> None:
        cache = TTLCache()
        cache.set("a", {"value": 1}, 60)
        assert cache.get("a") == {"value": 1}

    def test_missing_key_returns_none(self) -> None:
        assert TTLCache().get("absent") is None

    def test_keys_are_isolated(self) -> None:
        cache = TTLCache()
        cache.set("quote:AAPL", "apple", 60)
        cache.set("quote:MSFT", "microsoft", 60)
        assert cache.get("quote:AAPL") == "apple"
        assert cache.get("quote:MSFT") == "microsoft"

    def test_falsy_values_round_trip(self) -> None:
        """`0`, `[]` and `False` must not be mistaken for a cache miss."""
        cache = TTLCache()
        for key, value in [("zero", 0), ("empty", []), ("false", False)]:
            cache.set(key, value, 60)
            assert cache.get(key) == value


class TestExpiry:
    def test_entries_expire(self) -> None:
        cache = TTLCache()
        cache.set("short", "value", 1)
        assert cache.get("short") == "value"
        time.sleep(1.05)
        assert cache.get("short") is None

    def test_non_positive_ttl_does_not_store(self) -> None:
        """Lets caching be disabled by configuration without branching."""
        cache = TTLCache()
        cache.set("zero-ttl", "value", 0)
        cache.set("negative-ttl", "value", -5)
        assert cache.get("zero-ttl") is None
        assert cache.get("negative-ttl") is None

    def test_expired_entries_are_reaped_on_read(self) -> None:
        cache = TTLCache()
        cache.set("temp", "value", 1)
        time.sleep(1.05)
        cache.get("temp")
        assert cache.size() == 0


class TestInvalidation:
    def test_single_key(self) -> None:
        cache = TTLCache()
        cache.set("a", 1, 60)
        cache.invalidate("a")
        assert cache.get("a") is None

    def test_prefix_removes_matching_only(self) -> None:
        cache = TTLCache()
        cache.set("quote:AAPL", 1, 60)
        cache.set("history:AAPL", 2, 60)
        cache.set("quote:MSFT", 3, 60)

        removed = cache.invalidate_prefix("quote:AAPL")

        assert removed == 1
        assert cache.get("quote:AAPL") is None
        assert cache.get("history:AAPL") == 2
        assert cache.get("quote:MSFT") == 3

    def test_clear_empties_everything(self) -> None:
        cache = TTLCache()
        cache.set("a", 1, 60)
        cache.set("b", 2, 60)
        cache.clear()
        assert cache.size() == 0


class TestEviction:
    def test_size_is_bounded(self) -> None:
        """An unbounded cache in a long-running process is a memory leak."""
        cache = TTLCache(max_entries=10)
        for index in range(50):
            cache.set(f"key-{index}", index, 60)
        assert cache.size() <= 10


class TestThreadSafety:
    def test_concurrent_access_does_not_corrupt(self) -> None:
        """FastAPI runs sync endpoints in a thread pool, so this is real."""
        cache = TTLCache(max_entries=500)

        def hammer(worker: int) -> None:
            for index in range(100):
                key = f"w{worker}-{index}"
                cache.set(key, index, 60)
                cache.get(key)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(hammer, range(8)))

        assert cache.size() <= 500


class TestKeyBuilder:
    def test_namespacing(self) -> None:
        assert make_key("quote", "AAPL") == "quote:AAPL"
        assert make_key("history", "AAPL", 90) == "history:AAPL:90"

    def test_different_arguments_are_different_keys(self) -> None:
        """A 30-day window must not serve a 365-day request."""
        assert make_key("history", "AAPL", 30) != make_key("history", "AAPL", 365)
