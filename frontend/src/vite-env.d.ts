/// <reference types="vite/client" />

/**
 * Typed environment variables.
 *
 * Only non-secret values belong here. Every `VITE_*` variable is inlined into
 * the public JavaScript bundle at build time and is readable by anyone who
 * opens devtools, so an API key placed here would be published, not hidden.
 * All third-party credentials stay on the backend.
 */
interface ImportMetaEnv {
  /** Backend origin. Empty in development so the Vite proxy handles `/api`. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
