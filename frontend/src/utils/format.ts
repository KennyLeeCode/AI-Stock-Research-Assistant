/**
 * Display formatters.
 *
 * The single most important rule in this file: **`null` renders as an em dash,
 * never as `0`.** The backend is careful to distinguish "the provider had no
 * value" from "the value is zero", and that distinction is worthless if the UI
 * collapses it at the last step. A company with negative earnings has no P/E
 * ratio; printing `0.00` there would be a fabricated figure.
 *
 * Every function here therefore takes `number | null | undefined` and returns
 * `EM_DASH` for absent input.
 */

/** Shown wherever a value is genuinely unavailable. */
export const EM_DASH = '—'

/** Locale used for all number and date formatting. */
const LOCALE = 'en-US'

function isAbsent(value: number | null | undefined): value is null | undefined {
  return value === null || value === undefined || Number.isNaN(value)
}

/* ==========================================================================
   Numbers
   ========================================================================== */

/** A price, e.g. `186.40`. */
export function formatPrice(
  value: number | null | undefined,
  currency?: string | null,
): string {
  if (isAbsent(value)) return EM_DASH

  // Sub-dollar instruments need more precision than two decimals to be useful.
  const decimals = Math.abs(value) < 1 ? 4 : 2
  const formatted = value.toLocaleString(LOCALE, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
  return currency ? `${formatted} ${currency}` : formatted
}

/** A percentage from an already-scaled value: `1.25` renders as `1.25%`. */
export function formatPercent(
  value: number | null | undefined,
  decimals = 2,
): string {
  if (isAbsent(value)) return EM_DASH
  return `${value.toFixed(decimals)}%`
}

/** A percentage with an explicit sign, e.g. `+1.25%`. */
export function formatSignedPercent(
  value: number | null | undefined,
  decimals = 2,
): string {
  if (isAbsent(value)) return EM_DASH
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(decimals)}%`
}

/** A signed absolute change, e.g. `+1.50`. */
export function formatSignedNumber(
  value: number | null | undefined,
  decimals = 2,
): string {
  if (isAbsent(value)) return EM_DASH
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(decimals)}`
}

/**
 * A fraction rendered as a percentage: `0.0044` becomes `0.44%`.
 *
 * Kept separate from `formatPercent` on purpose. The backend returns margins
 * and dividend yields as fractions but price changes as percentages, and
 * confusing the two would misreport a figure by a factor of 100.
 */
export function formatFractionAsPercent(
  value: number | null | undefined,
  decimals = 2,
): string {
  if (isAbsent(value)) return EM_DASH
  return `${(value * 100).toFixed(decimals)}%`
}

/** A large number in compact form: `2900000000000` becomes `2.90T`. */
export function formatCompact(value: number | null | undefined): string {
  if (isAbsent(value)) return EM_DASH

  const abs = Math.abs(value)
  const sign = value < 0 ? '-' : ''

  const units: Array<[number, string]> = [
    [1e12, 'T'],
    [1e9, 'B'],
    [1e6, 'M'],
    [1e3, 'K'],
  ]

  for (const [threshold, suffix] of units) {
    if (abs >= threshold) {
      return `${sign}${(abs / threshold).toFixed(2)}${suffix}`
    }
  }
  return `${sign}${abs.toLocaleString(LOCALE)}`
}

/** An integer with thousands separators. */
export function formatInteger(value: number | null | undefined): string {
  if (isAbsent(value)) return EM_DASH
  return Math.round(value).toLocaleString(LOCALE)
}

/** A plain decimal, e.g. a P/E ratio or beta. */
export function formatDecimal(
  value: number | null | undefined,
  decimals = 2,
): string {
  if (isAbsent(value)) return EM_DASH
  return value.toFixed(decimals)
}

/* ==========================================================================
   Dates
   ========================================================================== */

function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

/** `2026-07-24` becomes `Jul 24, 2026`. */
export function formatDate(value: string | null | undefined): string {
  const date = parseDate(value)
  if (!date) return EM_DASH
  return date.toLocaleDateString(LOCALE, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/** Date plus time, for "as of" attribution. */
export function formatDateTime(value: string | null | undefined): string {
  const date = parseDate(value)
  if (!date) return EM_DASH
  return date.toLocaleString(LOCALE, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

/** `2 hours ago`, `just now`, `3 days ago`. Falls back to a date past a week. */
export function formatRelativeTime(value: string | null | undefined): string {
  const date = parseDate(value)
  if (!date) return EM_DASH

  const seconds = Math.round((Date.now() - date.getTime()) / 1000)

  if (seconds < 0) return formatDate(value)
  if (seconds < 45) return 'just now'

  const formatter = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' })
  const divisions: Array<[number, Intl.RelativeTimeFormatUnit]> = [
    [60, 'second'],
    [3600, 'minute'],
    [86400, 'hour'],
    [604800, 'day'],
  ]

  let previous = 1
  for (const [limit, unit] of divisions) {
    if (seconds < limit) {
      return formatter.format(-Math.round(seconds / previous), unit)
    }
    previous = limit
  }
  return formatDate(value)
}

/* ==========================================================================
   Semantics
   ========================================================================== */

/** Direction of a change, for choosing colour and an accessible label. */
export type Direction = 'positive' | 'negative' | 'neutral'

export function directionOf(value: number | null | undefined): Direction {
  if (isAbsent(value) || value === 0) return 'neutral'
  return value > 0 ? 'positive' : 'negative'
}

/**
 * Text describing a direction, for screen readers.
 *
 * Colour and an arrow convey direction visually. Neither is available to a
 * screen reader, so this is rendered into a visually hidden element.
 */
export function directionLabel(direction: Direction): string {
  switch (direction) {
    case 'positive':
      return 'up'
    case 'negative':
      return 'down'
    case 'neutral':
      return 'unchanged'
  }
}

/** Conventional RSI reading. Context only — never presented as a signal to act. */
export function rsiZone(
  value: number | null | undefined,
): 'overbought' | 'oversold' | 'neutral' | null {
  if (isAbsent(value)) return null
  if (value >= 70) return 'overbought'
  if (value <= 30) return 'oversold'
  return 'neutral'
}
