"""Watchlist endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.deps import TickerParam
from app.schemas.watchlist import WatchlistItemCreate, WatchlistItemRead
from app.services import watchlist_service

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get(
    "",
    response_model=list[WatchlistItemRead],
    summary="List saved tickers",
)
async def list_watchlist(db: DbSession) -> list[WatchlistItemRead]:
    """Every saved ticker, newest first.

    An empty list is a normal state for a new install, not an error.
    """
    items = await watchlist_service.list_items(db)
    return [WatchlistItemRead.model_validate(item) for item in items]


@router.post(
    "",
    response_model=WatchlistItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a ticker to the watchlist",
    responses={
        409: {"description": "The ticker is already on the watchlist."},
        422: {"description": "The ticker symbol is malformed."},
    },
)
async def add_to_watchlist(
    payload: WatchlistItemCreate, db: DbSession
) -> WatchlistItemRead:
    """Save a ticker.

    The company name is resolved best-effort for display. If the market-data
    provider is unavailable or out of quota, the ticker is still saved — just
    without a name.
    """
    item = await watchlist_service.add_ticker(db, payload.ticker, payload.notes)
    return WatchlistItemRead.model_validate(item)


@router.delete(
    "/{ticker}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a ticker from the watchlist",
    responses={
        400: {"description": "The ticker symbol is malformed."},
        404: {"description": "The ticker is not on the watchlist."},
    },
)
async def remove_from_watchlist(ticker: TickerParam, db: DbSession) -> None:
    """Remove a saved ticker. Returns 204 with no body on success."""
    await watchlist_service.remove_ticker(db, ticker)
