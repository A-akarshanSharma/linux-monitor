import { useCallback } from 'react'
import { api } from '../api/client'
import { ALERTS_WINDOW_MINUTES, POLL_INTERVALS_MS } from '../config'
import { usePolling } from './usePolling'

export function useAlerts(minutes = ALERTS_WINDOW_MINUTES) {
  const fetcher = useCallback(() => api.getAlerts(minutes), [minutes])
  return usePolling(fetcher, POLL_INTERVALS_MS.alerts)
}
