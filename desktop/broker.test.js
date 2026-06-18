const test = require('node:test')
const assert = require('node:assert')
const http = require('http')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { DatabaseSync } = require('node:sqlite')
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

test('serves /api/plate from the store (token-gated), forwards unknown paths', async () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-broker-'))
  fs.writeFileSync(path.join(d, '.dashboard-token'), 'tok')
  const db = new DatabaseSync(path.join(d, 'state.db'))
  db.exec(`CREATE TABLE task (id INTEGER PRIMARY KEY, domain TEXT, kind TEXT, subject TEXT, status TEXT,
    priority INTEGER DEFAULT 0, source_ref TEXT, created_at TEXT, updated_at TEXT)`)
  db.prepare("INSERT INTO task(id,domain,kind,subject,status,created_at,updated_at) VALUES(1,'ops','x','on plate','waiting','t','t')").run()
  db.close()
  let forwarded = false
  const upstream = http.createServer((req, res) => { forwarded = true; res.end('up') })
  const upPort = await listen(upstream)
  const broker = createBroker({ targetPort: upPort, sopDir: d })
  const brPort = await listen(broker)
  // served + no token -> 401, never forwarded
  assert.equal((await request(brPort, '/api/plate')).status, 401)
  // served + valid token -> answered from the store
  const ok = await request(brPort, '/api/plate?t=tok')
  assert.equal(ok.status, 200)
  assert.deepEqual(JSON.parse(ok.body).plate.map((r) => r.subject), ['on plate'])
  assert.equal(forwarded, false, 'a served read never hits the upstream')
  // an unhandled path still forwards to FastAPI: the broker proxies anything it doesn't own
  await request(brPort, '/api/unknown?t=tok')
  assert.equal(forwarded, true)
  upstream.close(); broker.close()
})

test('a served read is DENIED when the token file is missing/empty (fails closed, no upstream contact)', async () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-broker-'))  // no .dashboard-token written
  const db = new DatabaseSync(path.join(d, 'state.db'))
  db.exec(`CREATE TABLE task (id INTEGER PRIMARY KEY, domain TEXT, kind TEXT, subject TEXT, status TEXT,
    priority INTEGER DEFAULT 0, source_ref TEXT, created_at TEXT, updated_at TEXT)`)
  db.close()
  let forwarded = false
  const upstream = http.createServer((req, res) => { forwarded = true; res.end('up') })
  const upPort = await listen(upstream)
  const broker = createBroker({ targetPort: upPort, sopDir: d })
  const brPort = await listen(broker)
  assert.equal((await request(brPort, '/api/plate?t=')).status, 401)          // empty token -> deny
  assert.equal((await request(brPort, '/api/plate?t=anything')).status, 401)  // no token file -> deny, not allow
  assert.equal(forwarded, false, 'a denied served read must not fall through to the upstream')
  upstream.close(); broker.close()
})

test('POST actions: header-token gated; maps each engine exit code to the HTTP status', async () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-run-'))
  fs.writeFileSync(path.join(d, '.dashboard-token'), 'tok')
  // a stub "engine": /bin/sh reads argv [stub, <cmd>, sopDir, ...]; branch on the subcommand ($1),
  // and for `run` on the id ($3). Covers the exit-code -> HTTP map for every action path.
  const stub = path.join(d, 'stub.sh')
  fs.writeFileSync(stub,
    'case "$1" in\n' +
    '  resolve) echo \'{"detail":"nf"}\'; exit 4;;\n' +        // -> 404
    '  dequeue) echo \'{"status":"dequeued"}\'; exit 0;;\n' +  // -> 200
    '  task-status) echo \'{"detail":"conflict"}\'; exit 9;;\n' +  // -> 409
    '  queue) echo \'{"status":"queued","sop":"x"}\'; exit 0;;\n' +  // -> 200
    '  autonomy) echo \'{"id":"x","autonomy":"with_me"}\'; exit 0;;\n' +  // -> 200
    '  launch) echo \'{"status":"launched","task_id":1}\'; exit 0;;\n' +  // -> 200
    '  open-session) echo \'{"status":"opened","task_id":1}\'; exit 0;;\n' +  // -> 200
    '  launch-sop) echo \'{"status":"launched","sop":"x"}\'; exit 0;;\n' +  // -> 200
    '  apply-item) echo \'{"status":"applied"}\'; exit 0;;\n' +  // -> 200
    '  settings-get) echo \'{"settings":{"launch_permission":"trust","terminal":"terminal","budget":0,"spent":0}}\'; exit 0;;\n' +  // GET via engine
    '  settings-set) echo \'{"settings":{"launch_permission":"ask","terminal":"terminal","budget":0,"spent":0}}\'; exit 0;;\n' +  // -> 200
    '  run) case "$3" in\n' +
    '    refuse) echo \'{"detail":"nope"}\'; exit 3;;\n' +     // -> 409
    '    boom) echo \'{"detail":"boom"}\'; exit 1;;\n' +       // -> 500
    '    *) echo "{\\"status\\":\\"started\\",\\"sop\\":\\"$3\\"}"; exit 0;;\n' +
    '  esac;;\n' +
    'esac\n')
  const prevPy = process.env.SMBOS_PYTHON, prevEng = process.env.SMBOS_ENGINE
  process.env.SMBOS_PYTHON = '/bin/sh'; process.env.SMBOS_ENGINE = stub
  try {
    const broker = createBroker({ targetPort: 9, sopDir: d })  // targetPort unused: actions are handled, not forwarded
    const brPort = await listen(broker)
    const post = (route, body, headers) => request(brPort, route, { method: 'POST', body, headers })
    const T = { 'x-smbos-token': 'tok' }
    assert.equal((await post('/api/run', '{"id":"x"}', {})).status, 401)               // no token
    assert.equal((await post('/api/run', 'not json', T)).status, 400)                  // bad body
    assert.equal((await post('/api/run', '{"id":"refuse"}', T)).status, 409)           // exit 3 -> 409
    assert.equal((await post('/api/run', '{"id":"boom"}', T)).status, 500)             // exit 1 -> 500
    const ok = await post('/api/run', '{"id":"weekly"}', T)
    assert.equal(ok.status, 200); assert.equal(JSON.parse(ok.body).sop, 'weekly')      // exit 0 -> 200 body
    assert.equal((await post('/api/resolve', '{"file":"x.md","decision":"approve"}', T)).status, 404)  // exit 4 -> 404
    assert.equal((await post('/api/dequeue', '{"file":"x.md"}', T)).status, 200)        // exit 0 -> 200
    assert.equal((await post('/api/task-status', '{"task_id":1,"status":"done"}', T)).status, 409)  // exit 9 -> 409
    assert.equal((await post('/api/queue', '{"id":"x"}', T)).status, 200)               // dispatched -> 200
    assert.equal((await post('/api/autonomy', '{"id":"x","level":"with_me"}', T)).status, 200)  // dispatched -> 200
    assert.equal((await post('/api/launch', '{"task_id":1}', T)).status, 200)           // dispatched -> 200
    assert.equal((await post('/api/open-session', '{"task_id":1}', T)).status, 200)     // dispatched -> 200
    assert.equal((await post('/api/launch-sop', '{"id":"x"}', T)).status, 200)          // dispatched -> 200
    assert.equal((await post('/api/apply-item', '{"file":"p.md","index":0}', T)).status, 200)  // dispatched -> 200
    assert.equal((await post('/api/settings', '{"key":"launch_permission","value":"ask"}', T)).status, 200)  // POST dispatched
    assert.equal((await request(brPort, '/api/settings?t=tok')).status, 200)            // GET via the engine, ?t= gated
    assert.equal((await request(brPort, '/api/settings')).status, 401)                  // GET needs the token
    assert.equal((await post('/api/launch', '{}', {})).status, 401)                     // every action is token-gated
    broker.close()
  } finally {
    // restore, but DELETE if originally unset (env[x] = undefined would set the string "undefined")
    if (prevPy === undefined) delete process.env.SMBOS_PYTHON; else process.env.SMBOS_PYTHON = prevPy
    if (prevEng === undefined) delete process.env.SMBOS_ENGINE; else process.env.SMBOS_ENGINE = prevEng
  }
})

