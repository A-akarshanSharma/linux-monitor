import assert from 'node:assert/strict'
import test from 'node:test'
import { startPolling } from '../src/hooks/polling.js'
import { api } from '../src/api/client.js'

class Visibility extends EventTarget {
  hidden = false
  change(hidden) {
    this.hidden = hidden
    this.dispatchEvent(new Event('visibilitychange'))
  }
}

function setup(t, fetcher, hidden = false) {
  t.mock.timers.enable({ apis: ['setInterval'] })
  const visibility = new Visibility()
  visibility.hidden = hidden
  const values = [], errors = []
  let settlements = 0
  const polling = startPolling(fetcher, 1000, {
    success: (value) => values.push(value),
    error: (error) => errors.push(error),
    settled: () => { settlements++ },
  }, visibility)
  t.after(() => polling.stop())
  return { polling, visibility, values, errors, get settlements() { return settlements } }
}

const flush = async () => { await Promise.resolve(); await Promise.resolve() }

test('slow requests cannot pile up; polling continues after completion', async (t) => {
  let finish, calls = 0
  const state = setup(t, () => {
    calls++
    return new Promise((resolve) => { finish = resolve })
  })
  t.mock.timers.tick(5000)
  await state.polling.refetch()
  assert.equal(calls, 1)
  finish('first')
  await flush()
  assert.deepEqual(state.values, ['first'])
  t.mock.timers.tick(1000)
  assert.equal(calls, 2)
})

test('hidden windows make no requests and immediately refresh on return', async (t) => {
  let calls = 0
  const state = setup(t, async () => ++calls, true)
  t.mock.timers.tick(10000)
  assert.equal(calls, 0)
  state.visibility.change(false)
  await flush()
  assert.deepEqual(state.values, [1])
  state.visibility.change(true)
  t.mock.timers.tick(10000)
  assert.equal(calls, 1)
  state.visibility.change(false)
  await flush()
  assert.deepEqual(state.values, [1, 2])
})

test('hiding aborts a pending request and ignores its late result after resuming', async (t) => {
  const pending = []
  const state = setup(t, (signal) => new Promise((resolve) => pending.push({ signal, resolve })))
  state.visibility.change(true)
  assert.equal(pending[0].signal.aborted, true)
  state.visibility.change(false)
  pending[1].resolve('fresh')
  await flush()
  pending[0].resolve('obsolete')
  await flush()
  assert.deepEqual(state.values, ['fresh'])
  assert.equal(state.settlements, 1)
})

test('unmount aborts pending work and removes timers and visibility listeners', async (t) => {
  let signal, finish, calls = 0
  const state = setup(t, (s) => {
    signal = s
    calls++
    return new Promise((resolve) => { finish = resolve })
  })
  state.polling.stop()
  assert.equal(signal.aborted, true)
  finish('obsolete')
  await flush()
  t.mock.timers.tick(10000)
  state.visibility.change(false)
  assert.equal(calls, 1)
  assert.deepEqual(state.values, [])
  assert.equal(state.settlements, 0)
})

test('a failed request reports an error and a subsequent poll recovers', async (t) => {
  let fail = true
  const problem = new Error('unavailable')
  const state = setup(t, async () => {
    if (fail) throw problem
    return 'recovered'
  })
  await flush()
  assert.deepEqual(state.errors, [problem])
  assert.equal(state.settlements, 1)
  fail = false
  t.mock.timers.tick(1000)
  await flush()
  assert.deepEqual(state.values, ['recovered'])
})

test('every API method forwards the request AbortSignal', async (t) => {
  const controller = new AbortController()
  const seen = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    seen.push({ url, options })
    return { ok: true, json: async () => ({}) }
  })
  await Promise.all([
    api.getHealth(controller.signal), api.getSystem(controller.signal),
    api.getCurrentMetrics(controller.signal), api.getServices(controller.signal),
    api.getMetricsHistory(30, controller.signal), api.getAlerts(60, controller.signal),
    api.getProcesses(8, controller.signal),
  ])
  assert.equal(seen.length, 7)
  for (const { options } of seen) {
    assert.equal(options.signal, controller.signal)
    assert.equal(options.cache, 'no-store')
  }
})
