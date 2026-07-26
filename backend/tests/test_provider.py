"""Alpha Vantage provider: normalization, error mapping, retries, key safety.

Alpha Vantage signals most failures with HTTP 200 and an explanatory key in the
body, so status codes alone cannot be trusted. These tests pin that behaviour
down, along with the rule that the API key — which travels as a query parameter
— never appears in a log line or an exception message.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import get_settings
from app.core.exceptions import (
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    TickerNotFoundError,
)
from app.services.providers.alpha_vantage import AlphaVantageProvider

from .conftest import (
    ALPHA_VANTAGE_URL,
    NEWS_PAYLOAD,
    OVERVIEW_PAYLOAD,
    QUOTE_PAYLOAD,
    build_daily_series,
)


@pytest.fixture
async def provider():
    """A provider instance whose HTTP client is closed after the test."""
    instance = AlphaVantageProvider(get_settings())
    yield instance
    await instance.aclose()


class TestQuoteNormalization:
    async def test_fields_are_normalized(self, provider, market_data) -> None:
        quote = await provider.get_quote("AAPL")

        assert quote.symbol == "AAPL"
        assert quote.price == pytest.approx(186.40)
        assert quote.previous_close == pytest.approx(184.90)
        assert quote.volume == 51234567
        # "0.8112%" -> 0.8112, with the percent sign stripped.
        assert quote.change_percent == pytest.approx(0.8112)
        assert quote.source == "Alpha Vantage"
        assert quote.retrieved_at is not None


class TestOverviewNormalization:
    async def test_missing_metrics_are_none_not_zero(
        self, provider, market_data
    ) -> None:
        overview = await provider.get_overview("AAPL")

        assert overview.pe_ratio == pytest.approx(31.2)
        # "None", "-" and "" in the upstream payload.
        assert overview.peg_ratio is None
        assert overview.forward_pe is None
        assert overview.ebitda is None
        # The distinction that matters.
        assert overview.peg_ratio != 0

    async def test_scalar_fields(self, provider, market_data) -> None:
        overview = await provider.get_overview("AAPL")
        assert overview.name == "Apple Inc"
        assert overview.market_cap == 2_900_000_000_000
        assert overview.currency == "USD"


class TestHistoryNormalization:
    async def test_points_are_chronological(self, provider, market_data) -> None:
        history = await provider.get_history("AAPL", 365)
        dates = [point.date for point in history.points]
        assert dates == sorted(dates)
        assert len(history.points) > 0

    async def test_window_is_respected(self, provider, market_data) -> None:
        history = await provider.get_history("AAPL", 30)
        assert len(history.points) <= 31

    async def test_rows_without_a_close_are_dropped(self, provider) -> None:
        """A day with no close is not a usable observation.

        Dropping it is correct; interpolating one would invent a price that
        then flows into every indicator computed from the series.
        """
        series = build_daily_series(10)
        broken_day = sorted(series)[3]
        series[broken_day]["4. close"] = "None"

        with respx.mock(assert_all_called=False) as router:
            router.get(ALPHA_VANTAGE_URL).mock(
                return_value=httpx.Response(
                    200, json={"Time Series (Daily)": series}
                )
            )
            history = await provider.get_history("AAPL", 365)

        assert len(history.points) == 9
        assert all(point.date.isoformat() != broken_day for point in history.points)


class TestNewsNormalization:
    async def test_unrenderable_articles_are_dropped(
        self, provider, market_data
    ) -> None:
        """An article with no headline or no link cannot be displayed."""
        news = await provider.get_news("AAPL", 10)
        assert len(news.articles) == 1
        assert news.articles[0].title == "Apple reports quarterly results"
        assert news.articles[0].published_at is not None

    async def test_empty_feed_is_not_an_error(self, provider) -> None:
        """No news is a valid outcome; the UI renders an empty state."""
        with respx.mock(assert_all_called=False) as router:
            router.get(ALPHA_VANTAGE_URL).mock(
                return_value=httpx.Response(200, json={"feed": []})
            )
            news = await provider.get_news("AAPL", 10)
        assert news.articles == []


class TestHttp200Errors:
    """Alpha Vantage reports failures with a 200 and a key in the body."""

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ({"Error Message": "Invalid API call"}, TickerNotFoundError),
            (
                {"Information": "Our standard API rate limit is 25 requests per day"},
                ProviderRateLimitError,
            ),
            (
                {"Note": "Thank you for using Alpha Vantage! Our API call frequency is 5 per minute"},
                ProviderRateLimitError,
            ),
            # An unknown symbol yields an empty object with no error key at all.
            ({"Global Quote": {}}, TickerNotFoundError),
        ],
    )
    async def test_error_bodies_map_to_exceptions(
        self, provider, payload: dict, expected: type[Exception]
    ) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(ALPHA_VANTAGE_URL).mock(
                return_value=httpx.Response(200, json=payload)
            )
            with pytest.raises(expected):
                await provider.get_quote("FAKE")

    async def test_empty_overview_is_not_found(self, provider) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(ALPHA_VANTAGE_URL).mock(
                return_value=httpx.Response(200, json={})
            )
            with pytest.raises(TickerNotFoundError):
                await provider.get_overview("FAKE")


class TestRetriesAndTimeouts:
    async def test_timeouts_are_retried_then_raise(self, provider) -> None:
        attempts = get_settings().http_max_retries + 1
        with respx.mock(assert_all_called=False) as router:
            route = router.get(ALPHA_VANTAGE_URL).mock(
                side_effect=httpx.ConnectTimeout("timed out")
            )
            with pytest.raises(ProviderTimeoutError):
                await provider.get_quote("AAPL")
        assert route.call_count == attempts

    async def test_server_errors_are_retried(self, provider) -> None:
        attempts = get_settings().http_max_retries + 1
        with respx.mock(assert_all_called=False) as router:
            route = router.get(ALPHA_VANTAGE_URL).mock(
                return_value=httpx.Response(500, text="boom")
            )
            with pytest.raises(ProviderError):
                await provider.get_quote("AAPL")
        assert route.call_count == attempts

    async def test_client_errors_are_not_retried(self, provider) -> None:
        """Repeating a rejected request cannot help."""
        with respx.mock(assert_all_called=False) as router:
            route = router.get(ALPHA_VANTAGE_URL).mock(
                return_value=httpx.Response(403, text="forbidden")
            )
            with pytest.raises(ProviderError):
                await provider.get_quote("AAPL")
        assert route.call_count == 1

    async def test_recovers_after_a_transient_failure(self, provider) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(ALPHA_VANTAGE_URL).mock(
                side_effect=[
                    httpx.Response(503, text="unavailable"),
                    httpx.Response(200, json=QUOTE_PAYLOAD),
                ]
            )
            quote = await provider.get_quote("AAPL")
        assert quote.price == pytest.approx(186.40)


class TestApiKeyIsNeverLeaked:
    """The key travels as a query parameter, so URLs must never be surfaced."""

    async def test_key_is_sent_upstream(self, provider, market_data) -> None:
        await provider.get_quote("AAPL")
        request = market_data.calls.last.request
        assert request.url.params["apikey"] == "TEST_MARKET_KEY"

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(500, text="boom"),
            httpx.Response(200, json={"Error Message": "Invalid API call"}),
            httpx.Response(200, json={"Information": "rate limit is 25 requests per day"}),
        ],
    )
    async def test_key_absent_from_exception_text(self, provider, response) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(ALPHA_VANTAGE_URL).mock(return_value=response)
            with pytest.raises(Exception) as caught:
                await provider.get_quote("AAPL")

        rendered = f"{caught.value!s} {caught.value!r} {getattr(caught.value, 'details', '')}"
        assert "TEST_MARKET_KEY" not in rendered

    async def test_key_absent_from_logs(self, provider, caplog) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(ALPHA_VANTAGE_URL).mock(
                return_value=httpx.Response(500, text="boom")
            )
            with pytest.raises(ProviderError):
                await provider.get_quote("AAPL")

        assert "TEST_MARKET_KEY" not in caplog.text
        assert "apikey" not in caplog.text


class TestUnconfiguredKey:
    async def test_missing_key_raises_configuration_error(self, monkeypatch) -> None:
        from pydantic import SecretStr

        from app.core.exceptions import ConfigurationError

        settings = get_settings()
        monkeypatch.setattr(
            settings, "alpha_vantage_api_key", SecretStr("your_key_here")
        )
        instance = AlphaVantageProvider(settings)
        try:
            with pytest.raises(ConfigurationError):
                await instance.get_quote("AAPL")
        finally:
            await instance.aclose()


class TestOverviewPayloadShape:
    def test_fixture_covers_the_missing_value_sentinels(self) -> None:
        """Guards the fixture itself, so these cases cannot silently vanish."""
        assert OVERVIEW_PAYLOAD["PEGRatio"] == "None"
        assert OVERVIEW_PAYLOAD["ForwardPE"] == "-"
        assert OVERVIEW_PAYLOAD["EBITDA"] == ""
        assert len(NEWS_PAYLOAD["feed"]) == 3
