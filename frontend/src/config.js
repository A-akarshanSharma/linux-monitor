// Central place for the numbers that shape how the dashboard behaves, so they're
// easy to find and explain rather than scattered as magic numbers through hooks.

export const POLL_INTERVALS_MS = {
  system: 15_000, // hostname/OS/uptime - essentially static between polls
  currentMetrics: 10_000, // matches the backend's default polling_interval_seconds
  history: 15_000, // chart data; a bit slower than current so charts don't jitter
  processes: 10_000,
  alerts: 10_000, // worth checking a bit more eagerly - these are the "what's wrong" signal
  services: 15_000,
}

// How far back the history charts look. The backend clamps this to its own
// retention window (7 days by default), so a too-large value here just degrades
// gracefully to "everything there is" rather than erroring.
export const HISTORY_WINDOW_MINUTES = 30

export const PROCESS_LIST_LIMIT = 8

// Resolved alerts older than this aren't shown in the "recent alerts" feed.
// Active alerts are always shown by the backend regardless of age.
export const ALERTS_WINDOW_MINUTES = 1440
