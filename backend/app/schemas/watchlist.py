"""Pydantic schemas for the watchlist API.

These are the wire contract. They are intentionally separate from the ORM model
in `app/models/watchlist.py` so that a storage change (adding a column, moving
to a different table layout) does not silently alter the public API.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.exceptions import InvalidTickerError
from app.core.validation import normalize_ticker
from app.models.watchlist import NOTES_MAX_LENGTH


class WatchlistItemCreate(BaseModel):
    """Request body for `POST /api/watchlist`."""

    ticker: str = Field(
        ...,
        description="Ticker symbol to add. Normalized to uppercase.",
        examples=["AAPL"],
    )
    notes: str | None = Field(
        default=None,
        max_length=NOTES_MAX_LENGTH,
        description="Optional free-text note stored alongside the entry.",
        examples=["Watching for the next earnings report."],
    )

    @field_validator("ticker")
    @classmethod
    def _validate_ticker(cls, value: str) -> str:
        """Apply the same validation used everywhere else in the app.

        `normalize_ticker` raises `InvalidTickerError`, which is not a
        `ValueError`, so Pydantic would let it escape as an unhandled 500. It is
        re-raised as a `ValueError` here so FastAPI renders a 422 through the
        request-validation handler.
        """
        try:
            return normalize_ticker(value)
        except InvalidTickerError as exc:
            raise ValueError(exc.message) from exc

    @field_validator("notes")
    @classmethod
    def _clean_notes(cls, value: str | None) -> str | None:
        """Trim surrounding whitespace; treat a blank note as no note."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class WatchlistItemRead(BaseModel):
    """A watchlist entry as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    company_name: str | None = None
    notes: str | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        """Guarantee the timestamp is timezone-aware UTC.

        SQLite has no native timezone storage, so a value written as aware UTC
        reads back naive. Postgres returns it aware. Normalizing here means the
        frontend receives an unambiguous ISO-8601 instant on every backend.
        """
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
