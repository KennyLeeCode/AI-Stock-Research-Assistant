"""The market-data provider contract, plus shared parsing helpers.

`StockDataProvider` is the seam that keeps the rest of the application free of
vendor details. Routers and services depend on this interface and on the
normalized schemas in `app/schemas/stock.py`; only the concrete implementation
in this package knows what the upstream JSON looks like.

Swapping providers (Finnhub, Polygon, IEX, ...) means adding one module that
subclasses `StockDataProvider` and changing the `MARKET_DATA_PROVIDER` setting.

The parsing helpers live here because *every* provider needs them and because
they encode the project's central data rule: an unparseable or absent figure
becomes `None`, never a substituted number.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import date, datetime

from app.schemas.stock import CompanyOverview, NewsFeed, PriceHistory, Quote

# Strings providers use to mean "no value". Alpha Vantage in particular returns
# the literal text "None" and "-" inside otherwise-numeric fields.
_MISSING_TOKENS = {"", "-", "--", "none", "n/a", "na", "null", "nan", "unknown"}


def parse_optional_float(raw: object) -> float | None:
    """Convert a provider value to a float, or `None` if it is not a number.

    Handles thousands separators, a trailing percent sign, and the sentinel
    strings providers use for missing data. Non-finite results (`inf`, `nan`)
    are rejected, since they would poison any downstream arithmetic.

    Returns `None` rather than raising: a missing metric is an expected state,
    not an error.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        return value if math.isfinite(value) else None

    text = str(raw).strip()
    if text.lower() in _MISSING_TOKENS:
        return None

    text = text.replace(",", "").replace("%", "").strip()
    if not text or text.lower() in _MISSING_TOKENS:
        return None

    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def parse_optional_int(raw: object) -> int | None:
    """Convert a provider value to an int, or `None` if it is not a number."""
    value = parse_optional_float(raw)
    if value is None:
        return None
    try:
        return int(value)
    except (OverflowError, ValueError):
        return None


def parse_optional_str(raw: object) -> str | None:
    """Trim a provider string, mapping sentinel values to `None`."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() in _MISSING_TOKENS:
        return None
    return text


def parse_optional_date(raw: object) -> date | None:
    """Parse an ISO `YYYY-MM-DD` date, or `None` if absent or malformed."""
    text = parse_optional_str(raw)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_optional_datetime(raw: object, *, formats: tuple[str, ...]) -> datetime | None:
    """Parse a timestamp using the first matching format, else `None`."""
    text = parse_optional_str(raw)
    if text is None:
        return None
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


class StockDataProvider(ABC):
    """Interface every market-data provider must implement.

    Implementations are responsible for:
      * performing the network call with a timeout,
      * translating upstream failure modes into the application's
        `ProviderError` family,
      * normalizing the response into the schemas in `app/schemas/stock.py`.

    Implementations must not cache; caching is the orchestrating service's job.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name, surfaced to users as the data source."""

    @abstractmethod
    async def get_quote(self, ticker: str) -> Quote:
        """Return the latest price snapshot for `ticker`."""

    @abstractmethod
    async def get_history(self, ticker: str, days: int) -> PriceHistory:
        """Return up to `days` calendar days of daily prices, oldest first."""

    @abstractmethod
    async def get_overview(self, ticker: str) -> CompanyOverview:
        """Return the company profile and reported fundamentals for `ticker`."""

    @abstractmethod
    async def get_news(self, ticker: str, limit: int) -> NewsFeed:
        """Return up to `limit` recent news articles for `ticker`, newest first."""

    async def aclose(self) -> None:
        """Release any held network resources. Called on application shutdown."""
        return None
