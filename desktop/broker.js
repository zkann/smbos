// SmbOS desktop broker -- Phases 2-3 of the strangler-fig switchover.
//
// The single front door the Electron renderer talks to. It SERVES the static reads (plate / queue /
// settings) directly from the SQLite work-state + plain files (Phase 3), and FORWARDS everything else
// to FastAPI -- the liveness-bearing reads (inflight/runs) and the SSE live mirror keep forwarding,
// since their flock/pid liveness migrates with the Phase 5 native layer. Forwarded responses are
// streamed (SSE-safe).
//
// Loopback only. For what it FORWARDS, FastAPI owns the token gate; for what it SERVES, the broker
// owns the token gate itself (FastAPI's check doesn't run on a broker-served response).

const http = require('http')
const crypto = require('crypto')
const store = require('./store')
const liveness = require('./liveness')
const sse = require('./sse')
const actions = require('./actions')
const spa = require('./spa')
const { token } = require('./resolve')

// POST action endpoints the broker owns (Phase 4): it gates the HTTP (Host + HEADER token, the CSRF
// posture the writes use) then invokes the Python engine-action CLI, which reuses the exact stdlib
// gate/spawn -- no FastAPI in the action path, no re-implemented cage in Node.
function readBody(req, limit = 1 << 20, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const chunks = []
    let len = 0
    const timer = setTimeout(() => { reject(new Error('body timeout')); req.destroy() }, timeoutMs)  // slow-loris guard
    req.on('data', (c) => {
      len += c.length  // bytes
      if (len > limit) { clearTimeout(timer); reject(new Error('body too large')); req.destroy(); return }
      chunks.push(c)  // buffer the raw chunks; decode once at the end so a multibyte char split
    })                // across a TCP chunk boundary isn't corrupted
    req.on('end', () => { clearTimeout(timer); resolve(Buffer.concat(chunks).toString('utf8')) })
    req.on('error', (e) => { clearTimeout(timer); reject(e) })
  })
}

// POST action routes -> { argv, input } for the engine CLI. A value that could begin with '-' uses
// the --opt=value form so argparse never misparses it as an option; the run id is slug-sanitized
// (the engine re-sanitizes). Returns null for an unknown path.
const sanitizeId = (v) => String(v || '').toLowerCase().replace(/[^a-z0-9-]/g, '').replace(/^-+/, '')  // slug, no leading '-' (engine re-sanitizes)

function actionRequest(pathname, sopDir, body) {
  switch (pathname) {
    case '/api/run': {
      const argv = ['run', sopDir, sanitizeId(body.id)]
      if (String(body.mode || '').trim().toLowerCase() === 'prepare') argv.push('--prepare')
      const inputs = String(body.inputs || '').trim()
      if (inputs) argv.push('--inputs-stdin')  // inputs ride on stdin (unbounded; no argparse misparse)
      return { argv, input: inputs }
    }
    case '/api/queue': {
      const argv = ['queue', sopDir, sanitizeId(body.id), '--scope=' + String(body.scope || 'here')]
      // 'Queue here' persists a project: folder that LATER launches the run's session. The broker's
      // own cwd (an Electron app dir, maybe /) is NOT a meaningful launch folder, so pass it only when
      // the desktop app sets $SMBOS_LAUNCH_CWD; otherwise omit it -> the engine uses None and a
      // folder-less SOP just gets no project (never an unrelated directory).
      if (process.env.SMBOS_LAUNCH_CWD) argv.push('--launch-cwd=' + process.env.SMBOS_LAUNCH_CWD)
      const inputs = String(body.inputs || '').trim()
      if (inputs) argv.push('--inputs-stdin')
      return { argv, input: inputs }
    }
    case '/api/autonomy':
      return { argv: ['autonomy', sopDir, sanitizeId(body.id), '--level=' + String(body.level || '')] }
    case '/api/launch':
      return { argv: ['launch', sopDir, '--task-id=' + String(body.task_id || '')] }
    case '/api/launch-tracker':
      return { argv: ['launch-tracker', sopDir, '--tracker-id=' + String(body.tracker_id || '')] }
    case '/api/open-session':
      return { argv: ['open-session', sopDir, '--task-id=' + String(body.task_id || '')] }
    case '/api/launch-sop':
      return { argv: ['launch-sop', sopDir, sanitizeId(body.id)] }
    case '/api/apply-item':
      return { argv: ['apply-item', sopDir, '--file=' + String(body.file || ''), '--index=' + String(body.index ?? '')] }
    case '/api/resolve':
      return { argv: ['resolve', sopDir, '--file=' + String(body.file || ''), '--decision=' + String(body.decision || '')] }
    case '/api/dequeue':
      return { argv: ['dequeue', sopDir, '--file=' + String(body.file || '')] }
    case '/api/task-status':
      return { argv: ['task-status', sopDir, '--task-id=' + String(body.task_id || ''), '--status=' + String(body.status || ''), '--from=' + String(body.from || '')] }
    case '/api/settings':
      return { argv: ['settings-set', sopDir, '--key=' + String(body.key || ''), '--value=' + String(body.value ?? '')] }
    case '/api/job-set':
      // the whole edit (name + fields) rides on stdin: the description is free text, unsafe as argv
      return { argv: ['job-set', sopDir], input: JSON.stringify(body || {}) }
    case '/api/job-create':
      // the new spec (incl. a free-text command + description) rides on stdin, never argv
      return { argv: ['job-create', sopDir], input: JSON.stringify(body || {}) }
    case '/api/job-delete':
      return { argv: ['job-delete', sopDir, '--name=' + sanitizeId(body.name)] }
    case '/api/job-build':
      // the free-text intent rides on stdin; the engine opens a primed Claude session to build the job
      return { argv: ['job-build', sopDir], input: JSON.stringify(body || {}) }
    default:
      return null
  }
}

