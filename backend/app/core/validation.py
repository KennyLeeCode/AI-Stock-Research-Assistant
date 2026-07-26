"""Ticker symbol validation and normalization.

Every ticker entering the application passes through `normalize_ticker` before
it is used in an outbound URL, a cache key, or a database row. This gives one
canonical form (uppercase, trimmed) and rejects anything that is not a
plausible symbol, so unvalidated user input never reaches the provider.
"""

from __future__ import annotations

import re

from app.core.exceptions import InvalidTickerError

# Base symbol, optionally followed by a class/series suffix.
#   AAPL, MSFT, GOOGL   -> base only
#   BRK.B, BF-A         -> base + suffix
_TICKER_PATTERN = re.compile(r"^[A-Z0-9]{1,6}(?:[.\-][A-Z0-9]{1,4})?$")

MAX_TICKER_LENGTH = 12


def normalize_ticker(raw: str) -> str:
    """Validate `raw` and return its canonical uppercase form.

    Args:
        raw: The user-supplied symbol, in any case, possibly padded.

    Returns:
        The normalized symbol, e.g. `" brk.b "` -> `"BRK.B"`.

    Raises:
        InvalidTickerError: If the value is empty, too long, or does not look
            like a ticker symbol.
    """
    if not isinstance(raw, str):
        raise InvalidTickerError("A ticker symbol must be provided as text.")

    candidate = raw.strip().upper()

    if not candidate:
        raise InvalidTickerError("A ticker symbol is required.")

    if len(candidate) > MAX_TICKER_LENGTH:
        raise InvalidTickerError(
            f"Ticker symbols cannot be longer than {MAX_TICKER_LENGTH} characters.",
            details={"ticker": candidate[:MAX_TICKER_LENGTH]},
        )

    if not _TICKER_PATTERN.fullmatch(candidate):
        raise InvalidTickerError(
            f"{candidate!r} is not a valid ticker symbol.",
            details={"ticker": candidate},
        )

    # Guard against all-numeric input such as "12345", which matches the
    # character class but is not a symbol.
    if not any(char.isalpha() for char in candidate):
        raise InvalidTickerError(
            f"{candidate!r} is not a valid ticker symbol.",
            details={"ticker": candidate},
        )

    return candidate


def is_valid_ticker(raw: str) -> bool:
    """Return True if `raw` is a valid ticker, without raising."""
    try:
        normalize_ticker(raw)
    except InvalidTickerError:
        return False
    return True
