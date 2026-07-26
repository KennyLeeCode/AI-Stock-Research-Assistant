# AI Stock Research Assistant

A full-stack stock research dashboard. Search a ticker and get a structured
view of it: live quote, price history, company fundamentals, technical
indicators, recent news, and an AI-generated research report that presents a
balanced bull and bear case.

The AI **interprets** data — it never produces it. Every number in the
application comes from the market-data service. See
[Data integrity](#data-integrity) for how that is enforced.

---

## Build status

This project is being built in phases. The table below reflects what is
actually working today, not what is planned.

| # | Phase | Status |
|---|-------|--------|
| 1 | Architecture and folder structure | Done |
| 2 | Backend setup (config, database, cache, errors) | Done |
| 3 | Database models (watchlist) | Done |
| 4 | Financial data service (Alpha Vantage provider) | Done |
| 5 | Technical indicator service | Done |
| 6 | AI research service | Done |
| 7 | Backend routes | Done |
| 8 | Frontend setup | Done |
| 9 | Dashboard components | Done |
| 10 | Watchlist UI | Done |
| 11 | Error handling | Not started |
| 12 | Testing | Done |
| 13 | Docker and deployment | Done |
| 14 | Documentation | Not started |

**What you can run right now:** the whole application. Start the backend and
the frontend (see [Setup](#setup)), open <http://localhost:5173>, and search a
ticker for a live quote, price chart, technical indicators, fundamentals, news,
an on-demand AI research report, and a persistent watchlist. All nine API
endpoints are live.

Remaining phases harden rather than extend it: a global error boundary and
offline handling, an automated test suite, container images, and final
documentation.

---

## Tech stack

**Backend** — Python, FastAPI, Pydantic v2, SQLAlchemy 2.0, httpx
**Frontend** — React, TypeScript, Vite, Axios, Recharts
**Database** — SQLite in development; PostgreSQL or MySQL by changing one setting
**External services** — Alpha Vantage (market data), Anthropic Claude (research)

---

## Architecture

```
Browser
   |
   |  JSON over HTTP.  No API keys ever reach the browser.
   v
FastAPI
   |
   +-- routers/     HTTP only: parse the request, call a service, return a model
   |
   +-- services/    All business logic
   |     |
   |     +-- stock_service      validation, caching, concurrent fetch
   |     +-- indicator_service  pure maths over price history
   |     +-- research_service   Claude call, schema-constrained output
   |     +-- watchlist_service  database CRUD
   |     |
   |     +-- providers/         the only code that knows a vendor's payload shape
   |           +-- base.py            StockDataProvider interface
   |           +-- alpha_vantage.py   concrete implementation
   |
   +-- models/      SQLAlchemy ORM  (how data is stored)
   +-- schemas/     Pydantic        (what crosses the wire)
   +-- core/        validation, caching, error types
```

Two rules keep this honest:

- **Routers never call a provider, a database session, or the AI SDK directly.**
  They call a service. This is what makes the provider swappable and the
  services testable without starting a web server.
- **Vendor field names never escape `providers/`.** Alpha Vantage returns keys
  like `"05. price"` and `"MarketCapitalization": "2900000000000"`. Those are
  normalized into typed Pydantic models inside the provider. Nothing downstream
  has ever heard of Alpha Vantage.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12 or 3.13 | 3.14 may lack wheels for some dependencies |
| Node.js | 22 LTS or newer | Required from Phase 8 onward |
| Git | any recent | |

> **Node version matters.** The current Vite release requires
> `^20.19.0 \|\| >=22.12.0`. If `node --version` reports anything older —
> Node 20.12, for example — the frontend scaffold will fail. Install Node 22 LTS
> from [nodejs.org](https://nodejs.org) or run
> `winget install OpenJS.NodeJS.LTS`.

### API keys

Both are free to obtain; the Anthropic key requires billing credit to make calls.

| Key | Where | Notes |
|---|---|---|
| `ALPHA_VANTAGE_API_KEY` | [alphavantage.co](https://www.alphavantage.co/support/#api-key) | Instant, no card. Free tier allows about **25 requests per day** — this is why the app caches aggressively. |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/settings/keys) | Used only for generating research reports. |

---

## Setup

### 1. Clone

```bash
git clone https://github.com/KennyLeeCode/AI-Stock-Research-Assistant.git
cd AI-Stock-Research-Assistant
```

### 2. Backend

**Windows (PowerShell)**

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
copy .env.example .env
```

**macOS / Linux**

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
cp .env.example .env
```

### 3. Add your keys

Open `backend/.env` and replace the two placeholder values:

```ini
ALPHA_VANTAGE_API_KEY=your_actual_key
ANTHROPIC_API_KEY=your_actual_key
```

`backend/.env` is git-ignored and must never be committed. The application
detects untouched placeholders — if you leave `your_..._here` in place, it will
warn you at startup by name rather than failing later with a confusing
authentication error from the upstream API.

### 4. Frontend

```bash
cd frontend
npm install
cp .env.example .env      # Windows: copy .env.example .env
```

### 5. Run both

Two terminals.

```bash
# terminal 1 — backend
cd backend
uvicorn app.main:app --reload --port 8000
```

```bash
# terminal 2 — frontend
cd frontend
npm run dev
```

Then open **<http://localhost:5173>**.

The dev server proxies `/api` to the backend, so the browser makes same-origin
requests and never needs to know the backend's address — there is no host and
no key to configure client-side.

Backend startup output:

Expected output:

```
INFO     app.database: Database ready at sqlite:///./stock_research.db
INFO     app.main: AI Stock Research Assistant started in development mode
INFO     Application startup complete.
INFO     Uvicorn running on http://127.0.0.1:8000
```

If a key is missing you will also see, before that line:

```
WARNING  app.main: ALPHA_VANTAGE_API_KEY is not set. Market data endpoints will fail.
```

### 6. Verify

| URL | What it is |
|---|---|
| http://localhost:5173 | The application |
| http://localhost:8000/api/health | Health and configuration check |
| http://localhost:8000/docs | Interactive Swagger UI |
| http://localhost:8000/redoc | ReDoc API reference |

```bash
curl http://localhost:8000/api/health
```

```json
{
  "status": "ok",
  "app": "AI Stock Research Assistant",
  "version": "0.1.0",
  "environment": "development",
  "dependencies": {
    "market_data_configured": true,
    "ai_configured": true
  }
}
```

Those two booleans report only whether a real key is present. Key values are
stored as Pydantic `SecretStr` and are never logged, echoed, or serialized.

---

## Configuration

Every setting is read from `backend/.env`. Defaults live in
`backend/.env.example`.

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | Any value other than `development` disables `/docs`, `/redoc`, and `/openapi.json` |
| `LOG_LEVEL` | `INFO` | `DEBUG` also logs cache hits |
| `DATABASE_URL` | `sqlite:///./stock_research.db` | See [Switching database](#switching-database) |
| `ALPHA_VANTAGE_API_KEY` | — | Required for market data |
| `ANTHROPIC_API_KEY` | — | Required for research reports |
| `ANTHROPIC_MODEL` | `claude-opus-5` | Model used for report generation |
| `HTTP_TIMEOUT_SECONDS` | `15` | Per-request timeout for outbound calls |
| `HTTP_MAX_RETRIES` | `2` | Retries on timeouts and 5xx; 4xx is never retried |
| `CACHE_TTL_QUOTE` | `60` | Seconds |
| `CACHE_TTL_HISTORY` | `3600` | Seconds |
| `CACHE_TTL_OVERVIEW` | `86400` | Seconds — company profiles rarely change |
| `CACHE_TTL_NEWS` | `900` | Seconds |
| `CACHE_TTL_RESEARCH` | `3600` | Seconds |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated allowed frontend origins |

### Caching

The free Alpha Vantage tier allows roughly 25 requests per day, and one
dashboard load needs four. Responses are cached in-process with a per-datatype
TTL, so repeat views of the same ticker cost nothing. Only successful responses
are cached — a transient failure is never stored for the length of a TTL.

For a single-process deployment this is sufficient. Scaling to multiple workers
means replacing `app/core/cache.py` with Redis; the `get`/`set`/`invalidate`
interface is deliberately narrow so nothing else changes.

### Switching database

Change one line. No code changes are required.

```ini
# SQLite (default)
DATABASE_URL=sqlite:///./stock_research.db

# PostgreSQL   — also: pip install "psycopg[binary]"
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/stockresearch

# MySQL        — also: pip install PyMySQL
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/stockresearch
```

Models avoid engine-specific types and use bounded `String` columns with
explicitly named constraints, so the schema is portable across all three.

### Switching market-data provider

Write a class implementing `StockDataProvider` (see
`backend/app/services/providers/base.py`), register it in
`backend/app/services/providers/__init__.py`, and set
`MARKET_DATA_PROVIDER` in `.env`. No router or service code changes.

---

## Data integrity

The core constraint of this project is that **the AI is a writer, not a
calculator**. Four mechanisms enforce it.

**1. Missing data stays missing.** Providers return `"None"`, `"-"`, and `""`
inside numeric fields. These are parsed to `None`, never to `0`. A company with
negative earnings genuinely has no P/E ratio; rendering `0` there would be a
fabricated figure. A `None` propagates all the way to the UI and displays as an
em dash.

**2. Unusable rows are dropped, not repaired.** A trading day missing its
closing price is discarded from the price history. Interpolating one would
invent a price that then flows into every indicator computed from it.

**3. Indicators refuse rather than approximate.** If only 30 days of history
exist, the 50-day moving average raises `InsufficientDataError` instead of
quietly averaging 30 days and labelling the result "SMA 50".

**4. The AI cannot emit a number that is displayed as data.** The research
request sends Claude a pre-computed, read-only JSON block. The model has no
tools and no web access. Its response schema contains **only prose and lists of
strings — not one numeric field** — so it is structurally incapable of returning
a figure that the UI would present as a metric. The response is additionally
constrained with a JSON Schema at the API level and re-validated through a
Pydantic model on receipt; a report that fails validation is discarded rather
than partially rendered.

---

## Security

- **No API key ever reaches the browser.** All provider and AI calls are
  server-side. The frontend knows only `VITE_API_BASE_URL`. Note that every
  `VITE_*` variable is inlined into the public JavaScript bundle, which is why
  `frontend/.env.example` contains no secrets and says so explicitly.
- **Keys are `SecretStr`.** They render as `**********` in any log line,
  stack trace, or `print(settings)`.
- **Provider URLs are never logged.** Alpha Vantage takes its key as a query
  parameter, so logging a request URL would leak it. Log statements name the
  API function and ticker only.
- **Unexpected errors return a bare 500.** Internal exception details are
  logged server-side and never included in a response body.
- **Ticker input is validated before use.** Symbols are normalized against a
  strict pattern before entering an outbound URL, a cache key, or a database
  row, so input like `../etc` is rejected at the boundary.
- **CORS is restrictive.** An explicit origin list, credentials disabled, and
  only the methods this API actually uses.
- **API docs are disabled outside development.**

---

## Project structure

```
AI-Stock-Research-Assistant/
├── backend/
│   ├── .env.example            template; copy to .env
│   ├── requirements.txt
│   └── app/
│       ├── main.py             app factory, CORS, lifespan, /api/health
│       ├── config.py           typed settings from environment
│       ├── database.py         engine, session factory, declarative base
│       ├── core/
│       │   ├── cache.py        thread-safe TTL cache
│       │   ├── exceptions.py   error hierarchy and handlers
│       │   └── validation.py   ticker normalization
│       ├── models/             SQLAlchemy ORM
│       ├── schemas/            Pydantic request/response models
│       ├── routers/            HTTP layer            (Phase 7)
│       └── services/
│           ├── stock_service.py
│           └── providers/
│               ├── base.py
│               └── alpha_vantage.py
└── frontend/                   React + TypeScript    (Phase 8)
    ├── .env.example
    └── src/
```

---

## Planned API

These endpoints are designed and their data layer is built; they are exposed
over HTTP in Phase 7.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Health check — **available now** |
| `GET` | `/api/stocks/{ticker}/quote` | Current price and daily change |
| `GET` | `/api/stocks/{ticker}/history` | Historical daily prices |
| `GET` | `/api/stocks/{ticker}/overview` | Company profile and fundamentals |
| `GET` | `/api/stocks/{ticker}/indicators` | SMA 20/50, RSI, volatility, 52-week range |
| `GET` | `/api/stocks/{ticker}/news` | Recent news articles |
| `POST` | `/api/research` | Generate an AI research report |
| `GET` | `/api/watchlist` | List saved tickers |
| `POST` | `/api/watchlist` | Add a ticker |
| `DELETE` | `/api/watchlist/{ticker}` | Remove a ticker |

Errors share one envelope, with a stable `code` the frontend branches on:

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
| `duplicate_resource` | 409 | Ticker already on the watchlist |
| `insufficient_data` | 422 | Not enough history to compute the result |
| `provider_rate_limited` | 429 | Daily quota exhausted |
| `provider_error` | 502 | Upstream returned something unexpected |
| `ai_service_error` | 502 | AI provider call failed |
| `ai_response_invalid` | 502 | AI report failed validation and was discarded |
| `configuration_error` | 503 | A required API key is not set on the server |
| `provider_timeout` | 504 | Upstream did not respond in time |

---

## Docker

The whole stack runs in two containers. Only the frontend is published; nginx
serves the built app and proxies `/api` to the backend over the internal
network, so every request is same-origin — no CORS to configure and no backend
hostname compiled into the JavaScript bundle.

```bash
cp backend/.env.example backend/.env     # then add your two API keys
docker compose up --build
```

Open **<http://localhost:8080>**.

| Service | Base image | Notes |
|---|---|---|
| `backend` | `python:3.13-slim` | Runs as UID 1000, not root. Not published to the host. SQLite lives on a named volume. |
| `frontend` | `nginxinc/nginx-unprivileged:1.29-alpine` | Multi-stage: Node builds, nginx serves. No Node or `node_modules` in the final image. |

The frontend waits for the backend's health check to pass rather than merely
for its container to start, so nginx never proxies to a backend that is still
creating its schema.

### PostgreSQL

```bash
docker compose --profile postgres up --build
```

Then in `backend/.env`:

```ini
DATABASE_URL=postgresql+psycopg://stock:stock@postgres:5432/stockresearch
```

and add `psycopg[binary]` to `backend/requirements.txt`. No application code
changes — the models avoid engine-specific types and name their constraints
explicitly so the schema is portable.

### Deployment notes

- **Set `ENVIRONMENT` to anything other than `development`** in production.
  That disables `/docs`, `/redoc`, and `/openapi.json`.
- **The backend is intentionally not published** to the host in
  `docker-compose.yml`. Add `ports: ["8000:8000"]` temporarily if you need to
  reach the API directly while debugging.
- **`backend/.env` is never copied into an image.** Both `.dockerignore` files
  exclude it; secrets are injected at runtime via `env_file`.
- **The SQLite database is on a named volume** (`backend_data`), so it survives
  `docker compose down`. `docker compose down -v` deletes it.

## Tests

```bash
cd backend
pytest                                      # 206 tests
pytest --cov=app --cov-report=term-missing  # coverage report
```

No test makes a real network call: market-data requests are intercepted with
`respx` and the AI client is replaced outright, so the suite costs nothing to
run and cannot consume the daily API quota.

Coverage is 93%. The tests concentrate on the invariants that are easiest to
erode:

| Area | What is pinned down |
|---|---|
| Data integrity | Provider sentinels (`"None"`, `"-"`, `""`) become `null`, never `0`; a genuine `0` survives; `inf` and `NaN` are rejected |
| Indicators | RSI cross-checked against an independently written implementation; short history refuses rather than approximating; every null field carries a reason |
| Provider | HTTP-200 error bodies map to the right exceptions; retry and timeout behaviour; the API key never appears in an exception or a log line |
| API | All nine endpoints, their error paths, and cache behaviour |
| Research | The AI response schema cannot contain a numeric field; unbalanced reports fail validation; the disclaimer is fixed server-side |
| Errors | Every response uses one envelope; 500s carry a request id and disclose nothing else |

## Known limitations

- **25 requests per day** on the free Alpha Vantage tier. Caching stretches this
  a long way, but researching many distinct tickers in one day will hit it.
- **Prices are not split- or dividend-adjusted.** `TIME_SERIES_DAILY_ADJUSTED`
  is a premium endpoint, so the free `TIME_SERIES_DAILY` is used. A stock split
  inside the displayed window appears as a price discontinuity.
- **The cache is per-process.** Running multiple workers means each holds its
  own copy. Redis is the fix; see [Caching](#caching).
- **No authentication.** The watchlist is global to the deployment rather than
  per-user.

---

## Disclaimer

This application is a software engineering portfolio project. It is **not
financial advice**, and it is not a recommendation to buy, sell, or hold any
security.

AI-generated research reports are automated interpretations of publicly
available data. They may be incomplete, out of date, or wrong. Market data is
supplied by a third party and may be delayed or inaccurate. Nothing in this
application should be relied upon for an investment decision. Always do your
own research and consult a qualified financial professional.

---

## License

MIT
