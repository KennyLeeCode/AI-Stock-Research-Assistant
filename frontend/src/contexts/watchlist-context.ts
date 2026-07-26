import { createContext } from 'react'

import type { ApiError } from '@/api/client'
import type { WatchlistItem } from '@/types/api'

export interface WatchlistContextValue {
  items: WatchlistItem[]
  /** True during the initial load only, not during add/remove. */
  loading: boolean
  /** Failure of the initial load. Mutation errors are thrown to the caller. */
  error: ApiError | null
  /** Whether a symbol is currently saved. */
  isSaved: (ticker: string) => boolean
  /** Whether a symbol has an add or remove request in flight. */
  isPending: (ticker: string) => boolean
  /** Adds a symbol. Throws `ApiError` on failure after rolling back. */
  add: (ticker: string, notes?: string | null) => Promise<void>
  /** Removes a symbol. Throws `ApiError` on failure after rolling back. */
  remove: (ticker: string) => Promise<void>
  /** Re-fetches the list. */
  reload: () => void
}

/**
 * Watchlist state, shared between the sidebar and the save button in the quote
 * header. Both must reflect the same list instantly — saving from the header
 * has to appear in the sidebar without a refetch — which is what makes this
 * shared rather than local state.
 *
 * The context object lives in its own module so `WatchlistProvider.tsx` exports
 * only a component, which is what React Fast Refresh needs to hot-reload it.
 */
export const WatchlistContext = createContext<WatchlistContextValue | null>(
  null,
)
