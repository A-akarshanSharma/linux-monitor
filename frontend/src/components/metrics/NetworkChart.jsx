import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatClockTime, formatRate } from '../../utils/format'
import { ChartTooltip } from './ChartTooltip'
import './chart-common.css'

const AXIS_TICK = { fontSize: 11, fill: 'var(--text-tertiary)' }
const SEND_COLOR = '#4fd1c5' // --accent
const RECV_COLOR = '#a5d6ff' // a cooler, distinct blue - "incoming" reads as the cooler tone

export function NetworkChart({ data }) {
  if (!data || data.length === 0) {
    return <div className="chart-empty">No history yet - check back in a few seconds.</div>
  }

  return (
    <>
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="collected_at"
              tickFormatter={formatClockTime}
              tick={AXIS_TICK}
              axisLine={{ stroke: 'var(--border)' }}
              tickLine={false}
              minTickGap={48}
            />
            <YAxis
              tickFormatter={(v) => formatRate(v)}
              tick={AXIS_TICK}
              axisLine={false}
              tickLine={false}
              width={64}
            />
            <Tooltip content={<ChartTooltip formatValue={formatRate} />} cursor={{ stroke: 'var(--border-strong)' }} />
            <Line
              type="monotone"
              dataKey="send_rate_bytes_per_sec"
              name="sent"
              stroke={SEND_COLOR}
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3 }}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="recv_rate_bytes_per_sec"
              name="received"
              stroke={RECV_COLOR}
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3 }}
              isAnimationActive={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-legend">
        <span className="chart-legend-item">
          <span className="chart-legend-swatch" style={{ background: SEND_COLOR }} />
          sent
        </span>
        <span className="chart-legend-item">
          <span className="chart-legend-swatch" style={{ background: RECV_COLOR }} />
          received
        </span>
      </div>
    </>
  )
}
