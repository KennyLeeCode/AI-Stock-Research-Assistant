"""Shared test fixtures.

Two things must happen before anything from `app` is imported:

  * `DATABASE_URL` has to point at a throwaway file, because `app.database`
    builds its engine at module import time. Importing first and patching after
    would leave the tests writing to the development database.
  * The API keys have to look real. `Settings.has_market_data_key` rejects
    placeholder values like `your_..._here`, so leaving the sample values in
    place would make every provider call raise `ConfigurationError` instead of
    exercising the code under test.

No test in this suite makes a real network call. Market-data requests are
intercepted by `respx`, and the AI client is replaced outright.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Environment — must precede any `app` import.
# ---------------------------------------------------------------------------
_TEST_DB_DIR = tempfile.mkdtemp(prefix="stock-research-tests-")
_TEST_DB_PATH = os.path.join(_TEST_DB_DIR, "test.db").replace("\\", "/")

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["ALPHA_VANTAGE_API_KEY"] = "TEST_MARKET_KEY"
os.environ["ANTHROPIC_API_KEY"] = "TEST_AI_KEY"
os.environ["ENVIRONMENT"] = "development"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["HTTP_MAX_RETRIES"] = "2"

import warnings  # noqa: E402

# Starlette warns that its TestClient still uses httpx. The suite runs with
# `filterwarnings = error`, and that warning fires at *import* time — before
# pytest applies the filters from pytest.ini — so it has to be silenced here or
# it aborts collection. Scoped to this one message so genuine warnings still
# fail the build.
warnings.filterwarnings(
    "ignore",
    message=r".*`httpx` with `starlette\.testclient` is deprecated.*",
)

import httpx  # noqa: E402
import pytest  # noqa: E402
import respx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.core.cache import cache  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import WatchlistItem  # noqa: E402

SETTINGS = get_settings()
ALPHA_VANTAGE_URL = SETTINGS.alpha_vantage_base_url


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    """Create the schema once, and delete the database file afterwards."""
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    """Reset shared state between tests.

    The cache and the watchlist table are process-wide, so without this a test
    that saved a ticker or warmed the cache would silently change the outcome
    of the next one. Ordering-dependent tests are worse than no tests.
    """
    cache.clear()
    with engine.begin() as connection:
        connection.execute(WatchlistItem.__table__.delete())
    yield
    cache.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A test client with the application's lifespan running."""
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Synthetic upstream payloads
# ---------------------------------------------------------------------------
def build_daily_series(days: int = 420) -> dict[str, dict[str, str]]:
    """A deterministic price series shaped like Alpha Vantage's response."""
    start = date.today() - timedelta(days=days)
    series: dict[str, dict[str, str]] = {}
    for index in range(days):
        day = start + timedelta(days=index)
        close = 100.0 + (index % 37) * 0.8 + index * 0.05
        series[day.isoformat()] = {
            "1. open": f"{close - 0.5:.4f}",
            "2. high": f"{close + 1.0:.4f}",
            "3. low": f"{close - 1.0:.4f}",
            "4. close": f"{close:.4f}",
            "5. volume": "1000000",
        }
    return series


QUOTE_PAYLOAD: dict[str, Any] = {
    "Global Quote": {
        "01. symbol": "AAPL",
        "02. open": "185.0000",
        "03. high": "187.0500",
        "04. low": "184.2100",
        "05. price": "186.4000",
        "06. volume": "51234567",
        "07. latest trading day": date.today().isoformat(),
        "08. previous close": "184.9000",
        "09. change": "1.5000",
        "10. change percent": "0.8112%",
    }
}

OVERVIEW_PAYLOAD: dict[str, Any] = {
    "Symbol": "AAPL",
    "Name": "Apple Inc",
    "Description": "Apple designs and sells consumer electronics.",
    "Exchange": "NASDAQ",
    "Currency": "USD",
    "Country": "USA",
    "Sector": "TECHNOLOGY",
    "Industry": "ELECTRONIC COMPUTERS",
    "MarketCapitalization": "2900000000000",
    "PERatio": "31.2",
    # Values Alpha Vantage uses for "no data". These must become None, not 0.
    "PEGRatio": "None",
    "ForwardPE": "-",
    "EBITDA": "",
    "DividendYield": "0.0044",
    "EPS": "6.13",
    "Beta": "1.29",
    "ProfitMargin": "0.253",
    "52WeekHigh": "199.62",
    "52WeekLow": "164.08",
    "LatestQuarter": "2026-06-30",
}

NEWS_PAYLOAD: dict[str, Any] = {
    "feed": [
        {
            "title": "Apple reports quarterly results",
            "url": "https://example.com/article-1",
            "source": "Example Wire",
            "time_published": "20260724T133000",
            "summary": "A summary of the results.",
            "overall_sentiment_label": "Bullish",
            "overall_sentiment_score": "0.31",
        },
        # Unrenderable entries the provider must drop.
        {"title": None, "url": "https://example.com/article-2"},
        {"title": "Missing link", "url": ""},
    ]
}


def _dispatch(request: httpx.Request) -> httpx.Response:
    """Route a mocked request by its `function` query parameter."""
    params = request.url.params
    symbol = params.get("symbol") or params.get("tickers") or ""

    if symbol == "NOSUCH":
        return httpx.Response(200, json={"Error Message": "Invalid API call"})
    if symbol == "QUOTA":
        return httpx.Response(
            200, json={"Information": "Our standard API rate limit is 25 requests per day"}
        )

    function = params.get("function")
    if function == "GLOBAL_QUOTE":
        return httpx.Response(200, json=QUOTE_PAYLOAD)
    if function == "TIME_SERIES_DAILY":
        return httpx.Response(200, json={"Time Series (Daily)": build_daily_series()})
    if function == "OVERVIEW":
        return httpx.Response(200, json=OVERVIEW_PAYLOAD)
    if function == "NEWS_SENTIMENT":
        return httpx.Response(200, json=NEWS_PAYLOAD)

    return httpx.Response(404, json={"Error Message": "unknown function"})


@pytest.fixture
def market_data() -> Iterator[respx.MockRouter]:
    """Intercept every Alpha Vantage call with deterministic payloads."""
    with respx.mock(assert_all_called=False) as router:
        router.get(ALPHA_VANTAGE_URL).mock(side_effect=_dispatch)
        yield router
