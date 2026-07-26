/**
 * Axios instance and error normalization.
 *
 * Every failure mode — a backend error envelope, a network drop, a timeout, an
 * aborted request — is converted into a single `ApiError` type. Components then
 * have exactly one shape to handle, and can branch on a stable `code` rather
 * than parsing messages or checking status numbers inline.
 *
 * There are no API keys here, and there never will be. The browser talks only
 * to this application's own backend; every third-party credential lives
 * server-side. `VITE_API_BASE_URL` is the sole configuration value, it is not a
 * secret, and in development it is empty so that Vite's dev-server proxy
 * forwards `/api` to the backend as a same-origin request.
 */

import axios, { AxiosError, type AxiosInstance } from 'axios'

import type { ApiErrorBody, ApiErrorCode } from '@/types/api'

/**
 * A normalized API failure.
 *
 * `message` is always safe to render: it is either the backend's
 * user-facing text or a written fallback, never a raw exception string.
 */
export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status: number | null
  readonly details: Record<string, unknown> | undefined

  constructor(
    code: ApiErrorCode,
    message: string,
    status: number | null = null,
    details?: Record<string, unknown>,
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.details = details
  }

  /** True when retrying the same request could plausibly succeed. */
  get isRetryable(): boolean {
    return (
      this.code === 'provider_timeout' ||
      this.code === 'provider_error' ||
      this.code === 'provider_rate_limited' ||
      this.code === 'ai_service_error' ||
      this.code === 'network_error' ||
      this.code === 'internal_error'
    )
  }

  /** True when the user asked for something that does not exist. */
  get isNotFound(): boolean {
    return this.code === 'ticker_not_found' || this.code === 'not_found'
  }

  /** True when the server is missing configuration the user cannot fix. */
  get isConfiguration(): boolean {
    return this.code === 'configuration_error'
  }
}

/** Empty in development so the Vite proxy handles `/api` as same-origin. */
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

/**
 * Generous timeout. Report generation waits on a language model, which can
 * legitimately take tens of seconds; a default 10s timeout would cancel a
 * request that was going to succeed.
 */
const REQUEST_TIMEOUT_MS = 120_000

export const http: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: REQUEST_TIMEOUT_MS,
  headers: { 'Content-Type': 'application/json' },
})

/** Type guard for the backend's error envelope. */
function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as { error?: unknown }
  if (typeof candidate.error !== 'object' || candidate.error === null) {
    return false
  }
  const detail = candidate.error as { code?: unknown; message?: unknown }
  return typeof detail.code === 'string' && typeof detail.message === 'string'
}

/** Convert any thrown value into an `ApiError`. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error

  if (axios.isCancel(error)) {
    return new ApiError(
      'request_cancelled',
      'The request was cancelled.',
      null,
    )
  }

  if (error instanceof AxiosError) {
    const status = error.response?.status ?? null

    // The backend's own envelope. Its message is written for users.
    if (isApiErrorBody(error.response?.data)) {
      const { code, message, details } = error.response.data.error
      return new ApiError(code, message, status, details)
    }

    if (error.code === 'ECONNABORTED') {
      return new ApiError(
        'provider_timeout',
        'The request took too long and was stopped. Please try again.',
        status,
      )
    }

    // No response at all: the backend is down, or the browser is offline.
    if (!error.response) {
      return new ApiError(
        'network_error',
        'Could not reach the server. Check that the backend is running and that you are online.',
        null,
      )
    }

    // A response with an unrecognized body — a proxy error page, for example.
    // Read the status off the response rather than the nullable local, so the
    // server/client split below is provably non-null.
    const responseStatus = error.response.status
    return new ApiError(
      responseStatus >= 500 ? 'internal_error' : 'client_error',
      responseStatus >= 500
        ? 'The server encountered an error. Please try again shortly.'
        : 'The request could not be completed.',
      responseStatus,
    )
  }

  return new ApiError(
    'internal_error',
    'Something went wrong. Please try again.',
    null,
  )
}

// Normalize at the boundary so no caller ever sees a raw AxiosError.
http.interceptors.response.use(
  (response) => response,
  (error: unknown) => Promise.reject(toApiError(error)),
)
