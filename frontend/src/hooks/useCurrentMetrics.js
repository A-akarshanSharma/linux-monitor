import { api } from '../api/client'
import { POLL_INTERVALS_MS } from '../config'
import { usePolling } from './usePolling'

export function useCurrentMetrics() {
  return usePolling(api.getCurrentMetrics, POLL_INTERVALS_MS.currentMetrics)
}