const ACTION_PATHS = new Set(['/api/run', '/api/queue', '/api/autonomy', '/api/launch', '/api/launch-tracker', '/api/open-session', '/api/launch-sop', '/api/apply-item', '/api/resolve', '/api/dequeue', '/api/task-status', '/api/settings', '/api/job-set', '/api/job-create', '/api/job-delete', '/api/job-build'])
const EXIT_STATUS = { 0: 200, 3: 409, 4: 404, 8: 400, 9: 409 }  // engine exit code -> HTTP status; anything else -> 500

// GET endpoints the broker answers itself, in FastAPI's response shape (parity-tested against the
// live FastAPI). The static reads come from the store; inflight/runs add the Node-derived liveness
// (Phase 5 pulled forward -- pid+sig in place of the flock). Cost/autonomy numbers ride as JSON
// numbers, so a whole dollar serializes as `1` here vs `1.0` in Python -- semantically identical
// after JSON.parse (what the SPA does), so the parity check compares parsed values, not bytes.
// Still forwarded: settings (reads an environment-detected terminal) and the /events SSE stream.
const SERVED = {
  '/api/plate': (sopDir) => ({ plate: store.plate(sopDir) }),
  '/api/queue': (sopDir) => ({ queue: store.queue(sopDir) }),
  '/api/procedures': (sopDir) => ({ procedures: store.procedures(sopDir) }),
  '/api/pending': (sopDir) => ({ pending: store.pending(sopDir) }),
  '/api/inflight': (sopDir) => ({ inflight: liveness.inflightWithLiveness(store, sopDir) }),
  '/api/runs': (sopDir) => ({ runs: liveness.runsWithLiveness(store, sopDir) }),
  '/api/trackers': (sopDir) => ({ trackers: store.trackers(sopDir) }),
  '/api/tracker': (sopDir, q) => ({ tracker: store.getTracker(sopDir, q && q.get('id')) }),
}

// Constant-time token compare (the broker now gates the reads it serves, mirroring FastAPI's check).
function tokenOk(provided, expected) {
  if (!expected || !provided) return false
  const a = Buffer.from(String(provided))
  const b = Buffer.from(String(expected))
  return a.length === b.length && crypto.timingSafeEqual(a, b)
}

// Hop-by-hop headers must not be forwarded by a proxy (RFC 7230 6.1). In practice Node + a loopback
// upstream rarely sets these, but strip them so we never proxy a stale connection/keep-alive header.
const HOP_BY_HOP = new Set([
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailer', 'transfer-encoding', 'upgrade',
])

