import type { ReactNode } from 'react'

import styles from './Card.module.css'

interface CardProps {
  /** Section label. Rendered uppercase; omit for a bare container. */
  title?: string
  /** Supporting line under the title - typically data provenance. */
  subtitle?: ReactNode
  /** Control aligned to the top-right, e.g. a refresh button. */
  action?: ReactNode
  /** Attribution strip along the bottom. */
  footer?: ReactNode
  /** Adds hover affordances. Use only when the whole card is clickable. */
  interactive?: boolean
  className?: string
  children: ReactNode
}

/**
 * The single surface primitive every dashboard panel is built from.
 *
 * Centralising the border, radius, padding, and header treatment here is what
 * makes ten different panels read as one designed product rather than ten
 * separately styled boxes.
 *
 * Renders as `<section>` with the title as its accessible name, so screen
 * reader users can navigate the dashboard by landmark.
 */
export function Card({
  title,
  subtitle,
  action,
  footer,
  interactive = false,
  className,
  children,
}: CardProps) {
  const classes = [styles.card, interactive ? styles.interactive : '', className]
    .filter(Boolean)
    .join(' ')

  return (
    <section className={classes} aria-label={title}>
      {(title || action) && (
        <header className={styles.header}>
          <div className={styles.headerText}>
            {title && <h2 className={styles.title}>{title}</h2>}
            {subtitle && <div className={styles.subtitle}>{subtitle}</div>}
          </div>
          {action && <div className={styles.action}>{action}</div>}
        </header>
      )}

      <div className={`${styles.body} ${title ? '' : styles.bodyOnly}`}>
        {children}
      </div>

      {footer && <footer className={styles.footer}>{footer}</footer>}
    </section>
  )
}
