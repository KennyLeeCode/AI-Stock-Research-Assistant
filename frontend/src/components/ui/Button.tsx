import type { ButtonHTMLAttributes, ReactNode } from 'react'

import styles from './Button.module.css'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  /** Shows a spinner and disables interaction. */
  loading?: boolean
  fullWidth?: boolean
  /** Rendered before the label, e.g. a small icon. */
  icon?: ReactNode
  children?: ReactNode
}

/**
 * The application's only button.
 *
 * Loading state keeps the label mounted rather than swapping it for a spinner,
 * so the button does not change width mid-click and shove adjacent controls
 * sideways. `aria-busy` announces the state to assistive technology.
 */
export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  fullWidth = false,
  icon,
  children,
  className,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  const classes = [
    styles.button,
    styles[variant],
    styles[size],
    fullWidth ? styles.fullWidth : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      type={type}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span className={styles.spinner} aria-hidden="true" /> : icon}
      {children && (
        <span className={loading ? styles.loadingLabel : undefined}>
          {children}
        </span>
      )}
    </button>
  )
}