test('serves the SPA: / token-gated + token-injected, /assets bundle, traversal blocked', async () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-spa-'))
  fs.writeFileSync(path.join(d, '.dashboard-token'), 'tok')
  const dist = path.join(d, 'dist'); fs.mkdirSync(path.join(dist, 'assets'), { recursive: true })
  fs.writeFileSync(path.join(dist, 'index.html'), '<html><head></head><body>app</body></html>')
  fs.writeFileSync(path.join(dist, 'assets', 'app.js'), 'console.log(1)')
  fs.writeFileSync(path.join(d, 'secret.txt'), 'SECRET')  // outside assets/, for the traversal test
  const prev = process.env.SMBOS_DIST; process.env.SMBOS_DIST = dist
  try {
    const broker = createBroker({ targetPort: 9, sopDir: d }); const brPort = await listen(broker)
    const noTok = await request(brPort, '/')
    assert.equal(noTok.status, 401); assert.ok(noTok.body.includes('needs its access token'))
    const ok = await request(brPort, '/?t=tok')
    assert.equal(ok.status, 200)
    assert.ok(ok.body.includes('window.__SMBOS_TOKEN__="tok"'))  // the server token, injected
    assert.equal(ok.headers['cache-control'], 'no-store')
    const asset = await request(brPort, '/assets/app.js')        // no token needed for the bundle
    assert.equal(asset.status, 200); assert.equal(asset.body, 'console.log(1)')
    assert.ok(asset.headers['content-type'].includes('javascript'))
    assert.equal((await request(brPort, '/assets/..%2f..%2fsecret.txt')).status, 404)  // traversal blocked
    fs.symlinkSync(path.join(d, 'secret.txt'), path.join(dist, 'assets', 'link'))  // symlink escaping assets/
    assert.equal((await request(brPort, '/assets/link')).status, 404)             // realpath containment blocks it
    broker.close()
  } finally {
    if (prev === undefined) delete process.env.SMBOS_DIST; else process.env.SMBOS_DIST = prev
  }
})

test('does not proxy to itself: when targetPort == its own port, an unowned path 404s (no loop)', async () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-broker-'))
  fs.writeFileSync(path.join(d, '.dashboard-token'), 'tok')
  // grab a free port, then bind the broker to it with targetPort == that same port (the cutover case:
  // the broker IS the dashboard server, so there's no upstream -- a forward would loop back forever)
  const probe = http.createServer()
  const selfPort = await listen(probe)
  await new Promise((r) => probe.close(r))
  const broker = createBroker({ targetPort: selfPort, sopDir: d })
  await new Promise((r) => broker.listen(selfPort, '127.0.0.1', r))
  try {
    const res = await request(selfPort, '/api/unknown?t=tok')  // would self-forward without the guard
    assert.equal(res.status, 404)                              // 404'd immediately, no hang
    assert.equal(JSON.parse(res.body).detail, 'not found')
  } finally {
    await new Promise((r) => broker.close(r))                  // guaranteed teardown even if an assert throws
  }
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
