import assert from 'node:assert/strict'
import test from 'node:test'
import { formatClockTime, formatDateTime } from '../src/utils/format.js'

test('shared formatters preserve local date and time formatting', () => {
  for (const timestamp of ['2026-10-07T00:00:00Z', '2026-12-31T23:59:59Z']) {
    const date = new Date(timestamp)
    const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    assert.equal(formatClockTime(timestamp), time)
    assert.equal(formatDateTime(timestamp), `${date.toLocaleDateString([], { month: 'short', day: 'numeric' })}, ${time}`)
  }
  assert.equal(formatClockTime(null), '—')
  assert.equal(formatDateTime(null), '—')
})
