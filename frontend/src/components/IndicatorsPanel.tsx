import { Metric, MetricGrid } from '@/components/Metric'
import { Badge, Skeleton } from '@/components/ui'
import type { TechnicalIndicators } from '@/types/api'
import {
  formatDate,
  formatDecimal,
  formatPercent,
  formatPrice,
  formatSignedPercent,
  rsiZone,
} from '@/utils/format'

interface IndicatorsPanelProps {
  indicators: TechnicalIndicators
  currency?: string | null
}

/**
 * Computed technical indicators.
 *
 * Any indicator the price history could not support is `null`, and the reason
 * comes from the backend's `unavailable` map - so a blank cell always carries a
 * specific explanation ("a 50-day average needs 50 closes; only 25 are
 * available") rather than leaving the reader to guess whether the figure is
 * missing, zero, or broken.
 */
export function IndicatorsPanel({
  indicators,
  currency,
}: IndicatorsPanelProps) {
  const zone = rsiZone(indicators.rsi_14)

  return (
    <div>
      <MetricGrid>
        <Metric
          label="SMA 20"
          value={formatPrice(indicators.sma_20, currency)}
          unavailableReason={indicators.unavailable.sma_20}
        />
        <Metric
          label="SMA 50"
          value={formatPrice(indicators.sma_50, currency)}
          unavailableReason={indicators.unavailable.sma_50}
        />
        <Metric
          label="RSI (14)"
          value={formatDecimal(indicators.rsi_14, 1)}
          hint={
            zone && zone !== 'neutral'
              ? // Context, never a recommendation. The conventional reading is
                // stated; what to do about it is left to the reader.
                `Conventionally ${zone}`
              : undefined
          }
          unavailableReason={indicators.unavailable.rsi_14}
        />
        <Metric
          label="Volatility (30d)"
          value={formatPercent(indicators.volatility_30d, 1)}
          hint="Annualized"
          unavailableReason={indicators.unavailable.volatility_30d}
        />
        <Metric
          label="1-month change"
          value={formatSignedPercent(indicators.price_change_1m)}
          unavailableReason={indicators.unavailable.price_change_1m}
        />
        <Metric
          label="3-month change"
          value={formatSignedPercent(indicators.price_change_3m)}
          unavailableReason={indicators.unavailable.price_change_3m}
        />
        <Metric
          label="52-week high"
          value={formatPrice(indicators.week_52_high, currency)}
          hint={
            indicators.week_52_high_date
              ? formatDate(indicators.week_52_high_date)
              : undefined
          }
          unavailableReason={indicators.unavailable.week_52_high}
        />
        <Metric
          label="52-week low"
          value={formatPrice(indicators.week_52_low, currency)}
          hint={
            indicators.week_52_low_date
              ? formatDate(indicators.week_52_low_date)
              : undefined
          }
          unavailableReason={indicators.unavailable.week_52_low}
        />
      </MetricGrid>

      {zone && zone !== 'neutral' && (
        <div style={{ marginTop: 'var(--space-4)' }}>
          <Badge
            tone={zone === 'overbought' ? 'warning' : 'accent'}
            srLabel={`RSI is in the conventionally ${zone} range`}
          >
            RSI {zone}
          </Badge>
        </div>
      )}
    </div>
  )
}

/** Placeholder matching the eight-metric grid. */
export function IndicatorsPanelSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading technical indicators">
      <MetricGrid>
        {Array.from({ length: 8 }, (_, index) => (
          <div key={index}>
            <Skeleton variant="text" width="60%" />
            <div style={{ height: 4 }} />
            <Skeleton variant="text" width="80%" />
          </div>
        ))}
      </MetricGrid>
    </div>
  )
}
