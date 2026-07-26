# AI Stock Research Assistant

A full-stack stock research dashboard. Search a ticker and get a structured view
of it: live quote, price history, company fundamentals, technical indicators,
recent news, and an AI-generated research report that argues both the bull and
the bear case.

The AI **interprets** data — it never produces it. Every number in the
application comes from the market-data service. [How that is
enforced](#data-integrity) is the most interesting part of the codebase.

**Stack:** Python · FastAPI · SQLAlchemy · React · TypeScript · Vite · Recharts · Docker

<!--
  SCREENSHOTS
  Add two or three images here once you have run the app with real data:

      ![Dashboard](docs/screenshots/dashboard.png)
      ![Research report](docs/screenshots/research.png)

  Put the files in docs/screenshots/. Good candidates: the full dashboard for a
  well-known ticker, the AI report with the bull/bear columns visible, and a
  loading or error state to show the app handles failure gracefully.
-->

---

## Features

| | |
|---|---|
| **Ticker search** | Validated symbol lookup with instant feedback and example shortcuts |
| **Live quote** | Price, absolute and percentage change, day range, volume |
| **Price history** | Interactive chart with 1M / 3M / 6M / 1Y / 5Y ranges |
| **Fundamentals** | Market cap, P/E, PEG, margins, ROE, revenue, dividend yield, beta, and more |
| **Technical indicators** | SMA 20/50, RSI 14, 30-day annualized volatility, 1- and 3-month change, 52-week range |
| **News** | Recent headlines with source, age, and provider sentiment |
| **AI research report** | Company summary, performance, technical and fundamental reads, bull case, bear case, risks, catalysts, and a neutral conclusion |
| **Watchlist** | Persistent saved tickers with optimistic add and remove |
| **Attribution** | Every panel names its data source and fetch time |

Each panel loads independently, so a failure in one — an exhausted news quota,
say — leaves the rest of the dashboard fully usable.

---

## Architecture

```
Browser
   │  JSON over HTTP. No API key ever reaches the browser.
   ▼
FastAPI
   │
   ├── routers/     HTTP only: validate input, call a service, return a model
   │
   ├── services/    All business logic
   │     ├── stock_service       validation, caching, concurrent fetch
   │     ├── indicator_service   pure maths over price history (no I/O)
   │     ├── research_service    AI call, schema-constrained output
   │     ├── watchlist_service   database access
   │     └── providers/          the only code that knows a vendor's shapes
   │           ├── base.py             StockDataProvider interface
   │           └── alpha_vantage.py    concrete implementation
   │
   ├── models/      SQLAlchemy ORM   (how data is stored)
   ├── schemas/     Pydantic         (what crosses the wire)
   └── core/        validation, caching, error types, request tracing
```

Three rules hold this together:

- **Routers never touch a provider, a database session, or the AI SDK.** They
  call a service. That is what makes the provider swappable and the services
  testable without starting a web server.
- **Vendor field names never escape `providers/`.** Alpha Vantage returns keys
  like `"05. price"` and `"MarketCapitalization": "2900000000000"`. Those are
  normalized into typed Pydantic models inside the provider; nothing downstream
  has heard of Alpha Vantage.
- **ORM models and API schemas are separate.** A storage change cannot silently
  alter the public API.

---

## Data integrity

The central constraint: **the AI is a writer, not a calculator.** Four
independent mechanisms enforce it.

**1. Missing data stays missing.** Providers return `"None"`, `"-"`, and `""`
inside numeric fields. These become `null`, never `0`. A company with negative
earnings genuinely has no P/E ratio; rendering `0` there would be a fabricated
figure. The `null` propagates all the way to the UI and displays as an em dash.

**2. Unusable rows are dropped, not repaired.** A trading day missing its
closing price is discarded from the price history. Interpolating one would
invent a price that then flows into every indicator computed from it.

**3. Indicators refuse rather than approximate.** With only 30 days of history,
the 50-day moving average is not computed from 30 days and mislabelled — it is
returned as `null` with the reason attached: *"a 50-day moving average needs 50
daily closes; only 30 are available."* The 52-week range is refused outright
below ~300 days of coverage.

**4. The AI cannot emit a number that is displayed as data.** The model receives
a pre-computed, read-only JSON block. It has no tools and no web access. Its
response schema contains **only prose and lists of strings — not one numeric
field** — so it is structurally incapable of returning a figure the UI would
present as a metric. The response is constrained by a JSON Schema at the API
boundary *and* re-validated through Pydantic on receipt; a report failing either
check is discarded rather than partially rendered.

The prompt also forbids buy/sell recommendations, and the schema requires at
least two substantive points in **both** the bull and bear case — balance is a
validation rule, not a polite request.

---

## Quick start

### With Docker

```bash
git clone https://github.com/KennyLeeCode/AI-Stock-Research-Assistant.git
cd AI-Stock-Research-Assistant

cp backend/.env.example backend/.env    # then add your two API keys
docker compose up --build
```

Open **<http://localhost:8080>**.

### Without Docker

<details>
<summary>Prerequisites</summary>

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12 or 3.13 | 3.14 may lack wheels for some dependencies |
| Node.js | `^20.19` or `>=22.12` | Required by Vite. `node --version` to check |
| Git | any recent | |

If Node is older, install the current LTS from [nodejs.org](https://nodejs.org)
or run `winget install OpenJS.NodeJS.LTS`.

</details>

**Backend**

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
cp .env.example .env               # Windows: copy .env.example .env
```

Add your keys to `backend/.env`, then:

```bash
uvicorn app.main:app --reload --port 8000
```

**Frontend** (second terminal)

```bash
cd frontend
npm install
cp .env.example .env               # Windows: copy .env.example .env
npm run dev
```

Open **<http://localhost:5173>**. The dev server proxies `/api` to the backend,
so the browser makes same-origin requests and never needs to know the backend's
address.

### API keys

Both are free to obtain; the Anthropic key requires billing credit to make calls.

| Key | Where | Notes |
|---|---|---|
| `ALPHA_VANTAGE_API_KEY` | [alphavantage.co](https://www.alphavantage.co/support/#api-key) | Instant, no card. Free tier allows about **25 requests per day** — hence the aggressive caching |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/settings/keys) | Used only for generating research reports |

`backend/.env` is git-ignored and must never be committed. The application
detects untouched placeholders: leaving `your_..._here` in place produces a
named warning at startup rather than a confusing authentication error later.

Expected startup output:

```
INFO  app.database: Database ready at sqlite:///./stock_research.db
INFO  app.main: AI Stock Research Assistant started in development mode
INFO  Application startup complete.
```

Verify with <http://localhost:8000/api/health>, or browse the interactive API
docs at <http://localhost:8000/docs>.

---

## API

Base path `/api`. All nine endpoints are live.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Health and configuration check |
| `GET` | `/stocks/{ticker}/quote` | Current price and daily change |
| `GET` | `/stocks/{ticker}/history?days=365` | Historical daily prices |
| `GET` | `/stocks/{ticker}/overview` | Company profile and fundamentals |
| `GET` | `/stocks/{ticker}/indicators?days=365` | Computed technical indicators |
| `GET` | `/stocks/{ticker}/news?limit=10` | Recent news articles |
| `POST` | `/research` | Generate an AI research report |
| `GET` | `/watchlist` | List saved tickers |
| `POST` | `/watchlist` | Add a ticker |
| `DELETE` | `/watchlist/{ticker}` | Remove a ticker |

Every error — including framework-level 404s and 405s — uses one envelope, so
the frontend can always branch on `error.code`:

```json
{
  "error": {
    "code": "provider_rate_limited",
    "message": "The market data provider's rate limit was reached. Please wait a moment and try again."
  }
}
```

| `code` | HTTP | Meaning |
|---|---|---|
| `invalid_ticker` | 400 | Symbol is malformed |
| `ticker_not_found` | 404 | Provider has no such security |
| `not_found` | 404 | Resource or route does not exist |
| `method_not_allowed` | 405 | Wrong HTTP verb for the route |
| `duplicate_resource` | 409 | Ticker already on the watchlist |
| `insufficient_data` | 422 | Not enough history to compute the result |
| `validation_error` | 422 | Request body or query parameter rejected |
| `provider_rate_limited` | 429 | Daily quota exhausted |
| `provider_error` | 502 | Upstream returned something unexpected |
| `ai_service_error` | 502 | AI provider call failed |
| `ai_response_invalid` | 502 | AI report failed validation and was discarded |
| `configuration_error` | 503 | A required API key is not set on the server |
| `provider_timeout` | 504 | Upstream did not respond in time |

Server errors (5xx) additionally carry a `request_id`, echoed in the
`X-Request-ID` response header and written to the access log — quoting it in a
bug report locates the exact traceback. Client errors deliberately omit it.

---

## Configuration

Every setting is read from `backend/.env`; defaults live in
`backend/.env.example`.

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME` | `AI Stock Research Assistant` | Shown in API docs and the health response |
| `ENVIRONMENT` | `development` | Any other value disables `/docs`, `/redoc`, `/openapi.json` |
| `LOG_LEVEL` | `INFO` | `DEBUG` also logs cache hits |
| `DATABASE_URL` | `sqlite:///./stock_research.db` | See [switching database](#switching-database) |
| `MARKET_DATA_PROVIDER` | `alpha_vantage` | Selects the provider implementation |
| `ALPHA_VANTAGE_API_KEY` | — | Required for market data |
| `ALPHA_VANTAGE_BASE_URL` | `https://www.alphavantage.co/query` | Override to point at a mock or proxy |
| `ANTHROPIC_API_KEY` | — | Required for research reports |
| `ANTHROPIC_MODEL` | `claude-opus-5` | Model used for report generation |
| `ANTHROPIC_MAX_TOKENS` | `8000` | Output ceiling per report |
| `HTTP_TIMEOUT_SECONDS` | `15` | Per-request timeout for outbound calls |
| `HTTP_MAX_RETRIES` | `2` | Retries on timeouts and 5xx; 4xx is never retried |
| `CACHE_TTL_QUOTE` | `60` | Seconds |
| `CACHE_TTL_HISTORY` | `3600` | Seconds |
| `CACHE_TTL_OVERVIEW` | `86400` | Seconds — company profiles rarely change |
| `CACHE_TTL_NEWS` | `900` | Seconds |
| `CACHE_TTL_RESEARCH` | `3600` | Seconds |
| `CORS_ORIGINS` | `http://localhost:5173,…` | Comma-separated allowed origins |

### Caching

The free Alpha Vantage tier allows roughly 25 requests per day and one dashboard
load needs four, so responses are cached in-process with a per-datatype TTL.
Only *successful* responses are cached — a transient failure is never stored for
the length of a TTL.

Sufficient for a single process. Scaling to multiple workers means replacing
`app/core/cache.py` with Redis; its `get`/`set`/`invalidate` interface is
deliberately narrow so nothing else changes.

### Switching database

One line, no code changes:

```ini
DATABASE_URL=sqlite:///./stock_research.db
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/stockresearch   # + pip install "psycopg[binary]"
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/stockresearch        # + pip install PyMySQL
```

Models avoid engine-specific types and use bounded `String` columns with
explicitly named constraints, so the schema is portable across all three.
PostgreSQL is also available in Docker via `docker compose --profile postgres up`.

### Switching market-data provider

Write a class implementing `StockDataProvider`
(`backend/app/services/providers/base.py`), register it in that package's
`__init__.py`, and set `MARKET_DATA_PROVIDER`. No router or service changes.

---

## Tests

```bash
cd backend
pytest                                      # 206 tests
pytest --cov=app --cov-report=term-missing  # coverage report
```

No test makes a real network call: market-data requests are intercepted with
`respx` and the AI client is replaced outright, so the suite costs nothing to
run and cannot consume the daily quota.

Coverage is 93%, concentrated on the invariants easiest to erode:

| Area | What is pinned down |
|---|---|
| Data integrity | Provider sentinels become `null`, never `0`; a genuine `0` survives; `inf` and `NaN` are rejected |
| Indicators | RSI cross-checked against an independently written implementation; short history refuses rather than approximating; every null field carries a reason |
| Provider | HTTP-200 error bodies map to the right exceptions; retry and timeout behaviour; the API key never appears in an exception or a log line |
| API | All nine endpoints, their error paths, and cache behaviour |
| Research | The AI response schema cannot contain a numeric field; unbalanced reports fail validation; the disclaimer is fixed server-side |
| Errors | Every response uses one envelope; 500s carry a request id and disclose nothing else |

Frontend checks:

```bash
cd frontend
npm run typecheck    # tsc, strict mode
npm run lint         # eslint
npm run build        # production bundle
```

---

## Security

- **No API key ever reaches the browser.** All provider and AI calls are
  server-side. Every `VITE_*` variable is inlined into the public JavaScript
  bundle, which is why `frontend/.env.example` holds no secrets and says so.
- **Keys are `SecretStr`** — they render as `**********` in any log line, stack
  trace, or `print(settings)`.
- **Provider URLs are never logged.** Alpha Vantage takes its key as a query
  parameter, so logging a request URL would leak it. Log lines name the API
  function and ticker only. This is asserted in the test suite.
- **Unexpected errors return a bare 500.** Internal detail is logged
  server-side and never included in a response body.
- **Input is validated at the boundary.** Symbols are normalized against a
  strict pattern before entering an outbound URL, a cache key, or a database
  row, so input like `../etc` is rejected before anything acts on it.
- **Request ids are sanitized.** Client-supplied `X-Request-ID` values are
  stripped of control characters and length-capped to prevent log and header
  injection.
- **Containers run as non-root** and `.env` is excluded from both build
  contexts, so secrets are never baked into an image layer.
- **CORS is restrictive** and API docs are disabled outside development.

---

## Project structure

```
AI-Stock-Research-Assistant/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt / requirements-dev.txt
│   ├── .env.example                 template; copy to .env
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py                  app factory, middleware, lifespan
│   │   ├── config.py                typed settings from environment
│   │   ├── database.py              engine, session factory, base
│   │   ├── core/
│   │   │   ├── cache.py             thread-safe TTL cache
│   │   │   ├── exceptions.py        error hierarchy and handlers
│   │   │   ├── middleware.py        request ids and access logging
│   │   │   └── validation.py        ticker normalization
│   │   ├── models/                  SQLAlchemy ORM
│   │   ├── schemas/                 Pydantic request/response models
│   │   ├── routers/                 stocks, research, watchlist
│   │   └── services/
│   │       ├── stock_service.py     caching and orchestration
│   │       ├── indicator_service.py pure indicator maths
│   │       ├── research_service.py  AI report generation
│   │       ├── watchlist_service.py persistence
│   │       └── providers/           market-data abstraction
│   └── tests/                       206 tests
└── frontend/
    ├── Dockerfile
    ├── nginx.conf                   static serving + /api proxy
    └── src/
        ├── api/                     axios client, typed endpoints
        ├── components/              dashboard panels
        │   └── ui/                  reusable primitives
        ├── contexts/                watchlist state
        ├── hooks/                   data fetching, theme, connectivity
        ├── styles/                  design tokens
        ├── types/                   interfaces mirroring the API
        └── utils/                   formatters
```

---

## Known limitations

- **25 requests per day** on the free Alpha Vantage tier. Caching stretches this
  a long way, but researching many distinct tickers in one day will hit it.
- **Prices are not split- or dividend-adjusted.** `TIME_SERIES_DAILY_ADJUSTED`
  is a premium endpoint, so the free `TIME_SERIES_DAILY` is used. A split inside
  the displayed window appears as a price discontinuity.
- **The cache is per-process.** Multiple workers each hold their own copy;
  Redis is the fix.
- **No authentication.** The watchlist is global to the deployment rather than
  per-user. Adding users means a `user_id` column and widening the unique
  constraint to `(user_id, ticker)`.
- **Figures quoted inside AI prose are model-written text.** The schema
  guarantees no prose figure is ever parsed back out and treated as data — every
  number rendered as a metric comes from the typed market-data models — but the
  narrative itself is generated text and should be read as such.

---

## Disclaimer

This application is a software engineering portfolio project. It is **not
financial advice**, and it is not a recommendation to buy, sell, or hold any
security.

AI-generated research reports are automated interpretations of publicly
available data and may be incomplete, out of date, or wrong. Market data is
supplied by a third party and may be delayed or inaccurate. Nothing here should
be relied upon for an investment decision. Always do your own research and
consult a qualified financial professional.

---

## License

Released under the [MIT License](LICENSE).
