import { formatRelativeTime } from '../../utils/format'
import { Panel } from '../layout/Panel'
import { StatusDot } from '../layout/StatusDot'
import './AlertsPanel.css'

const STATE_INFO = {
  WARNING: { status: 'warning', label: 'warning' },
  CRITICAL: { status: 'critical', label: 'critical' },
  RESOLVED: { status: 'ok', label: 'resolved' },
}

function targetLabel(alert) {
  return alert.target ? `${alert.rule_key}:${alert.target}` : alert.rule_key
}

export function AlertsPanel({ alerts, isLoading, error, lastUpdated }) {
  const activeCount = alerts?.filter((alert) => alert.state !== 'RESOLVED').length ?? 0

  return (
    <Panel
      title="Alerts"
      description={alerts ? (activeCount > 0 ? `${activeCount} active` : 'all clear') : undefined}
      isLoading={isLoading}
      error={error}
      lastUpdated={lastUpdated}
      hasData={!!alerts}
    >
      {alerts ? (
        alerts.length === 0 ? (
          <p className="alerts-empty">No alerts - everything's within thresholds.</p>
        ) : (
          <ul className="alerts-list">
            {alerts.map((alert) => {
              const info = STATE_INFO[alert.state] ?? STATE_INFO.WARNING
              const timestamp = alert.state === 'RESOLVED' ? alert.resolved_at : alert.last_updated_at
              return (
                <li className="alert-row" key={alert.id}>
                  <StatusDot status={info.status} />
                  <div className="alert-row-body">
                    <div className="alert-row-top">
                      <span className="alert-row-target num">{targetLabel(alert)}</span>
                      <span className="alert-row-state" data-status={info.status}>
                        {info.label}
                      </span>
                    </div>
                    <p className="alert-row-message">{alert.message}</p>
                  </div>
                  <span className="alert-row-time">{formatRelativeTime(timestamp)}</span>
                </li>
              )
            })}
          </ul>
        )
      ) : null}
    </Panel>
  )
}
