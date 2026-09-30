import { api } from '../api/client'
import { POLL_INTERVALS_MS } from '../config'
import { usePolling } from './usePolling'

/** Used only for the small "connected/unreachable" indicator in the header -
 * deliberately on the same cadence as system info, not its own timer. */
export function useHealth() {
  return usePolling(api.getHealth, POLL_INTERVALS_MS.system)
}
