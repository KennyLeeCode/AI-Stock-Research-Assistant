"""Market-data endpoints, exercised over real HTTP against a mocked provider."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from .conftest import ALPHA_VANTAGE_URL, QUOTE_PAYLOAD


class TestQuote:
    def test_returns_normalized_quote(self, client: TestClient, market_data) -> None:
        response = client.get("/api/stocks/AAPL/quote")
        assert response.status_code == 200

        body = response.json()
        assert body["symbol"] == "AAPL"
        assert body["price"] == pytest.approx(186.40)
        assert body["source"] == "Alpha Vantage"
        assert body["retrieved_at"]

    def test_lowercase_input_is_normalized(
        self, client: TestClient, market_data
    ) -> None:
        assert client.get("/api/stocks/aapl/quote").json()["symbol"] == "AAPL"


class TestHistory:
    def test_points_are_chronological(self, client: TestClient, market_data) -> None:
        points = client.get("/api/stocks/AAPL/history", params={"days": 90}).json()[
            "points"
        ]
        assert len(points) > 0
        assert [p["date"] for p in points] == sorted(p["date"] for p in points)

    @pytest.mark.parametrize("days", [0, -1, 99999])
    def test_out_of_range_days_rejected(
        self, client: TestClient, market_data, days: int
    ) -> None:
        response = client.get("/api/stocks/AAPL/history", params={"days": days})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


class TestOverview:
    def test_missing_metrics_serialize_as_null(
        self, client: TestClient, market_data
    ) -> None:
        body = client.get("/api/stocks/AAPL/overview").json()

        assert body["pe_ratio"] == pytest.approx(31.2)
        assert body["peg_ratio"] is None
        assert body["forward_pe"] is None
        assert body["ebitda"] is None
        # The rule this whole project is built around.
        assert body["peg_ratio"] != 0


class TestIndicators:
    def test_computed_from_history(self, client: TestClient, market_data) -> None:
        body = client.get("/api/stocks/AAPL/indicators").json()

        assert body["symbol"] == "AAPL"
        assert body["sma_20"] is not None
        assert body["sma_50"] is not None
        assert 0 <= body["rsi_14"] <= 100
        assert body["data_points_used"] > 0

    def test_unavailable_map_matches_null_fields(
        self, client: TestClient, market_data
    ) -> None:
        body = client.get("/api/stocks/AAPL/indicators").json()
        for name in body["unavailable"]:
            assert body[name] is None


class TestNews:
    def test_drops_unrenderable_articles(
        self, client: TestClient, market_data
    ) -> None:
        body = client.get("/api/stocks/AAPL/news", params={"limit": 5}).json()
        assert len(body["articles"]) == 1
        assert body["articles"][0]["url"].startswith("https://")

    @pytest.mark.parametrize("limit", [0, 999])
    def test_out_of_range_limit_rejected(
        self, client: TestClient, market_data, limit: int
    ) -> None:
        response = client.get("/api/stocks/AAPL/news", params={"limit": limit})
        assert response.status_code == 422


class TestInputValidation:
    @pytest.mark.parametrize(
        ("ticker", "status", "code"),
        [
            ("12345", 400, "invalid_ticker"),
            ("AA..PL", 400, "invalid_ticker"),
            ("TOOLONGSYMBOL", 400, "invalid_ticker"),
        ],
    )
    def test_malformed_tickers_rejected(
        self, client: TestClient, market_data, ticker: str, status: int, code: str
    ) -> None:
        response = client.get(f"/api/stocks/{ticker}/quote")
        assert response.status_code == status
        assert response.json()["error"]["code"] == code

    def test_no_provider_call_for_invalid_ticker(
        self, client: TestClient, market_data
    ) -> None:
        """Validation happens before anything leaves the server."""
        client.get("/api/stocks/12345/quote")
        assert market_data.calls.call_count == 0


class TestUpstreamFailures:
    def test_unknown_symbol_is_404(self, client: TestClient, market_data) -> None:
        response = client.get("/api/stocks/NOSUCH/quote")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ticker_not_found"

    def test_quota_exhaustion_is_429(self, client: TestClient, market_data) -> None:
        response = client.get("/api/stocks/QUOTA/quote")
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "provider_rate_limited"

    def test_timeout_is_504(self, client: TestClient) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(ALPHA_VANTAGE_URL).mock(
                side_effect=httpx.ConnectTimeout("timed out")
            )
            response = client.get("/api/stocks/AAPL/quote")
        assert response.status_code == 504
        assert response.json()["error"]["code"] == "provider_timeout"

    def test_upstream_5xx_is_502(self, client: TestClient) -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(ALPHA_VANTAGE_URL).mock(
                return_value=httpx.Response(500, text="boom")
            )
            response = client.get("/api/stocks/AAPL/quote")
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "provider_error"


class TestCaching:
    def test_repeat_requests_hit_the_cache(
        self, client: TestClient, market_data
    ) -> None:
        """The whole reason a 25-request daily quota is workable."""
        client.get("/api/stocks/AAPL/quote")
        first = market_data.calls.call_count

        client.get("/api/stocks/AAPL/quote")
        client.get("/api/stocks/AAPL/quote")

        assert market_data.calls.call_count == first == 1

    def test_different_symbols_are_cached_separately(
        self, client: TestClient, market_data
    ) -> None:
        client.get("/api/stocks/AAPL/quote")
        client.get("/api/stocks/MSFT/quote")
        assert market_data.calls.call_count == 2

    def test_indicators_reuse_cached_history(
        self, client: TestClient, market_data
    ) -> None:
        """Indicators must not cost a second provider call."""
        client.get("/api/stocks/AAPL/history", params={"days": 365})
        after_history = market_data.calls.call_count

        client.get("/api/stocks/AAPL/indicators")

        assert market_data.calls.call_count == after_history

    def test_failures_are_not_cached(self, client: TestClient) -> None:
        """A transient outage must not persist for the length of a TTL."""
        with respx.mock(assert_all_called=False) as router:
            router.get(ALPHA_VANTAGE_URL).mock(
                return_value=httpx.Response(500, text="boom")
            )
            assert client.get("/api/stocks/AAPL/quote").status_code == 502

        with respx.mock(assert_all_called=False) as router:
            router.get(ALPHA_VANTAGE_URL).mock(
                return_value=httpx.Response(200, json=QUOTE_PAYLOAD)
            )
            assert client.get("/api/stocks/AAPL/quote").status_code == 200
