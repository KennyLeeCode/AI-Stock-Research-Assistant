"""Watchlist endpoints."""

from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from .conftest import ALPHA_VANTAGE_URL


class TestListing:
    def test_empty_watchlist_is_a_normal_state(self, client: TestClient) -> None:
        response = client.get("/api/watchlist")
        assert response.status_code == 200
        assert response.json() == []

    def test_newest_first(self, client: TestClient, market_data) -> None:
        client.post("/api/watchlist", json={"ticker": "AAPL"})
        client.post("/api/watchlist", json={"ticker": "MSFT"})

        tickers = [item["ticker"] for item in client.get("/api/watchlist").json()]
        assert tickers == ["MSFT", "AAPL"]


class TestAdding:
    def test_creates_and_normalizes(self, client: TestClient, market_data) -> None:
        response = client.post("/api/watchlist", json={"ticker": "  aapl  "})

        assert response.status_code == 201
        body = response.json()
        assert body["ticker"] == "AAPL"
        assert body["id"] > 0
        # SQLite stores naive datetimes; the schema normalizes to aware UTC.
        assert body["created_at"].endswith("Z") or "+00:00" in body["created_at"]

    def test_company_name_is_resolved(self, client: TestClient, market_data) -> None:
        body = client.post("/api/watchlist", json={"ticker": "AAPL"}).json()
        assert body["company_name"] == "Apple Inc"

    def test_blank_notes_become_null(self, client: TestClient, market_data) -> None:
        """One absent case for the frontend to handle, not two."""
        body = client.post(
            "/api/watchlist", json={"ticker": "AAPL", "notes": "   "}
        ).json()
        assert body["notes"] is None

    def test_notes_are_stored(self, client: TestClient, market_data) -> None:
        body = client.post(
            "/api/watchlist", json={"ticker": "AAPL", "notes": "Watch earnings"}
        ).json()
        assert body["notes"] == "Watch earnings"

    def test_duplicate_is_rejected(self, client: TestClient, market_data) -> None:
        client.post("/api/watchlist", json={"ticker": "AAPL"})
        response = client.post("/api/watchlist", json={"ticker": "aapl"})

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "duplicate_resource"

    def test_invalid_ticker_is_rejected(self, client: TestClient) -> None:
        response = client.post("/api/watchlist", json={"ticker": "12345"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_saves_even_when_provider_is_down(self, client: TestClient) -> None:
        """A third-party outage must not stop the user saving a ticker."""
        with respx.mock(assert_all_called=False) as router:
            router.get(ALPHA_VANTAGE_URL).mock(
                return_value=httpx.Response(500, text="boom")
            )
            response = client.post("/api/watchlist", json={"ticker": "AAPL"})

        assert response.status_code == 201
        assert response.json()["company_name"] is None


class TestRemoving:
    def test_removes_and_returns_204(self, client: TestClient, market_data) -> None:
        client.post("/api/watchlist", json={"ticker": "AAPL"})

        response = client.delete("/api/watchlist/aapl")

        assert response.status_code == 204
        assert response.content == b""
        assert client.get("/api/watchlist").json() == []

    def test_removing_absent_ticker_is_404(self, client: TestClient) -> None:
        response = client.delete("/api/watchlist/AAPL")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_invalid_ticker_is_400(self, client: TestClient) -> None:
        response = client.delete("/api/watchlist/12345")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_ticker"


class TestPersistence:
    def test_entries_survive_across_clients(
        self, client: TestClient, market_data
    ) -> None:
        """Proves the row is in the database, not in process memory."""
        client.post("/api/watchlist", json={"ticker": "AAPL"})

        from app.main import app

        with TestClient(app) as second_client:
            tickers = [
                item["ticker"] for item in second_client.get("/api/watchlist").json()
            ]

        assert tickers == ["AAPL"]
