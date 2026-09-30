import { api } from '../api/client'
import { POLL_INTERVALS_MS } from '../config'
import { usePolling } from './usePolling'

export function useServices() {
  return usePolling(api.getServices, POLL_INTERVALS_MS.services)
}
