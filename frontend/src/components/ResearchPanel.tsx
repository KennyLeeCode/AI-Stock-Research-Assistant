import { Badge, Button, Skeleton, SkeletonText } from '@/components/ui'
import type { ResearchReport } from '@/types/api'
import { formatDate, formatRelativeTime } from '@/utils/format'

import styles from './ResearchPanel.module.css'

function ProseSection({ title, body }: { title: string; body: string }) {
  return (
    <div className={styles.section}>
      <h3 className={styles.sectionTitle}>{title}</h3>
      <p className={styles.prose}>{body}</p>
    </div>
  )
}

function PointList({ points }: { points: string[] }) {
  return (
    <ul className={styles.points}>
      {points.map((point, index) => (
        <li key={index} className={styles.point}>
          <span className={styles.bullet} aria-hidden="true" />
          <span>{point}</span>
        </li>
      ))}
    </ul>
  )
}

interface ResearchPanelProps {
  report: ResearchReport
}

/**
 * A generated research report.
 *
 * The bull and bear cases are laid out side by side rather than stacked. That
 * is a deliberate editorial choice: presenting one above the other implies a
 * ranking, and the backend guarantees both are populated precisely so the
 * reader is shown a balanced view. The conclusion is styled as a summary of the
 * tension between them, not as a verdict.
 *
 * Nothing rendered here is a number the application treats as data - the
 * report contains prose only. Every figure on the dashboard comes from the
 * market-data panels.
 */
export function ResearchPanel({ report }: ResearchPanelProps) {
  return (
    <div className={styles.report}>
      <div className={styles.meta}>
        {report.cached && (
          <Badge tone="accent" srLabel="This report was served from cache">
            Cached
          </Badge>
        )}
        <span>
          Generated {formatRelativeTime(report.generated_at)} by {report.model}
        </span>
        {report.price_as_of && (
          <span>· Prices as of {formatDate(report.price_as_of)}</span>
        )}
      </div>

      <ProseSection title="Company summary" body={report.company_summary} />
      <ProseSection title="Recent performance" body={report.recent_performance} />
      <ProseSection title="Technical analysis" body={report.technical_analysis} />
      <ProseSection
        title="Fundamental analysis"
        body={report.fundamental_analysis}
      />

      <div className={styles.cases}>
        <div className={styles.caseCard}>
          <div className={`${styles.caseHeader} ${styles.bull}`}>
            <span aria-hidden="true">▲</span>
            <span>Bull case</span>
          </div>
          <PointList points={report.bull_case} />
        </div>

        <div className={styles.caseCard}>
          <div className={`${styles.caseHeader} ${styles.bear}`}>
            <span aria-hidden="true">▼</span>
            <span>Bear case</span>
          </div>
          <PointList points={report.bear_case} />
        </div>
      </div>

      <div className={styles.cases}>
        <div className={styles.caseCard}>
          <div className={styles.caseHeader}>
            <span>Risks</span>
          </div>
          <PointList points={report.risks} />
        </div>

        <div className={styles.caseCard}>
          <div className={styles.caseHeader}>
            <span>Catalysts</span>
          </div>
          <PointList points={report.catalysts} />
        </div>
      </div>

      <div className={styles.conclusion}>
        <div className={styles.conclusionTitle}>Neutral conclusion</div>
        <p className={styles.conclusionText}>{report.neutral_conclusion}</p>
      </div>

      <p className={styles.disclaimer}>{report.disclaimer}</p>

      {report.data_sources.length > 0 && (
        <div className={styles.meta}>
          <span>Built from:</span>
          {report.data_sources.map((source) => (
            <Badge key={source.dataset} tone="outline">
              {source.dataset} · {source.provider}
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}

interface ResearchIntroProps {
  symbol: string
  onGenerate: () => void
  loading: boolean
}

/**
 * Idle state shown before a report is requested.
 *
 * Generation is explicitly opt-in rather than automatic: each report is a
 * billed language-model call, so firing one on every search would spend money
 * the user did not ask to spend.
 */
export function ResearchIntro({
  symbol,
  onGenerate,
  loading,
}: ResearchIntroProps) {
  return (
    <div className={styles.intro}>
      <p className={styles.introText}>
        Generate a balanced research briefing for {symbol}. The report is written
        from the quote, price history, indicators, fundamentals, and headlines
        shown on this page - the model interprets that data and cannot introduce
        figures of its own.
      </p>
      <Button variant="primary" onClick={onGenerate} loading={loading}>
        {loading ? 'Generating report…' : 'Generate research report'}
      </Button>
    </div>
  )
}

/** Placeholder shaped like a finished report. */
export function ResearchPanelSkeleton() {
  return (
    <div
      className={styles.report}
      aria-busy="true"
      aria-label="Generating research report"
    >
      {Array.from({ length: 2 }, (_, index) => (
        <div key={index} className={styles.section}>
          <Skeleton variant="text" width={140} />
          <SkeletonText lines={3} />
        </div>
      ))}
      <div className={styles.cases}>
        {Array.from({ length: 2 }, (_, index) => (
          <div key={index} className={styles.caseCard}>
            <Skeleton variant="text" width={90} />
            <div style={{ height: 12 }} />
            <SkeletonText lines={3} />
          </div>
        ))}
      </div>
    </div>
  )
}
