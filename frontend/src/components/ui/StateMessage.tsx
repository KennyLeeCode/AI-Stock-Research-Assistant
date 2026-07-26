import type { ReactNode } from 'react'

import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/Button'
import type { ApiErrorCode } from '@/types/api'

import styles from './StateMessage.module.css'

/* ==========================================================================
   Icons
   ========================================================================== */

function IconSearch() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  )
}

function IconAlert() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5v5" />
      <path d="M12 16.5h.01" />
    </svg>
  )
}

function IconClock() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  )
}

function IconOffline() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <path d="M3 3l18 18" />
      <path d="M5 12.5a11 11 0 0 1 4-2.6" />
      <path d="M8.5 16a6 6 0 0 1 2.2-1.4" />
      <path d="M12 20h.01" />
      <path d="M19.5 12.5a11 11 0 0 0-6.8-3.4" />
    </svg>
  )
}

/* ==========================================================================
   Empty state
   ========================================================================== */

interface EmptyStateProps {
  title: string
  description?: string
  /** Secondary line for guidance the user might not otherwise know. */
  hint?: string
  icon?: ReactNode
  action?: ReactNode
  compact?: boolean
}

/**
 * Shown when a request succeeded but there is nothing to display.
 *
 * Deliberately distinct from `ErrorState`: "this company has no recent news" is
 * a normal, correct outcome, and dressing it up as a failure teaches users to
 * distrust the app.
 */
export function EmptyState({
  title,
  description,
  hint,
  icon,
  action,
  compact = false,
}: EmptyStateProps) {
  return (
    <div className={`${styles.wrapper} ${compact ? styles.compact : ''}`}>
      <div className={styles.icon}>{icon ?? <IconSearch />}</div>
      <p className={styles.title}>{title}</p>
      {description && <p className={styles.description}>{description}</p>}
      {hint && <p className={styles.hint}>{hint}</p>}
      {action && <div className={styles.actions}>{action}</div>}
    </div>
  )
}

/* ==========================================================================
   Error state
   ========================================================================== */

interface ErrorCopy {
  title: string
  description: string
  /** Extra guidance the message alone does not convey. */
  hint?: string
  icon: ReactNode
  variant: 'error' | 'warning'
  /** Whether a retry button makes sense for this failure. */
  retryable: boolean
}

/**
 * Maps a backend error code to copy written for the person reading it.
 *
 * The backend's own message is used as the description wherever it is already
 * user-facing; this adds a short title and, where useful, a hint that explains
 * *why* something happened and what to do — for example, that the free market
 * data tier allows only about 25 requests a day.
 */
function copyForError(error: ApiError): ErrorCopy {
  const code: ApiErrorCode = error.code

  switch (code) {
    case 'invalid_ticker':
      return {
        title: 'That does not look like a ticker symbol',
        description: error.message,
        hint: 'Symbols are 1–6 letters, optionally with a class suffix — for example AAPL, MSFT, or BRK.B.',
        icon: <IconSearch />,
        variant: 'warning',
        retryable: false,
      }

    case 'ticker_not_found':
      return {
        title: 'No data for that symbol',
        description: error.message,
        hint: 'Check the spelling, or try the symbol as listed on its primary exchange.',
        icon: <IconSearch />,
        variant: 'warning',
        retryable: false,
      }

    case 'not_found':
      return {
        title: 'Not found',
        description: error.message,
        icon: <IconSearch />,
        variant: 'warning',
        retryable: false,
      }

    case 'duplicate_resource':
      return {
        title: 'Already saved',
        description: error.message,
        icon: <IconAlert />,
        variant: 'warning',
        retryable: false,
      }

    case 'insufficient_data':
      return {
        title: 'Not enough price history',
        description: error.message,
        hint: 'This usually means the company listed recently. Figures are only shown when there is enough real data to calculate them.',
        icon: <IconAlert />,
        variant: 'warning',
        retryable: false,
      }

    case 'validation_error':
      return {
        title: 'Check the details',
        description: error.message,
        icon: <IconAlert />,
        variant: 'warning',
        retryable: false,
      }

    case 'provider_rate_limited':
      return {
        title: 'Data limit reached',
        description: error.message,
        hint: 'The free market data plan allows about 25 requests per day. Results already loaded are cached and stay available.',
        icon: <IconClock />,
        variant: 'warning',
        retryable: true,
      }

    case 'provider_timeout':
      return {
        title: 'The data provider timed out',
        description: error.message,
        icon: <IconClock />,
        variant: 'warning',
        retryable: true,
      }

    case 'provider_error':
      return {
        title: 'Market data unavailable',
        description: error.message,
        hint: 'This is a problem at the data provider, not with your search.',
        icon: <IconAlert />,
        variant: 'error',
        retryable: true,
      }

    case 'ai_service_error':
      return {
        title: 'Research service unavailable',
        description: error.message,
        hint: 'Market data on this page is unaffected.',
        icon: <IconAlert />,
        variant: 'error',
        retryable: true,
      }

    case 'ai_response_invalid':
      return {
        title: 'The report could not be verified',
        description: error.message,
        hint: 'The report failed validation and was discarded rather than shown incomplete. Generating it again usually works.',
        icon: <IconAlert />,
        variant: 'error',
        retryable: true,
      }

    case 'configuration_error':
      return {
        title: 'The server is missing an API key',
        description: error.message,
        hint: 'Add the key to backend/.env and restart the server. See the README for setup.',
        icon: <IconAlert />,
        variant: 'error',
        retryable: false,
      }

    case 'network_error':
      return {
        title: 'Cannot reach the server',
        description: error.message,
        hint: 'Check that the backend is running on port 8000.',
        icon: <IconOffline />,
        variant: 'error',
        retryable: true,
      }

    default:
      return {
        title: 'Something went wrong',
        description: error.message,
        icon: <IconAlert />,
        variant: 'error',
        retryable: true,
      }
  }
}

interface ErrorStateProps {
  error: unknown
  /** Retry handler. A retry button appears only when the error warrants one. */
  onRetry?: () => void
  retryLabel?: string
  compact?: boolean
}

/**
 * Renders a failure with copy the user can act on.
 *
 * `role="alert"` so assistive technology announces it when it appears mid-page
 * rather than leaving the user waiting on content that will never arrive.
 */
export function ErrorState({
  error,
  onRetry,
  retryLabel = 'Try again',
  compact = false,
}: ErrorStateProps) {
  const apiError =
    error instanceof ApiError
      ? error
      : new ApiError('internal_error', 'Something went wrong. Please try again.')

  const copy = copyForError(apiError)
  const iconClass =
    copy.variant === 'error' ? styles.iconError : styles.iconWarning

  return (
    <div
      className={`${styles.wrapper} ${compact ? styles.compact : ''}`}
      role="alert"
    >
      <div className={`${styles.icon} ${iconClass}`}>{copy.icon}</div>
      <p className={styles.title}>{copy.title}</p>
      <p className={styles.description}>{copy.description}</p>
      {copy.hint && <p className={styles.hint}>{copy.hint}</p>}
      {onRetry && copy.retryable && (
        <div className={styles.actions}>
          <Button variant="secondary" size="sm" onClick={onRetry}>
            {retryLabel}
          </Button>
        </div>
      )}
    </div>
  )
}
