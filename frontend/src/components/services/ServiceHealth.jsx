import { useServices } from '../../hooks/useServices'
import { formatRelativeTime } from '../../utils/format'
import { Panel } from '../layout/Panel'
import { StatusDot } from '../layout/StatusDot'
import './ServiceHealth.css'

const STATE_INFO = {
  RUNNING: { status: 'ok', label: 'running' },
  STOPPED: { status: 'critical', label: 'stopped' },
  UNKNOWN: { status: 'unknown', label: 'unknown' },
}

export function ServiceHealth() {
  const { data, error, isLoading, lastUpdated } = useServices()
  const services = data?.services

  return (
    <Panel
      title="Services"
      isLoading={isLoading}
      error={error}
      lastUpdated={lastUpdated}
      hasData={!!services}
    >
      {services ? (
        services.length === 0 ? (
          <p className="service-empty">No services configured to monitor.</p>
        ) : (
          <ul className="service-list">
            {services.map((service) => {
              const info = STATE_INFO[service.state] ?? STATE_INFO.UNKNOWN
              return (
                <li className="service-row" key={service.name} title={service.detail ?? undefined}>
                  <StatusDot status={info.status} />
                  <span className="service-name">{service.name}</span>
                  <span className="service-state" data-status={info.status}>
                    {info.label}
                  </span>
                  <span className="service-since">{formatRelativeTime(service.last_changed_at)}</span>
                </li>
              )
            })}
          </ul>
        )
      ) : null}
    </Panel>
  )
}
