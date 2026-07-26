"""Market-data endpoints.

Route handlers do three things only: accept validated input, call a service, and
return a typed model. There is no business logic, no HTTP client, and no
database access here — that is what keeps the services testable without a web
server and the provider swappable without touching the API surface.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.routers.deps import TickerParam
from app.schemas.indicators import TechnicalIndicators
from app.schemas.stock import CompanyOverview, NewsFeed, PriceHistory, Quote
from app.services import stock_service
from app.services.indicator_service import compute_indicators

router = APIRouter(prefix="/stocks", tags=["stocks"])

# Documented error shapes, so the generated OpenAPI spec tells the frontend
# exactly what it must handle.
COMMON_ERRORS: dict[int | str, dict] = {
    400: {"description": "The ticker symbol is malformed."},
    404: {"description": "The provider has no data for this symbol."},
    429: {"description": "The provider's rate limit or daily quota was reached."},
    502: {"description": "The provider returned an unexpected response."},
    503: {"description": "The server is missing a required API key."},
    504: {"description": "The provider did not respond in time."},
}

HistoryDays = Annotated[
    int,
    Query(
        ge=1,
        le=stock_service.MAX_HISTORY_DAYS,
        description="Calendar days of history to return.",
    ),
]

NewsLimit = Annotated[
    int,
    Query(ge=1, le=stock_service.MAX_NEWS_LIMIT, description="Maximum articles."),
]


@router.get(
    "/{ticker}/quote",
    response_model=Quote,
    summary="Current price and daily change",
    responses=COMMON_ERRORS,
)
async def get_quote(ticker: TickerParam) -> Quote:
    """Latest trade price, change versus previous close, and day range."""
    return await stock_service.get_quote(ticker)


@router.get(
    "/{ticker}/history",
    response_model=PriceHistory,
    summary="Historical daily prices",
    responses=COMMON_ERRORS,
)
async def get_history(
    ticker: TickerParam,
    days: HistoryDays = stock_service.DEFAULT_HISTORY_DAYS,
) -> PriceHistory:
    """Daily OHLCV data, oldest first.

    Days on which the provider reported no closing price are omitted rather
    than interpolated.
    """
    return await stock_service.get_history(ticker, days)


@router.get(
    "/{ticker}/overview",
    response_model=CompanyOverview,
    summary="Company profile and fundamentals",
    responses=COMMON_ERRORS,
)
async def get_overview(ticker: TickerParam) -> CompanyOverview:
    """Company profile and reported fundamental metrics.

    Metrics the provider does not supply are returned as `null`, never as `0`.
    """
    return await stock_service.get_overview(ticker)


@router.get(
    "/{ticker}/news",
    response_model=NewsFeed,
    summary="Recent news articles",
    responses=COMMON_ERRORS,
)
async def get_news(
    ticker: TickerParam,
    limit: NewsLimit = stock_service.DEFAULT_NEWS_LIMIT,
) -> NewsFeed:
    """Recent news for the security, newest first.

    An empty `articles` list is a valid result, not an error.
    """
    return await stock_service.get_news(ticker, limit)


@router.get(
    "/{ticker}/indicators",
    response_model=TechnicalIndicators,
    summary="Computed technical indicators",
    responses={
        **COMMON_ERRORS,
        422: {"description": "Too little price history to compute any indicator."},
    },
)
async def get_indicators(
    ticker: TickerParam,
    days: HistoryDays = stock_service.DEFAULT_HISTORY_DAYS,
) -> TechnicalIndicators:
    """SMA 20/50, RSI 14, 30-day volatility, 1- and 3-month change, 52-week range.

    Computed from the price history this API fetched. Any indicator the
    available history cannot support is `null`, with the reason given in the
    `unavailable` map.
    """
    history = await stock_service.get_history(ticker, days)
    return compute_indicators(history)
