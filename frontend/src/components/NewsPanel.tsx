import { Badge, EmptyState, Skeleton } from '@/components/ui'
import type { NewsArticle, NewsFeed } from '@/types/api'
import { formatRelativeTime } from '@/utils/format'

import styles from './NewsPanel.module.css'

function IconExternal() {
  return (
    <svg
      className={styles.external}
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M9 5h10v10" />
      <path d="M19 5 5 19" />
    </svg>
  )
}

/** Maps the provider's sentiment label to a badge tone. */
function sentimentTone(
  label: string | null,
): 'positive' | 'negative' | 'neutral' {
  if (!label) return 'neutral'
  const lowered = label.toLowerCase()
  if (lowered.includes('bullish')) return 'positive'
  if (lowered.includes('bearish')) return 'negative'
  return 'neutral'
}

function NewsItem({ article }: { article: NewsArticle }) {
  const tone = sentimentTone(article.sentiment_label)

  return (
    <li className={styles.item}>
      <a
        className={styles.headline}
        href={article.url}
        target="_blank"
        // `noopener` prevents the opened page from reaching back through
        // `window.opener`; `noreferrer` withholds the referring URL.
        rel="noopener noreferrer"
      >
        {article.title}
        <IconExternal />
        <span className="sr-only"> (opens in a new tab)</span>
      </a>

      {article.summary && <p className={styles.summary}>{article.summary}</p>}

      <div className={styles.meta}>
        {article.source && <span>{article.source}</span>}
        {article.source && article.published_at && (
          <span className={styles.divider} aria-hidden="true">
            ·
          </span>
        )}
        {article.published_at && (
          <time dateTime={article.published_at}>
            {formatRelativeTime(article.published_at)}
          </time>
        )}
        {article.sentiment_label && (
          <Badge
            tone={tone}
            srLabel={`Provider sentiment: ${article.sentiment_label}`}
          >
            {article.sentiment_label}
          </Badge>
        )}
      </div>
    </li>
  )
}

interface NewsPanelProps {
  news: NewsFeed
}

export function NewsPanel({ news }: NewsPanelProps) {
  if (news.articles.length === 0) {
    return (
      <EmptyState
        title="No recent news"
        description={`The data provider returned no recent articles for ${news.symbol}.`}
        hint="This is common for smaller companies and is not an error."
        compact
      />
    )
  }

  return (
    <ul className={styles.list}>
      {news.articles.map((article) => (
        <NewsItem key={article.url} article={article} />
      ))}
    </ul>
  )
}

/** Placeholder shaped like a list of headlines. */
export function NewsPanelSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading news">
      <ul className={styles.list}>
        {Array.from({ length: 4 }, (_, index) => (
          <li key={index} className={styles.item}>
            <Skeleton variant="text" width="92%" />
            <div style={{ height: 6 }} />
            <Skeleton variant="text" width="70%" />
            <div style={{ height: 8 }} />
            <Skeleton variant="text" width="35%" />
          </li>
        ))}
      </ul>
    </div>
  )
}
