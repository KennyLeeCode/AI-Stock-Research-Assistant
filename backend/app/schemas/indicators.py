"""Schemas for computed technical indicators.

Every value here is derived from the daily closes returned by the market-data
provider. Nothing is estimated and nothing is carried over from the provider's
own analytics.

Each indicator is optional. When there is not enough history to compute one
honestly - a 50-day average needs 50 closes - the field is `None` and the
`unavailable` map explains why in plain language, so the UI can show a specific
reason instead of a blank cell.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class TechnicalIndicators(BaseModel):
    """Indicators computed from a security's daily price history."""

    symbol: str
    as_of: date = Field(description="Date of the most recent close used in the calculations.")

    # -- Provenance --------------------------------------------------------
    source: str = Field(
        description="Provider that supplied the underlying price history.",
    )
    history_retrieved_at: datetime = Field(
        description="UTC instant at which the underlying price history was fetched.",
    )
    data_points_used: int = Field(
        description="Number of daily closes available to the calculations.",
    )

    # -- Trend -------------------------------------------------------------
    sma_20: float | None = Field(default=None, description="20-day simple moving average.")
    sma_50: float | None = Field(default=None, description="50-day simple moving average.")

    # -- Momentum ----------------------------------------------------------
    rsi_14: float | None = Field(
        default=None,
        description="14-period Relative Strength Index using Wilder's smoothing, 0-100.",
    )

    # -- Risk --------------------------------------------------------------
    volatility_30d: float | None = Field(
        default=None,
        description=(
            "Annualized volatility from the last 30 daily returns, as a percent "
            "(24.5 means 24.5%)."
        ),
    )

    # -- Performance -------------------------------------------------------
    price_change_1m: float | None = Field(
        default=None, description="Percent change over roughly one month."
    )
    price_change_3m: float | None = Field(
        default=None, description="Percent change over roughly three months."
    )

    # -- 52-week range -----------------------------------------------------
    # Computed from daily *closing* prices in the history this application
    # fetched. Deliberately distinct from `CompanyOverview.week_52_high/low`,
    # which is the provider's own reported figure and is normally based on
    # intraday extremes. The two will differ slightly; that is expected, and is
    # why they are surfaced as separate fields rather than merged.
    week_52_high: float | None = Field(
        default=None, description="Highest daily close in the last 52 weeks."
    )
    week_52_low: float | None = Field(
        default=None, description="Lowest daily close in the last 52 weeks."
    )
    week_52_high_date: date | None = None
    week_52_low_date: date | None = None

    # -- Gaps --------------------------------------------------------------
    unavailable: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Indicator name mapped to the reason it could not be computed. "
            "A name appearing here always corresponds to a null field above."
        ),
    )
