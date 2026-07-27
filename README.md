# AI Stock Research Assistant

Search a stock ticker and get a full research dashboard: live quote, price
chart, company fundamentals, technical indicators, and an AI-written research
report that argues both sides of the trade.

The AI reads the data. It never makes the data up. Every number on the screen
comes from the market data service, and the model is only allowed to write
prose about it. There's a [section below](#how-the-ai-is-kept-honest) on how
that's enforced, because it's the part of this project I'd want to talk about
in an interview.

**Built with:** Python, FastAPI, SQLAlchemy, React, TypeScript, Vite, Recharts, Docker

<!--
  SCREENSHOTS
  Drop two or three images in here once you've run the app with real data:

      ![Dashboard](docs/screenshots/dashboard.png)
      ![Research report](docs/screenshots/research.png)

  Save them under docs/screenshots/. Worth capturing: the full dashboard for a
  well-known ticker, the AI report with the bull and bear columns side by side,
  and a loading or error state to show the app handles failure properly.
-->

---

## What it does

| | |
|---|---|
| **Ticker search** | Validates the symbol before it hits the network, with example shortcuts |
| **Live quote** | Price, change in dollars and percent, day range, volume |
| **Price chart** | 1M, 3M, 6M, 1Y and 5Y ranges |
| **Fundamentals** | Market cap, P/E, PEG, price to book, margins, ROE, revenue, dividend yield, beta |
| **Technical indicators** | SMA 20 and 50, RSI 14, 30 day annualised volatility, 1 and 3 month change, 52 week range |
| **News** | Recent headlines, where the data plan includes them |
| **AI research report** | Company summary, recent performance, technical and fundamental reads, bull case, bear case, risks, catalysts, and a neutral conclusion |
| **Watchlist** | Saved tickers that persist between sessions |
| **Attribution** | Every panel says where its data came from and when it was fetched |

Each panel loads on its own. If the news endpoint is down or out of quota, the
rest of the dashboard still works.

---

## How it's put together

```
Browser
   │  JSON over HTTP. No API key ever reaches the browser.
   ▼
FastAPI
   │
   ├── routers/     HTTP only: check the input, call a service, return a model
   │
   ├── services/    All the actual logic
   │     ├── stock_service       validation, caching, fetching in parallel
   │     ├── indicator_service   the maths, with no network or database access
   │     ├── research_service    the AI call and its guardrails
   │     ├── watchlist_service   database reads and writes
   │     └── providers/          the only code that knows a vendor's field names
   │           ├── base.py       the StockDataProvider interface
   │           ├── fmp.py        Financial Modeling Prep
   │           └── alpha_vantage.py
   │
   ├── models/      SQLAlchemy, how data is stored
   ├── schemas/     Pydantic, what goes over the wire
   └── core/        validation, caching, errors, request tracing
```

Three rules keep it from turning into spaghetti:

**Routers don't do anything.** They don't open a database session, call an HTTP
client, or touch the AI SDK. They call a service and return what it gives back.
That's what makes the services testable without spinning up a web server.

**Vendor field names stop at the provider.** FMP returns `changePercentage` and
a 52 week range as the string `"201.5-339.57"`. Alpha Vantage returns
`"05. price"`. Both get normalised inside their own provider module, and
nothing downstream knows which vendor is in use.

**Storage models and API models are separate files.** Changing a column can't
quietly change the API response.

---

## How the AI is kept honest

The one rule this project is built around: the model writes, it doesn't
calculate. Four things enforce that, and they work independently.

**Missing data stays missing.** Providers return `"None"`, `"-"` and empty
strings inside numeric fields. All of those become `null`, never `0`. A company
losing money genuinely has no P/E ratio, and printing `0` there would be a
number nobody measured. The `null` travels all the way to the browser and shows
up as a dash.

**Broken rows get dropped, not patched.** If a trading day has no closing
price, it's removed from the history. Filling it in would invent a price that
then feeds into every indicator calculated from that series.

**Indicators refuse instead of guessing.** With 30 days of history, the 50 day
moving average doesn't quietly average 30 days and call itself SMA 50. It
returns `null` with a reason attached: "a 50-day moving average needs 50 daily
closes; only 30 are available." The UI shows that reason next to the blank.

