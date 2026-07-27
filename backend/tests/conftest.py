"""Shared test fixtures.

Two things must happen before anything from `app` is imported:

  * `DATABASE_URL` has to point at a throwaway file, because `app.database`
    builds its engine at module import time. Importing first and patching after
    would leave the tests writing to the development database.
  * The API keys have to look real. `Settings` rejects placeholder values like
    `your_..._here`, so leaving the sample values in place would make every
    provider call raise `ConfigurationError` instead of exercising the code
    under test.

No test in this suite makes a real network call. Market-data requests are
intercepted by `respx`, and the AI client is replaced outright.

Both providers are configured with keys so that provider-specific unit tests can
construct either one directly, regardless of which is selected.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Environment - must precede any `app` import.
# ---------------------------------------------------------------------------
_TEST_DB_DIR = tempfile.mkdtemp(prefix="stock-research-tests-")
_TEST_DB_PATH = os.path.join(_TEST_DB_DIR, "test.db").replace("\\", "/")

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["MARKET_DATA_PROVIDER"] = "fmp"
os.environ["FMP_API_KEY"] = "TEST_FMP_KEY"
os.environ["ALPHA_VANTAGE_API_KEY"] = "TEST_MARKET_KEY"
os.environ["ANTHROPIC_API_KEY"] = "TEST_AI_KEY"
os.environ["ENVIRONMENT"] = "development"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["HTTP_MAX_RETRIES"] = "2"

import warnings  # noqa: E402

# Starlette warns that its TestClient still uses httpx. The suite runs with
# `filterwarnings = error`, and that warning fires at *import* time - before
# pytest applies the filters from pytest.ini - so it has to be silenced here or
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
FMP_URL = SETTINGS.fmp_base_url
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


# ===========================================================================
# Financial Modeling Prep fixtures (the selected provider)
#
# Shapes below were taken from the live `/stable` API, not from documentation.
# ===========================================================================
def build_fmp_series(days: int = 420) -> list[dict[str, Any]]:
    """A deterministic price series shaped like FMP's response, newest first."""
    today = date.today()
    rows: list[dict[str, Any]] = []
    for index in range(days):
        day = today - timedelta(days=index)
        close = 100.0 + ((days - index) % 37) * 0.8 + (days - index) * 0.05
        rows.append(
            {
                "symbol": "AAPL",
                "date": day.isoformat(),
                "open": round(close - 0.5, 4),
                "high": round(close + 1.0, 4),
                "low": round(close - 1.0, 4),
                "close": round(close, 4),
                "volume": 47221369,
            }
        )
    return rows


FMP_QUOTE: list[dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "price": 336.91,
        "changePercentage": 1.1681,
        "change": 3.89,
        "volume": 45246885,
        "dayLow": 334.02,
        "dayHigh": 339.57,
        "yearHigh": 339.57,
        "yearLow": 201.5,
        "marketCap": 4948317109960,
        "exchange": "NASDAQ",
        "open": 334.9,
        "previousClose": 333.02,
        "timestamp": 1785182401,
    }
]

FMP_PROFILE: list[dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "price": 336.91,
        "marketCap": 4948317109960,
        "beta": 1.097,
        "lastDividend": 1.05,
        "range": "201.5-339.57",
        "companyName": "Apple Inc.",
        "currency": "USD",
        "exchange": "NASDAQ",
        "industry": "Consumer Electronics",
        "description": "Apple Inc. designs and sells consumer electronics.",
        "sector": "Technology",
        "country": "US",
    }
]

FMP_RATIOS: list[dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "netProfitMarginTTM": 0.2715188219084622,
        "operatingProfitMarginTTM": 0.32643396050876966,
        "priceToEarningsRatioTTM": 40.64053075995175,
        "priceToEarningsGrowthRatioTTM": 1.4049387784219867,
        "priceToBookRatioTTM": 46.54090957339118,
        "dividendYieldTTM": 0.00311656,
        "dividendPerShareTTM": 1.05,
        "netIncomePerShareTTM": 8.332360120015895,
        "bookValuePerShareTTM": 7.239007640551603,
    }
]

FMP_KEY_METRICS: list[dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "returnOnEquityTTM": 1.4668924498270723,
        "returnOnAssetsTTM": 0.3303178273265747,
    }
]

FMP_INCOME: list[dict[str, Any]] = [
    {
        "date": "2025-09-27",
        "period": "FY",
        "revenue": 416161000000,
        "grossProfit": 195201000000,
        "netIncome": 112010000000,
        "ebitda": 144427000000,
        "eps": 7.49,
        "weightedAverageShsOut": 14948500000,
    }
]

# Live error bodies. Note both 402 messages end the same way; only the prefix
# distinguishes an unknown symbol from a plan restriction.
FMP_UNKNOWN_SYMBOL_BODY = (
    "Premium Query Parameter: 'Special Endpoint : This value set for 'symbol' "
    "is not available under your current subscription."
)
FMP_RESTRICTED_BODY = (
    "Restricted Endpoint: This endpoint is not available under your current "
    "subscription please visit our subscription page to upgrade your plan."
)


def _fmp_dispatch(request: httpx.Request) -> httpx.Response:
    """Route a mocked FMP request by its path and symbol."""
    path = request.url.path.rsplit("/stable/", 1)[-1]
    symbol = request.url.params.get("symbol", "")

    if symbol == "NOSUCH":
        return httpx.Response(402, text=FMP_UNKNOWN_SYMBOL_BODY)
    if symbol == "QUOTA":
        return httpx.Response(429, json={"Error Message": "Limit Reach."})
    if symbol == "RESTRICTED":
        return httpx.Response(402, text=FMP_RESTRICTED_BODY)

    payloads: dict[str, list[dict[str, Any]]] = {
        "quote": FMP_QUOTE,
        "profile": FMP_PROFILE,
        "ratios-ttm": FMP_RATIOS,
        "key-metrics-ttm": FMP_KEY_METRICS,
        "income-statement": FMP_INCOME,
    }
    if path in payloads:
        return httpx.Response(200, json=payloads[path])
    if path.startswith("historical-price-eod"):
        return httpx.Response(200, json=build_fmp_series())

    return httpx.Response(404, json={"Error Message": "Unknown endpoint"})


@pytest.fixture
def market_data() -> Iterator[respx.MockRouter]:
    """Intercept every FMP call with deterministic payloads."""
    with respx.mock(assert_all_called=False) as router:
        router.get(url__startswith=FMP_URL).mock(side_effect=_fmp_dispatch)
        yield router


# ===========================================================================
# Alpha Vantage fixtures (alternative provider, unit-tested directly)
# ===========================================================================
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


def _alpha_vantage_dispatch(request: httpx.Request) -> httpx.Response:
    """Route a mocked Alpha Vantage request by its `function` parameter."""
    params = request.url.params
    symbol = params.get("symbol") or params.get("tickers") or ""

    if symbol == "NOSUCH":
        return httpx.Response(200, json={"Error Message": "Invalid API call"})
    if symbol == "QUOTA":
        return httpx.Response(
            200,
            json={"Information": "Our standard API rate limit is 25 requests per day"},
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
def alpha_vantage_data() -> Iterator[respx.MockRouter]:
    """Intercept every Alpha Vantage call with deterministic payloads."""
    with respx.mock(assert_all_called=False) as router:
        router.get(ALPHA_VANTAGE_URL).mock(side_effect=_alpha_vantage_dispatch)
        yield router
