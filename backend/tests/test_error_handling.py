"""Error envelope, request tracing, and information disclosure.

The frontend branches on `error.code`, so a single response missing it is a
crash rather than a handled state. And a 500 must expose exactly one piece of
internal state - the request id - and nothing else.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.main import app

from .conftest import FMP_URL

SECRET = "sk-ant-DO-NOT-LEAK"


@pytest.fixture(scope="module", autouse=True)
def _boom_route():
    """A deliberately crashing route, registered once for this module."""

    @app.get("/api/_test_boom")
    def boom() -> dict[str, str]:
        raise RuntimeError(f"synthetic failure carrying {SECRET}")

    yield
    # Leaving the route registered would leak a crashing endpoint into any
    # later module that builds a client from the same app object.
    app.router.routes = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) != "/api/_test_boom"
    ]


@pytest.fixture
def unsafe_client() -> TestClient:
    """A client that returns the 500 response instead of re-raising."""
    return TestClient(app, raise_server_exceptions=False)


class TestEnvelopeConsistency:
    @pytest.mark.parametrize(
        ("method", "path", "status"),
        [
            ("get", "/api/stocks/12345/quote", 400),
            ("get", "/api/nonexistent-route", 404),
            ("get", "/api/watchlist/12345", 404),
            ("delete", "/api/watchlist/AAPL", 404),
        ],
    )
    def test_every_error_has_code_and_message(
        self, client: TestClient, method: str, path: str, status: int
    ) -> None:
        response = getattr(client, method)(path)
        body = response.json()

        assert "error" in body, f"{path} did not use the error envelope"
        assert isinstance(body["error"].get("code"), str)
        assert isinstance(body["error"].get("message"), str)

    def test_unmatched_route_uses_the_envelope(self, client: TestClient) -> None:
        """Starlette's default is `{"detail": ...}`, which has no `code`."""
        body = client.get("/api/definitely-not-a-route").json()
        assert body["error"]["code"] == "not_found"
        assert "detail" not in body

    def test_method_not_allowed_uses_the_envelope(self, client: TestClient) -> None:
        body = client.put("/api/health").json()
        assert body["error"]["code"] == "method_not_allowed"


class TestRequestTracing:
    def test_id_on_successful_responses(self, client: TestClient) -> None:
        request_id = client.get("/api/health").headers.get("X-Request-ID")
        assert request_id and len(request_id) == 16

    def test_ids_are_unique_per_request(self, client: TestClient) -> None:
        first = client.get("/api/health").headers["X-Request-ID"]
        second = client.get("/api/health").headers["X-Request-ID"]
        assert first != second

    def test_client_supplied_id_is_propagated(self, client: TestClient) -> None:
        """Lets a reverse proxy trace a request through this service."""
        response = client.get(
            "/api/health", headers={"X-Request-ID": "trace-abc-123"}
        )
        assert response.headers["X-Request-ID"] == "trace-abc-123"

    @pytest.mark.parametrize(
        "hostile",
        [
            "a b\nX-Injected: yes",
            "id\r\nSet-Cookie: evil=1",
            "Z" * 500,
        ],
    )
    def test_hostile_ids_are_sanitized(
        self, client: TestClient, hostile: str
    ) -> None:
        """The value lands in a log line and a response header."""
        echoed = client.get(
            "/api/health", headers={"X-Request-ID": hostile}
        ).headers["X-Request-ID"]

        assert "\n" not in echoed
        assert "\r" not in echoed
        assert " " not in echoed
        assert len(echoed) <= 64


class TestServerErrors:
    def test_500_uses_the_envelope(self, unsafe_client: TestClient) -> None:
        response = unsafe_client.get("/api/_test_boom")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"

    def test_500_carries_a_correlation_id(self, unsafe_client: TestClient) -> None:
        response = unsafe_client.get("/api/_test_boom")
        body = response.json()

        assert "request_id" in body["error"]
        # Body and header must agree, or the id is useless for correlation.
        assert body["error"]["request_id"] == response.headers.get("X-Request-ID")

    @pytest.mark.parametrize(
        "leak", [SECRET, "RuntimeError", "Traceback", "synthetic failure"]
    )
    def test_no_internal_detail_is_disclosed(
        self, unsafe_client: TestClient, leak: str
    ) -> None:
        assert leak not in unsafe_client.get("/api/_test_boom").text

    def test_client_errors_omit_the_correlation_id(
        self, client: TestClient
    ) -> None:
        """A 4xx is the caller's to fix; a trace id there is noise."""
        body = client.get("/api/stocks/12345/quote").json()
        assert "request_id" not in body["error"]


class TestUpstreamErrorsAreTranslated:
    def test_provider_url_is_not_disclosed(self, client: TestClient) -> None:
        """The upstream URL carries the API key as a query parameter."""
        with respx.mock(assert_all_called=False) as router:
            router.get(url__startswith=FMP_URL).mock(
                return_value=httpx.Response(500, text="boom")
            )
            text = client.get("/api/stocks/AAPL/quote").text

        assert "apikey" not in text
        assert "TEST_FMP_KEY" not in text
        assert "financialmodelingprep.com" not in text


class TestHealth:
    def test_reports_configuration_without_revealing_it(
        self, client: TestClient
    ) -> None:
        body = client.get("/api/health").json()

        assert body["status"] == "ok"
        assert body["dependencies"]["market_data_configured"] is True
        assert body["dependencies"]["ai_configured"] is True
        # Booleans only - never the values.
        assert "TEST_FMP_KEY" not in client.get("/api/health").text
