import { useEffect, useState } from 'react'

/** Resolved token values the chart needs as concrete colours. */
export interface ThemeColors {
  accent: string
  positive: string
  negative: string
  neutral: string
  textSecondary: string
  textTertiary: string
  borderSubtle: string
  surface: string
}

const TOKEN_MAP: Record<keyof ThemeColors, string> = {
  accent: '--accent',
  positive: '--positive',
  negative: '--negative',
  neutral: '--neutral',
  textSecondary: '--text-secondary',
  textTertiary: '--text-tertiary',
  borderSubtle: '--border-subtle',
  surface: '--bg-surface',
}

/** Used before the DOM is available and if a token is somehow missing. */
const FALLBACKS: ThemeColors = {
  accent: '#4f8ef7',
  positive: '#3fb950',
  negative: '#f85149',
  neutral: '#8b949e',
  textSecondary: '#9aa3af',
  textTertiary: '#6b7480',
  borderSubtle: '#1f242e',
  surface: '#12151c',
}

function readColors(): ThemeColors {
  if (typeof window === 'undefined') return FALLBACKS

  const computed = getComputedStyle(document.documentElement)
  const entries = Object.entries(TOKEN_MAP) as Array<
    [keyof ThemeColors, string]
  >

  const resolved = {} as ThemeColors
  for (const [key, token] of entries) {
    const value = computed.getPropertyValue(token).trim()
    resolved[key] = value || FALLBACKS[key]
  }
  return resolved
}

/**
 * Resolves design tokens to concrete colour strings for Recharts.
 *
 * SVG presentation attributes do not reliably resolve `var()` across browsers,
 * so the chart cannot simply be handed `var(--accent)` the way ordinary CSS
 * can. Reading the computed values keeps the chart on the same palette as the
 * rest of the app instead of hard-coding a second set of colours that would
 * drift from the tokens.
 *
 * The initial read happens in a lazy `useState` initializer rather than an
 * effect, so the first paint already has the right colours and no extra render
 * pass is triggered.
 */
export function useThemeColors(): ThemeColors {
  const [colors, setColors] = useState<ThemeColors>(readColors)

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: light)')
    const handleChange = () => setColors(readColors())

    media.addEventListener('change', handleChange)

    // Also re-read if the theme is pinned via `data-theme` on <html>.
    const observer = new MutationObserver(handleChange)
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })

    return () => {
      media.removeEventListener('change', handleChange)
      observer.disconnect()
    }
  }, [])

  return colors
}
