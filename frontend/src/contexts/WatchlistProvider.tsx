import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { ApiError, toApiError } from '@/api/client'
import {
  addToWatchlist,
  fetchWatchlist,
  removeFromWatchlist,
} from '@/api/endpoints'
import {
  WatchlistContext,
  type WatchlistContextValue,
} from '@/contexts/watchlist-context'
import type { WatchlistItem } from '@/types/api'

/**
 * Builds a placeholder entry shown while an add request is in flight.
 *
 * The id is negative so it can never collide with a real server-assigned id,
 * which is what lets the optimistic row be found and replaced (or removed)
 * once the request settles.
 */
function optimisticItem(ticker: string, notes: string | null): WatchlistItem {
  return {
    id: -Date.now(),
    ticker,
    company_name: null,
    notes,
    created_at: new Date().toISOString(),
  }
}

/**
 * Holds the watchlist and applies changes optimistically.
 *
 * Saving a ticker updates the UI immediately and reconciles with the server
 * response when it arrives; if the request fails, the change is rolled back and
 * the error is thrown to the caller so it can be shown next to the control the
 * user actually pressed. Waiting for a round trip before reflecting a click
 * makes the app feel broken on a slow connection, and silently swallowing the
 * failure would leave the UI claiming something was saved when it was not.
 */
export function WatchlistProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<WatchlistItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set())
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let active = true

    fetchWatchlist({ signal: controller.signal })
      .then((data) => {
        if (!active) return
        setItems(data)
        setError(null)
      })
      .catch((caught: unknown) => {
        if (!active) return
        const normalized = toApiError(caught)
        if (normalized.code === 'request_cancelled') return
        setError(normalized)
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [reloadToken])

  const markPending = useCallback((ticker: string, active: boolean) => {
    setPending((current) => {
      const next = new Set(current)
      if (active) next.add(ticker)
      else next.delete(ticker)
      return next
    })
  }, [])

  const add = useCallback(
    async (rawTicker: string, notes: string | null = null) => {
      const ticker = rawTicker.trim().toUpperCase()
      const placeholder = optimisticItem(ticker, notes)

      markPending(ticker, true)
      setItems((current) => [placeholder, ...current])

      try {
        const saved = await addToWatchlist(ticker, notes)
        // Swap the placeholder for the server's row, which carries the real id
        // and the resolved company name.
        setItems((current) =>
          current.map((item) => (item.id === placeholder.id ? saved : item)),
        )
      } catch (caught: unknown) {
        setItems((current) =>
          current.filter((item) => item.id !== placeholder.id),
        )
        throw toApiError(caught)
      } finally {
        markPending(ticker, false)
      }
    },
    [markPending],
  )

  const remove = useCallback(
    async (rawTicker: string) => {
      const ticker = rawTicker.trim().toUpperCase()
      let removed: WatchlistItem[] = []

      markPending(ticker, true)
      setItems((current) => {
        removed = current.filter((item) => item.ticker === ticker)
        return current.filter((item) => item.ticker !== ticker)
      })

      try {
        await removeFromWatchlist(ticker)
      } catch (caught: unknown) {
        // Put the rows back exactly where they were, ordered by creation date
        // so the list does not visibly reshuffle on a failed delete.
        setItems((current) =>
          [...current, ...removed].sort((a, b) =>
            b.created_at.localeCompare(a.created_at),
          ),
        )
        throw toApiError(caught)
      } finally {
        markPending(ticker, false)
      }
    },
    [markPending],
  )

  const isSaved = useCallback(
    (ticker: string) => {
      const symbol = ticker.trim().toUpperCase()
      return items.some((item) => item.ticker === symbol)
    },
    [items],
  )

  const isPending = useCallback(
    (ticker: string) => pending.has(ticker.trim().toUpperCase()),
    [pending],
  )

  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    setReloadToken((token) => token + 1)
  }, [])

  const value = useMemo<WatchlistContextValue>(
    () => ({ items, loading, error, isSaved, isPending, add, remove, reload }),
    [items, loading, error, isSaved, isPending, add, remove, reload],
  )

  return (
    <WatchlistContext.Provider value={value}>
      {children}
    </WatchlistContext.Provider>
  )
}
