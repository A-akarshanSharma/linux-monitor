/* The build replaces these tokens with a content version and an explicit list
 * of local shell files. API responses and third-party resources are never cached. */
const CACHE_NAME = '__SHELL_CACHE_NAME__'
const SHELL_URLS = __SHELL_URLS__
const SHELL_PATHS = new Set(SHELL_URLS)

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME)
    try {
      await cache.addAll(SHELL_URLS.map((url) => new Request(url, { cache: 'reload' })))
    } catch (error) {
      // A partial download must not replace the last working shell.
      await caches.delete(CACHE_NAME)
      throw error
    }
  })())
  // Let updates wait until all existing dashboard windows/tabs are closed, so
  // an open app keeps using a consistent set of HTML, JS, and CSS.
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys()
    await Promise.all(names
      .filter((name) => name.startsWith('linux-monitor-shell-') && name !== CACHE_NAME)
      .map((name) => caches.delete(name)))
    await self.clients.claim()
  })())
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin) return
  if (url.pathname === '/api' || url.pathname.startsWith('/api/')) return

  // Navigation uses the cached shell immediately. Only known build files can
  // use this cache; arbitrary requests and missing assets go to the server.
  const path = request.mode === 'navigate' ? '/index.html' : url.pathname
  if (!SHELL_PATHS.has(path)) return

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME)
    return await cache.match(path) || fetch(request)
  })())
})
