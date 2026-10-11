import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { test } from 'node:test'
import { appShellPlugin } from '../pwa/plugin.js'
import { api } from '../src/api/client.js'

const dist = new URL('../dist/', import.meta.url)
const worker = readFileSync(new URL('sw.js', dist), 'utf8')
const origin = 'http://localhost:8080'

function workerHarness({ failInstall = false } = {}) {
  const listeners = {}
  const storage = new Map()
  const oldName = 'linux-monitor-shell-old'
  storage.set(oldName, new Map())
  storage.set('another-app', new Map())
  const network = []
  let claimed = false
  class LocalRequest extends Request {
    constructor(url, options) {
      super(new URL(url, origin), options)
    }
  }
  const context = vm.createContext({
    URL,
    Request: LocalRequest,
    Set,
    self: {
      location: { origin },
      clients: { claim: async () => { claimed = true } },
      addEventListener: (name, listener) => { listeners[name] = listener },
    },
    caches: {
      keys: async () => [...storage.keys()],
      delete: async (name) => storage.delete(name),
      open: async (name) => {
        if (!storage.has(name)) storage.set(name, new Map())
        const entries = storage.get(name)
        return {
          addAll: async (requests) => {
            for (const request of requests) {
              assert.equal(request.cache, 'reload')
              entries.set(new URL(request.url).pathname, `cached:${request.url}`)
              if (failInstall) throw new Error('download failed')
            }
          },
          match: async (url) => entries.get(url),
        }
      },
    },
    fetch: async (request) => {
      network.push(request.url)
      throw new Error('offline')
    },
  })
  vm.runInContext(worker, context)
  const cacheName = vm.runInContext('CACHE_NAME', context)
  const shellUrls = [...vm.runInContext('SHELL_URLS', context)]
  return {
    storage, oldName, cacheName, shellUrls, network,
    get claimed() { return claimed },
    async lifecycle(name) {
      let pending
      listeners[name]({ waitUntil: (promise) => { pending = promise } })
      await pending
    },
    async request(path, options = {}) {
      let response
      listeners.fetch({
        request: { url: new URL(path, origin).href, method: 'GET', mode: 'cors', ...options },
        respondWith: (promise) => { response = promise },
      })
      return response ? { handled: true, response: await response } : { handled: false }
    },
  }
}

test('manifest has standalone launch and valid install icons in the build', () => {
  const manifest = JSON.parse(readFileSync(new URL('manifest.webmanifest', dist)))
  assert.equal(manifest.display, 'standalone')
  assert.equal(manifest.start_url, '/')
  assert.equal(manifest.scope, '/')
  assert.deepEqual(manifest.icons.map((icon) => icon.sizes), ['192x192', '512x512', '512x512'])
  for (const icon of manifest.icons) {
    const png = readFileSync(new URL(icon.src.slice(1), dist))
    assert.equal(png.subarray(1, 4).toString(), 'PNG')
    assert.equal(`${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`, icon.sizes)
  }
})

test('the precache contains the built HTML, scripts, styles, and install assets', async () => {
  const harness = workerHarness()
  await harness.lifecycle('install')
  const html = readFileSync(new URL('index.html', dist), 'utf8')
  for (const [, url] of html.matchAll(/(?:src|href)="(\/[^"?#]+)"/g)) {
    assert.ok(harness.shellUrls.includes(url), `Missing precache file: ${url}`)
  }
  for (const url of harness.shellUrls) {
    assert.ok(!url.startsWith('/api'))
    assert.ok(readFileSync(new URL(url.slice(1), dist)).length > 0)
  }
})

test('offline navigation and built files use the cached shell without network requests', async () => {
  const harness = workerHarness()
  await harness.lifecycle('install')
  const nav = await harness.request('/?source=desktop', { mode: 'navigate' })
  assert.equal(nav.response, `cached:${origin}/index.html`)
  const script = harness.shellUrls.find((url) => url.endsWith('.js'))
  const asset = await harness.request(`${script}?v=1`)
  assert.equal(asset.response, `cached:${origin}${script}`)
  assert.deepEqual(harness.network, [])
})

test('API, external resources, mutations, and unknown files bypass the worker', async () => {
  const harness = workerHarness()
  await harness.lifecycle('install')
  const sizeBefore = harness.storage.get(harness.cacheName).size
  for (const path of ['/api', '/api/health', '/api/metrics/current?minutes=5']) {
    assert.equal((await harness.request(path)).handled, false)
    assert.equal((await harness.request(path, { mode: 'navigate' })).handled, false)
  }
  assert.equal((await harness.request('/assets/missing.js')).handled, false)
  assert.equal((await harness.request('/favicon.svg', { method: 'POST' })).handled, false)
  assert.equal((await harness.request('https://example.com/favicon.svg')).handled, false)
  assert.equal(harness.storage.get(harness.cacheName).size, sizeBefore)
})

test('activation cleans up only this app\'s obsolete caches and claims clients', async () => {
  const harness = workerHarness()
  await harness.lifecycle('install')
  assert.ok(harness.storage.has(harness.oldName))
  await harness.lifecycle('activate')
  assert.ok(!harness.storage.has(harness.oldName))
  assert.ok(harness.storage.has(harness.cacheName))
  assert.ok(harness.storage.has('another-app'))
  assert.equal(harness.claimed, true)
})

test('a failed shell download removes the partial cache and preserves the previous build', async () => {
  const harness = workerHarness({ failInstall: true })
  await assert.rejects(harness.lifecycle('install'), /download failed/)
  assert.ok(!harness.storage.has(harness.cacheName))
  assert.ok(harness.storage.has(harness.oldName))
})

test('the shell cache version changes when built content changes', () => {
  function generate(code) {
    let output
    appShellPlugin().generateBundle.call({ emitFile: (file) => { output = file } }, {}, {
      'index.html': { type: 'asset', source: '<html></html>' },
      'assets/test.js': { type: 'chunk', code },
    })
    return output.source.match(/const CACHE_NAME = '([^']+)'/)[1]
  }
  assert.equal(generate('version1'), generate('version1'))
  assert.notEqual(generate('version1'), generate('version2'))
})

test('live API fetches bypass the browser HTTP cache', async () => {
  const previousFetch = globalThis.fetch
  try {
    let seen
    globalThis.fetch = async (url, options) => {
      seen = { url, options }
      return { ok: true, json: async () => ({ status: 'ok' }) }
    }
    assert.deepEqual(await api.getHealth(), { status: 'ok' })
    assert.equal(seen.url, '/api/health')
    assert.equal(seen.options.cache, 'no-store')
  } finally {
    globalThis.fetch = previousFetch
  }
})