function filterHeaders(headers, overrides) {
  const out = {}
  for (const [k, v] of Object.entries(headers)) {
    if (!HOP_BY_HOP.has(k.toLowerCase())) out[k] = v
  }
  return { ...out, ...overrides }
}

// Build a reverse-proxy server forwarding to http://targetHost:targetPort. Does NOT call listen();
// the caller binds it (127.0.0.1:0 for a free port). Throws if targetPort isn't a real port, so a
// bad caller can't silently turn the broker into a proxy to port 80.
function createBroker({ targetHost = '127.0.0.1', targetPort, sopDir }) {
  if (!Number.isInteger(targetPort) || targetPort < 1 || targetPort > 65535) {
    throw new TypeError(`createBroker: targetPort must be a valid port (got ${targetPort})`)
  }
  return http.createServer((req, res) => {
    // Host guard (the DNS-rebinding defense): the broker overrides Host before forwarding, so
    // FastAPI's own _guard_host would always see loopback -- the broker must re-enforce it here, as
    // the new front door, or a rebinding request to the broker's port would slip through. Mirrors
    // dashboard_app._guard_host; holds even with a valid token.
    const hostname = String(req.headers.host || '').split(':')[0]
    if (hostname !== '127.0.0.1' && hostname !== 'localhost') {
      res.writeHead(403, { 'content-type': 'text/plain' })
      res.end('forbidden host')
      return
    }
    // Serve a static read directly from the store (Phase 3). The broker owns the token gate for
    // these, since FastAPI's check never runs on a broker-served response.
    const pathname = req.url.split('?')[0]
    // The broker serves the built SPA itself (/ token-gated with the token injected, /assets the
    // secret-free bundle), so FastAPI no longer serves the page.
    if (req.method === 'GET' && pathname === '/' && sopDir) {
      try { spa.serveIndex(req, res, sopDir) } catch (_) { try { if (!res.headersSent) res.writeHead(500); res.end() } catch (_) { /* sent */ } }
      return
    }
    if (req.method === 'GET' && pathname.startsWith('/assets/') && sopDir) {
      let rel
      try { rel = decodeURIComponent(pathname.slice('/assets/'.length)) } catch (_) { res.writeHead(404); res.end(); return }
      try { spa.serveAsset(req, res, rel) } catch (_) { try { if (!res.headersSent) res.writeHead(500); res.end() } catch (_) { /* sent */ } }
      return
    }
    // The /events live-mirror stream is served by the broker (Phase 3 complete): token-gated, then
    // a long-lived SSE response instead of a JSON body.
    if (req.method === 'GET' && pathname === '/events' && sopDir) {
      const t = new URL(req.url, 'http://x').searchParams.get('t')
      if (!tokenOk(t, token({ SOP_DIR: sopDir }))) {
        res.writeHead(401, { 'content-type': 'application/json' })
        res.end(JSON.stringify({ detail: 'bad or missing token' }))
        return
      }
      try { sse.createEventStream(req, res, sopDir) } catch (_) {
        try { if (!res.headersSent) res.writeHead(500); res.end() } catch (_) { /* already closed */ }
      }
      return
    }
    // POST action endpoints (Phase 4): HEADER token (the writes' CSRF posture, not ?t=, matching
    // FastAPI's check(headers["x-smbos-token"])), then invoke the engine CLI and map its exit code.
    if (req.method === 'POST' && ACTION_PATHS.has(pathname) && sopDir) {
      if (!tokenOk(req.headers['x-smbos-token'], token({ SOP_DIR: sopDir }))) {
        res.writeHead(401, { 'content-type': 'application/json' })
        res.end(JSON.stringify({ detail: 'bad or missing token' }))
        return
      }
      const sendJson = (code, obj) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(obj)) }
      readBody(req).then((raw) => {
        let body
        try { body = JSON.parse(raw) } catch (_) { return sendJson(400, { detail: 'invalid JSON body' }) }
        if (!body || typeof body !== 'object' || Array.isArray(body)) return sendJson(400, { detail: 'body must be a JSON object' })
        const spec = actionRequest(pathname, sopDir, body)
        if (!spec) return sendJson(404, { detail: 'unknown action' })
        return actions.runAction(spec.argv, spec.input || '').then(({ code, json }) => {
          const status = EXIT_STATUS[code] || 500
          sendJson(status, json || { detail: status === 500 ? 'the engine could not complete that action' : 'refused' })
        })
      }, () => sendJson(400, { detail: 'could not read the request body' }))  // readBody rejection ONLY
        .catch(() => { try { if (!res.headersSent) sendJson(500, { detail: 'internal error' }) } catch (_) { /* sent */ } })
      return
    }
    // GET /api/settings is answered via the engine (its terminal field is env-detected, not a pure
    // file read), token-gated by ?t= like the other reads.
    if (req.method === 'GET' && pathname === '/api/settings' && sopDir) {
      const t = new URL(req.url, 'http://x').searchParams.get('t')
      if (!tokenOk(t, token({ SOP_DIR: sopDir }))) {
        res.writeHead(401, { 'content-type': 'application/json' })
        res.end(JSON.stringify({ detail: 'bad or missing token' }))
        return
      }
      actions.runAction(['settings-get', sopDir]).then(({ code, json }) => {
        res.writeHead(code === 0 ? 200 : 500, { 'content-type': 'application/json' })
        res.end(JSON.stringify(code === 0 ? (json || {}) : { detail: 'could not read the settings' }))
      }).catch(() => { try { if (!res.headersSent) { res.writeHead(500); res.end() } } catch (_) { /* sent */ } })
      return
    }
    const serve = req.method === 'GET' && sopDir ? SERVED[pathname] : undefined
    if (serve) {
      const t = new URL(req.url, 'http://x').searchParams.get('t')
      if (!tokenOk(t, token({ SOP_DIR: sopDir }))) {
        res.writeHead(401, { 'content-type': 'application/json' })
        res.end(JSON.stringify({ detail: 'bad or missing token' }))
        return
      }
      let payload
      try {
        payload = serve(sopDir, new URL(req.url, 'http://x').searchParams)
      } catch (_) {
        res.writeHead(500, { 'content-type': 'application/json' })
        res.end(JSON.stringify({ detail: 'could not read the dashboard state' }))
        return
      }
      res.writeHead(200, { 'content-type': 'application/json' })
      res.end(JSON.stringify(payload))
      return
    }
    // Don't proxy to ourselves: when the broker IS the dashboard server (it bound the dashboard port,
    // so targetPort == our own port), an unowned path would otherwise loop back into this same server
    // forever. Once the broker owns the whole surface there's no upstream to reach, so 404 it.
    if (targetPort === req.socket.localPort) {
      res.writeHead(404, { 'content-type': 'application/json' })
      res.end(JSON.stringify({ detail: 'not found' }))
      return
    }
    // address the upstream correctly (override Host); forward everything else verbatim
    const headers = filterHeaders(req.headers, { host: `${targetHost}:${targetPort}` })
    const upstream = http.request(
      { host: targetHost, port: targetPort, method: req.method, path: req.url, headers },
      (up) => {
        // verbatim pass-through (minus hop-by-hop). The verbatim copy is load-bearing for set-cookie,
        // which Node keeps as an ARRAY in up.headers; don't normalize it to a string.
        res.writeHead(up.statusCode || 502, filterHeaders(up.headers, {}))
        up.pipe(res)  // stream the response body -- SSE-safe (no buffering)
      },
    )
    upstream.on('error', () => {
      if (res.headersSent) { res.destroy(); return }  // mid-stream failure: don't append to a partial body
      res.writeHead(502, { 'content-type': 'text/plain' })
      res.end('broker: dashboard not reachable')
    })
    // Tear down the upstream if the client goes away (an SSE reconnect, a window reload, an abort), so
    // its socket doesn't dangle for the life of the tray app.
    req.on('error', () => upstream.destroy())
    res.on('close', () => { if (!res.writableEnded) upstream.destroy() })
    req.pipe(upstream)  // forward the request body (POST bodies)
  })
}

module.exports = { createBroker, HOP_BY_HOP }
