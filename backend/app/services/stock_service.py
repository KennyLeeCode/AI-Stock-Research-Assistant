"""Orchestrates market-data retrieval: validation, caching, provider calls.

This is the layer routers talk to. It owns three concerns the provider
deliberately does not:

  * **Validation** — every ticker is normalized before it is used in a request
    or a cache key, so one symbol cannot occupy two cache slots and unvalidated
    input never reaches an outbound URL.
  * **Caching** — the free Alpha Vantage tier allows roughly 25 requests a day,
    and a single dashboard load needs four. TTLs are per data type: quotes go
    stale in a minute, company profiles do not change daily.
  * **Concurrency** — the dashboard needs four independent datasets, so they are
    fetched in parallel rather than serially.

Only successful responses are cached. An error is never stored, so a transient
provider failure does not persist for the length of a TTL.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.config import get_settings
from app.core.cache import cache, make_key
from app.core.validation import normalize_ticker
from app.schemas.stock import CompanyOverview, NewsFeed, PriceHistory, Quote
from app.services.providers import get_provider

logger = logging.getLogger(__name__)

# Defaults chosen so a single history fetch can serve every indicator:
# 52-week range needs ~365 days, and the 50-day SMA needs ~70 calendar days.
DEFAULT_HISTORY_DAYS = 365
MAX_HISTORY_DAYS = 1825  # five years
DEFAULT_NEWS_LIMIT = 10
MAX_NEWS_LIMIT = 50


@dataclass(slots=True)
class StockSnapshot:
    """Everything the dashboard needs for one symbol, fetched together.

    `news` is optional because an empty or unavailable news feed should not
    prevent the rest of the dashboard from rendering.
    """

    ticker: str
    quote: Quote
    history: PriceHistory
    overview: CompanyOverview
    news: NewsFeed | None


async def get_quote(ticker: str) -> Quote:
    """Return a cached-or-fresh price snapshot."""
    symbol = normalize_ticker(ticker)
    settings = get_settings()
    key = make_key("quote", symbol)

    cached = cache.get(key)
    if cached is not None:
        logger.debug("cache hit: %s", key)
        return cached

    quote = await get_provider().get_quote(symbol)
    cache.set(key, quote, settings.cache_ttl_quote)
    return quote


async def get_history(ticker: str, days: int = DEFAULT_HISTORY_DAYS) -> PriceHistory:
    """Return up to `days` calendar days of daily prices, oldest first."""
    symbol = normalize_ticker(ticker)
    settings = get_settings()
    window = max(1, min(int(days), MAX_HISTORY_DAYS))
    key = make_key("history", symbol, window)

    cached = cache.get(key)
    if cached is not None:
        logger.debug("cache hit: %s", key)
        return cached

    history = await get_provider().get_history(symbol, window)
    cache.set(key, history, settings.cache_ttl_history)
    return history


async def get_overview(ticker: str) -> CompanyOverview:
    """Return the company profile and reported fundamentals."""
    symbol = normalize_ticker(ticker)
    settings = get_settings()
    key = make_key("overview", symbol)

    cached = cache.get(key)
    if cached is not None:
        logger.debug("cache hit: %s", key)
        return cached

    overview = await get_provider().get_overview(symbol)
    cache.set(key, overview, settings.cache_ttl_overview)
    return overview


async def get_news(ticker: str, limit: int = DEFAULT_NEWS_LIMIT) -> NewsFeed:
    """Return up to `limit` recent news articles, newest first."""
    symbol = normalize_ticker(ticker)
    settings = get_settings()
    count = max(1, min(int(limit), MAX_NEWS_LIMIT))
    key = make_key("news", symbol, count)

    cached = cache.get(key)
    if cached is not None:
        logger.debug("cache hit: %s", key)
        return cached

    news = await get_provider().get_news(symbol, count)
    cache.set(key, news, settings.cache_ttl_news)
    return news


async def get_snapshot(
    ticker: str,
    *,
    history_days: int = DEFAULT_HISTORY_DAYS,
    news_limit: int = DEFAULT_NEWS_LIMIT,
) -> StockSnapshot:
    """Fetch quote, history, overview, and news concurrently.

    Quote, history, and overview are required — if any fails, the caller gets
    that error, because a research report or dashboard built on two of three
    datasets would be misleading.

    News is best-effort: a failure there is logged and yields `None`, so an
    outage in the news endpoint does not take down the whole page.
    """
    symbol = normalize_ticker(ticker)

    quote_task = asyncio.create_task(get_quote(symbol))
    history_task = asyncio.create_task(get_history(symbol, history_days))
    overview_task = asyncio.create_task(get_overview(symbol))
    news_task = asyncio.create_task(get_news(symbol, news_limit))

    results = await asyncio.gather(
        quote_task, history_task, overview_task, news_task, return_exceptions=True
    )
    quote, history, overview, news = results

    # Surface the first required-dataset failure.
    for result in (quote, history, overview):
        if isinstance(result, BaseException):
            raise result

    if isinstance(news, BaseException):
        logger.warning(
            "News unavailable for %s (%s); continuing without it.",
            symbol,
            type(news).__name__,
        )
        news = None

    assert isinstance(quote, Quote)
    assert isinstance(history, PriceHistory)
    assert isinstance(overview, CompanyOverview)

    return StockSnapshot(
        ticker=symbol,
        quote=quote,
        history=history,
        overview=overview,
        news=news,
    )


def invalidate_ticker(ticker: str) -> int:
    """Drop every cached dataset for one symbol. Returns entries removed."""
    symbol = normalize_ticker(ticker)
    removed = 0
    for namespace in ("quote", "history", "overview", "news", "indicators", "research"):
        removed += cache.invalidate_prefix(f"{namespace}:{symbol}")
    return removed