**The AI physically can't return a number.** Its response schema is prose and
lists of strings. There isn't a single numeric field in it, so there's no way
for the model to hand back a figure that the app would render as a metric. It
gets no tools and no web access either, just a read-only block of data that's
already been computed. The response is checked against a JSON schema at the API
boundary and then validated again with Pydantic when it arrives. If either
check fails the report is thrown away rather than shown half-finished.

On top of that, the prompt bans buy and sell recommendations, and the schema
requires at least two real points in both the bull and the bear case. Balance
isn't a suggestion in the prompt, it's a validation rule.

---

## Running it

### Docker

```bash
git clone https://github.com/KennyLeeCode/AI-Stock-Research-Platform.git
cd AI-Stock-Research-Platform

cp backend/.env.example backend/.env    # then paste your API keys in
docker compose up --build
```

Open <http://localhost:8080>.

### Without Docker

<details>
<summary>What you need first</summary>

| | Version | Notes |
|---|---|---|
| Python | 3.12 or 3.13 | 3.14 may not have wheels for everything yet |
| Node.js | 20.19+ or 22.12+ | Required by Vite. Check with `node --version` |

If Node is older, grab the current LTS from [nodejs.org](https://nodejs.org) or
run `winget install OpenJS.NodeJS.LTS`.

</details>

Backend:

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cp .env.example .env               # Windows: copy .env.example .env
```

Put your keys in `backend/.env`, then:

```bash
uvicorn app.main:app --reload --port 8000
```

Frontend, in a second terminal:

```bash
cd frontend
npm install
cp .env.example .env               # Windows: copy .env.example .env
npm run dev
```

Open <http://localhost:5173>. The dev server forwards `/api` to the backend, so
the browser only ever talks to one origin and there's no backend address to
configure on the client.

### API keys

| Key | Where to get it | Notes |
|---|---|---|
| `FMP_API_KEY` | [financialmodelingprep.com](https://site.financialmodelingprep.com/developer/docs) | Free, instant. Covers quotes, history, profile and fundamentals. News needs a paid plan |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/settings/keys) | Only used for research reports |

`backend/.env` is git ignored and should stay that way. If you copy the example
file and forget to fill it in, the app spots the leftover placeholder and warns
you by name at startup instead of failing later with a confusing 401 from
someone else's API.

You should see this when it starts:

```
INFO  app.database: Database ready at sqlite:///./stock_research.db
INFO  app.main: AI Stock Research Assistant started in development mode
INFO  Application startup complete.
```

Check <http://localhost:8000/api/health>, or browse the API at
<http://localhost:8000/docs>.

---

## API

Everything sits under `/api`.

| Method | Path | What it does |
|---|---|---|
| `GET` | `/health` | Health and configuration check |
| `GET` | `/stocks/{ticker}/quote` | Current price and daily change |
| `GET` | `/stocks/{ticker}/history?days=365` | Daily price history |
| `GET` | `/stocks/{ticker}/overview` | Company profile and fundamentals |
| `GET` | `/stocks/{ticker}/indicators?days=365` | Computed technical indicators |
| `GET` | `/stocks/{ticker}/news?limit=10` | Recent news |
| `POST` | `/research` | Generate an AI research report |
| `GET` | `/watchlist` | List saved tickers |
| `POST` | `/watchlist` | Save a ticker |
| `DELETE` | `/watchlist/{ticker}` | Remove a ticker |

Every error uses the same shape, including the 404s and 405s that come from the
framework rather than from application code. That means the frontend can always
read `error.code` without checking whether the response is the odd one out:

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
| `invalid_ticker` | 400 | The symbol isn't shaped like a ticker |
| `ticker_not_found` | 404 | The provider has no data for it |
| `not_found` | 404 | Resource or route doesn't exist |
| `method_not_allowed` | 405 | Wrong verb for that route |
| `duplicate_resource` | 409 | Already on the watchlist |
| `insufficient_data` | 422 | Not enough history to calculate it |
| `validation_error` | 422 | Body or query parameter rejected |
| `provider_rate_limited` | 429 | Out of quota |
| `provider_error` | 502 | Upstream returned something unexpected |
| `ai_service_error` | 502 | The AI call failed |
| `ai_response_invalid` | 502 | The report failed validation and was discarded |
| `configuration_error` | 503 | A required API key isn't set on the server |
| `provider_timeout` | 504 | Upstream took too long |

Server errors also include a `request_id`, which is echoed in the
`X-Request-ID` header and written to the access log. If someone reports a bug
and quotes that id, you can find the exact stack trace. Client errors leave it
out on purpose, since a 4xx is the caller's problem and the id would just be
noise.

---

## Configuration

Everything is read from `backend/.env`. Defaults live in `backend/.env.example`.

| Variable | Default | What it does |
|---|---|---|
| `APP_NAME` | `AI Stock Research Assistant` | Shown in the docs and health response |
| `ENVIRONMENT` | `development` | Anything else turns off `/docs`, `/redoc` and `/openapi.json` |
| `LOG_LEVEL` | `INFO` | `DEBUG` also logs cache hits |
| `DATABASE_URL` | `sqlite:///./stock_research.db` | See [swapping the database](#swapping-the-database) |
| `MARKET_DATA_PROVIDER` | `fmp` | Either `fmp` or `alpha_vantage` |
| `FMP_API_KEY` | | Needed when the provider is `fmp` |
| `FMP_BASE_URL` | `https://financialmodelingprep.com/stable` | Point this at a mock if you want |
| `ALPHA_VANTAGE_API_KEY` | | Needed when the provider is `alpha_vantage` |
| `ALPHA_VANTAGE_BASE_URL` | `https://www.alphavantage.co/query` | |
| `ANTHROPIC_API_KEY` | | Needed for research reports |
| `ANTHROPIC_MODEL` | `claude-opus-5` | |
| `ANTHROPIC_MAX_TOKENS` | `8000` | Output ceiling per report |
| `HTTP_TIMEOUT_SECONDS` | `15` | Timeout on outbound calls |
| `HTTP_MAX_RETRIES` | `2` | Retries on timeouts and 5xx. 4xx is never retried |
| `CACHE_TTL_QUOTE` | `60` | Seconds |
| `CACHE_TTL_HISTORY` | `3600` | Seconds |
| `CACHE_TTL_OVERVIEW` | `86400` | Seconds. Company profiles barely change |
| `CACHE_TTL_NEWS` | `900` | Seconds |
| `CACHE_TTL_RESEARCH` | `3600` | Seconds |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma separated |

### Caching

Free market data plans are metered, and one dashboard load needs several calls,
so responses are cached in memory with a different TTL per data type. Only
successful responses get cached. A failure is never stored, so a blip doesn't
stick around for an hour.

That's fine for one process. If you run multiple workers, each gets its own
copy, and the fix is to swap `app/core/cache.py` for Redis. Its interface is
deliberately tiny (`get`, `set`, `invalidate`) so nothing else has to change.

### Swapping the database

One line, no code changes:

```ini
DATABASE_URL=sqlite:///./stock_research.db
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/stockresearch   # also: pip install "psycopg[binary]"
DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/stockresearch        # also: pip install PyMySQL
```

The models stick to portable column types and give their constraints explicit
names, so the schema works on all three. There's a PostgreSQL service in the
compose file behind a profile: `docker compose --profile postgres up`.

### Swapping the market data provider

This one's already been done once, which is the best evidence the abstraction
works. The project started on Alpha Vantage and moved to Financial Modeling
Prep, and the only files that changed were the new provider, one line in a
registry, and the env var. No router, service, schema or frontend code was
touched.

To add a third: write a class implementing `StockDataProvider` in
`backend/app/services/providers/`, add one entry to `_PROVIDERS` in that
package's `__init__.py`, and set `MARKET_DATA_PROVIDER`.

---

## Tests

```bash
cd backend
pytest                                      # 234 tests
pytest --cov=app --cov-report=term-missing  # with coverage
```

No test touches the network. Market data calls are intercepted with `respx` and
the AI client is swapped out, so the suite is free to run and can't burn your
daily quota.

The tests focus on the things that are easy to break by accident:

| Area | What's covered |
|---|---|
| Data integrity | Provider placeholders become `null` not `0`, a real `0` survives, `inf` and `NaN` are rejected |
| Indicators | RSI checked against a separately written implementation, short history refuses instead of approximating, every blank field has a reason |
| Providers | Both FMP and Alpha Vantage: error mapping, retries, and the API key never showing up in an exception or a log line |
| API | All ten operations, their error paths, and caching |
| Research | The AI schema can't hold a number, one-sided reports fail validation, the disclaimer is fixed server side |
| Errors | One envelope everywhere, 500s carry a request id and nothing else |

Frontend checks:

```bash
cd frontend
npm run typecheck    # strict TypeScript
npm run lint
npm run build
```

---

## Security

No API key ever reaches the browser. All provider and AI calls happen on the
server. Every `VITE_*` variable gets baked into the public JavaScript bundle,
which is exactly why `frontend/.env.example` has no secrets in it and says so.

Keys are stored as Pydantic `SecretStr`, so they render as `**********` in any
log line, stack trace, or accidental `print(settings)`.

Provider URLs are never logged, because the key travels as a query parameter
and logging a request URL would leak it. Log lines name the endpoint and the
ticker instead. There's a test asserting the key doesn't appear in exception
text or captured logs.

Unexpected errors return a plain 500. The traceback goes to the server log and
nothing internal goes in the response body.

Input is validated at the boundary. Ticker symbols are normalised against a
strict pattern before they can end up in an outbound URL, a cache key, or a
database row, so something like `../etc` is rejected before anything acts on it.

Client supplied `X-Request-ID` values are stripped of control characters and
length capped, so they can't be used for log or header injection.

Both containers run as non-root, and `.env` is excluded from both build
contexts so secrets never end up in an image layer.

---

## Project layout

```
AI-Stock-Research-Assistant/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt / requirements-dev.txt
│   ├── .env.example
│   ├── app/
│   │   ├── main.py                  app factory, middleware, lifespan
│   │   ├── config.py                typed settings
│   │   ├── database.py              engine, session factory, base
│   │   ├── core/
│   │   │   ├── cache.py             thread safe TTL cache
│   │   │   ├── exceptions.py        error types and handlers
│   │   │   ├── middleware.py        request ids and access logging
│   │   │   └── validation.py        ticker normalisation
│   │   ├── models/                  SQLAlchemy
│   │   ├── schemas/                 Pydantic
│   │   ├── routers/                 stocks, research, watchlist
│   │   └── services/
│   │       ├── stock_service.py
│   │       ├── indicator_service.py
│   │       ├── research_service.py
│   │       ├── watchlist_service.py
│   │       └── providers/           fmp.py, alpha_vantage.py, base.py
│   └── tests/                       234 tests
└── frontend/
    ├── Dockerfile
    ├── nginx.conf                   serves the build, proxies /api
    └── src/
        ├── api/                     axios client and typed endpoints
        ├── components/              dashboard panels
        │   └── ui/                  reusable primitives
        ├── contexts/                watchlist state
        ├── hooks/                   data fetching, theme, connectivity
        ├── styles/                  design tokens
        ├── types/                   interfaces matching the API
        └── utils/                   formatters
```

---

## Known limitations

**Free data plans are metered.** Caching stretches it a long way, but looking up
a lot of different tickers in one day will eventually hit the ceiling.

**News needs a paid FMP plan.** Rather than showing an error, the news panel
says so. Switching `MARKET_DATA_PROVIDER` to `alpha_vantage` gets you news on
its free tier instead.

**Prices aren't adjusted for splits or dividends** on the free tiers, so a split
inside the window you're looking at shows up as a jump in the chart.

**The cache is per process.** Multiple workers each keep their own.

**There's no login.** The watchlist belongs to the deployment, not to a user.
Adding accounts means a `user_id` column and widening the unique constraint to
`(user_id, ticker)`. That column was left out rather than added and ignored.

**Numbers inside the AI's prose are written by the model.** The schema
guarantees no figure in the narrative is ever parsed back out and treated as
data, and every number rendered as a metric comes from the typed market data
models. But the report text itself is generated, and should be read that way.

---

## Disclaimer

This is a software engineering portfolio project. It is **not financial
advice** and it is not a recommendation to buy, sell or hold anything.

AI research reports are automated interpretations of public data and can be
incomplete, out of date, or simply wrong. Market data comes from a third party
and may be delayed or inaccurate. Don't make investment decisions based on it.
Do your own research and talk to a qualified financial professional.

---

## License

[MIT](LICENSE)
