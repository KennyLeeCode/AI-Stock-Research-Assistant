/**
 * Typed wrappers for every backend endpoint.
 *
 * One function per route, each returning a typed model. Components never build
 * a URL or touch axios directly, so a route change is a single-file edit.
 *
 * Every function accepts an optional `AbortSignal`. React 19 effects clean up
 * on unmount and on dependency change, and without a signal a stale response
 * for a previously searched ticker can land after a newer one and overwrite it.
 */

import { http } from '@/api/client'
import type {
  CompanyOverview,
  HealthResponse,
  NewsFeed,
  PriceHistory,
  Quote,
  ResearchReport,
  TechnicalIndicators,
  WatchlistItem,
} from '@/types/api'

interface RequestOptions {
  signal?: AbortSignal
}

/* ==========================================================================
   System
   ========================================================================== */

export async function fetchHealth(options?: RequestOptions): Promise<HealthResponse> {
  const { data } = await http.get<HealthResponse>('/api/health', {
    signal: options?.signal,
  })
  return data
}

/* ==========================================================================
   Market data
   ========================================================================== */

export async function fetchQuote(
  ticker: string,
  options?: RequestOptions,
): Promise<Quote> {
  const { data } = await http.get<Quote>(
    `/api/stocks/${encodeURIComponent(ticker)}/quote`,
    { signal: options?.signal },
  )
  return data
}

export async function fetchHistory(
  ticker: string,
  days = 365,
  options?: RequestOptions,
): Promise<PriceHistory> {
  const { data } = await http.get<PriceHistory>(
    `/api/stocks/${encodeURIComponent(ticker)}/history`,
    { params: { days }, signal: options?.signal },
  )
  return data
}

export async function fetchOverview(
  ticker: string,
  options?: RequestOptions,
): Promise<CompanyOverview> {
  const { data } = await http.get<CompanyOverview>(
    `/api/stocks/${encodeURIComponent(ticker)}/overview`,
    { signal: options?.signal },
  )
  return data
}

export async function fetchIndicators(
  ticker: string,
  days = 365,
  options?: RequestOptions,
): Promise<TechnicalIndicators> {
  const { data } = await http.get<TechnicalIndicators>(
    `/api/stocks/${encodeURIComponent(ticker)}/indicators`,
    { params: { days }, signal: options?.signal },
  )
  return data
}

export async function fetchNews(
  ticker: string,
  limit = 10,
  options?: RequestOptions,
): Promise<NewsFeed> {
  const { data } = await http.get<NewsFeed>(
    `/api/stocks/${encodeURIComponent(ticker)}/news`,
    { params: { limit }, signal: options?.signal },
  )
  return data
}

/* ==========================================================================
   Research
   ========================================================================== */

export async function generateResearch(
  ticker: string,
  refresh = false,
  options?: RequestOptions,
): Promise<ResearchReport> {
  const { data } = await http.post<ResearchReport>(
    '/api/research',
    { ticker, refresh },
    { signal: options?.signal },
  )
  return data
}

/* ==========================================================================
   Watchlist
   ========================================================================== */

export async function fetchWatchlist(
  options?: RequestOptions,
): Promise<WatchlistItem[]> {
  const { data } = await http.get<WatchlistItem[]>('/api/watchlist', {
    signal: options?.signal,
  })
  return data
}

export async function addToWatchlist(
  ticker: string,
  notes?: string | null,
  options?: RequestOptions,
): Promise<WatchlistItem> {
  const { data } = await http.post<WatchlistItem>(
    '/api/watchlist',
    { ticker, notes: notes ?? null },
    { signal: options?.signal },
  )
  return data
}

export async function removeFromWatchlist(
  ticker: string,
  options?: RequestOptions,
): Promise<void> {
  await http.delete(`/api/watchlist/${encodeURIComponent(ticker)}`, {
    signal: options?.signal,
  })
}
