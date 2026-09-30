import { useCurrentMetrics } from '../../hooks/useCurrentMetrics'
import { useMetricsHistory } from '../../hooks/useMetricsHistory'
import { HISTORY_WINDOW_MINUTES } from '../../config'
import { formatPercent, formatRate } from '../../utils/format'
import { severityFor } from '../../utils/alerts'
import { Panel } from '../layout/Panel'
import { StatCard } from './StatCard'
import { DiskUsageList } from './DiskUsageList'
import { MetricAreaChart } from './MetricAreaChart'
import { NetworkChart } from './NetworkChart'
import './MetricsOverview.css'

// Plain hex rather than CSS custom properties: these become raw SVG stroke/fill
// attributes inside recharts, which is a context where var() resolution isn't
// worth the risk. Kept close to the palette in index.css - --accent and a
// violet clearly distinct from every status color.
const CPU_COLOR = '#4fd1c5'
const MEMORY_COLOR = '#a78bfa'

export function MetricsOverview({ alerts }) {
  const current = useCurrentMetrics()
  const history = useMetricsHistory()

  const snapshot = current.data
  const points = history.data?.points

  return (
    <>
      <Panel
        title="Current usage"
        isLoading={current.isLoading}
        error={current.error}
        lastUpdated={current.lastUpdated}
        hasData={!!snapshot}
      >
        {snapshot ? (
          <>
            <div className="stat-grid">
              <StatCard
                label="CPU"
                value={formatPercent(snapshot.cpu.utilization_percent)}
                detail={`load avg ${snapshot.cpu.load_avg_1m.toFixed(2)} · ${snapshot.cpu.logical_cores} cores`}
                status={severityFor(alerts, 'cpu')}
              />
              <StatCard
                label="Memory"
                value={formatPercent(snapshot.memory.ram_percent)}
                detail={`${formatPercent(snapshot.memory.ram_percent, { decimals: 0 })} of installed RAM`}
                status={severityFor(alerts, 'memory')}
              />
              <StatCard
                label="Swap"
                value={formatPercent(snapshot.memory.swap_percent)}
                detail={
                  snapshot.memory.swap_total_bytes > 0 ? 'in use' : 'no swap configured'
                }
                status="normal"
              />
              <StatCard
                label="Network"
                value={formatRate(snapshot.network.send_rate_bytes_per_sec)}
                detail={`↓ ${formatRate(snapshot.network.recv_rate_bytes_per_sec)}`}
                status="normal"
              />
            </div>
            <div className="panel-divider" />
            <h3 className="subsection-title">Disks</h3>
            <DiskUsageList disks={snapshot.disks} alerts={alerts} />
          </>
        ) : null}
      </Panel>

      <div className="chart-grid">
        <Panel
          title="CPU"
          description={`last ${HISTORY_WINDOW_MINUTES} min`}
          isLoading={history.isLoading}
          error={history.error}
          lastUpdated={history.lastUpdated}
          hasData={!!points}
        >
          {points ? (
            <MetricAreaChart
              data={points}
              dataKey="cpu_percent"
              seriesName="CPU"
              color={CPU_COLOR}
              formatValue={(v) => formatPercent(v)}
            />
          ) : null}
        </Panel>

        <Panel
          title="Memory"
          description={`last ${HISTORY_WINDOW_MINUTES} min`}
          isLoading={history.isLoading}
          error={history.error}
          lastUpdated={history.lastUpdated}
          hasData={!!points}
        >
          {points ? (
            <MetricAreaChart
              data={points}
              dataKey="ram_percent"
              seriesName="Memory"
              color={MEMORY_COLOR}
              formatValue={(v) => formatPercent(v)}
            />
          ) : null}
        </Panel>

        <Panel
          title="Network"
          description={`last ${HISTORY_WINDOW_MINUTES} min`}
          isLoading={history.isLoading}
          error={history.error}
          lastUpdated={history.lastUpdated}
          hasData={!!points}
        >
          {points ? <NetworkChart data={points} /> : null}
        </Panel>
      </div>
    </>
  )
}
