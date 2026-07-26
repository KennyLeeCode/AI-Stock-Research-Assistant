import { formatDateTime, formatRelativeTime } from '@/utils/format'

import styles from './DataSource.module.css'

interface DataSourceProps {
  /** Provider name, e.g. "Alpha Vantage". */
  source: string
  /** ISO-8601 instant the data was fetched. */
  retrievedAt: string
  /** Extra note, e.g. "computed from daily closes". */
  note?: string
}

/**
 * Attribution line shown in the footer of every data panel.
 *
 * Naming the provider and the fetch time is a requirement of showing financial
 * figures at all: a price with no timestamp invites the reader to assume it is
 * live. The relative time is the quick read; the exact instant is in the
 * tooltip for anyone who needs precision.
 */
export function DataSource({ source, retrievedAt, note }: DataSourceProps) {
  return (
    <div className={styles.source}>
      <span>Source: {source}</span>
      <span className={styles.divider} aria-hidden="true">
        ·
      </span>
      <span>
        Retrieved{' '}
        <time dateTime={retrievedAt} title={formatDateTime(retrievedAt)}>
          {formatRelativeTime(retrievedAt)}
        </time>
      </span>
      {note && (
        <>
          <span className={styles.divider} aria-hidden="true">
            ·
          </span>
          <span>{note}</span>
        </>
      )}
    </div>
  )
}
