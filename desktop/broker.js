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
    // POST /api/run (Phase 4): gate the HTTP, then invoke the engine. HEADER token (the writes' CSRF
    // posture), not ?t=, matching FastAPI's check(request.headers["x-smbos-token"]).
    if (req.method === 'POST' && pathname === '/api/run' && sopDir) {
      if (!tokenOk(req.headers['x-smbos-token'], token({ SOP_DIR: sopDir }))) {
        res.writeHead(401, { 'content-type': 'application/json' })
        res.end(JSON.stringify({ detail: 'bad or missing token' }))
        return
      }
      const sendJson = (code, obj) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(obj)) }
      readBody(req).then(async (raw) => {
        let body
        try { body = JSON.parse(raw) } catch (_) { return sendJson(400, { detail: 'invalid JSON body' }) }
        if (!body || typeof body !== 'object' || Array.isArray(body)) return sendJson(400, { detail: 'body must be a JSON object' })
        const id = String(body.id || '').toLowerCase().replace(/[^a-z0-9-]/g, '').replace(/^-+/, '')  // engine re-sanitizes
        const inputs = String(body.inputs || '').trim()
        const prepare = String(body.mode || '').trim().toLowerCase() === 'prepare'
        const argv = ['run', sopDir, id]
        if (prepare) argv.push('--prepare')
        // inputs ride on STDIN (not argv): avoids the ARG_MAX limit for long owner inputs and the
        // argparse "looks like an option" misparse of a dash-leading value -- matches FastAPI's
        // in-process pass-through.
        if (inputs) argv.push('--inputs-stdin')
        const { code, json } = await actions.runAction(argv, inputs || '')
        if (code === 0) sendJson(200, json || {})
        else if (code === 3) sendJson(409, json || { detail: 'refused' })       // gate refusal
        else sendJson(500, json || { detail: 'the engine could not start that run' })
      }, () => sendJson(400, { detail: 'could not read the request body' }))  // readBody rejection ONLY
        .catch(() => { try { if (!res.headersSent) sendJson(500, { detail: 'internal error' }) } catch (_) { /* sent */ } })
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
        payload = serve(sopDir)
      } catch (_) {
        res.writeHead(500, { 'content-type': 'application/json' })
        res.end(JSON.stringify({ detail: 'could not read the dashboard state' }))
        return
      }
      res.writeHead(200, { 'content-type': 'application/json' })
      res.end(JSON.stringify(payload))
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
