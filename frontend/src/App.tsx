import { useCallback } from 'react'

import { fetchHealth } from '@/api/endpoints'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Skeleton,
  SkeletonText,
} from '@/components/ui'
import { useAsyncData } from '@/hooks/useAsyncData'
import type { HealthResponse } from '@/types/api'

import styles from './App.module.css'

function LogoMark() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 17.5 9 11l4 4 8-8.5" />
      <path d="M15 6.5h6v6" />
    </svg>
  )
}

/**
 * Application shell.
 *
 * At this stage it renders the header, footer, and a live connection check
 * against the backend, which is enough to prove the API client, error
 * normalization, design tokens, primitives, and data hook all work together.
 * The search bar and dashboard panels replace the placeholder region in the
 * next phase.
 */
export default function App() {
  const fetchHealthStatus = useCallback(
    (signal: AbortSignal) => fetchHealth({ signal }),
    [],
  )

  const {
    data: health,
    error,
    loading,
    reload,
  } = useAsyncData<HealthResponse>(fetchHealthStatus, [])

  const marketDataReady = health?.dependencies.market_data_configured ?? false
  const aiReady = health?.dependencies.ai_configured ?? false

  return (
    <div className={styles.shell}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.brand}>
            <span className={styles.mark}>
              <LogoMark />
            </span>
            <div className={styles.brandText}>
              <div className={styles.brandName}>AI Stock Research Assistant</div>
              <div className={styles.brandTag}>
                Data-grounded equity research
              </div>
            </div>
          </div>

          {health && (
            <div className={styles.statusRow}>
              <Badge tone={marketDataReady ? 'positive' : 'warning'}>
                {marketDataReady
                  ? 'Market data ready'
                  : 'Market data key missing'}
              </Badge>
              <Badge tone={aiReady ? 'positive' : 'warning'}>
                {aiReady ? 'AI ready' : 'AI key missing'}
              </Badge>
            </div>
          )}
        </div>
      </header>

      <main className={styles.main} id="main">
        <div className={styles.hero}>
          <h1 className={styles.heroTitle}>Research any listed company</h1>
          <p className={styles.heroText}>
            Search a ticker for a live quote, price history, fundamentals,
            technical indicators, recent news, and a balanced AI research report
            grounded strictly in that data.
          </p>
        </div>

        <div className={styles.grid}>
          <Card
            title="Backend connection"
            action={
              <Button size="sm" loading={loading} onClick={reload}>
                Recheck
              </Button>
            }
          >
            {loading && !health ? (
              <div aria-busy="true" aria-label="Checking backend connection">
                <Skeleton variant="heading" width="45%" />
                <SkeletonText lines={2} />
              </div>
            ) : error ? (
              <ErrorState error={error} onRetry={reload} compact />
            ) : health ? (
              <p>
                Connected to <strong>{health.app}</strong> v{health.version} in{' '}
                {health.environment} mode.
              </p>
            ) : null}
          </Card>

          <Card title="Search">
            <EmptyState
              title="No ticker selected"
              description="The search bar and dashboard land in the next phase."
              hint="Try AAPL, MSFT, or NVDA once it is wired up."
              compact
            />
          </Card>

          <Card title="Design system" subtitle="Primitives shared by every panel">
            <div className={styles.swatches}>
              <Badge tone="positive">+1.25%</Badge>
              <Badge tone="negative">-0.84%</Badge>
              <Badge tone="neutral">Unchanged</Badge>
              <Badge tone="accent">Cached</Badge>
              <Badge tone="warning">Overbought</Badge>
              <Badge tone="outline">Alpha Vantage</Badge>
            </div>
          </Card>
        </div>
      </main>

      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <p className={styles.disclaimer}>
            <strong>Not financial advice.</strong> This application is a software
            engineering portfolio project. Figures come from a third-party market
            data provider and may be delayed or inaccurate. AI-generated reports
            are automated interpretations of that data and may be incomplete or
            wrong. Nothing here is a recommendation to buy, sell, or hold any
            security. Always do your own research and consult a qualified
            financial professional.
          </p>
        </div>
      </footer>
    </div>
  )
}
