import { statusColors } from '../../utils/statusColor'
import './StatCard.css'

export function StatCard({ label, value, detail, status = 'normal' }) {
  const { fg } = statusColors(status)
  return (
    <div className="stat-card" style={{ '--stat-color': fg }}>
      <span className="stat-card-label">{label}</span>
      <span className="stat-card-value num">{value}</span>
      {detail ? <span className="stat-card-detail">{detail}</span> : null}
    </div>
  )
}
