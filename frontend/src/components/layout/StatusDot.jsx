import { statusColors } from '../../utils/statusColor'
import './StatusDot.css'

/** A small colored dot plus optional label. The one place a status color is
 * actually rendered as a shape - everywhere else (pills, borders) reuses the
 * same statusColors() lookup so the vocabulary stays consistent. */
export function StatusDot({ status, label, pulse = false }) {
  const { fg } = statusColors(status)
  return (
    <span className="status-dot-group">
      <span
        className={`status-dot${pulse ? ' status-dot--pulse' : ''}`}
        style={{ '--dot-color': fg }}
        aria-hidden="true"
      />
      {label ? <span className="status-dot-label">{label}</span> : null}
    </span>
  )
}
