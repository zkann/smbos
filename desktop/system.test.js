const test = require('node:test')
const assert = require('node:assert')
const system = require('./system')

test('compute parses the runner JSON', async () => {
  const fake = () => Promise.resolve(JSON.stringify({ health: 'ok', jobs: [{ name: 'x' }] }))
  assert.deepEqual(await system.compute('/sop', fake), { health: 'ok', jobs: [{ name: 'x' }] })
})

test('compute returns null on a runner error (so the SSE just skips the frame)', async () => {
  assert.equal(await system.compute('/sop', () => Promise.reject(new Error('boom'))), null)
})

test('compute returns null on non-JSON output', async () => {
  assert.equal(await system.compute('/sop', () => Promise.resolve('not json at all')), null)
})
