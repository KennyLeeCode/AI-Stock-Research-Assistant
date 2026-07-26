import { useMemo } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { CHART_RANGES } from '@/constants/chart'
import { useThemeColors } from '@/hooks/useThemeColors'
import type { PriceHistory } from '@/types/api'
import {
  formatCompact,
  formatDate,
  formatPrice,
  formatSignedPercent,
} from '@/utils/format'

import styles from './PriceChart.module.css'

interface ChartDatum {
  date: string
  close: number
  volume: number | null
  /** Milliseconds, used for a proportional time axis. */
  timestamp: number
}

interface TooltipPayloadEntry {
  payload: ChartDatum
}

interface ChartTooltipProps {
  active?: boolean
  payload?: TooltipPayloadEntry[]
  currency?: string | null
}

function ChartTooltip({ active, payload, currency }: ChartTooltipProps) {
  const entry = payload?.[0]?.payload
  if (!active || !entry) return null

  return (
    <div className={styles.tooltip}>
      <div className={styles.tooltipDate}>{formatDate(entry.date)}</div>
      <div className={styles.tooltipPrice}>
        {formatPrice(entry.close, currency)}
      </div>
      {entry.volume !== null && (
        <div className={styles.tooltipRow}>
          <span>Volume</span>
          <span>{formatCompact(entry.volume)}</span>
        </div>
      )}
    </div>
  )
}

interface PriceChartProps {
  history: PriceHistory
  currency?: string | null
  selectedRange: number
  onRangeChange: (days: number) => void
  /** Disables the range buttons while a new range is loading. */
  loading?: boolean
}

/**
 * Closing-price chart with a range selector.
 *
 * Line colour follows the period's direction — green if the security is up over
 * the window, red if down — which is a convention readers already understand.
 * The Y axis is deliberately *not* zero-based: equity prices rarely approach
 * zero, and anchoring the axis there would flatten every series into a
 * meaningless straight line.
 */
export function PriceChart({
  history,
  currency,
  selectedRange,
  onRangeChange,
  loading = false,
}: PriceChartProps) {
  const colors = useThemeColors()

  const data = useMemo<ChartDatum[]>(
    () =>
      history.points.map((point) => ({
        date: point.date,
        close: point.close,
        volume: point.volume,
        timestamp: new Date(point.date).getTime(),
      })),
    [history.points],
  )

  const first = data[0]
  const last = data[data.length - 1]

  const periodChange =
    first && last && first.close !== 0
      ? ((last.close - first.close) / first.close) * 100
      : null

  const isPositive = (periodChange ?? 0) >= 0
  const lineColor = isPositive ? colors.positive : colors.negative

  // Pad the domain by 4% so the series never touches the panel edges.
  const closes = data.map((point) => point.close)
  const min = closes.length ? Math.min(...closes) : 0
  const max = closes.length ? Math.max(...closes) : 0
  const padding = (max - min) * 0.04 || max * 0.04 || 1

  const gradientId = `price-gradient-${history.symbol}`

  return (
    <div className={styles.wrapper}>
      <div className={styles.controls}>
        <div className={styles.summary}>
          <span style={{ color: lineColor, fontWeight: 600 }}>
            {formatSignedPercent(periodChange)}
          </span>
          <span style={{ color: colors.textTertiary }}>
            over {data.length} trading {data.length === 1 ? 'day' : 'days'}
          </span>
        </div>

        <div
          className={styles.ranges}
          role="group"
          aria-label="Chart time range"
        >
          {CHART_RANGES.map((range) => {
            const active = range.days === selectedRange
            return (
              <button
                key={range.label}
                type="button"
                className={`${styles.range} ${active ? styles.rangeActive : ''}`}
                onClick={() => onRangeChange(range.days)}
                disabled={loading}
                aria-pressed={active}
              >
                {range.label}
              </button>
            )
          })}
        </div>
      </div>

      <div className={styles.chart}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
          >
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={lineColor} stopOpacity={0.22} />
                <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
              </linearGradient>
            </defs>

            <CartesianGrid
              strokeDasharray="3 3"
              stroke={colors.borderSubtle}
              vertical={false}
            />

            <XAxis
              dataKey="timestamp"
              type="number"
              scale="time"
              domain={['dataMin', 'dataMax']}
              tickFormatter={(value: number) =>
                new Date(value).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                })
              }
              stroke={colors.textTertiary}
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: colors.borderSubtle }}
              minTickGap={40}
            />

            <YAxis
              domain={[min - padding, max + padding]}
              tickFormatter={(value: number) => value.toFixed(0)}
              stroke={colors.textTertiary}
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={52}
              orientation="right"
            />

            <Tooltip
              content={<ChartTooltip currency={currency} />}
              cursor={{ stroke: colors.textTertiary, strokeDasharray: '3 3' }}
            />

            <Area
              type="monotone"
              dataKey="close"
              stroke={lineColor}
              strokeWidth={2}
              fill={`url(#${gradientId})`}
              // A dot per point turns a 1250-day series into visual noise; the
              // tooltip cursor already indicates the hovered observation.
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0, fill: lineColor }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
