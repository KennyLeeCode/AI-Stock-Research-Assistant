"""Watchlist persistence.

Database work is synchronous (SQLAlchemy's `Session`), but the routers are
async. Running a blocking call directly inside an async endpoint would stall the
event loop for every other in-flight request. Each database operation is
therefore dispatched to the threadpool, which is what FastAPI does automatically
for `def` endpoints and what it cannot do for `async def` ones.

With SQLite the blocking window is sub-millisecond and this is close to
academic; against a networked PostgreSQL instance it is not.
"""

from __future__ import annotations

import logging

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AppError,
    DuplicateResourceError,
    ResourceNotFoundError,
)
from app.core.validation import normalize_ticker
from app.models.watchlist import WatchlistItem
from app.services import stock_service

logger = logging.getLogger(__name__)


# ==========================================================================
# Synchronous database operations
# ==========================================================================
def _list_sync(db: Session) -> list[WatchlistItem]:
    """Newest entries first."""
    statement = select(WatchlistItem).order_by(WatchlistItem.created_at.desc())
    return list(db.execute(statement).scalars().all())


def _get_sync(db: Session, symbol: str) -> WatchlistItem | None:
    statement = select(WatchlistItem).where(WatchlistItem.ticker == symbol)
    return db.execute(statement).scalar_one_or_none()


def _add_sync(
    db: Session, symbol: str, company_name: str | None, notes: str | None
) -> WatchlistItem:
    item = WatchlistItem(ticker=symbol, company_name=company_name, notes=notes)
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        # The unique constraint is the authority, not the pre-check in
        # `add_ticker`. Two concurrent requests can both pass that check; only
        # one wins here, and the loser must still get a clean 409.
        db.rollback()
        raise DuplicateResourceError(
            f"{symbol} is already on the watchlist.", details={"ticker": symbol}
        ) from exc
    db.refresh(item)
    return item


def _delete_sync(db: Session, symbol: str) -> bool:
    item = _get_sync(db, symbol)
    if item is None:
        return False
    db.delete(item)
    db.commit()
    return True


# ==========================================================================
# Async interface used by the routers
# ==========================================================================
async def list_items(db: Session) -> list[WatchlistItem]:
    """Return every watchlist entry, newest first."""
    return await run_in_threadpool(_list_sync, db)


async def add_ticker(
    db: Session, ticker: str, notes: str | None = None
) -> WatchlistItem:
    """Add `ticker` to the watchlist.

    The company name is fetched best-effort so the list can render something
    readable. A provider outage or an exhausted quota must not stop the user
    saving a ticker, so a failed lookup simply leaves the name empty.

    Raises:
        InvalidTickerError: If the symbol is malformed.
        DuplicateResourceError: If the symbol is already saved.
    """
    symbol = normalize_ticker(ticker)

    existing = await run_in_threadpool(_get_sync, db, symbol)
    if existing is not None:
        raise DuplicateResourceError(
            f"{symbol} is already on the watchlist.", details={"ticker": symbol}
        )

    company_name: str | None = None
    try:
        overview = await stock_service.get_overview(symbol)
        company_name = overview.name
    except AppError as exc:
        logger.info(
            "Could not resolve a company name for %s (%s); saving without one.",
            symbol,
            exc.code,
        )

    return await run_in_threadpool(_add_sync, db, symbol, company_name, notes)


async def remove_ticker(db: Session, ticker: str) -> None:
    """Remove `ticker` from the watchlist.

    Raises:
        InvalidTickerError: If the symbol is malformed.
        ResourceNotFoundError: If the symbol is not on the watchlist.
    """
    symbol = normalize_ticker(ticker)
    deleted = await run_in_threadpool(_delete_sync, db, symbol)
    if not deleted:
        raise ResourceNotFoundError(
            f"{symbol} is not on the watchlist.", details={"ticker": symbol}
        )
