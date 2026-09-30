// Single source of truth mapping a status word to its CSS custom properties,
// so every component that colors something by status (stat cards, disk rows,
// service rows, alert rows) stays visually consistent.

const STATUS_VARS = {
  ok: { fg: 'var(--status-ok)', bg: 'var(--status-ok-bg)' },
  normal: { fg: 'var(--status-ok)', bg: 'var(--status-ok-bg)' },
  warning: { fg: 'var(--status-warning)', bg: 'var(--status-warning-bg)' },
  critical: { fg: 'var(--status-critical)', bg: 'var(--status-critical-bg)' },
  unknown: { fg: 'var(--status-unknown)', bg: 'var(--status-unknown-bg)' },
}

export function statusColors(status) {
  return STATUS_VARS[status] ?? STATUS_VARS.unknown
}
