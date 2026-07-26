import { Suspense, lazy, useCallback, useState, type ReactNode } from 'react'

import {
  fetchHistory,
  fetchIndicators,
  fetchNews,
  fetchOverview,
  fetchQuote,
  generateResearch,
} from '@/api/endpoints'
import { CompanyPanel, CompanyPanelSkeleton } from '@/components/CompanyPanel'
import { DataSource } from '@/components/DataSource'
import {
  IndicatorsPanel,
  IndicatorsPanelSkeleton,
} from '@/components/IndicatorsPanel'
import { NewsPanel, NewsPanelSkeleton } from '@/components/NewsPanel'
import { QuoteHeader, QuoteHeaderSkeleton } from '@/components/QuoteHeader'
import {
  ResearchIntro,
  ResearchPanel,
  ResearchPanelSkeleton,
} from '@/components/ResearchPanel'
import { Button, Card, ErrorState, Skeleton } from '@/components/ui'
import { useAsyncData } from '@/hooks/useAsyncData'
import type {
  CompanyOverview,
  NewsFeed,
  PriceHistory,
  Quote,
  ResearchReport,
  TechnicalIndicators,
} from '@/types/api'

import styles from './Dashboard.module.css'

/**
 * Recharts is roughly 380 kB of the bundle and is only needed once a ticker has
 * been searched. Loading it lazily keeps the initial payload small, so the
 * landing page is interactive without downloading a charting library the user
 * may never reach.
 */
const PriceChart = lazy(() =>
  import('@/components/PriceChart').then((module) => ({
    default: module.PriceChart,
  })),
)

const DEFAULT_RANGE_DAYS = 365
const NEWS_LIMIT = 8

/** Reserves the chart's height so nothing shifts when the module resolves. */
function ChartFallback() {
  return (
    <div aria-busy="true" aria-label="Loading price chart">
      <Skeleton variant="block" height={320} />
    </div>
  )
}

/**
 * Renders one panel's three possible states in a consistent order.
 *
 * Every panel resolves independently, so a news outage or an exhausted quota on
 * one endpoint leaves the rest of the dashboard fully usable. Collapsing all
 * five requests into a single all-or-nothing fetch would mean one failing
 * provider call blanks the whole page.
 */
function PanelBody<T>({
  state,
  skeleton,
  children,
}: {
  state: { data: T | null; error: unknown; loading: boolean; reload: () => void }
  skeleton: ReactNode
  children: (data: T) => ReactNode
}) {
  if (state.loading && !state.data) return <>{skeleton}</>
  if (state.error) {
    return <ErrorState error={state.error} onRetry={state.reload} compact />
  }
  if (!state.data) return null
  return <>{children(state.data)}</>
}

interface DashboardProps {
  ticker: string
  /** Watchlist controls, injected so this component stays presentational. */
  watchlistAction?: ReactNode
}

