import { useId, useState, type FormEvent } from 'react'

import { Button } from '@/components/ui'

import styles from './SearchBar.module.css'

/**
 * Mirrors the server's rule in `app/core/validation.py`.
 *
 * Client-side validation here is purely to give instant feedback and avoid a
 * pointless round trip - it is not a security control. The server validates
 * every symbol again regardless, because anything sent from a browser can be
 * forged.
 */
const TICKER_PATTERN = /^[A-Z0-9]{1,6}([.-][A-Z0-9]{1,4})?$/
const MAX_TICKER_LENGTH = 12

const SUGGESTIONS = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL'] as const

function validate(raw: string): string | null {
  const value = raw.trim().toUpperCase()
  if (!value) return 'Enter a ticker symbol to search.'
  if (value.length > MAX_TICKER_LENGTH) {
    return `Ticker symbols are at most ${MAX_TICKER_LENGTH} characters.`
  }
  if (!TICKER_PATTERN.test(value) || !/[A-Z]/.test(value)) {
    return `"${value}" is not a valid ticker symbol.`
  }
  return null
}

function IconSearch() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  )
}

interface SearchBarProps {
  /** Called with the normalized, validated symbol. */
  onSearch: (ticker: string) => void
  /** Disables input while a search is in flight. */
  loading?: boolean
  /** Prefills the field, e.g. when arriving from the watchlist. */
  initialValue?: string
}

export function SearchBar({
  onSearch,
  loading = false,
  initialValue = '',
}: SearchBarProps) {
  const [value, setValue] = useState(initialValue)
  const [error, setError] = useState<string | null>(null)
  const inputId = useId()
  const errorId = useId()

  function submit(raw: string) {
    const problem = validate(raw)
    if (problem) {
      setError(problem)
      return
    }
    setError(null)
    onSearch(raw.trim().toUpperCase())
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    submit(value)
  }

  function handleSuggestion(ticker: string) {
    setValue(ticker)
    setError(null)
    onSearch(ticker)
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} role="search">
      <label className="sr-only" htmlFor={inputId}>
        Ticker symbol
      </label>

      <div className={styles.row}>
        <div className={styles.inputWrap}>
          <span className={styles.icon}>
            <IconSearch />
          </span>
          <input
            id={inputId}
            className={`${styles.input} ${error ? styles.inputInvalid : ''}`}
            type="text"
            inputMode="text"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="characters"
            spellCheck={false}
            maxLength={MAX_TICKER_LENGTH}
            placeholder="Search a ticker, e.g. AAPL"
            value={value}
            disabled={loading}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : undefined}
            onChange={(event) => {
              setValue(event.target.value)
              // Clear the message as soon as the user starts correcting it;
              // leaving a stale error under a field they are actively fixing
              // reads as though the fix did not register.
              if (error) setError(null)
            }}
          />
        </div>

        <Button type="submit" variant="primary" size="lg" loading={loading}>
          Research
        </Button>
      </div>

      {error && (
        <p className={styles.error} id={errorId} role="alert">
          {error}
        </p>
      )}

      <div className={styles.suggestions}>
        <span>Try:</span>
        {SUGGESTIONS.map((ticker) => (
          <button
            key={ticker}
            type="button"
            className={styles.chip}
            onClick={() => handleSuggestion(ticker)}
            disabled={loading}
          >
            {ticker}
          </button>
        ))}
      </div>
    </form>
  )
}
