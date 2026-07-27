"""Normalized market-data schemas.

Every figure the application shows originates here, in a model produced by the
market-data provider layer. Two rules govern this module:

  1. **Optional means absent, not zero.** A numeric field that the provider did
     not supply is `None`. Nothing is defaulted to `0`, back-filled, estimated,
     or carried over from another field. A `None` propagates to the frontend and
     renders as an em dash.
  2. **Every payload is attributed.** Each response carries `source` and
     `retrieved_at`, so the UI can state where a number came from and when it
     was read.

These models are provider-agnostic. Vendor-specific field names such as Alpha
Vantage's `"05. price"` never escape the provider module.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class ProviderPayload(BaseModel):
    """Fields common to every provider response, for attribution in the UI."""

    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(description="Human-readable name of the data provider.")
    retrieved_at: datetime = Field(
        default_factory=utcnow,
        description="UTC instant at which this data was fetched from the provider.",
    )


class Quote(ProviderPayload):
    """A current price snapshot."""

    symbol: str
    price: float | None = Field(default=None, description="Most recent trade price.")
    change: float | None = Field(default=None, description="Absolute change vs previous close.")
    change_percent: float | None = Field(
        default=None,
        description="Percentage change vs previous close, as a percent (e.g. 1.25 means +1.25%).",
    )
    previous_close: float | None = None
    open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    volume: int | None = None
    latest_trading_day: date | None = None


class PricePoint(BaseModel):
    """One trading day of OHLCV data.

    `close` is required: a point without a close price is not a usable
    observation, so the provider drops it rather than emitting a partial row
    that downstream indicator maths would have to guess about.
    """

    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    volume: int | None = None


class PriceHistory(ProviderPayload):
    """A time-ordered series of daily prices, oldest first."""

    symbol: str
    points: list[PricePoint] = Field(default_factory=list)

    @property
    def closes(self) -> list[float]:
        """Closing prices in chronological order."""
        return [point.close for point in self.points]


class CompanyOverview(ProviderPayload):
    """Company profile and reported fundamental metrics.

    Every metric is optional. Providers routinely omit figures for ETFs, ADRs,
    recently listed companies, and loss-making firms (a negative-earnings company
    legitimately has no P/E). Those arrive as `None`.
    """

    symbol: str
    name: str | None = None
    description: str | None = None
    exchange: str | None = None
    currency: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
    fiscal_year_end: str | None = None
    latest_quarter: date | None = None

    # -- Valuation --
    market_cap: int | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    price_to_book: float | None = None
    book_value: float | None = None
    analyst_target_price: float | None = None

    # -- Profitability --
    eps: float | None = None
    profit_margin: float | None = Field(
        default=None, description="Net profit margin as a fraction (0.25 means 25%)."
    )
    operating_margin: float | None = Field(
        default=None, description="Operating margin as a fraction."
    )
    return_on_equity: float | None = Field(
        default=None, description="Return on equity as a fraction."
    )
    return_on_assets: float | None = Field(
        default=None, description="Return on assets as a fraction."
    )

    # -- Scale --
    revenue_ttm: int | None = None
    gross_profit_ttm: int | None = None
    ebitda: int | None = None
    shares_outstanding: int | None = None

    # -- Dividend & risk --
    dividend_yield: float | None = Field(
        default=None, description="Dividend yield as a fraction (0.0044 means 0.44%)."
    )
    dividend_per_share: float | None = None
    beta: float | None = None

    # -- Provider-reported 52-week range --
    # Kept distinct from the 52-week range in `TechnicalIndicators`, which is
    # computed from the price history this app fetched. The two can differ
    # slightly; labelling them separately avoids presenting one as the other.
    week_52_high: float | None = None
    week_52_low: float | None = None


class NewsArticle(BaseModel):
    """A single news item related to a security."""

    title: str
    url: str
    source: str | None = None
    published_at: datetime | None = None
    summary: str | None = None
    banner_image: str | None = None
    sentiment_label: str | None = Field(
        default=None,
        description="Provider-assigned sentiment label, e.g. 'Bullish'. Not computed here.",
    )
    sentiment_score: float | None = Field(
        default=None, description="Provider-assigned sentiment score."
    )


class NewsFeed(ProviderPayload):
    """Recent news for a security, newest first."""

    symbol: str
    articles: list[NewsArticle] = Field(default_factory=list)
    note: str | None = Field(
        default=None,
        description=(
            "Why the feed is empty, when the reason is not simply that no "
            "articles exist - for example, the endpoint requiring a paid plan. "
            "Lets the UI explain an empty list instead of implying the company "
            "has no coverage."
        ),
    )
