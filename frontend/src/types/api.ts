/**
 * TypeScript mirrors of the backend's Pydantic schemas.
 *
 * Rule: every field the backend types as `float | None` is `number | null`
 * here — never `number | undefined` and never an optional `?`. That distinction
 * carries real meaning in this app. `null` means the data provider genuinely
 * had no value for that metric, and the UI must render an em dash rather than a
 * zero. Making these optional would let a component silently fall back to a
 * default and display a number that nobody measured.
 */

/* ==========================================================================
   Shared
   ========================================================================== */

/** Fields present on every provider-sourced payload, used for attribution. */
export interface ProviderPayload {
  /** Human-readable provider name, e.g. "Alpha Vantage". */
  source: string
  /** ISO-8601 UTC instant the data was fetched. */
  retrieved_at: string
}

/* ==========================================================================
   Market data
   ========================================================================== */

export interface Quote extends ProviderPayload {
  symbol: string
  price: number | null
  change: number | null
  /** Percentage change, already scaled: 1.25 means +1.25%. */
  change_percent: number | null
  previous_close: number | null
  open: number | null
  day_high: number | null
  day_low: number | null
  volume: number | null
  /** ISO date, e.g. "2026-07-24". */
  latest_trading_day: string | null
}

export interface PricePoint {
  /** ISO date, e.g. "2026-07-24". */
  date: string
  open: number | null
  high: number | null
  low: number | null
  /** Required: a day without a close is omitted by the backend, not zeroed. */
  close: number
  volume: number | null
}

export interface PriceHistory extends ProviderPayload {
  symbol: string
  /** Oldest first. */
  points: PricePoint[]
}

export interface CompanyOverview extends ProviderPayload {
  symbol: string
  name: string | null
  description: string | null
  exchange: string | null
  currency: string | null
  country: string | null
  sector: string | null
  industry: string | null
  fiscal_year_end: string | null
  latest_quarter: string | null

  // Valuation
  market_cap: number | null
  pe_ratio: number | null
  forward_pe: number | null
  peg_ratio: number | null
  price_to_book: number | null
  book_value: number | null
  analyst_target_price: number | null

  // Profitability — fractions, not percentages: 0.25 means 25%.
  eps: number | null
  profit_margin: number | null
  operating_margin: number | null
  return_on_equity: number | null
  return_on_assets: number | null

  // Scale
  revenue_ttm: number | null
  gross_profit_ttm: number | null
  ebitda: number | null
  shares_outstanding: number | null

  // Dividend & risk — dividend_yield is a fraction: 0.0044 means 0.44%.
  dividend_yield: number | null
  dividend_per_share: number | null
  beta: number | null

  /** Provider-reported, normally from intraday extremes. */
  week_52_high: number | null
  week_52_low: number | null
}

export interface NewsArticle {
  title: string
  url: string
  source: string | null
  /** ISO-8601 instant, or null when the provider omitted it. */
  published_at: string | null
  summary: string | null
  banner_image: string | null
  /** Provider-assigned, e.g. "Bullish". Not computed by this app. */
  sentiment_label: string | null
  sentiment_score: number | null
}

export interface NewsFeed extends ProviderPayload {
  symbol: string
  /** Newest first. An empty array is a valid result, not an error. */
  articles: NewsArticle[]
}

/* ==========================================================================
   Technical indicators
   ========================================================================== */

/** Keys that can appear in `TechnicalIndicators.unavailable`. */
export type IndicatorKey =
  | 'sma_20'
  | 'sma_50'
  | 'rsi_14'
  | 'volatility_30d'
  | 'price_change_1m'
  | 'price_change_3m'
  | 'week_52_high'
  | 'week_52_low'

export interface TechnicalIndicators {
  symbol: string
  /** Date of the most recent close used, ISO. */
  as_of: string

  // Provenance
  source: string
  history_retrieved_at: string
  data_points_used: number

  // Trend
  sma_20: number | null
  sma_50: number | null

  // Momentum — 0 to 100.
  rsi_14: number | null

  // Risk — annualized percent: 24.5 means 24.5%.
  volatility_30d: number | null

  // Performance — percent.
  price_change_1m: number | null
  price_change_3m: number | null

  /** Computed from daily closes in the history this app fetched. */
  week_52_high: number | null
  week_52_low: number | null
  week_52_high_date: string | null
  week_52_low_date: string | null

  /**
   * Indicator name mapped to a plain-language reason it could not be computed.
   * A key here always corresponds to a null field above, so the UI can render a
   * specific explanation instead of an unexplained blank.
   */
  unavailable: Partial<Record<IndicatorKey, string>>
}

/* ==========================================================================
   Research
   ========================================================================== */

export interface DataSourceRef {
  dataset: string
  provider: string
  retrieved_at: string
}

/**
 * An AI-generated research report.
 *
 * Note there is not a single numeric field here. The model returns prose only;
 * every figure the dashboard displays comes from the market-data types above.
 */
export interface ResearchReport {
  symbol: string
  generated_at: string
  model: string
  cached: boolean

  price_as_of: string | null
  data_sources: DataSourceRef[]

  company_summary: string
  recent_performance: string
  technical_analysis: string
  fundamental_analysis: string
  bull_case: string[]
  bear_case: string[]
  risks: string[]
  catalysts: string[]
  neutral_conclusion: string
  disclaimer: string
}

export interface ResearchRequest {
  ticker: string
  refresh?: boolean
}

/* ==========================================================================
   Watchlist
   ========================================================================== */

export interface WatchlistItem {
  id: number
  ticker: string
  company_name: string | null
  notes: string | null
  created_at: string
}

export interface WatchlistItemCreate {
  ticker: string
  notes?: string | null
}

/* ==========================================================================
   Errors
   ========================================================================== */

/**
 * Stable error codes from the backend. Every error response uses this
 * envelope, including framework-level 404s and 405s, so a handler can always
 * read `error.code`.
 */
export type ApiErrorCode =
  | 'invalid_ticker'
  | 'ticker_not_found'
  | 'not_found'
  | 'duplicate_resource'
  | 'insufficient_data'
  | 'validation_error'
  | 'provider_rate_limited'
  | 'provider_error'
  | 'provider_timeout'
  | 'ai_service_error'
  | 'ai_response_invalid'
  | 'configuration_error'
  | 'bad_request'
  | 'method_not_allowed'
  | 'client_error'
  | 'internal_error'
  // Client-side only; never sent by the server.
  | 'network_error'
  | 'request_cancelled'

export interface ApiErrorBody {
  error: {
    code: ApiErrorCode
    message: string
    details?: Record<string, unknown>
  }
}

/* ==========================================================================
   Health
   ========================================================================== */

export interface HealthResponse {
  status: string
  app: string
  version: string
  environment: string
  dependencies: {
    market_data_configured: boolean
    ai_configured: boolean
  }
}
