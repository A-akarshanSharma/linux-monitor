import { api } from '../api/client'
import { POLL_INTERVALS_MS } from '../config'
import { usePolling } from './usePolling'

export function useSystemInfo() {
  return usePolling(api.getSystem, POLL_INTERVALS_MS.system)
}
