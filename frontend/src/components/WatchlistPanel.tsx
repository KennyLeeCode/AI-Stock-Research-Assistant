import { useState } from 'react'

import { ApiError } from '@/api/client'
import { Badge, Card, EmptyState, ErrorState, Skeleton } from '@/components/ui'
import { useWatchlist } from '@/hooks/useWatchlist'
import type { WatchlistItem } from '@/types/api'

import styles from './WatchlistPanel.module.css'

function IconClose() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  )
}

function IconBookmark() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 4h12v16l-6-4-6 4z" />
    </svg>
  )
}

interface WatchlistRowProps {
  item: WatchlistItem
  active: boolean
  pending: boolean
  onSelect: (ticker: string) => void
  onRemove: (ticker: string) => void
}

function WatchlistRow({
  item,
  active,
  pending,
  onSelect,
  onRemove,
}: WatchlistRowProps) {
  return (
    <li
      className={[
        styles.row,
        active ? styles.rowActive : '',
        pending ? styles.rowPending : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <button
        type="button"
        className={styles.select}
        onClick={() => onSelect(item.ticker)}
        aria-current={active ? 'true' : undefined}
      >
        <span
          className={`${styles.ticker} ${active ? styles.tickerActive : ''}`}
        >
          {item.ticker}
        </span>
        {item.company_name && (
          <span className={styles.company}>{item.company_name}</span>
        )}
      </button>

      <button
        type="button"
        className={styles.remove}
        onClick={() => onRemove(item.ticker)}
        disabled={pending}
        aria-label={`Remove ${item.ticker} from watchlist`}
        title={`Remove ${item.ticker}`}
      >
        <IconClose />
      </button>
    </li>
  )
}

interface WatchlistPanelProps {
  /** Currently displayed ticker, highlighted in the list. */
  activeTicker: string | null
  onSelect: (ticker: string) => void
}

/**
 * Saved tickers, with click-to-load and inline removal.
 *
 * Removal errors are surfaced in the panel rather than thrown away, because the
 * optimistic delete is rolled back on failure - the row reappearing with no
 * explanation would look like a bug.
 */
export function WatchlistPanel({
  activeTicker,
  onSelect,
}: WatchlistPanelProps) {
  const { items, loading, error, isPending, remove, reload } = useWatchlist()
  const [removeError, setRemoveError] = useState<string | null>(null)

  async function handleRemove(ticker: string) {
    setRemoveError(null)
    try {
      await remove(ticker)
    } catch (caught: unknown) {
      setRemoveError(
        caught instanceof ApiError
          ? caught.message
          : `Could not remove ${ticker}.`,
      )
    }
  }

  return (
    <Card
      title="Watchlist"
      subtitle={
        items.length > 0 ? (
          <span className={styles.count}>
            {items.length} {items.length === 1 ? 'company' : 'companies'}
          </span>
        ) : undefined
      }
    >
      {loading ? (
        <div aria-busy="true" aria-label="Loading watchlist">
          {Array.from({ length: 3 }, (_, index) => (
            <div key={index} style={{ padding: 'var(--space-2) 0' }}>
              <Skeleton variant="text" width="45%" />
              <div style={{ height: 4 }} />
              <Skeleton variant="text" width="75%" />
            </div>
          ))}
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={reload} compact />
      ) : items.length === 0 ? (
        <EmptyState
          title="No saved companies"
          description="Search a ticker and select Add to watchlist to keep it here."
          hint="Saved companies persist between sessions."
          icon={<IconBookmark />}
          compact
        />
      ) : (
        <>
          <ul className={styles.list}>
            {items.map((item) => (
              <WatchlistRow
                key={item.id}
                item={item}
                active={item.ticker === activeTicker}
                pending={isPending(item.ticker)}
                onSelect={onSelect}
                onRemove={handleRemove}
              />
            ))}
          </ul>
          {removeError && (
            <p className={styles.error} role="alert">
              {removeError}
            </p>
          )}
        </>
      )}
    </Card>
  )
}

/** Compact chip row used above the dashboard on narrow screens. */
export function WatchlistChips({
  activeTicker,
  onSelect,
}: WatchlistPanelProps) {
  const { items } = useWatchlist()

  if (items.length === 0) return null

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 'var(--space-2)',
        alignItems: 'center',
      }}
    >
      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
        Watchlist:
      </span>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => onSelect(item.ticker)}
          style={{ padding: 0 }}
        >
          <Badge tone={item.ticker === activeTicker ? 'accent' : 'outline'}>
            {item.ticker}
          </Badge>
        </button>
      ))}
    </div>
  )
}
