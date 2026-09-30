import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatClockTime } from '../../utils/format'
import { ChartTooltip } from './ChartTooltip'
import './chart-common.css'

const AXIS_TICK = { fontSize: 11, fill: 'var(--text-tertiary)' }

/** A single-series percentage-over-time chart (0-100). Shared by CPU and
 * memory - they differ only in which field and color they plot. */
export function MetricAreaChart({ data, dataKey, seriesName, color, formatValue }) {
  if (!data || data.length === 0) {
    return <div className="chart-empty">No history yet - check back in a few seconds.</div>
  }

  const gradientId = `metric-area-${dataKey}`

  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
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
            domain={[0, 100]}
            tickFormatter={(v) => `${v}%`}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
            width={36}
          />
          <Tooltip
            content={<ChartTooltip formatValue={formatValue} />}
            cursor={{ stroke: 'var(--border-strong)' }}
          />
          <Area
            type="monotone"
            dataKey={dataKey}
            name={seriesName}
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#${gradientId})`}
            isAnimationActive={false}
            dot={false}
            activeDot={{ r: 3 }}
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
