/**
 * Chart configuration.
 *
 * Kept out of the component file so `PriceChart.tsx` exports only a component,
 * which is what React Fast Refresh needs to hot-reload it reliably.
 */

export interface ChartRange {
  label: string
  days: number
}

export const CHART_RANGES: readonly ChartRange[] = [
  { label: '1M', days: 30 },
  { label: '3M', days: 91 },
  { label: '6M', days: 182 },
  { label: '1Y', days: 365 },
  { label: '5Y', days: 1825 },
] as const

export const DEFAULT_RANGE_DAYS = 365
