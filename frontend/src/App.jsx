import { useAlerts } from './hooks/useAlerts'
import { Header } from './components/layout/Header'
import { MetricsOverview } from './components/metrics/MetricsOverview'
import { ProcessTable } from './components/processes/ProcessTable'
import { ServiceHealth } from './components/services/ServiceHealth'
import { AlertsPanel } from './components/alerts/AlertsPanel'
import './App.css'

export default function App() {
  // Owned once here: both MetricsOverview (for CPU/memory/disk severity coloring)
  // and AlertsPanel (for the list itself) need this data, and lifting it avoids
  // polling /api/alerts twice on independent timers.
  const alertsQuery = useAlerts()
  const alerts = alertsQuery.data?.alerts

  return (
    <div className="app-shell">
      <Header />
      <main className="app-main">
        <MetricsOverview alerts={alerts} />
        <div className="lower-grid">
          <ProcessTable />
          <div className="side-stack">
            <ServiceHealth />
            <AlertsPanel
              alerts={alerts}
              isLoading={alertsQuery.isLoading}
              error={alertsQuery.error}
              lastUpdated={alertsQuery.lastUpdated}
            />
          </div>
        </div>
      </main>
    </div>
  )
}
