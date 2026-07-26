"""Alpha Vantage implementation of `StockDataProvider`.

This is the only module in the application that knows Alpha Vantage's payload
shapes. It converts them into the normalized schemas in `app/schemas/stock.py`.

Two upstream behaviours drive most of the code here:

  * **Errors arrive as HTTP 200.** A bad symbol, an exhausted quota, and a
    premium-only endpoint all return status 200 with an explanatory key in the
    JSON body (`Error Message`, `Note`, or `Information`). Status codes alone
    cannot be trusted, so every response is inspected.
  * **Missing numbers are strings.** Fields come back as `"None"`, `"-"`, or
    `""` rather than JSON `null`. These are mapped to `None` by the shared
    parsers, never to `0`.

The API key is passed as a query parameter, so raw URLs must never be logged.
Every log statement here names the function and symbol only.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

import httpx

from app.config import Settings
from app.core.exceptions import (
    ConfigurationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    TickerNotFoundError,
)
from app.schemas.stock import (
    CompanyOverview,
    NewsArticle,
    NewsFeed,
    PriceHistory,
    PricePoint,
    Quote,
    utcnow,
)
from app.services.providers.base import (
    StockDataProvider,
    parse_optional_date,
    parse_optional_datetime,
    parse_optional_float,
    parse_optional_int,
    parse_optional_str,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "Alpha Vantage"

# `compact` returns the latest 100 points; `full` returns 20+ years. Anything
# beyond ~100 trading days (52-week range, 3-month change) needs `full`.
_COMPACT_POINT_LIMIT = 100

# Substrings that identify a quota/rate-limit message rather than a genuine
# data error. Alpha Vantage phrases these inconsistently across endpoints.
_RATE_LIMIT_MARKERS = (
    "rate limit",
    "api call frequency",
    "requests per day",
    "premium",
    "higher api call volume",
)


class AlphaVantageProvider(StockDataProvider):
    """Fetches and normalizes market data from Alpha Vantage."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.alpha_vantage_base_url
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------
    async def _get_client(self) -> httpx.AsyncClient:
        """Return the shared client, creating it on first use.

        A single client reuses connections across requests. The lock prevents
        two concurrent first-requests from each building one.
        """
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    self._client = httpx.AsyncClient(
                        timeout=httpx.Timeout(self._settings.http_timeout_seconds),
                        headers={"User-Agent": "ai-stock-research-assistant/0.1"},
                        follow_redirects=True,
                    )
        return self._client

    async def aclose(self) -> None:
        """Close the shared client. Called from the application lifespan."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, params: dict[str, str], *, symbol: str) -> dict[str, Any]:
        """Perform one API call and return the parsed JSON body.

        Retries transport failures and 5xx responses with exponential backoff.
        Client errors (4xx) are not retried, since repeating them cannot help.
        """
        if not self._settings.has_market_data_key:
            raise ConfigurationError(
                "ALPHA_VANTAGE_API_KEY is not configured on the server."
            )

        query = {
            **params,
            "apikey": self._settings.alpha_vantage_api_key.get_secret_value(),
        }
        client = await self._get_client()
        function = params.get("function", "?")
        attempts = self._settings.http_max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                # NOTE: never log `response.url` or `query` — both carry the API key.
                response = await client.get(self._base_url, params=query)

                if response.status_code >= 500:
                    last_error = ProviderError(
                        f"{PROVIDER_NAME} returned HTTP {response.status_code}."
                    )
                    logger.warning(
                        "%s %s/%s -> HTTP %s (attempt %d/%d)",
                        PROVIDER_NAME, function, symbol,
                        response.status_code, attempt, attempts,
                    )
                    await self._backoff(attempt, attempts)
                    continue

                if response.status_code == 429:
                    raise ProviderRateLimitError()

                if response.status_code >= 400:
                    raise ProviderError(
                        f"{PROVIDER_NAME} rejected the request "
                        f"(HTTP {response.status_code})."
                    )

                try:
                    payload = response.json()
                except ValueError as exc:
                    raise ProviderError(
                        f"{PROVIDER_NAME} returned a non-JSON response."
                    ) from exc

                if not isinstance(payload, dict):
                    raise ProviderError(
                        f"{PROVIDER_NAME} returned an unexpected response shape."
                    )

                self._raise_for_payload_error(payload, symbol=symbol, function=function)
                return payload

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                logger.warning(
                    "%s %s/%s -> %s (attempt %d/%d)",
                    PROVIDER_NAME, function, symbol,
                    type(exc).__name__, attempt, attempts,
                )
                await self._backoff(attempt, attempts)

        # Retries exhausted.
        if isinstance(last_error, httpx.TimeoutException):
            raise ProviderTimeoutError() from last_error
        raise ProviderError(
            f"{PROVIDER_NAME} could not be reached after {attempts} attempts."
        ) from last_error

    @staticmethod
    async def _backoff(attempt: int, attempts: int) -> None:
        """Sleep between retries; no sleep after the final attempt."""
        if attempt < attempts:
            await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

    @staticmethod
    def _raise_for_payload_error(
        payload: dict[str, Any], *, symbol: str, function: str
    ) -> None:
        """Translate Alpha Vantage's HTTP-200 error bodies into exceptions."""
        # "Information" and "Note" mean quota/premium; "Error Message" means the
        # request itself was rejected, almost always an unknown symbol.
        for key in ("Information", "Note"):
            message = parse_optional_str(payload.get(key))
            if message:
                lowered = message.lower()
                if any(marker in lowered for marker in _RATE_LIMIT_MARKERS):
                    logger.warning("%s quota hit on %s/%s", PROVIDER_NAME, function, symbol)
                    raise ProviderRateLimitError()
                raise ProviderError(f"{PROVIDER_NAME}: {message}")

        error_message = parse_optional_str(payload.get("Error Message"))
        if error_message:
            raise TickerNotFoundError(
                f"{PROVIDER_NAME} has no data for {symbol!r}.",
                details={"ticker": symbol},
            )

    # ------------------------------------------------------------------
    # Quote
    # ------------------------------------------------------------------
    async def get_quote(self, ticker: str) -> Quote:
        payload = await self._request(
            {"function": "GLOBAL_QUOTE", "symbol": ticker}, symbol=ticker
        )
        raw = payload.get("Global Quote") or payload.get("Global Quote - DATA DELAYED")

        # An unknown symbol yields `{"Global Quote": {}}` with no error key.
        if not isinstance(raw, dict) or not raw:
            raise TickerNotFoundError(
                f"No quote data was returned for {ticker!r}.",
                details={"ticker": ticker},
            )

        return Quote(
            source=PROVIDER_NAME,
            retrieved_at=utcnow(),
            symbol=parse_optional_str(raw.get("01. symbol")) or ticker,
            open=parse_optional_float(raw.get("02. open")),
            day_high=parse_optional_float(raw.get("03. high")),
            day_low=parse_optional_float(raw.get("04. low")),
            price=parse_optional_float(raw.get("05. price")),
            volume=parse_optional_int(raw.get("06. volume")),
            latest_trading_day=parse_optional_date(raw.get("07. latest trading day")),
            previous_close=parse_optional_float(raw.get("08. previous close")),
            change=parse_optional_float(raw.get("09. change")),
            # Arrives as e.g. "1.2345%"; the parser strips the sign and returns 1.2345.
            change_percent=parse_optional_float(raw.get("10. change percent")),
        )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    async def get_history(self, ticker: str, days: int) -> PriceHistory:
        output_size = "compact" if days <= _COMPACT_POINT_LIMIT else "full"
        payload = await self._request(
            {
                "function": "TIME_SERIES_DAILY",
                "symbol": ticker,
                "outputsize": output_size,
            },
            symbol=ticker,
        )

        series = payload.get("Time Series (Daily)")
        if not isinstance(series, dict) or not series:
            raise TickerNotFoundError(
                f"No price history was returned for {ticker!r}.",
                details={"ticker": ticker},
            )

        cutoff = date.today() - timedelta(days=days)
        points: list[PricePoint] = []

        for raw_day, raw_values in series.items():
            day = parse_optional_date(raw_day)
            if day is None or day < cutoff or not isinstance(raw_values, dict):
                continue

            close = parse_optional_float(raw_values.get("4. close"))
            if close is None:
                # A day without a close is not a usable observation. Dropping it
                # is correct; interpolating one would fabricate a price.
                continue

            points.append(
                PricePoint(
                    date=day,
                    open=parse_optional_float(raw_values.get("1. open")),
                    high=parse_optional_float(raw_values.get("2. high")),
                    low=parse_optional_float(raw_values.get("3. low")),
                    close=close,
                    volume=parse_optional_int(raw_values.get("5. volume")),
                )
            )

        points.sort(key=lambda point: point.date)

        if not points:
            raise TickerNotFoundError(
                f"No usable price history was returned for {ticker!r}.",
                details={"ticker": ticker},
            )

        return PriceHistory(
            source=PROVIDER_NAME,
            retrieved_at=utcnow(),
            symbol=ticker,
            points=points,
        )

    # ------------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------------
    async def get_overview(self, ticker: str) -> CompanyOverview:
        payload = await self._request(
            {"function": "OVERVIEW", "symbol": ticker}, symbol=ticker
        )

        # An unknown symbol yields `{}`.
        if not payload or not parse_optional_str(payload.get("Symbol")):
            raise TickerNotFoundError(
                f"No company profile was returned for {ticker!r}.",
                details={"ticker": ticker},
            )

        return CompanyOverview(
            source=PROVIDER_NAME,
            retrieved_at=utcnow(),
            symbol=parse_optional_str(payload.get("Symbol")) or ticker,
            name=parse_optional_str(payload.get("Name")),
            description=parse_optional_str(payload.get("Description")),
            exchange=parse_optional_str(payload.get("Exchange")),
            currency=parse_optional_str(payload.get("Currency")),
            country=parse_optional_str(payload.get("Country")),
            sector=parse_optional_str(payload.get("Sector")),
            industry=parse_optional_str(payload.get("Industry")),
            fiscal_year_end=parse_optional_str(payload.get("FiscalYearEnd")),
            latest_quarter=parse_optional_date(payload.get("LatestQuarter")),
            market_cap=parse_optional_int(payload.get("MarketCapitalization")),
            pe_ratio=parse_optional_float(payload.get("PERatio")),
            forward_pe=parse_optional_float(payload.get("ForwardPE")),
            peg_ratio=parse_optional_float(payload.get("PEGRatio")),
            price_to_book=parse_optional_float(payload.get("PriceToBookRatio")),
            book_value=parse_optional_float(payload.get("BookValue")),
            analyst_target_price=parse_optional_float(payload.get("AnalystTargetPrice")),
            eps=parse_optional_float(payload.get("EPS")),
            profit_margin=parse_optional_float(payload.get("ProfitMargin")),
            operating_margin=parse_optional_float(payload.get("OperatingMarginTTM")),
            return_on_equity=parse_optional_float(payload.get("ReturnOnEquityTTM")),
            return_on_assets=parse_optional_float(payload.get("ReturnOnAssetsTTM")),
            revenue_ttm=parse_optional_int(payload.get("RevenueTTM")),
            gross_profit_ttm=parse_optional_int(payload.get("GrossProfitTTM")),
            ebitda=parse_optional_int(payload.get("EBITDA")),
            shares_outstanding=parse_optional_int(payload.get("SharesOutstanding")),
            dividend_yield=parse_optional_float(payload.get("DividendYield")),
            dividend_per_share=parse_optional_float(payload.get("DividendPerShare")),
            beta=parse_optional_float(payload.get("Beta")),
            week_52_high=parse_optional_float(payload.get("52WeekHigh")),
            week_52_low=parse_optional_float(payload.get("52WeekLow")),
        )

    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------
    async def get_news(self, ticker: str, limit: int) -> NewsFeed:
        payload = await self._request(
            {
                "function": "NEWS_SENTIMENT",
                "tickers": ticker,
                "limit": str(max(1, min(limit, 200))),
                "sort": "LATEST",
            },
            symbol=ticker,
        )

        feed = payload.get("feed")
        if not isinstance(feed, list):
            # No news is a legitimate outcome, not an error. Return an empty
            # feed so the UI can render an empty state rather than a failure.
            return NewsFeed(
                source=PROVIDER_NAME, retrieved_at=utcnow(), symbol=ticker, articles=[]
            )

        articles: list[NewsArticle] = []
        for entry in feed[:limit]:
            if not isinstance(entry, dict):
                continue
            title = parse_optional_str(entry.get("title"))
            url = parse_optional_str(entry.get("url"))
            if not title or not url:
                # An article with no headline or no link is not renderable.
                continue

            articles.append(
                NewsArticle(
                    title=title,
                    url=url,
                    source=parse_optional_str(entry.get("source")),
                    # Alpha Vantage timestamps look like "20240115T130000".
                    published_at=parse_optional_datetime(
                        entry.get("time_published"),
                        formats=("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"),
                    ),
                    summary=parse_optional_str(entry.get("summary")),
                    banner_image=parse_optional_str(entry.get("banner_image")),
                    sentiment_label=parse_optional_str(
                        entry.get("overall_sentiment_label")
                    ),
                    sentiment_score=parse_optional_float(
                        entry.get("overall_sentiment_score")
                    ),
                )
            )

        return NewsFeed(
            source=PROVIDER_NAME,
            retrieved_at=utcnow(),
            symbol=ticker,
            articles=articles,
        )
