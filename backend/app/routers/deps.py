"""Shared router dependencies.

Keeps ticker validation in one place so every path that accepts a symbol
enforces it identically.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Path

from app.core.validation import MAX_TICKER_LENGTH, normalize_ticker


def validated_ticker(
    ticker: Annotated[
        str,
        Path(
            description="Ticker symbol, case-insensitive.",
            examples=["AAPL"],
            max_length=MAX_TICKER_LENGTH,
        ),
    ],
) -> str:
    """Normalize and validate a ticker taken from the URL path.

    A malformed symbol raises `InvalidTickerError`, which the registered handler
    renders as a 400 with code `invalid_ticker`.
    """
    return normalize_ticker(ticker)


# Use as: `ticker: TickerParam`
TickerParam = Annotated[str, Depends(validated_ticker)]
