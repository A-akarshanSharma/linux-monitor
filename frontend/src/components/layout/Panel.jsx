import { useEffect, useState } from 'react'
import { formatRelativeTime } from '../../utils/format'
import { StatusDot } from './StatusDot'
import './Panel.css'

/**
 * The shared shell for every section: a titled, bordered panel with a small
 * freshness indicator (green pulsing dot + "Xs ago") and a consistent way of
 * handling the three states a polled panel can be in:
 *   - first load, nothing yet -> `loadingFallback`
 *   - has data, but the most recent poll failed -> data stays visible, plus a
 *     small inline "last update failed" notice (never a blocking error screen)
 *   - no data and the most recent poll failed -> `errorFallback`
 */
export function Panel({ title, description, isLoading, error, lastUpdated, hasData, children }) {
  // Re-render once a second so "Xs ago" stays live without needing a poll.
  const [, forceTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => forceTick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const showEmptyState = isLoading && !hasData
  const showErrorState = !isLoading && error && !hasData

  return (
    <section className="panel">
      <header className="panel-header">
        <div>
          <h2 className="panel-title">{title}</h2>
          {description ? <p className="panel-description">{description}</p> : null}
        </div>
        {lastUpdated ? (
          <StatusDot status={error ? 'warning' : 'ok'} pulse={!error} label={formatRelativeTime(lastUpdated)} />
        ) : null}
      </header>

      <div className="panel-body">
        {showEmptyState ? (
          <p className="panel-placeholder">Waiting for first reading…</p>
        ) : showErrorState ? (
          <p className="panel-placeholder panel-placeholder--error">
            Couldn't load this section. Retrying automatically.
          </p>
        ) : (
          <>
            {error && hasData ? (
              <p className="panel-stale-notice">Last update failed - showing the previous reading.</p>
            ) : null}
            {children}
          </>
        )}
      </div>
    </section>
  )
}
