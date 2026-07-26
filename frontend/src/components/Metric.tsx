import type { ReactNode } from 'react'

import { EM_DASH, directionLabel, directionOf } from '@/utils/format'

import styles from './Metric.module.css'

interface MetricProps {
  label: string
  /** Pre-formatted display value. Pass `EM_DASH` for absent data. */
  value: string
  /** Larger treatment, for the one or two headline figures on a panel. */
  size?: 'default' | 'large'
  /** Supporting line under the value, e.g. a date. */
  hint?: string
  /**
   * Why this metric is unavailable. Rendered as a hover/focus explanation on
   * the label. Supplied from the backend's `unavailable` map, so the user sees
   * a specific reason rather than an unexplained dash.
   */
  unavailableReason?: string
}

/**
 * One labelled figure.
 *
 * A value equal to the em dash is styled as absent — dimmer and lighter weight
 * — so a missing metric visually reads as missing rather than as a number the
 * reader should try to interpret.
 */
export function Metric({
  label,
  value,
  size = 'default',
  hint,
  unavailableReason,
}: MetricProps) {
  const isAbsent = value === EM_DASH

  return (
    <div className={styles.metric}>
      <div className={styles.label}>
        <span>{label}</span>
        {isAbsent && unavailableReason && (
          <span
            className={styles.info}
            title={unavailableReason}
            aria-label={`${label} unavailable: ${unavailableReason}`}
            role="img"
          >
            ?
          </span>
        )}
      </div>
      <div
        className={[
          styles.value,
          size === 'large' ? styles.valueLarge : '',
          isAbsent ? styles.absent : '',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        {value}
      </div>
      {hint && <div className={styles.hint}>{hint}</div>}
    </div>
  )
}

interface ChangeValueProps {
  /** Absolute change. Pass null when unavailable. */
  change: number | null | undefined
  /** Percentage change, already scaled (1.25 means 1.25%). */
  changePercent: number | null | undefined
  /** Pre-formatted absolute change. */
  formattedChange: string
  /** Pre-formatted percentage. */
  formattedPercent: string
  size?: 'default' | 'large'
}

/**
 * A price change with direction conveyed three ways.
 *
 * Colour alone is not enough: roughly 8% of men have red-green colour blindness,
 * and colour carries nothing at all to a screen reader. Every change therefore
 * also has an explicit sign, an arrow glyph, and a visually hidden word.
 */
export function ChangeValue({
  change,
  changePercent,
  formattedChange,
  formattedPercent,
  size = 'default',
}: ChangeValueProps) {
  // Prefer the percentage for direction; fall back to the absolute change.
  const direction = directionOf(changePercent ?? change)
  const arrow =
    direction === 'positive' ? '▲' : direction === 'negative' ? '▼' : '–'

  return (
    <span
      className={[
        styles.change,
        styles[direction],
        size === 'large' ? styles.valueLarge : styles.value,
      ].join(' ')}
    >
      <span className={styles.arrow} aria-hidden="true">
        {arrow}
      </span>
      <span className="sr-only">{directionLabel(direction)} </span>
      <span>{formattedChange}</span>
      <span>({formattedPercent})</span>
    </span>
  )
}

interface MetricGridProps {
  children: ReactNode
}

/** Responsive grid that fits as many metric columns as the width allows. */
export function MetricGrid({ children }: MetricGridProps) {
  return <div className={styles.grid}>{children}</div>
}
