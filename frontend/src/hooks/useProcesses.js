import { useCallback } from 'react'
import { api } from '../api/client'
import { POLL_INTERVALS_MS, PROCESS_LIST_LIMIT } from '../config'
import { usePolling } from './usePolling'

export function useProcesses(limit = PROCESS_LIST_LIMIT) {
  const fetcher = useCallback(() => api.getProcesses(limit), [limit])
  return usePolling(fetcher, POLL_INTERVALS_MS.processes)
}
