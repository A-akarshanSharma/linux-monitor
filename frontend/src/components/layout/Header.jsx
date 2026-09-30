import { useHealth } from '../../hooks/useHealth'
import { useSystemInfo } from '../../hooks/useSystemInfo'
import { formatUptime } from '../../utils/format'
import { StatusDot } from './StatusDot'
import './Header.css'

const ENV_LABELS = {
  host: 'bare host',
  wsl: 'WSL',
  container: 'container',
}

export function Header() {
  const { data: system, error: systemError } = useSystemInfo()
  const { data: health, error: healthError } = useHealth()

  const connected = !systemError && !healthError && health?.status === 'ok'

  return (
    <header className="app-header">
      <div className="app-header-identity">
        <h1 className="app-header-title">
          {system?.hostname ?? 'server-monitor'}
          {system?.runtime_environment ? (
            <span className="app-header-env">{ENV_LABELS[system.runtime_environment] ?? system.runtime_environment}</span>
          ) : null}
        </h1>
        <p className="app-header-subtitle">
          {system ? (
            <>
              {system.os_name} · {system.kernel} · {system.ip_address}
            </>
          ) : (
            'Connecting…'
          )}
        </p>
      </div>

      <div className="app-header-meta">
        {system ? (
          <div className="app-header-stat">
            <span className="app-header-stat-label">uptime</span>
            <span className="app-header-stat-value num">{formatUptime(system.uptime_seconds)}</span>
          </div>
        ) : null}
        <StatusDot status={connected ? 'ok' : 'critical'} pulse={connected} label={connected ? 'connected' : 'unreachable'} />
      </div>
    </header>
  )
}
