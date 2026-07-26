import { useContext } from 'react'

import {
  WatchlistContext,
  type WatchlistContextValue,
} from '@/contexts/watchlist-context'

/**
 * Access the shared watchlist.
 *
 * Throws when used outside `WatchlistProvider` rather than returning a default.
 * A silent default would let a component render a permanently empty watchlist
 * whose add button appears to do nothing — a bug that is far harder to trace
 * than an immediate, explicit error.
 */
export function useWatchlist(): WatchlistContextValue {
  const context = useContext(WatchlistContext)
  if (context === null) {
    throw new Error('useWatchlist must be used inside a WatchlistProvider')
  }
  return context
}
