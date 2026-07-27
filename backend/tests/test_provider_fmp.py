"""Financial Modeling Prep provider.

FMP reports failures with real HTTP status codes rather than a 200 with an error
body, but it overloads 402: the same status covers both "your plan does not
include this endpoint" and "your plan cannot query this symbol". Only the
message distinguishes them, and getting that wrong turns an unknown ticker into
a confusing server error. These tests pin the distinction down.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import get_settings
from app.core.exceptions import (
    ConfigurationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    TickerNotFoundError,
)
from app.services.providers.fmp import FMPProvider

from .conftest import (
    FMP_QUOTE,
    FMP_RESTRICTED_BODY,
    FMP_UNKNOWN_SYMBOL_BODY,
    FMP_URL,
    build_fmp_series,
)


@pytest.fixture
async def provider():
    """A provider whose HTTP client is closed after the test."""
    instance = FMPProvider(get_settings())
    yield instance
    await instance.aclose()


class TestQuoteNormalization:
    async def test_fields_are_normalized(self, provider, market_data) -> None:
        quote = await provider.get_quote("AAPL")

        assert quote.symbol == "AAPL"
        assert quote.price == pytest.approx(336.91)
        assert quote.previous_close == pytest.approx(333.02)
        assert quote.volume == 45246885
        # FMP already returns a percentage, so no scaling is applied.
        assert quote.change_percent == pytest.approx(1.1681)
        assert quote.source == "Financial Modeling Prep"

    async def test_trading_day_is_absent_not_guessed(
        self, provider, market_data
    ) -> None:
        """FMP returns a unix timestamp, not an exchange date.

        Converting it would mean assuming a timezone, so the field is left
        unset rather than filled with a value that could be a day out.
        """
        quote = await provider.get_quote("AAPL")
        assert quote.latest_trading_day is None


class TestHistoryNormalization:
    async def test_points_are_chronological(self, provider, market_data) -> None:
        """FMP returns newest first; the application contract is oldest first."""
        history = await provider.get_history("AAPL", 365)
        dates = [point.date for point in history.points]

        assert len(dates) > 0
        assert dates == sorted(dates)

    async def test_range_is_bounded_server_side(self, provider, market_data) -> None:
        """Unbounded, this endpoint returns ~280 KB going back decades."""
        await provider.get_history("AAPL", 90)
        params = market_data.calls.last.request.url.params

        assert "from" in params
        assert "to" in params

    async def test_rows_without_a_close_are_dropped(self, provider) -> None:
        rows = build_fmp_series(10)
        rows[3]["close"] = None

        with respx.mock(assert_all_called=False) as router:
            router.get(url__startswith=FMP_URL).mock(
                return_value=httpx.Response(200, json=rows)
            )
            history = await provider.get_history("AAPL", 365)

        assert len(history.points) == 9

    async def test_empty_history_is_not_found(self, provider) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(url__startswith=FMP_URL).mock(
                return_value=httpx.Response(200, json=[])
            )
            with pytest.raises(TickerNotFoundError):
                await provider.get_history("AAPL", 365)


class TestOverviewComposition:
    async def test_combines_four_endpoints(self, provider, market_data) -> None:
        """No single FMP endpoint carries a full fundamentals picture."""
        overview = await provider.get_overview("AAPL")

        assert overview.name == "Apple Inc."          # profile
        assert overview.pe_ratio is not None          # ratios-ttm
        assert overview.return_on_equity is not None  # key-metrics-ttm
        assert overview.revenue_ttm is not None       # income-statement
        assert market_data.calls.call_count == 4

    async def test_52_week_range_is_split_from_a_string(
        self, provider, market_data
    ) -> None:
        """The profile gives `range` as "201.5-339.57", not two numbers."""
        overview = await provider.get_overview("AAPL")

        assert overview.week_52_low == pytest.approx(201.5)
        assert overview.week_52_high == pytest.approx(339.57)

    async def test_unoffered_metrics_are_none_not_zero(
        self, provider, market_data
    ) -> None:
        """FMP has no forward P/E or analyst target on any plan."""
        overview = await provider.get_overview("AAPL")

        assert overview.forward_pe is None
        assert overview.analyst_target_price is None
        assert overview.forward_pe != 0

    async def test_secondary_endpoints_are_best_effort(self, provider) -> None:
        """A restricted ratios endpoint must not blank the company profile.

        Losing the description and sector because one supplementary call was
        rejected would be a worse outcome than showing the profile with some
        metrics missing.
        """
        from .conftest import FMP_PROFILE

        def dispatch(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/profile"):
                return httpx.Response(200, json=FMP_PROFILE)
            return httpx.Response(402, text=FMP_RESTRICTED_BODY)

        with respx.mock(assert_all_called=False) as router:
            router.get(url__startswith=FMP_URL).mock(side_effect=dispatch)
            overview = await provider.get_overview("AAPL")

        assert overview.name == "Apple Inc."
        assert overview.sector == "Technology"
        # Everything the restricted endpoints would have supplied is absent.
        assert overview.pe_ratio is None
        assert overview.return_on_equity is None

    async def test_missing_profile_is_fatal(self, provider) -> None:
        """The profile is the one required call."""
        with respx.mock(assert_all_called=False) as router:
            router.get(url__startswith=FMP_URL).mock(
                return_value=httpx.Response(200, json=[])
            )
            with pytest.raises(TickerNotFoundError):
                await provider.get_overview("AAPL")


class TestNewsDegradesGracefully:
    async def test_returns_empty_feed_with_a_reason(self, provider) -> None:
        """News needs a paid plan, so an empty feed explains itself.

        Raising would show an error panel on every ticker; returning a bare
        empty list would imply the company has no coverage.
        """
        news = await provider.get_news("AAPL", 10)

        assert news.articles == []
        assert news.note is not None
        assert "plan" in news.note.lower()

    async def test_makes_no_upstream_call(self, provider, market_data) -> None:
        await provider.get_news("AAPL", 10)
        assert market_data.calls.call_count == 0


class TestOverloaded402:
    """One status code, two meanings, distinguished only by the message."""

    async def test_unknown_symbol_is_not_found(self, provider) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(url__startswith=FMP_URL).mock(
                return_value=httpx.Response(402, text=FMP_UNKNOWN_SYMBOL_BODY)
            )
            with pytest.raises(TickerNotFoundError):
                await provider.get_quote("ZZZZQQ")

    async def test_restricted_endpoint_is_a_provider_error(self, provider) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(url__startswith=FMP_URL).mock(
                return_value=httpx.Response(402, text=FMP_RESTRICTED_BODY)
            )
            with pytest.raises(ProviderError) as caught:
                await provider.get_quote("AAPL")
        assert not isinstance(caught.value, TickerNotFoundError)
        assert "paid" in caught.value.message.lower()


class TestOtherStatusCodes:
    async def test_bad_key_is_a_configuration_error(self, provider) -> None:
        """A rejected key is the operator's problem, not the user's."""
        with respx.mock(assert_all_called=False) as router:
            router.get(url__startswith=FMP_URL).mock(
                return_value=httpx.Response(
                    401, json={"Error Message": "Invalid API KEY."}
                )
            )
            with pytest.raises(ConfigurationError):
                await provider.get_quote("AAPL")

    async def test_429_is_a_rate_limit(self, provider) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(url__startswith=FMP_URL).mock(
                return_value=httpx.Response(429, json={"Error Message": "Limit Reach."})
            )
            with pytest.raises(ProviderRateLimitError):
                await provider.get_quote("AAPL")

    async def test_retired_v3_route_is_a_provider_error(self, provider) -> None:
        """FMP answers its retired /api/v3 endpoints with 403."""
        with respx.mock(assert_all_called=False) as router:
            router.get(url__startswith=FMP_URL).mock(
                return_value=httpx.Response(
                    403, json={"Error Message": "Legacy Endpoint"}
                )
            )
            with pytest.raises(ProviderError):
                await provider.get_quote("AAPL")


class TestRetries:
    async def test_timeouts_are_retried_then_raise(self, provider) -> None:
        attempts = get_settings().http_max_retries + 1
        with respx.mock(assert_all_called=False) as router:
            route = router.get(url__startswith=FMP_URL).mock(
                side_effect=httpx.ConnectTimeout("timed out")
            )
            with pytest.raises(ProviderTimeoutError):
                await provider.get_quote("AAPL")
        assert route.call_count == attempts

    async def test_client_errors_are_not_retried(self, provider) -> None:
        with respx.mock(assert_all_called=False) as router:
            route = router.get(url__startswith=FMP_URL).mock(
                return_value=httpx.Response(429, json={"Error Message": "Limit"})
            )
            with pytest.raises(ProviderRateLimitError):
                await provider.get_quote("AAPL")
        assert route.call_count == 1

    async def test_recovers_after_a_transient_failure(self, provider) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(url__startswith=FMP_URL).mock(
                side_effect=[
                    httpx.Response(503, text="unavailable"),
                    httpx.Response(200, json=FMP_QUOTE),
                ]
            )
            quote = await provider.get_quote("AAPL")
        assert quote.price == pytest.approx(336.91)


class TestApiKeyIsNeverLeaked:
    async def test_key_is_sent_upstream(self, provider, market_data) -> None:
        await provider.get_quote("AAPL")
        assert market_data.calls.last.request.url.params["apikey"] == "TEST_FMP_KEY"

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(500, text="boom"),
            httpx.Response(402, text=FMP_UNKNOWN_SYMBOL_BODY),
            httpx.Response(401, json={"Error Message": "Invalid API KEY."}),
        ],
    )
    async def test_key_absent_from_exception_text(self, provider, response) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(url__startswith=FMP_URL).mock(return_value=response)
            with pytest.raises(Exception) as caught:
                await provider.get_quote("AAPL")

        rendered = f"{caught.value!s} {caught.value!r} {getattr(caught.value, 'details', '')}"
        assert "TEST_FMP_KEY" not in rendered

    async def test_key_absent_from_logs(self, provider, caplog) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(url__startswith=FMP_URL).mock(
                return_value=httpx.Response(500, text="boom")
            )
            with pytest.raises(ProviderError):
                await provider.get_quote("AAPL")

        assert "TEST_FMP_KEY" not in caplog.text
        assert "apikey" not in caplog.text


class TestUnconfiguredKey:
    async def test_missing_key_raises_configuration_error(self, monkeypatch) -> None:
        from pydantic import SecretStr

        settings = get_settings()
        monkeypatch.setattr(settings, "fmp_api_key", SecretStr("your_key_here"))
        instance = FMPProvider(settings)
        try:
            with pytest.raises(ConfigurationError):
                await instance.get_quote("AAPL")
        finally:
            await instance.aclose()
