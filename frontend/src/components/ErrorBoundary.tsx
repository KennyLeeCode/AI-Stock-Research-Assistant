import { Component, type ErrorInfo, type ReactNode } from 'react'

import { Button } from '@/components/ui'

interface ErrorBoundaryProps {
  children: ReactNode
  /**
   * When any value here changes, the boundary clears its error and retries.
   * Pass the current ticker so navigating to a different company recovers from
   * a crash instead of leaving the user stuck on the fallback.
   */
  resetKeys?: readonly unknown[]
  /** Custom fallback. Receives the error and a reset callback. */
  fallback?: (error: Error, reset: () => void) => ReactNode
  /** Short label naming the area that failed, e.g. "dashboard". */
  label?: string
}

interface ErrorBoundaryState {
  error: Error | null
}

function keysChanged(
  previous: readonly unknown[] | undefined,
  next: readonly unknown[] | undefined,
): boolean {
  if (previous === next) return false
  if (!previous || !next) return true
  if (previous.length !== next.length) return true
  return previous.some((value, index) => !Object.is(value, next[index]))
}

/**
 * Catches render-time crashes and shows a recoverable fallback.
 *
 * This is the one thing hooks cannot do — React only reports render errors to
 * class components. Without a boundary, an exception thrown while rendering
 * unmounts the entire tree and leaves a blank white page with nothing but a
 * console message, which is the worst possible failure mode for a user.
 *
 * Note this catches *render* errors only. Failed network requests are already
 * handled by `useAsyncData` and rendered as `ErrorState`; a boundary would
 * never see those.
 */
export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidUpdate(previousProps: ErrorBoundaryProps): void {
    if (
      this.state.error !== null &&
      keysChanged(previousProps.resetKeys, this.props.resetKeys)
    ) {
      this.reset()
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Kept in the console rather than sent anywhere: this project has no error
    // reporting backend, and inventing one would be worse than being explicit
    // that crashes are local-only.
    console.error(
      `[ErrorBoundary${this.props.label ? `: ${this.props.label}` : ''}]`,
      error,
      info.componentStack,
    )
  }

  reset = (): void => {
    this.setState({ error: null })
  }

  render(): ReactNode {
    const { error } = this.state
    if (error === null) return this.props.children

    if (this.props.fallback) return this.props.fallback(error, this.reset)

    return (
      <div
        role="alert"
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 'var(--space-3)',
          padding: 'var(--space-10) var(--space-5)',
          textAlign: 'center',
        }}
      >
        <p
          style={{
            fontSize: 'var(--text-base)',
            fontWeight: 'var(--weight-semibold)',
          }}
        >
          Something broke while displaying this
        </p>
        <p
          style={{
            maxWidth: '44ch',
            fontSize: 'var(--text-sm)',
            color: 'var(--text-secondary)',
          }}
        >
          This is a bug in the application, not a problem with your search or
          your connection. Reloading usually clears it.
        </p>
        <p
          style={{
            maxWidth: '44ch',
            fontSize: 'var(--text-xs)',
            color: 'var(--text-tertiary)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {error.message}
        </p>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <Button variant="secondary" size="sm" onClick={this.reset}>
            Try again
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => window.location.reload()}
          >
            Reload page
          </Button>
        </div>
      </div>
    )
  }
}
