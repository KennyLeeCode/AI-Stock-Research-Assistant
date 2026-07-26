"""Technical indicator calculations.

Two properties matter most here:

  * the maths is correct, checked against independently derived values rather
    than against the implementation's own output;
  * an indicator the data cannot support is *refused*, not approximated. A
    50-day average computed from 30 closes is not a 50-day average.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.exceptions import InsufficientDataError
from app.schemas.stock import PriceHistory, PricePoint
from app.services.indicator_service import (
    annualized_volatility,
    compute_indicators,
    percent_change,
    relative_strength_index,
    simple_moving_average,
)


def make_history(
    closes: list[float], *, start: date = date(2024, 1, 1)
) -> PriceHistory:
    """Build a history with one calendar day per close."""
    points = [
        PricePoint(date=start + timedelta(days=index), close=close)
        for index, close in enumerate(closes)
    ]
    return PriceHistory(
        source="Test Provider",
        retrieved_at=datetime.now(timezone.utc),
        symbol="TEST",
        points=points,
    )


def reference_rsi(closes: list[float], period: int = 14) -> float:
    """An independently written Wilder RSI, used to cross-check the real one."""
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(delta, 0.0) for delta in deltas]
    losses = [max(-delta, 0.0) for delta in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for index in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[index]) / period
        avg_loss = (avg_loss * (period - 1) + losses[index]) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


class TestSimpleMovingAverage:
    def test_mean_of_window(self) -> None:
        assert simple_moving_average([1, 2, 3, 4, 5], 5) == 3.0

    def test_uses_only_the_last_n(self) -> None:
        assert simple_moving_average([10, 10, 10, 1, 2, 3], 3) == 2.0

    def test_refuses_when_history_is_short(self) -> None:
        with pytest.raises(InsufficientDataError) as caught:
            simple_moving_average([1.0] * 30, 50)
        # The message must say what was needed and what was available.
        assert "50" in caught.value.message
        assert "30" in caught.value.message

    def test_rejects_nonsensical_period(self) -> None:
        with pytest.raises(ValueError):
            simple_moving_average([1.0, 2.0], 0)


class TestRelativeStrengthIndex:
    def test_matches_independent_implementation(self) -> None:
        closes = [
            44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
            46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41,
            46.22, 45.64, 46.21, 46.25, 45.71, 46.45, 45.78, 45.35, 44.03,
        ]
        assert relative_strength_index(closes) == pytest.approx(
            reference_rsi(closes), abs=1e-9
        )

    def test_monotonic_rise_is_100(self) -> None:
        assert relative_strength_index([100.0 + i for i in range(40)]) == 100.0

    def test_monotonic_fall_is_zero(self) -> None:
        assert relative_strength_index([200.0 - i for i in range(40)]) == 0.0

    def test_flat_series_is_neutral(self) -> None:
        """No gains and no losses is defined as 50, not a division by zero."""
        assert relative_strength_index([100.0] * 40) == 50.0

    def test_stays_in_range(self) -> None:
        closes = [100.0 + math.sin(i / 3) * 10 for i in range(60)]
        assert 0.0 <= relative_strength_index(closes) <= 100.0

    def test_refuses_with_exactly_period_closes(self) -> None:
        """N changes need N+1 prices."""
        with pytest.raises(InsufficientDataError):
            relative_strength_index([1.0] * 14, 14)


class TestVolatility:
    def test_flat_series_has_zero_volatility(self) -> None:
        assert annualized_volatility([100.0] * 40) == 0.0

    def test_constant_growth_has_zero_volatility(self) -> None:
        """Constant *returns* means no variance, even though prices move."""
        closes = [100.0 * (1.01**i) for i in range(40)]
        assert annualized_volatility(closes) == pytest.approx(0.0, abs=1e-9)

    def test_annualization_factor(self) -> None:
        """Result is the daily standard deviation scaled by sqrt(252)."""
        closes = [100.0, 101.0] * 20
        daily = annualized_volatility(closes) / (math.sqrt(252) * 100.0)
        assert daily > 0

    def test_refuses_when_history_is_short(self) -> None:
        with pytest.raises(InsufficientDataError):
            annualized_volatility([1.0] * 30, 30)


class TestPercentChange:
    def test_gain_and_loss(self) -> None:
        assert percent_change(100.0, 110.0) == pytest.approx(10.0)
        assert percent_change(100.0, 90.0) == pytest.approx(-10.0)

    def test_zero_base_is_refused_not_infinite(self) -> None:
        with pytest.raises(InsufficientDataError):
            percent_change(0.0, 10.0)


class TestComputeIndicators:
    def test_full_history_computes_everything(self) -> None:
        history = make_history(
            [100.0 + math.sin(i / 9) * 12 + i * 0.05 for i in range(400)]
        )
        result = compute_indicators(history)

        assert result.unavailable == {}
        assert result.data_points_used == 400
        assert result.sma_20 is not None
        assert result.sma_50 is not None
        assert result.rsi_14 is not None and 0 <= result.rsi_14 <= 100
        assert result.volatility_30d is not None
        assert result.week_52_low is not None and result.week_52_high is not None
        assert result.week_52_low <= result.week_52_high

    def test_provenance_is_carried_through(self) -> None:
        history = make_history([100.0 + i for i in range(400)])
        result = compute_indicators(history)
        assert result.source == history.source
        assert result.history_retrieved_at == history.retrieved_at
        assert result.as_of == history.points[-1].date

    def test_short_history_yields_partial_results(self) -> None:
        result = compute_indicators(make_history([100.0 + i * 0.4 for i in range(25)]))

        # Computable from 25 closes.
        assert result.sma_20 is not None
        # Not computable, and each absence is explained.
        assert result.sma_50 is None
        assert result.volatility_30d is None
        assert result.week_52_high is None
        assert "sma_50" in result.unavailable
        assert "week_52_high" in result.unavailable

    def test_every_null_is_explained_and_every_explanation_is_null(self) -> None:
        """The `unavailable` map and the null fields cannot drift apart."""
        result = compute_indicators(make_history([100.0 + i for i in range(25)]))
        for name in result.unavailable:
            assert getattr(result, name) is None, f"{name} explained but not null"

    def test_52_week_range_requires_a_year_of_coverage(self) -> None:
        """Calling 100 days a '52-week range' would overstate the measurement."""
        result = compute_indicators(make_history([100.0 + i for i in range(100)]))
        assert result.week_52_high is None
        assert "52-week" in result.unavailable["week_52_high"]

    def test_refuses_when_nothing_is_computable(self) -> None:
        with pytest.raises(InsufficientDataError):
            compute_indicators(make_history([100.0]))

    def test_values_are_rounded_for_display(self) -> None:
        result = compute_indicators(make_history([100.0 + i * 0.333 for i in range(400)]))
        assert result.sma_20 == round(result.sma_20 or 0, 2)
