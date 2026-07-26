import { useState } from 'react'

import { Metric, MetricGrid } from '@/components/Metric'
import { Badge, Skeleton, SkeletonText } from '@/components/ui'
import type { CompanyOverview } from '@/types/api'
import {
  formatCompact,
  formatDecimal,
  formatFractionAsPercent,
  formatPrice,
} from '@/utils/format'

import styles from './CompanyPanel.module.css'

const DESCRIPTION_CLAMP_THRESHOLD = 320

interface CompanyPanelProps {
  overview: CompanyOverview
}

/**
 * Company profile and reported fundamentals.
 *
 * Note the two different percentage formatters. The backend returns margins and
 * dividend yield as *fractions* (0.25 means 25%) but price changes as
 * *percentages* (1.25 means 1.25%). Using the wrong one would misreport a
 * figure by a factor of one hundred, so the distinction is explicit in the
 * formatter names rather than left to the caller to remember.
 */
export function CompanyPanel({ overview }: CompanyPanelProps) {
  const [expanded, setExpanded] = useState(false)

  const currency = overview.currency
  const description = overview.description
  const needsClamp =
    description !== null && description.length > DESCRIPTION_CLAMP_THRESHOLD

  return (
    <div>
      {description && (
        <div>
          <p
            className={`${styles.description} ${
              needsClamp && !expanded ? styles.clamped : ''
            }`}
          >
            {description}
          </p>
          {needsClamp && (
            <button
              type="button"
              className={styles.toggle}
              onClick={() => setExpanded((current) => !current)}
              aria-expanded={expanded}
            >
              {expanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </div>
      )}

      <div className={styles.tags} style={{ marginTop: 'var(--space-4)' }}>
        {overview.industry && <Badge tone="outline">{overview.industry}</Badge>}
        {overview.country && <Badge tone="outline">{overview.country}</Badge>}
        {overview.currency && <Badge tone="outline">{overview.currency}</Badge>}
      </div>

      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>Valuation</h3>
        <MetricGrid>
          <Metric label="Market cap" value={formatCompact(overview.market_cap)} />
          <Metric label="P/E ratio" value={formatDecimal(overview.pe_ratio)} />
          <Metric label="Forward P/E" value={formatDecimal(overview.forward_pe)} />
          <Metric label="PEG ratio" value={formatDecimal(overview.peg_ratio)} />
          <Metric
            label="Price / book"
            value={formatDecimal(overview.price_to_book)}
          />
          <Metric
            label="Book value"
            value={formatPrice(overview.book_value, currency)}
          />
        </MetricGrid>
      </div>

      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>Profitability</h3>
        <MetricGrid>
          <Metric label="EPS" value={formatPrice(overview.eps, currency)} />
          <Metric
            label="Profit margin"
            value={formatFractionAsPercent(overview.profit_margin)}
          />
          <Metric
            label="Operating margin"
            value={formatFractionAsPercent(overview.operating_margin)}
          />
          <Metric
            label="Return on equity"
            value={formatFractionAsPercent(overview.return_on_equity)}
          />
          <Metric
            label="Return on assets"
            value={formatFractionAsPercent(overview.return_on_assets)}
          />
          <Metric label="EBITDA" value={formatCompact(overview.ebitda)} />
        </MetricGrid>
      </div>

      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>Scale, dividend and risk</h3>
        <MetricGrid>
          <Metric
            label="Revenue (TTM)"
            value={formatCompact(overview.revenue_ttm)}
          />
          <Metric
            label="Gross profit (TTM)"
            value={formatCompact(overview.gross_profit_ttm)}
          />
          <Metric
            label="Shares outstanding"
            value={formatCompact(overview.shares_outstanding)}
          />
          <Metric
            label="Dividend yield"
            value={formatFractionAsPercent(overview.dividend_yield)}
          />
          <Metric
            label="Dividend / share"
            value={formatPrice(overview.dividend_per_share, currency)}
          />
          <Metric label="Beta" value={formatDecimal(overview.beta)} />
        </MetricGrid>
      </div>
    </div>
  )
}

/** Placeholder mirroring the description and three metric sections. */
export function CompanyPanelSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading company information">
      <SkeletonText lines={4} />
      <div className={styles.section}>
        <MetricGrid>
          {Array.from({ length: 6 }, (_, index) => (
            <div key={index}>
              <Skeleton variant="text" width="60%" />
              <div style={{ height: 4 }} />
              <Skeleton variant="text" width="80%" />
            </div>
          ))}
        </MetricGrid>
      </div>
    </div>
  )
}
