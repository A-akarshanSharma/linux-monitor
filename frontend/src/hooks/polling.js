/** One request at a time, only while visible. Abort and ignore obsolete results
 * on hide/unmount; the backend keeps collecting history independently. */
export function startPolling(fetcher, intervalMs, { success, error, settled }, visibility = document) {
  let stopped = false
  let timer
  let active

  const refetch = async () => {
    if (stopped || visibility.hidden || active) return
    const controller = new AbortController()
    active = controller
    try {
      const data = await fetcher(controller.signal)
      if (!stopped && !controller.signal.aborted) success(data)
    } catch (err) {
      if (!stopped && !controller.signal.aborted) error(err)
    } finally {
      if (active === controller) active = undefined
      if (!stopped && !controller.signal.aborted) settled()
    }
  }

  const updateVisibility = () => {
    clearInterval(timer)
    timer = undefined
    if (visibility.hidden) {
      active?.abort()
      active = undefined
    } else {
      void refetch()
      timer = setInterval(refetch, intervalMs)
    }
  }
  visibility.addEventListener('visibilitychange', updateVisibility)
  updateVisibility()

  return {
    refetch,
    stop() {
      stopped = true
      clearInterval(timer)
      active?.abort()
      visibility.removeEventListener('visibilitychange', updateVisibility)
    },
  }
}
