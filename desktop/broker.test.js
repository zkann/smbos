const test = require('node:test')
const assert = require('node:assert')
const http = require('http')
const { createBroker } = require('./broker')

function listen(server) {
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server.address().port)))
}
function request(port, path, opts = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      { host: '127.0.0.1', port, path, method: opts.method || 'GET', headers: opts.headers },
      (res) => {
        let b = ''
        res.on('data', (c) => { b += c })
        res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: b }))
      },
    )
    req.on('error', reject)
    if (opts.body) req.write(opts.body)
    req.end()
  })
}

test('forwards method, path, body, status, and headers to the upstream', async () => {
  const seen = {}
  const upstream = http.createServer((req, res) => {
    let body = ''
    req.on('data', (c) => { body += c })
    req.on('end', () => {
      Object.assign(seen, { method: req.method, url: req.url, body, token: req.headers['x-smbos-token'] })
      res.writeHead(201, { 'content-type': 'application/json', 'x-up': 'yes' })
      res.end(JSON.stringify({ ok: true }))
    })
  })
  const upPort = await listen(upstream)
  const broker = createBroker({ targetPort: upPort })
  const brPort = await listen(broker)
  const r = await request(brPort, '/api/run?t=abc',
    { method: 'POST', body: '{"id":"x"}', headers: { 'x-smbos-token': 'tok' } })
  assert.equal(r.status, 201)                          // upstream status forwarded
  assert.equal(r.headers['x-up'], 'yes')               // upstream header forwarded
  assert.deepEqual(JSON.parse(r.body), { ok: true })   // body forwarded
  assert.equal(seen.method, 'POST')
  assert.equal(seen.url, '/api/run?t=abc')             // path + query preserved
  assert.equal(seen.body, '{"id":"x"}')                // request body forwarded
  assert.equal(seen.token, 'tok')                      // the header token rides through (CSRF posture intact)
  upstream.close(); broker.close()
})

test('streams a chunked response (SSE-safe): the first frame arrives before the stream ends', async () => {
  // deterministic streaming check: the upstream sends frame 1, then frame 2 + end 150ms later. If
  // the broker streams, the client sees 'data: 1' BEFORE 'data: 2'/end; if it buffered, both arrive
  // together. Content-based, not chunk-count (TCP can coalesce writes, so chunk count is flaky).
  const upstream = http.createServer((req, res) => {
    res.writeHead(200, { 'content-type': 'text/event-stream' })
    res.write('event: a\ndata: 1\n\n')
    setTimeout(() => { res.write('event: b\ndata: 2\n\n'); res.end() }, 150)
  })
  const upPort = await listen(upstream)
  const broker = createBroker({ targetPort: upPort })
  const brPort = await listen(broker)
  let joined = ''
  let sawFirstFrameBeforeSecond = false
  await new Promise((resolve) => {
    http.get({ host: '127.0.0.1', port: brPort, path: '/events?t=x' }, (res) => {
      res.on('data', (c) => {
        joined += c.toString()
        if (joined.includes('data: 1') && !joined.includes('data: 2')) sawFirstFrameBeforeSecond = true
      })
      res.on('end', resolve)
    })
  })
  assert.ok(joined.includes('data: 1') && joined.includes('data: 2'))
  assert.ok(sawFirstFrameBeforeSecond, 'first frame was delivered before the second (streamed, not buffered)')
  upstream.close(); broker.close()
})

test('returns 502 when the upstream is unreachable, never crashes', async () => {
  const broker = createBroker({ targetPort: 1 })  // nothing listening on port 1
  const brPort = await listen(broker)
  const r = await request(brPort, '/api/plate?t=x')
  assert.equal(r.status, 502)
  broker.close()
})

test('throws if targetPort is not a valid port (no silent mis-target to port 80)', () => {
  assert.throws(() => createBroker({}), /targetPort/)
  assert.throws(() => createBroker({ targetPort: 'x' }), /targetPort/)
  assert.throws(() => createBroker({ targetPort: 0 }), /targetPort/)
  assert.throws(() => createBroker({ targetPort: 70000 }), /targetPort/)
})

test('tears down the upstream socket when the client aborts (SSE reconnect / window reload)', async () => {
  let upstreamReq = null
  const upstream = http.createServer((req, res) => {
    upstreamReq = req
    res.writeHead(200, { 'content-type': 'text/event-stream' })
    res.write('data: 1\n\n')  // keep the stream open (never .end) so the client must abort it
  })
  const upPort = await listen(upstream)
  const broker = createBroker({ targetPort: upPort })
  const brPort = await listen(broker)
  await new Promise((resolve) => {
    const req = http.get({ host: '127.0.0.1', port: brPort, path: '/events?t=x' }, (res) => {
      res.once('data', () => { req.destroy(); resolve() })  // got a frame, now abort the client
    })
  })
  await new Promise((r) => setTimeout(r, 60))
  assert.ok(upstreamReq && upstreamReq.destroyed, 'upstream torn down after the client aborted')
  upstream.close(); broker.close()
})

test('an absolute-form request-target still goes to the FIXED upstream (not an open proxy)', async () => {
  let seenUrl = null
  const upstream = http.createServer((req, res) => { seenUrl = req.url; res.end('ok') })
  const upPort = await listen(upstream)
  const broker = createBroker({ targetPort: upPort })
  const brPort = await listen(broker)
  await new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port: brPort, path: 'http://evil.example/api/plate?t=x' },
      (res) => { res.resume(); res.on('end', resolve) })
    req.on('error', reject)
    req.end()
  })
  // it reached the fixed upstream (handler ran) and forwarded the target verbatim -- never re-resolved
  // 'evil.example'. The hardcoded {host,port} is what makes this safe.
  assert.equal(seenUrl, 'http://evil.example/api/plate?t=x')
  upstream.close(); broker.close()
})

test('rejects a non-loopback Host (DNS-rebinding defense) before forwarding', async () => {
  let reached = false
  const upstream = http.createServer((req, res) => { reached = true; res.end('ok') })
  const upPort = await listen(upstream)
  const broker = createBroker({ targetPort: upPort })
  const brPort = await listen(broker)
  const bad = await request(brPort, '/api/plate?t=x', { headers: { host: 'evil.example' } })
  assert.equal(bad.status, 403)            // rebinding request refused at the broker
  assert.equal(reached, false, 'a non-loopback-Host request never reaches the upstream')
  const ok = await request(brPort, '/api/plate?t=x', { headers: { host: '127.0.0.1' } })
  assert.equal(ok.status, 200)             // loopback Host forwards normally
  upstream.close(); broker.close()
})
