import type { ReactNode } from 'react'

import styles from './Badge.module.css'

type BadgeTone =
  | 'positive'
  | 'negative'
  | 'neutral'
  | 'accent'
  | 'warning'
  | 'outline'

interface BadgeProps {
  tone?: BadgeTone
  /** Text read by assistive technology instead of the visible label. */
  srLabel?: string
  className?: string
  children: ReactNode
}

/**
 * A small status pill.
 *
 * `srLabel` exists because badges are often terse to the point of being
 * meaningless out of context - "RSI 72" paired with an "overbought" tone reads
 * fine visually but tells a screen reader nothing about the tone. Colour is
 * never the sole carrier of meaning here.
 */
export function Badge({
  tone = 'neutral',
  srLabel,
  className,
  children,
}: BadgeProps) {
  const classes = [styles.badge, styles[tone], className]
    .filter(Boolean)
    .join(' ')

  return (
    <span className={classes}>
      {srLabel && <span className="sr-only">{srLabel}</span>}
      <span aria-hidden={srLabel ? true : undefined}>{children}</span>
    </span>
  )
}
