import { useOnlineStatus } from '@/hooks/useOnlineStatus'

import styles from './OfflineBanner.module.css'

/**
 * Persistent notice shown while the browser reports no connection.
 *
 * `role="status"` with `aria-live="polite"` announces the change without
 * interrupting whatever a screen reader is currently reading - appearing and
 * disappearing as connectivity flaps would be intolerable with `alert`.
 */
export function OfflineBanner() {
  const online = useOnlineStatus()

  if (online) return null

  return (
    <div className={styles.banner} role="status" aria-live="polite">
      <span className={styles.dot} aria-hidden="true" />
      <span>
        You are offline. Data already loaded stays visible, but new searches
        will fail until the connection returns.
      </span>
    </div>
  )
}
