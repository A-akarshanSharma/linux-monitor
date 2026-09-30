import { useCallback } from 'react'
import { api } from '../api/client'
import { HISTORY_WINDOW_MINUTES, POLL_INTERVALS_MS } from '../config'
import { usePolling } from './usePolling'

export function useMetricsHistory(minutes = HISTORY_WINDOW_MINUTES) {
  const fetcher = useCallback(() => api.getMetricsHistory(minutes), [minutes])
  return usePolling(fetcher, POLL_INTERVALS_MS.history)
}
