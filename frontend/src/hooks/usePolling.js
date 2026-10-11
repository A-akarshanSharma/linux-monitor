import { useCallback, useEffect, useRef, useState } from 'react'
import { startPolling } from './polling'

/**
 * Fetches on mount and every `intervalMs` while visible. Refreshes on return.
 *
 * On a failed fetch, the previous successful `data` is kept on screen rather than
 * cleared - a panel should show slightly stale numbers through a transient error,
 * not blank itself out. `error` is still set, so callers can show a small inline
 * notice without losing the last good reading underneath it.
 */
export function usePolling(fetcher, intervalMs) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)

  // fetcher is re-created every render (it's usually an inline closure over
  // params); stashing it in a ref lets the interval effect below depend only on
  // intervalMs, so it doesn't tear down and restart the timer every render.
  // Assigning it in an effect (rather than inline during render) keeps render
  // itself pure, as React's rules-of-hooks lint now enforces.
  const fetcherRef = useRef(fetcher)
  useEffect(() => {
    fetcherRef.current = fetcher
  })

  const pollingRef = useRef(null)
  const load = useCallback(() => pollingRef.current?.refetch(), [])

  useEffect(() => {
    const polling = startPolling((signal) => fetcherRef.current(signal), intervalMs, {
      success(result) {
        setData(result)
        setError(null)
        setLastUpdated(new Date())
      },
      error: setError,
      settled: () => setIsLoading(false),
    })
    pollingRef.current = polling
    return () => {
      polling.stop()
      pollingRef.current = null
    }
  }, [intervalMs])

  return { data, error, isLoading, lastUpdated, refetch: load }
}
