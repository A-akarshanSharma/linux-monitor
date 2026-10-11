export function registerServiceWorker() {
  // The generated worker only exists in production builds. Never cache Vite's
  // development modules, where stale code would interfere with hot reloads.
  if (!import.meta.env.PROD || !('serviceWorker' in navigator) || !window.isSecureContext) return

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' }).catch((error) => {
      console.warn('Could not enable app-shell caching:', error)
    })
  }, { once: true })
}
