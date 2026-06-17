/* In desktop mode prefer the backend URL injected by preload; in browser dev mode use the same host as the frontend. */
const browserBackendUrl =
  typeof window !== 'undefined' && window.location.hostname
    ? `${window.location.protocol}//${window.location.hostname}:9000`
    : 'http://127.0.0.1:9000'

export const backendBaseUrl = (
  window.ocDesktop?.config.backendUrl ||
  import.meta.env.VITE_BACKEND_URL ||
  browserBackendUrl
).replace(/\/$/, '')

/**
 * Unified helper for requesting backend JSON endpoints.
 *
 * Args:
 *   path: A backend path starting with `/api`.
 *   init: The fetch request config.
 *
 * Returns:
 *   The deserialized response body.
 *
 * Throws:
 *   Error: Thrown when the backend returns a non-2xx status.
 */
export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${backendBaseUrl}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  // 204 No Content (e.g. DELETE) has no response body, and parsing JSON directly would throw.
  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
