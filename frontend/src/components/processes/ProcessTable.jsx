import { useState } from 'react'
import { useProcesses } from '../../hooks/useProcesses'
import { formatBytes, formatPercent } from '../../utils/format'
import { Panel } from '../layout/Panel'
import './ProcessTable.css'

const TABS = [
  { key: 'top_by_cpu', label: 'By CPU' },
  { key: 'top_by_memory', label: 'By memory' },
]

export function ProcessTable() {
  const { data, error, isLoading, lastUpdated } = useProcesses()
  const [activeTab, setActiveTab] = useState('top_by_cpu')

  const rows = data?.[activeTab]

  return (
    <Panel
      title="Top processes"
      description={data ? `${data.total_count} running` : undefined}
      isLoading={isLoading}
      error={error}
      lastUpdated={lastUpdated}
      hasData={!!data}
    >
      {data ? (
        <>
          <div className="process-tabs" role="tablist" aria-label="Sort processes by">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.key}
                className={`process-tab${activeTab === tab.key ? ' process-tab--active' : ''}`}
                onClick={() => setActiveTab(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <table className="process-table">
            <thead>
              <tr>
                <th className="process-table-num">PID</th>
                <th>Process</th>
                <th className="process-table-num">CPU</th>
                <th className="process-table-num">Mem</th>
                <th className="process-table-num">RSS</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((proc) => (
                <tr key={proc.pid}>
                  <td className="process-table-num num">{proc.pid}</td>
                  <td className="process-table-name">
                    <span className="process-table-name-text">{proc.name}</span>
                    {proc.username ? <span className="process-table-user">{proc.username}</span> : null}
                  </td>
                  <td className="process-table-num num">{formatPercent(proc.cpu_percent)}</td>
                  <td className="process-table-num num">{formatPercent(proc.memory_percent)}</td>
                  <td className="process-table-num num">{formatBytes(proc.memory_rss_bytes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}
    </Panel>
  )
}
