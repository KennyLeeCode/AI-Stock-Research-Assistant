"""Financial Modeling Prep implementation of `StockDataProvider`.

Endpoint shapes here were confirmed against the live API rather than taken from
documentation, which matters because FMP retired its `/api/v3/` routes: they now
return `403 Legacy Endpoint`. Everything below uses the current `/stable/` API.

Two quirks drive the error handling:

  * **402 is overloaded.** FMP returns it both for an endpoint the plan does not
    include *and* for a symbol the plan cannot query. Only the message body
    distinguishes them, so it is inspected rather than trusted to a status code.
  * **Error bodies are sometimes plain text.** A restricted endpoint returns a
    bare string, not JSON, so parsing has to tolerate both.

Fundamentals are assembled from four endpoints because no single one carries
everything: `/profile` has the company, `/ratios-ttm` the valuation multiples and
margins, `/key-metrics-ttm` the returns, and `/income-statement` the absolute
figures. They are fetched concurrently.

News requires a paid plan. Rather than failing, `get_news` returns an empty feed
carrying a note so the interface can say why.
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
    NewsFeed,
    PriceHistory,
    PricePoint,
    Quote,
    utcnow,
)
from app.services.providers.base import (
    StockDataProvider,
    parse_optional_date,
    parse_optional_float,
    parse_optional_int,
    parse_optional_str,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "Financial Modeling Prep"

NEWS_UNAVAILABLE_NOTE = (
    "Company news requires a paid Financial Modeling Prep plan. "
    "All other data on this page is live."
)

# Substrings that identify what a 402 actually means.
#
# Both messages end with "...not available under your current subscription", so
# that phrase cannot distinguish them. The discriminator is the prefix:
#
#   endpoint:  "Restricted Endpoint: This endpoint is not available under..."
#   symbol:    "Premium Query Parameter: 'Special Endpoint : This value set
#               for 'symbol' is not available under..."
#
# Symbol markers are therefore checked first, and both sets are specific enough
# not to overlap.
_SYMBOL_MARKERS = ("premium query parameter", "value set for", "'symbol'")
_RESTRICTED_MARKERS = ("restricted endpoint", "this endpoint is not available")


class FMPProvider(StockDataProvider):
    """Fetches and normalizes market data from Financial Modeling Prep."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.fmp_base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------
    async def _get_client(self) -> httpx.AsyncClient:
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
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self, path: str, params: dict[str, str], *, symbol: str
    ) -> Any:
        """Call one endpoint and return the decoded body.

        Retries transport failures and 5xx with exponential backoff. Client
        errors are not retried, since repeating a rejected request cannot help.
        """
        if not self._settings.has_fmp_key:
            raise ConfigurationError("FMP_API_KEY is not configured on the server.")

        query = {**params, "apikey": self._settings.fmp_api_key.get_secret_value()}
        client = await self._get_client()
        url = f"{self._base_url}/{path.lstrip('/')}"
        attempts = self._settings.http_max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                # NOTE: never log `response.url` or `query` — both carry the key.
                response = await client.get(url, params=query)

                if response.status_code >= 500:
                    last_error = ProviderError(
                        f"{PROVIDER_NAME} returned HTTP {response.status_code}."
                    )
                    logger.warning(
                        "%s %s/%s -> HTTP %s (attempt %d/%d)",
                        PROVIDER_NAME, path, symbol,
                        response.status_code, attempt, attempts,
                    )
                    await self._backoff(attempt, attempts)
                    continue

                self._raise_for_status(response, symbol=symbol, path=path)

                try:
                    return response.json()
                except ValueError as exc:
                    raise ProviderError(
                        f"{PROVIDER_NAME} returned a non-JSON response."
                    ) from exc

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                logger.warning(
                    "%s %s/%s -> %s (attempt %d/%d)",
                    PROVIDER_NAME, path, symbol,
                    type(exc).__name__, attempt, attempts,
                )
                await self._backoff(attempt, attempts)

        if isinstance(last_error, httpx.TimeoutException):
            raise ProviderTimeoutError() from last_error
        raise ProviderError(
            f"{PROVIDER_NAME} could not be reached after {attempts} attempts."
        ) from last_error

    @staticmethod
    async def _backoff(attempt: int, attempts: int) -> None:
        if attempt < attempts:
            await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

    @staticmethod
    def _raise_for_status(
        response: httpx.Response, *, symbol: str, path: str
    ) -> None:
        """Translate FMP's status codes and message bodies into exceptions."""
        status = response.status_code
        if status < 400:
            return

        # The body may be JSON or a bare string, depending on the failure.
        try:
            payload = response.json()
            message = (
                payload.get("Error Message", "")
                if isinstance(payload, dict)
                else str(payload)
            )
        except ValueError:
            message = response.text
        lowered = (message or "").lower()

        if status == 401:
            raise ConfigurationError(
                f"The configured FMP_API_KEY was rejected by {PROVIDER_NAME}."
            )

        if status == 429:
            raise ProviderRateLimitError()

        if status == 402:
            # Overloaded: a plan restriction and an unqueryable symbol share
            # this status, and only the message tells them apart. Symbol is
            # checked first — see the marker definitions above.
            #
            # FMP also conflates "this ticker does not exist" with "this ticker
            # needs a higher plan". Both are reported as not-found, because from
            # the user's point of view the outcome is identical: no data for
            # what they searched.
            if any(marker in lowered for marker in _SYMBOL_MARKERS):
                raise TickerNotFoundError(
                    f"{PROVIDER_NAME} has no data for {symbol!r} on the current plan.",
                    details={"ticker": symbol},
                )
            if any(marker in lowered for marker in _RESTRICTED_MARKERS):
                raise ProviderError(
                    f"This data requires a paid {PROVIDER_NAME} plan."
                )
            raise ProviderError(f"{PROVIDER_NAME} declined the request.")

        if status == 403:
            # Retired /api/v3 routes answer with this.
            raise ProviderError(
                f"{PROVIDER_NAME} rejected the request for {path!r}."
            )

        if status == 404:
            raise TickerNotFoundError(
                f"{PROVIDER_NAME} has no data for {symbol!r}.",
                details={"ticker": symbol},
            )

        raise ProviderError(f"{PROVIDER_NAME} returned HTTP {status}.")

    @staticmethod
    def _first_row(payload: Any, *, symbol: str, what: str) -> dict[str, Any]:
        """Return the first object from a list response.

        FMP wraps single records in a one-element array and signals an unknown
        symbol with an empty array rather than an error.
        """
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return payload[0]
        raise TickerNotFoundError(
            f"No {what} was returned for {symbol!r}.", details={"ticker": symbol}
        )

    # ------------------------------------------------------------------
    # Quote
    # ------------------------------------------------------------------
    async def get_quote(self, ticker: str) -> Quote:
        payload = await self._request("quote", {"symbol": ticker}, symbol=ticker)
        row = self._first_row(payload, symbol=ticker, what="quote data")

        return Quote(
            source=PROVIDER_NAME,
            retrieved_at=utcnow(),
            symbol=parse_optional_str(row.get("symbol")) or ticker,
            price=parse_optional_float(row.get("price")),
            change=parse_optional_float(row.get("change")),
            # Already a percentage: 1.1681 means +1.1681%.
            change_percent=parse_optional_float(row.get("changePercentage")),
            previous_close=parse_optional_float(row.get("previousClose")),
            open=parse_optional_float(row.get("open")),
            day_high=parse_optional_float(row.get("dayHigh")),
            day_low=parse_optional_float(row.get("dayLow")),
            volume=parse_optional_int(row.get("volume")),
            # FMP gives a unix timestamp, not a trading date. Deriving a date
            # from it would require assuming a timezone, so the exchange date is
            # taken from the price history instead and this is left unset.
            latest_trading_day=None,
        )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    async def get_history(self, ticker: str, days: int) -> PriceHistory:
        today = date.today()
        start = today - timedelta(days=days)

        # Bounding the range server-side matters: the unbounded response is
        # ~280 KB of JSON going back decades.
        payload = await self._request(
            "historical-price-eod/full",
            {"symbol": ticker, "from": start.isoformat(), "to": today.isoformat()},
            symbol=ticker,
        )

        rows = payload if isinstance(payload, list) else payload.get("historical", [])
        if not isinstance(rows, list) or not rows:
            raise TickerNotFoundError(
                f"No price history was returned for {ticker!r}.",
                details={"ticker": ticker},
            )

        points: list[PricePoint] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            day = parse_optional_date(row.get("date"))
            close = parse_optional_float(row.get("close"))
            if day is None or close is None:
                # A day without a date or a close is not a usable observation.
                # Dropping it is correct; interpolating would invent a price.
                continue
            points.append(
                PricePoint(
                    date=day,
                    open=parse_optional_float(row.get("open")),
                    high=parse_optional_float(row.get("high")),
                    low=parse_optional_float(row.get("low")),
                    close=close,
                    volume=parse_optional_int(row.get("volume")),
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
        """Combine four endpoints into one normalized profile.

        Only `/profile` is required. The other three are best-effort: a plan
        restriction on ratios should leave the company description and sector
        visible rather than failing the whole panel. Anything unavailable stays
        `None` — never zero.
        """
        profile_task = asyncio.create_task(
            self._request("profile", {"symbol": ticker}, symbol=ticker)
        )
        ratios_task = asyncio.create_task(
            self._request("ratios-ttm", {"symbol": ticker}, symbol=ticker)
        )
        metrics_task = asyncio.create_task(
            self._request("key-metrics-ttm", {"symbol": ticker}, symbol=ticker)
        )
        income_task = asyncio.create_task(
            self._request(
                "income-statement", {"symbol": ticker, "limit": "1"}, symbol=ticker
            )
        )

        results = await asyncio.gather(
            profile_task, ratios_task, metrics_task, income_task,
            return_exceptions=True,
        )
        profile_raw, ratios_raw, metrics_raw, income_raw = results

        if isinstance(profile_raw, BaseException):
            raise profile_raw

        profile = self._first_row(
            profile_raw, symbol=ticker, what="company profile"
        )

        def optional(result: Any, label: str) -> dict[str, Any]:
            if isinstance(result, BaseException):
                logger.info(
                    "%s: %s unavailable for %s (%s)",
                    PROVIDER_NAME, label, ticker, type(result).__name__,
                )
                return {}
            if isinstance(result, list) and result and isinstance(result[0], dict):
                return result[0]
            if isinstance(result, dict):
                return result
            return {}

        ratios = optional(ratios_raw, "ratios")
        metrics = optional(metrics_raw, "key metrics")
        income = optional(income_raw, "income statement")

        # `range` looks like "201.5-339.57". Split rather than parsed as a
        # number, and only when both halves are present.
        week_52_low = week_52_high = None
        raw_range = parse_optional_str(profile.get("range"))
        if raw_range and "-" in raw_range:
            low_text, _, high_text = raw_range.partition("-")
            week_52_low = parse_optional_float(low_text)
            week_52_high = parse_optional_float(high_text)

        return CompanyOverview(
            source=PROVIDER_NAME,
            retrieved_at=utcnow(),
            symbol=parse_optional_str(profile.get("symbol")) or ticker,
            name=parse_optional_str(profile.get("companyName")),
            description=parse_optional_str(profile.get("description")),
            exchange=parse_optional_str(profile.get("exchange")),
            currency=parse_optional_str(profile.get("currency")),
            country=parse_optional_str(profile.get("country")),
            sector=parse_optional_str(profile.get("sector")),
            industry=parse_optional_str(profile.get("industry")),
            fiscal_year_end=None,
            latest_quarter=parse_optional_date(income.get("date")),

            # -- Valuation --
            market_cap=parse_optional_int(profile.get("marketCap")),
            pe_ratio=parse_optional_float(ratios.get("priceToEarningsRatioTTM")),
            forward_pe=None,
            peg_ratio=parse_optional_float(
                ratios.get("priceToEarningsGrowthRatioTTM")
            ),
            price_to_book=parse_optional_float(ratios.get("priceToBookRatioTTM")),
            book_value=parse_optional_float(ratios.get("bookValuePerShareTTM")),
            analyst_target_price=None,

            # -- Profitability (fractions, matching the schema contract) --
            eps=parse_optional_float(
                ratios.get("netIncomePerShareTTM") or income.get("eps")
            ),
            profit_margin=parse_optional_float(ratios.get("netProfitMarginTTM")),
            operating_margin=parse_optional_float(
                ratios.get("operatingProfitMarginTTM")
            ),
            return_on_equity=parse_optional_float(metrics.get("returnOnEquityTTM")),
            return_on_assets=parse_optional_float(metrics.get("returnOnAssetsTTM")),

            # -- Scale --
            revenue_ttm=parse_optional_int(income.get("revenue")),
            gross_profit_ttm=parse_optional_int(income.get("grossProfit")),
            ebitda=parse_optional_int(income.get("ebitda")),
            shares_outstanding=parse_optional_int(
                income.get("weightedAverageShsOut")
            ),

            # -- Dividend & risk --
            dividend_yield=parse_optional_float(ratios.get("dividendYieldTTM")),
            dividend_per_share=parse_optional_float(
                ratios.get("dividendPerShareTTM") or profile.get("lastDividend")
            ),
            beta=parse_optional_float(profile.get("beta")),

            week_52_high=week_52_high,
            week_52_low=week_52_low,
        )

    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------
    async def get_news(self, ticker: str, limit: int) -> NewsFeed:
        """News is not available on the free plan.

        Returning an empty feed with a note, rather than raising, keeps the rest
        of the dashboard working and lets the interface state the real reason
        instead of implying the company has no coverage.
        """
        return NewsFeed(
            source=PROVIDER_NAME,
            retrieved_at=utcnow(),
            symbol=ticker,
            articles=[],
            note=NEWS_UNAVAILABLE_NOTE,
        )
