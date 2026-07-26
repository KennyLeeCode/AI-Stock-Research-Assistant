import { useEffect, useState } from 'react'

/**
 * Tracks browser connectivity.
 *
 * `navigator.onLine` is a weak signal — it reports whether the device has a
 * network interface, not whether the internet is reachable — so it is treated
 * as a hint, not a guarantee. It is reliable in one direction: when it reports
 * `false`, the device is definitely offline, and that is the case worth telling
 * the user about. A "you appear to be offline" banner is far more useful than
 * a generic request failure they cannot act on.
 *
 * The initial value is read in a lazy initializer rather than an effect, so the
 * first paint is already correct and no extra render is triggered.
 */
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState<boolean>(() =>
    typeof navigator === 'undefined' ? true : navigator.onLine,
  )

  useEffect(() => {
    const handleOnline = () => setOnline(true)
    const handleOffline = () => setOnline(false)

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  return online
}
