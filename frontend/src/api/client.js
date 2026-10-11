// Thin wrapper around fetch. All calls go to a relative /api/... path - the Vite
// dev server (and nginx in production) proxy that to the backend, so this file
// never needs to know a real backend origin or worry about CORS.

const BASE_PATH = '/api'

/** Mirrors the backend's {"error": {code, message, details}} envelope (see
 * backend/app/api/errors.py) so callers can branch on `code` if they need to. */
export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

async function request(path, signal) {
  let response
  try {
    response = await fetch(`${BASE_PATH}${path}`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal,
    })
  } catch (err) {
    if (signal?.aborted) throw err
    // fetch itself threw: network down, dev proxy target unreachable, etc. - not
    // an HTTP error response, so there's no envelope to parse.
    throw new ApiError(0, 'network_error', 'Could not reach the backend.')
  }

  if (!response.ok) {
    let body = null
    try {
      body = await response.json()
    } catch {
      // Response wasn't JSON (e.g. a proxy's own HTML error page) - fall through
      // to the generic message below.
    }
    const error = body?.error
    throw new ApiError(
      response.status,
      error?.code ?? 'unknown_error',
      error?.message ?? response.statusText ?? 'Request failed.',
      error?.details,
    )
  }

  return response.json()
}

function query(params) {
  const entries = Object.entries(params).filter(([, value]) => value !== undefined && value !== null)
  if (entries.length === 0) return ''
  return `?${new URLSearchParams(entries).toString()}`
}

export const api = {
  getHealth: (signal) => request('/health', signal),
  getSystem: (signal) => request('/system', signal),
  getCurrentMetrics: (signal) => request('/metrics/current', signal),
  getMetricsHistory: (minutes, signal) => request(`/metrics/history${query({ minutes })}`, signal),
  getProcesses: (limit, signal) => request(`/processes${query({ limit })}`, signal),
  getAlerts: (minutes, signal) => request(`/alerts${query({ minutes })}`, signal),
  getServices: (signal) => request('/services', signal),
}
