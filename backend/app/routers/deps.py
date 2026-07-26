"""Shared router dependencies.

Keeps ticker validation in one place so every path that accepts a symbol
enforces it identically.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Path

from app.core.validation import normalize_ticker


def validated_ticker(
    ticker: Annotated[
        str,
        Path(
            description="Ticker symbol, case-insensitive.",
            examples=["AAPL"],
        ),
    ],
) -> str:
    """Normalize and validate a ticker taken from the URL path.

    A malformed symbol raises `InvalidTickerError`, which the registered handler
    renders as a 400 with code `invalid_ticker`.

    Note there is deliberately no `max_length` constraint on the `Path`
    declaration. FastAPI enforces such constraints *before* this function runs
    and reports failures as a 422 `validation_error`, so an over-long symbol
    would return a different status and error code than any other malformed
    symbol — the same user mistake surfacing two ways, forcing the frontend to
    handle both. `normalize_ticker` owns every rule about what a symbol may
    look like, including its length, so all malformed input yields one
    consistent 400 `invalid_ticker`.
    """
    return normalize_ticker(ticker)


# Use as: `ticker: TickerParam`
TickerParam = Annotated[str, Depends(validated_ticker)]