export function Dashboard({ ticker, watchlistAction }: DashboardProps) {
  const [rangeDays, setRangeDays] = useState(DEFAULT_RANGE_DAYS)
  const [researchRequested, setResearchRequested] = useState(false)

  // Each fetcher is memoised on the values it closes over, so a re-render does
  // not look like a dependency change and refire the request.
  const quoteFetcher = useCallback(
    (signal: AbortSignal) => fetchQuote(ticker, { signal }),
    [ticker],
  )
  const historyFetcher = useCallback(
    (signal: AbortSignal) => fetchHistory(ticker, rangeDays, { signal }),
    [ticker, rangeDays],
  )
  const overviewFetcher = useCallback(
    (signal: AbortSignal) => fetchOverview(ticker, { signal }),
    [ticker],
  )
  const indicatorsFetcher = useCallback(
    (signal: AbortSignal) => fetchIndicators(ticker, 365, { signal }),
    [ticker],
  )
  const newsFetcher = useCallback(
    (signal: AbortSignal) => fetchNews(ticker, NEWS_LIMIT, { signal }),
    [ticker],
  )
  const researchFetcher = useCallback(
    (signal: AbortSignal) => generateResearch(ticker, false, { signal }),
    [ticker],
  )

  const quote = useAsyncData<Quote>(quoteFetcher, [ticker])
  const history = useAsyncData<PriceHistory>(historyFetcher, [ticker, rangeDays])
  const overview = useAsyncData<CompanyOverview>(overviewFetcher, [ticker])
  const indicators = useAsyncData<TechnicalIndicators>(indicatorsFetcher, [
    ticker,
  ])
  const news = useAsyncData<NewsFeed>(newsFetcher, [ticker])

  // Research is opt-in: each report is a billed model call, so it runs only
  // after the user asks for one.
  const research = useAsyncData<ResearchReport>(
    researchFetcher,
    [ticker, researchRequested],
    { enabled: researchRequested },
  )

  const currency = overview.data?.currency ?? null

  return (
    <div className={styles.dashboard}>
      <Card>
        <PanelBody state={quote} skeleton={<QuoteHeaderSkeleton />}>
          {(data) => (
            <QuoteHeader
              quote={data}
              overview={overview.data}
              actions={watchlistAction}
            />
          )}
        </PanelBody>
        {quote.data && (
          <div style={{ marginTop: 'var(--space-4)' }}>
            <DataSource
              source={quote.data.source}
              retrievedAt={quote.data.retrieved_at}
            />
          </div>
        )}
      </Card>

      <div className={styles.split}>
        <div className={styles.column}>
          <Card
            title="Price history"
            action={
              <Button size="sm" onClick={history.reload} loading={history.loading}>
                Refresh
              </Button>
            }
            footer={
              history.data ? (
                <DataSource
                  source={history.data.source}
                  retrievedAt={history.data.retrieved_at}
                  note="daily closing prices"
                />
              ) : undefined
            }
          >
            <PanelBody state={history} skeleton={<ChartFallback />}>
              {(data) => (
                <Suspense fallback={<ChartFallback />}>
                  <PriceChart
                    history={data}
                    currency={currency}
                    selectedRange={rangeDays}
                    onRangeChange={setRangeDays}
                    loading={history.loading}
                  />
                </Suspense>
              )}
            </PanelBody>
          </Card>

          <Card
            title="Recent news"
            footer={
              news.data ? (
                <DataSource
                  source={news.data.source}
                  retrievedAt={news.data.retrieved_at}
                />
              ) : undefined
            }
          >
            <PanelBody state={news} skeleton={<NewsPanelSkeleton />}>
              {(data) => <NewsPanel news={data} />}
            </PanelBody>
          </Card>
        </div>

        <div className={styles.column}>
          <Card
            title="Technical indicators"
            subtitle="Computed from this app's price history"
            footer={
              indicators.data ? (
                <DataSource
                  source={indicators.data.source}
                  retrievedAt={indicators.data.history_retrieved_at}
                  note={`${indicators.data.data_points_used} closes used`}
                />
              ) : undefined
            }
          >
            <PanelBody
              state={indicators}
              skeleton={<IndicatorsPanelSkeleton />}
            >
              {(data) => (
                <IndicatorsPanel indicators={data} currency={currency} />
              )}
            </PanelBody>
          </Card>

          <Card
            title="Company & fundamentals"
            footer={
              overview.data ? (
                <DataSource
                  source={overview.data.source}
                  retrievedAt={overview.data.retrieved_at}
                />
              ) : undefined
            }
          >
            <PanelBody state={overview} skeleton={<CompanyPanelSkeleton />}>
              {(data) => <CompanyPanel overview={data} />}
            </PanelBody>
          </Card>
        </div>
      </div>

      <Card
        title="AI research report"
        subtitle="Balanced interpretation of the data on this page"
        action={
          research.data ? (
            <Button size="sm" onClick={research.reload} loading={research.loading}>
              Regenerate
            </Button>
          ) : undefined
        }
      >
        {!researchRequested ? (
          <ResearchIntro
            symbol={ticker}
            loading={false}
            onGenerate={() => setResearchRequested(true)}
          />
        ) : (
          <PanelBody state={research} skeleton={<ResearchPanelSkeleton />}>
            {(data) => <ResearchPanel report={data} />}
          </PanelBody>
        )}
      </Card>
    </div>
  )
}
