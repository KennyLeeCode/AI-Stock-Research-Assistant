"""ORM model for saved watchlist entries.

Portability notes — this table is written to work unchanged on SQLite,
PostgreSQL, and MySQL:

  * `String(n)` is used rather than `Text` for the indexed/unique `ticker`
    column, because MySQL cannot build a unique index over an unbounded TEXT
    column without an explicit key length.
  * The unique constraint is explicitly named. Auto-generated constraint names
    differ per backend, which makes later migrations painful to write.
  * `created_at` is populated in Python rather than with a database
    `server_default`, since `CURRENT_TIMESTAMP` semantics and precision differ
    across the three engines.

Scope: the MVP has no authentication, so the watchlist is global to the
deployment. Adding multi-user support later means adding a `user_id` foreign
key and widening the unique constraint to `(user_id, ticker)`. That column is
deliberately not present yet rather than sitting unused.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.validation import MAX_TICKER_LENGTH
from app.database import Base

# Upper bounds for free-text columns.
COMPANY_NAME_MAX_LENGTH = 255
NOTES_MAX_LENGTH = 500


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class WatchlistItem(Base):
    """A ticker the user has saved to their watchlist."""

    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("ticker", name="uq_watchlist_items_ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Always stored in the canonical form produced by `normalize_ticker`.
    # No `index=True` here: the unique constraint below already creates an index
    # on this column, and adding a second one would cost writes and space for no
    # read benefit.
    ticker: Mapped[str] = mapped_column(
        String(MAX_TICKER_LENGTH),
        nullable=False,
    )

    # Cached from the provider at insert time purely so the watchlist can render
    # a readable name without N provider calls. It is a display convenience, not
    # a source of truth: live figures are always re-fetched.
    company_name: Mapped[str | None] = mapped_column(
        String(COMPANY_NAME_MAX_LENGTH),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        String(NOTES_MAX_LENGTH),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<WatchlistItem id={self.id} ticker={self.ticker!r}>"
