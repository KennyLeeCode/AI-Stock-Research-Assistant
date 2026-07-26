import { useCallback, useState } from 'react'

import { fetchHealth } from '@/api/endpoints'
import { Dashboard } from '@/components/Dashboard'
import { SearchBar } from '@/components/SearchBar'
import { WatchlistButton } from '@/components/WatchlistButton'
import { WatchlistChips, WatchlistPanel } from '@/components/WatchlistPanel'
import { Badge, Card, EmptyState } from '@/components/ui'
import { WatchlistProvider } from '@/contexts/WatchlistProvider'
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

function AppContent() {
  const [ticker, setTicker] = useState<string | null>(null)

  const fetchHealthStatus = useCallback(
    (signal: AbortSignal) => fetchHealth({ signal }),
    [],
  )
  const { data: health } = useAsyncData<HealthResponse>(fetchHealthStatus, [])

  const marketDataReady = health?.dependencies.market_data_configured ?? false
  const aiReady = health?.dependencies.ai_configured ?? false
  const showWarnings = health !== null && !(marketDataReady && aiReady)

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

          {showWarnings && (
            <div className={styles.statusRow}>
              {!marketDataReady && (
                <Badge tone="warning">Market data key missing</Badge>
              )}
              {!aiReady && <Badge tone="warning">AI key missing</Badge>}
            </div>
          )}
        </div>
      </header>

      <main className={styles.main} id="main">
        {!ticker && (
          <div className={styles.hero}>
            <h1 className={styles.heroTitle}>Research any listed company</h1>
            <p className={styles.heroText}>
              Search a ticker for a live quote, price history, fundamentals,
              technical indicators, recent news, and a balanced AI research
              report grounded strictly in that data.
            </p>
          </div>
        )}

        <div className={styles.layout}>
          <div className={styles.content}>
            <div>
              <SearchBar onSearch={setTicker} initialValue={ticker ?? ''} />
              <div className={styles.chips} style={{ marginTop: 'var(--space-3)' }}>
                <WatchlistChips activeTicker={ticker} onSelect={setTicker} />
              </div>
            </div>

            {ticker ? (
              // Keying on the ticker discards all panel state on a new search,
              // so the previous company's figures can never linger while the
              // next one loads.
              <Dashboard
                key={ticker}
                ticker={ticker}
                watchlistAction={<WatchlistButton ticker={ticker} />}
              />
            ) : (
              <Card>
                <EmptyState
                  title="Search a ticker to begin"
                  description="Enter a symbol above, or pick one of the examples, to load its dashboard."
                  hint="Market data is cached, so revisiting a company you have already looked up costs nothing."
                />
              </Card>
            )}
          </div>

          <aside className={styles.sidebar} aria-label="Watchlist">
            <WatchlistPanel activeTicker={ticker} onSelect={setTicker} />
          </aside>
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

export default function App() {
  return (
    <WatchlistProvider>
      <AppContent />
    </WatchlistProvider>
  )
}
