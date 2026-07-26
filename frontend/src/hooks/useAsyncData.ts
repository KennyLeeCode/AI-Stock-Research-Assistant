import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, toApiError } from '@/api/client'

export interface AsyncState<T> {
  data: T | null
  error: ApiError | null
  /** True while a request is in flight, including a manual reload. */
  loading: boolean
  /** Re-run the request, e.g. from a retry button. */
  reload: () => void
}

interface UseAsyncDataOptions {
  /**
   * When false, no request is made and the hook reports `loading: false` with
   * no data. Used for panels that should stay idle until a ticker is chosen.
   */
  enabled?: boolean
}

/**
 * Fetch-on-mount with cancellation, retry, and normalized errors.
 *
 * Every dashboard panel needs the same four things: run a request when its
 * inputs change, cancel the previous one so a slow response for an old ticker
 * cannot overwrite a newer one, expose a retry, and surface failures as
 * `ApiError`. Centralising that here keeps the panels declarative and means the
 * race-condition handling is written and reviewed once.
 *
 * The disabled state is *derived* rather than written into state by the effect.
 * Storing it would mean a synchronous `setState` during the effect body and an
 * extra render pass before paint; computing it at return time is both cheaper
 * and impossible to leave stale.
 *
 * @param fetcher Receives an `AbortSignal`; must pass it to the request.
 * @param deps Re-runs when these change, like a `useEffect` dependency array.
 */
export function useAsyncData<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
  options: UseAsyncDataOptions = {},
): AsyncState<T> {
  const { enabled = true } = options

  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [reloadToken, setReloadToken] = useState(0)

  // Held in a ref so changing the fetcher identity between renders does not
  // re-trigger the request. `deps` is the single source of truth for when to
  // re-run, which keeps the trigger explicit at the call site.
  const fetcherRef = useRef(fetcher)
  useEffect(() => {
    fetcherRef.current = fetcher
  }, [fetcher])

  useEffect(() => {
    if (!enabled) return

    const controller = new AbortController()
    let active = true

    fetcherRef
      .current(controller.signal)
      .then((result) => {
        // `active` guards against a resolved response arriving after this
        // effect was cleaned up — aborting alone does not stop an
        // already-settled promise from running its handler.
        if (!active) return
        setData(result)
        setError(null)
      })
      .catch((caught: unknown) => {
        if (!active) return
        const normalized = toApiError(caught)
        // A cancelled request is not a failure; a newer request superseded
        // this one and now owns the state.
        if (normalized.code === 'request_cancelled') return
        setData(null)
        setError(normalized)
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
      controller.abort()
    }
    // `fetcher` is intentionally excluded; it is read through a ref so that a
    // new function identity each render does not refire the request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, reloadToken])

  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    setReloadToken((token) => token + 1)
  }, [])

  if (!enabled) {
    return { data: null, error: null, loading: false, reload }
  }

  return { data, error, loading, reload }
}
