"""Technical indicator calculations.

Implemented in pure Python. The maths here is a few dozen arithmetic
operations over a list of floats, which does not justify a numpy/pandas
dependency - and keeping it dependency-free makes every function trivially
unit-testable and the deployment image far smaller.

Two layers:

  * **Pure functions** (`simple_moving_average`, `relative_strength_index`, ...)
    take a list of closes and either return a number or raise
    `InsufficientDataError`. They never approximate. A 50-day average computed
    from 30 closes is not a 50-day average, so it is refused rather than
    silently mislabelled.

  * **`compute_indicators`** orchestrates them. It catches each refusal
    individually, so a short history yields the indicators it *can* support
    while recording a plain-language reason for the rest. Failing the whole
    request because one window is too long would be needlessly brittle.

All returned figures are rounded for presentation only, after the full-precision
calculation is complete.
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from statistics import fmean, stdev

from app.core.exceptions import InsufficientDataError
from app.schemas.indicators import TechnicalIndicators
from app.schemas.stock import PriceHistory, PricePoint

logger = logging.getLogger(__name__)

# -- Windows ---------------------------------------------------------------
SMA_SHORT_PERIOD = 20
SMA_LONG_PERIOD = 50
RSI_PERIOD = 14
VOLATILITY_WINDOW = 30

# Trading days in a year, the conventional factor for annualizing a daily
# standard deviation.
TRADING_DAYS_PER_YEAR = 252

# Calendar lookbacks for performance figures. Calendar days rather than trading
# days so "1 month" means what a user expects; the nearest earlier trading day
# is used, since the exact date may fall on a weekend or holiday.
ONE_MONTH_DAYS = 30
THREE_MONTH_DAYS = 91
FIFTY_TWO_WEEK_DAYS = 365

# How far before the target date the reference close may sit before the result
# stops being a fair representation of the period.
LOOKBACK_TOLERANCE_DAYS = 10

# A "52-week" range needs close to 52 weeks of data. With less, the label would
# overstate what was actually measured.
MIN_52_WEEK_COVERAGE_DAYS = 300

# Below this, nothing meaningful can be computed at all.
MIN_POINTS_FOR_ANY_INDICATOR = 2

# Displayed precision. Applied only at the end, never mid-calculation.
_PRICE_DP = 2
_PERCENT_DP = 2
_RSI_DP = 2


# ==========================================================================
# Pure calculations
# ==========================================================================
def simple_moving_average(closes: list[float], period: int) -> float:
    """Mean of the last `period` closing prices.

    Raises:
        InsufficientDataError: If fewer than `period` closes are available.
    """
    if period <= 0:
        raise ValueError("period must be positive")
    if len(closes) < period:
        raise InsufficientDataError(
            f"A {period}-day moving average needs {period} daily closes; "
            f"only {len(closes)} are available.",
            details={"required": period, "available": len(closes)},
        )
    return fmean(closes[-period:])


def relative_strength_index(closes: list[float], period: int = RSI_PERIOD) -> float:
    """RSI using Wilder's smoothing, returned on a 0-100 scale.

    Wilder's method seeds the average gain and loss with a simple mean of the
    first `period` changes, then applies an exponential smoothing across the
    remainder of the series. This is the standard definition and matches what
    charting platforms display; a plain rolling mean would produce visibly
    different numbers.

    Raises:
        InsufficientDataError: If fewer than `period + 1` closes are available
            (N changes require N+1 prices).
    """
    if period <= 0:
        raise ValueError("period must be positive")

    required = period + 1
    if len(closes) < required:
        raise InsufficientDataError(
            f"A {period}-period RSI needs {required} daily closes; "
            f"only {len(closes)} are available.",
            details={"required": required, "available": len(closes)},
        )

    changes = [later - earlier for earlier, later in zip(closes, closes[1:])]

    gains = [change if change > 0 else 0.0 for change in changes]
    losses = [-change if change < 0 else 0.0 for change in changes]

    # Seed with the simple average of the first `period` changes.
    avg_gain = fmean(gains[:period])
    avg_loss = fmean(losses[:period])

    # Smooth across every remaining change.
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    # No downward movement in the window: RSI is defined as 100.
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    relative_strength = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def annualized_volatility(
    closes: list[float], window: int = VOLATILITY_WINDOW
) -> float:
    """Annualized standard deviation of daily returns, as a percent.

    Computes simple daily returns over the last `window` periods, takes their
    sample standard deviation, and scales by sqrt(252) to express the figure
    on an annual basis. A return of 24.5 means 24.5%.

    Raises:
        InsufficientDataError: If fewer than `window + 1` closes are available.
    """
    if window < 2:
        raise ValueError("window must be at least 2")

    required = window + 1
    if len(closes) < required:
        raise InsufficientDataError(
            f"{window}-day volatility needs {required} daily closes; "
            f"only {len(closes)} are available.",
            details={"required": required, "available": len(closes)},
        )

    recent = closes[-required:]
    returns: list[float] = []
    for earlier, later in zip(recent, recent[1:]):
        if earlier == 0:
            # A zero close makes the return undefined. Skipping the observation
            # is correct; substituting one would invent a price movement.
            continue
        returns.append((later - earlier) / earlier)

    if len(returns) < 2:
        raise InsufficientDataError(
            "Not enough usable daily returns to measure volatility.",
            details={"usable_returns": len(returns)},
        )

    return stdev(returns) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0


def percent_change(earlier: float, later: float) -> float:
    """Percent change from `earlier` to `later`.

    Raises:
        InsufficientDataError: If `earlier` is zero, which makes the change
            mathematically undefined.
    """
    if earlier == 0:
        raise InsufficientDataError(
            "Cannot compute a percent change from a starting price of zero."
        )
    return ((later - earlier) / earlier) * 100.0


# ==========================================================================
# History helpers
# ==========================================================================
def _close_on_or_before(points: list[PricePoint], target: date) -> PricePoint | None:
    """Most recent point dated on or before `target`, or None if none exists.

    `points` must be sorted oldest-first, which the provider guarantees.
    """
    match: PricePoint | None = None
    for point in points:
        if point.date <= target:
            match = point
        else:
            break
    return match


def _change_over_calendar_days(points: list[PricePoint], days: int) -> float:
    """Percent change between the latest close and the one `days` ago.

    Markets are shut at weekends and on holidays, so the exact target date
    frequently has no data. The nearest earlier trading day is used instead,
    provided it is within `LOOKBACK_TOLERANCE_DAYS` - beyond that, the window
    is too distorted for the result to be described as a one- or three-month
    change.

    Raises:
        InsufficientDataError: If no suitable reference point exists.
    """
    latest = points[-1]
    target = latest.date - timedelta(days=days)
    reference = _close_on_or_before(points, target)

    if reference is None:
        raise InsufficientDataError(
            f"Price history does not reach back {days} days.",
            details={"required_days": days},
        )

    drift = (target - reference.date).days
    if drift > LOOKBACK_TOLERANCE_DAYS:
        raise InsufficientDataError(
            f"The closest available close is {drift} days before the "
            f"{days}-day mark, which is too far to be representative.",
            details={"required_days": days, "gap_days": drift},
        )

    return percent_change(reference.close, latest.close)


# ==========================================================================
# Orchestration
# ==========================================================================
def compute_indicators(history: PriceHistory) -> TechnicalIndicators:
    """Compute every indicator the supplied history can honestly support.

    Args:
        history: Daily prices, oldest first, as returned by the provider.

    Returns:
        A `TechnicalIndicators` model. Indicators the history cannot support are
        `None`, with the reason recorded in `unavailable`.

    Raises:
        InsufficientDataError: If the history holds fewer than two closes, in
            which case no indicator is computable.
    """
    points = history.points
    if len(points) < MIN_POINTS_FOR_ANY_INDICATOR:
        raise InsufficientDataError(
            "At least two daily closes are required to compute any indicator.",
            details={"available": len(points)},
        )

    closes = [point.close for point in points]
    latest = points[-1]
    unavailable: dict[str, str] = {}

    def attempt(name: str, calculate, digits: int) -> float | None:
        """Run one calculation, recording the reason on refusal."""
        try:
            return round(calculate(), digits)
        except InsufficientDataError as exc:
            unavailable[name] = exc.message
            return None

    sma_20 = attempt("sma_20", lambda: simple_moving_average(closes, SMA_SHORT_PERIOD), _PRICE_DP)
    sma_50 = attempt("sma_50", lambda: simple_moving_average(closes, SMA_LONG_PERIOD), _PRICE_DP)
    rsi_14 = attempt("rsi_14", lambda: relative_strength_index(closes, RSI_PERIOD), _RSI_DP)
    volatility = attempt(
        "volatility_30d",
        lambda: annualized_volatility(closes, VOLATILITY_WINDOW),
        _PERCENT_DP,
    )
    change_1m = attempt(
        "price_change_1m",
        lambda: _change_over_calendar_days(points, ONE_MONTH_DAYS),
        _PERCENT_DP,
    )
    change_3m = attempt(
        "price_change_3m",
        lambda: _change_over_calendar_days(points, THREE_MONTH_DAYS),
        _PERCENT_DP,
    )

    # -- 52-week range -----------------------------------------------------
    week_52_high: float | None = None
    week_52_low: float | None = None
    week_52_high_date: date | None = None
    week_52_low_date: date | None = None

    coverage_days = (latest.date - points[0].date).days
    if coverage_days < MIN_52_WEEK_COVERAGE_DAYS:
        reason = (
            f"A 52-week range needs about a year of history; only "
            f"{coverage_days} days are available."
        )
        unavailable["week_52_high"] = reason
        unavailable["week_52_low"] = reason
    else:
        cutoff = latest.date - timedelta(days=FIFTY_TWO_WEEK_DAYS)
        window = [point for point in points if point.date >= cutoff]
        highest = max(window, key=lambda point: point.close)
        lowest = min(window, key=lambda point: point.close)
        week_52_high = round(highest.close, _PRICE_DP)
        week_52_high_date = highest.date
        week_52_low = round(lowest.close, _PRICE_DP)
        week_52_low_date = lowest.date

    if unavailable:
        logger.debug(
            "%s: %d indicator(s) unavailable from %d closes: %s",
            history.symbol, len(unavailable), len(closes), ", ".join(sorted(unavailable)),
        )

    return TechnicalIndicators(
        symbol=history.symbol,
        as_of=latest.date,
        source=history.source,
        history_retrieved_at=history.retrieved_at,
        data_points_used=len(closes),
        sma_20=sma_20,
        sma_50=sma_50,
        rsi_14=rsi_14,
        volatility_30d=volatility,
        price_change_1m=change_1m,
        price_change_3m=change_3m,
        week_52_high=week_52_high,
        week_52_low=week_52_low,
        week_52_high_date=week_52_high_date,
        week_52_low_date=week_52_low_date,
        unavailable=unavailable,
    )
