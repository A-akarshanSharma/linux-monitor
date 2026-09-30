// Formatting helpers shared across the dashboard. Kept dependency-free (no
// date/number-formatting library) since the formats needed are all simple.

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']

/** 1536 -> "1.5 KB". Binary (1024-based), matching `df`/`free` convention on Linux. */
export function formatBytes(bytes, { decimals = 1 } = {}) {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return '—'
  if (bytes === 0) return '0 B'
  const exponent = Math.min(
    Math.floor(Math.log(Math.abs(bytes)) / Math.log(1024)),
    BYTE_UNITS.length - 1,
  )
  const value = bytes / 1024 ** exponent
  return `${value.toFixed(exponent === 0 ? 0 : decimals)} ${BYTE_UNITS[exponent]}`
}

/** 1536 -> "1.5 KB/s". null (no rate sampled yet) -> "—". */
export function formatRate(bytesPerSecond) {
  if (bytesPerSecond === null || bytesPerSecond === undefined) return '—'
  return `${formatBytes(bytesPerSecond)}/s`
}

/** 42.53 -> "42.5%" */
export function formatPercent(value, { decimals = 1 } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${value.toFixed(decimals)}%`
}

/** 93784 (seconds) -> "1d 2h 3m" */
export function formatUptime(totalSeconds) {
  if (totalSeconds === null || totalSeconds === undefined) return '—'
  const totalMinutes = Math.floor(totalSeconds / 60)
  const days = Math.floor(totalMinutes / (60 * 24))
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60)
  const minutes = totalMinutes % 60

  if (days > 0) return `${days}d ${hours}h ${minutes}m`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

/** ISO timestamp -> "12s ago" / "3m ago" / "just now" */
export function formatRelativeTime(isoString, now = Date.now()) {
  if (!isoString) return '—'
  const then = new Date(isoString).getTime()
  const diffSeconds = Math.max(0, Math.round((now - then) / 1000))

  if (diffSeconds < 5) return 'just now'
  if (diffSeconds < 60) return `${diffSeconds}s ago`
  const diffMinutes = Math.round(diffSeconds / 60)
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  const diffHours = Math.round(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  return `${Math.round(diffHours / 24)}d ago`
}

/** ISO timestamp -> "14:32:05" for chart axes and tooltips. */
export function formatClockTime(isoString) {
  if (!isoString) return '—'
  return new Date(isoString).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** ISO timestamp -> "Jan 15, 14:32:05" for places that need the full moment. */
export function formatDateTime(isoString) {
  if (!isoString) return '—'
  const date = new Date(isoString)
  return `${date.toLocaleDateString([], { month: 'short', day: 'numeric' })}, ${formatClockTime(isoString)}`
}
