import { formatClockTime } from '../../utils/format'
import './ChartTooltip.css'

/** Recharts' default tooltip is a plain white box; this restyles it to match
 * the panel chrome and lets each chart supply its own value formatter. */
export function ChartTooltip({ active, payload, label, formatValue }) {
  if (!active || !payload?.length) return null

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-time">{formatClockTime(label)}</div>
      {payload.map((entry) => (
        <div className="chart-tooltip-row" key={entry.dataKey}>
          <span className="chart-tooltip-swatch" style={{ background: entry.color }} />
          <span className="chart-tooltip-name">{entry.name}</span>
          <span className="chart-tooltip-value num">{formatValue(entry.value)}</span>
        </div>
      ))}
    </div>
  )
}
