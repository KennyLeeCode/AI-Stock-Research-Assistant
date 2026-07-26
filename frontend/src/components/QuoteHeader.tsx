import type { ReactNode } from 'react'

import { ChangeValue, Metric } from '@/components/Metric'
import { Badge, Skeleton } from '@/components/ui'
import type { CompanyOverview, Quote } from '@/types/api'
import {
  formatCompact,
  formatDate,
  formatPrice,
  formatSignedNumber,
  formatSignedPercent,
} from '@/utils/format'

import styles from './QuoteHeader.module.css'

interface QuoteHeaderProps {
  quote: Quote
  /** Optional: supplies the company name and exchange when loaded. */
  overview?: CompanyOverview | null
  /** Watchlist controls, injected so this component stays presentational. */
  actions?: ReactNode
}

/**
 * The page's primary heading: symbol, name, current price, and daily change.
 *
 * The price is an `<h1>` region for the searched security, so screen reader
 * users landing here get the identity of what they are reading first.
 */
export function QuoteHeader({ quote, overview, actions }: QuoteHeaderProps) {
  const currency = overview?.currency ?? null

  return (
    <div>
      <div className={styles.header}>
        <div className={styles.identity}>
          <div className={styles.symbolRow}>
            <h1 className={styles.symbol}>{quote.symbol}</h1>
            {overview?.exchange && (
              <Badge tone="outline">{overview.exchange}</Badge>
            )}
            {overview?.sector && <Badge tone="neutral">{overview.sector}</Badge>}
          </div>

          {overview?.name && <p className={styles.company}>{overview.name}</p>}

          {quote.latest_trading_day && (
            <p className={styles.meta}>
              Close for {formatDate(quote.latest_trading_day)}
            </p>
          )}
        </div>

        <div className={styles.priceBlock}>
          <div className={styles.price}>
            {formatPrice(quote.price, currency)}
          </div>
          <ChangeValue
            change={quote.change}
            changePercent={quote.change_percent}
            formattedChange={formatSignedNumber(quote.change)}
            formattedPercent={formatSignedPercent(quote.change_percent)}
          />
        </div>
      </div>

      {actions && <div className={styles.actions}>{actions}</div>}

      <div className={styles.stats}>
        <Metric label="Open" value={formatPrice(quote.open, currency)} />
        <Metric label="Day high" value={formatPrice(quote.day_high, currency)} />
        <Metric label="Day low" value={formatPrice(quote.day_low, currency)} />
        <Metric
          label="Previous close"
          value={formatPrice(quote.previous_close, currency)}
        />
        <Metric label="Volume" value={formatCompact(quote.volume)} />
      </div>
    </div>
  )
}

/** Layout-matched placeholder, so nothing shifts when the quote arrives. */
export function QuoteHeaderSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading quote">
      <div className={styles.header}>
        <div className={styles.identity}>
          <Skeleton variant="heading" width={140} />
          <div style={{ height: 6 }} />
          <Skeleton variant="text" width={220} />
        </div>
        <div className={styles.priceBlock}>
          <Skeleton variant="heading" width={160} height={40} />
          <div style={{ height: 6 }} />
          <Skeleton variant="text" width={120} />
        </div>
      </div>
      <div className={styles.stats}>
        {Array.from({ length: 5 }, (_, index) => (
          <div key={index}>
            <Skeleton variant="text" width="55%" />
            <div style={{ height: 4 }} />
            <Skeleton variant="text" width="75%" />
          </div>
        ))}
      </div>
    </div>
  )
}
