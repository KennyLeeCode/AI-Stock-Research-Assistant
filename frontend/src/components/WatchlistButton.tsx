import { useState } from 'react'

import { ApiError } from '@/api/client'
import { Button } from '@/components/ui'
import { useWatchlist } from '@/hooks/useWatchlist'

function IconStar({ filled }: { filled: boolean }) {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m12 3.5 2.6 5.4 5.9.85-4.25 4.15 1 5.9L12 17l-5.25 2.8 1-5.9L3.5 9.75l5.9-.85z" />
    </svg>
  )
}

interface WatchlistButtonProps {
  ticker: string
}

/**
 * Toggles the current ticker in the watchlist.
 *
 * Failures are shown next to this button rather than as a page-level banner: a
 * user who clicked "Save" is looking here, and an error somewhere else on the
 * page is easy to miss entirely.
 */
export function WatchlistButton({ ticker }: WatchlistButtonProps) {
  const { isSaved, isPending, add, remove } = useWatchlist()
  const [error, setError] = useState<string | null>(null)

  const saved = isSaved(ticker)
  const pending = isPending(ticker)

  async function handleClick() {
    setError(null)
    try {
      if (saved) {
        await remove(ticker)
      } else {
        await add(ticker)
      }
    } catch (caught: unknown) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Could not update the watchlist.',
      )
    }
  }

  return (
    <div>
      <Button
        variant={saved ? 'secondary' : 'primary'}
        size="sm"
        onClick={handleClick}
        loading={pending}
        icon={<IconStar filled={saved} />}
        aria-pressed={saved}
      >
        {saved ? 'In watchlist' : 'Add to watchlist'}
      </Button>
      {error && (
        <p
          role="alert"
          style={{
            marginTop: 'var(--space-2)',
            fontSize: 'var(--text-xs)',
            color: 'var(--negative)',
          }}
        >
          {error}
        </p>
      )}
    </div>
  )
}
