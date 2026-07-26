"""Ticker validation.

This is the boundary between user input and outbound URLs, cache keys, and
database rows, so it is tested for both what it accepts and what it refuses.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import InvalidTickerError
from app.core.validation import MAX_TICKER_LENGTH, is_valid_ticker, normalize_ticker


class TestNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("AAPL", "AAPL"),
            ("aapl", "AAPL"),
            ("  aapl  ", "AAPL"),
            ("BRK.B", "BRK.B"),
            ("brk.b", "BRK.B"),
            ("BF-A", "BF-A"),
            ("A", "A"),
        ],
    )
    def test_valid_symbols(self, raw: str, expected: str) -> None:
        assert normalize_ticker(raw) == expected


class TestRejection:
    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "12345",  # all digits is not a symbol
            "TOOLONGSYMBOL",
            "AA PL",  # embedded space
            "AA..PL",
            "AAPL!",
            "<script>",
            "AAPL;DROP TABLE",
        ],
    )
    def test_invalid_symbols_raise(self, raw: str) -> None:
        with pytest.raises(InvalidTickerError):
            normalize_ticker(raw)
        assert is_valid_ticker(raw) is False

    @pytest.mark.parametrize("raw", ["../etc/passwd", "..%2Fetc", "./config", "a/b"])
    def test_path_traversal_is_rejected(self, raw: str) -> None:
        """Rejected before it can reach an outbound URL or a cache key."""
        with pytest.raises(InvalidTickerError):
            normalize_ticker(raw)

    def test_non_string_input(self) -> None:
        with pytest.raises(InvalidTickerError):
            normalize_ticker(None)  # type: ignore[arg-type]

    def test_length_limit_message_is_truncated(self) -> None:
        """The echoed value must not be unbounded attacker-controlled text."""
        with pytest.raises(InvalidTickerError) as caught:
            normalize_ticker("A" * 500)
        echoed = caught.value.details.get("ticker", "")
        assert len(echoed) <= MAX_TICKER_LENGTH
