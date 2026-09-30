import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Fetches immediately on mount, then again every `intervalMs`, until unmounted.
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

  const load = useCallback(async () => {
    try {
      const result = await fetcherRef.current()
      setData(result)
      setError(null)
      setLastUpdated(new Date())
    } catch (err) {
      setError(err)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    const tick = () => {
      if (!cancelled) load()
    }

    tick()
    const id = setInterval(tick, intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [intervalMs, load])

  return { data, error, isLoading, lastUpdated, refetch: load }
}
