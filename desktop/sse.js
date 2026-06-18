// The /events live-mirror stream, owned by the broker (completes Phase 3: the live mirror moves off
// FastAPI). Mirrors dashboard_app.event_stream: a snapshot on connect, a fresh snapshot whenever the
// DB changes (SQLite PRAGMA data_version on a held connection) OR a file/liveness signal changes, plus
// a heartbeat. Stops on client disconnect.

const { DatabaseSync } = require('node:sqlite')
const fs = require('fs')
const path = require('path')
const store = require('./store')
const liveness = require('./liveness')

const POLL_MS = (() => { const v = Number(process.env.SMBOS_SSE_POLL); return Number.isFinite(v) && v > 0 ? v * 1000 : 1000 })()
const HEARTBEAT_MS = (() => { const v = Number(process.env.SMBOS_SSE_HEARTBEAT); return Number.isFinite(v) && v > 0 ? v * 1000 : 10000 })()

function sse(event, payload) {
  return `event: ${event}\ndata: ${payload}\n\n`
}

// The five live-mirror frames, each the BARE array (dashboard_app._snapshot uses json.dumps(list),
// not a {key: list} wrapper -- the SSE shape differs from the GET endpoints' wrapped shape).
function snapshot(sopDir) {
  return [
    sse('plate', JSON.stringify(store.plate(sopDir))),
    sse('inflight', JSON.stringify(liveness.inflightWithLiveness(store, sopDir))),
    sse('pending', JSON.stringify(store.pending(sopDir))),
    sse('queue', JSON.stringify(store.queue(sopDir))),
    sse('runs', JSON.stringify(liveness.runsWithLiveness(store, sopDir))),
  ]
}

// [name, mtime-ns] over dir/*.md, sorted, tolerant of a file vanishing between readdir and stat.
// Mirrors dashboard_app._dir_mtime_sig: pending/ and queue/ change with no DB write, so data_version
// misses them. Nanosecond mtime (like Python st_mtime_ns) catches two sub-millisecond rewrites.
function dirSig(dir) {
  const sig = []
  let names
  try { names = fs.readdirSync(dir) } catch (_) { return [] }
  for (const f of names) {
    if (!f.endsWith('.md')) continue
    try { sig.push([f, String(fs.statSync(path.join(dir, f), { bigint: true }).mtimeNs)]) } catch (_) { /* vanished */ }
  }
  return sig.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
}

// Change signals that a DB write wouldn't move: run liveness, session liveness, and the file-based
// pending/ + queue/ dirs. verify=false keeps the once-a-second poll cheap (no ps fork) -- it catches
// the common pid-gone flip; the rendered frame does the full check. Mirrors the _signals() tuple.
// JSON-encoded structured values (not delimiter-joined) so an id/filename can't collide on a separator.
function signals(sopDir) {
  return JSON.stringify([
    liveness.activeRuns(sopDir, false).map((r) => [r.sop, r.state]).sort(),
    liveness.inflightWithLiveness(store, sopDir, false).map((t) => [t.id, t.state]),
    dirSig(path.join(sopDir, 'pending')),
    dirSig(path.join(sopDir, 'queue')),
  ])
}

// Run the SSE loop on an already-Host-guarded, token-checked GET /events request.
function createEventStream(req, res, sopDir) {
  res.writeHead(200, {
    'content-type': 'text/event-stream',
    'cache-control': 'no-cache',
    connection: 'keep-alive',
    'x-accel-buffering': 'no',  // don't let any proxy buffer the stream
  })
  // One held read-only connection so data_version is comparable across polls (it's per-connection).
  let db = null
  let timer = null
  const cleanup = () => {
    if (timer) { clearInterval(timer); timer = null }
    if (db) { try { db.close() } catch (_) { /* already gone */ } db = null }
  }
  // Attach cleanup BEFORE the first store/liveness read: if a read throws (corrupt/mid-recreate
  // state.db), we must still release the connection + timer and not leak or crash the broker.
  res.on('close', cleanup)
  res.on('error', cleanup)

  // Open lazily and re-open on error, so a state.db that doesn't exist yet at connect (fresh SOP dir)
  // or is recreated mid-stream gets picked up -- otherwise data_version stays 0 forever and DB-only
  // changes (a new waiting task) never re-emit until the client reconnects.
  const ensureDb = () => {
    if (db) return
    try { db = new DatabaseSync(path.join(sopDir, 'state.db'), { readOnly: true }); db.exec('PRAGMA busy_timeout = 2000') } catch (_) { db = null }
  }
  const dataVersion = () => {
    ensureDb()
    try { return db ? db.prepare('PRAGMA data_version').get().data_version : 0 } catch (_) { db = null; return 0 }
  }

  try {

    let lastDv = dataVersion()
    let lastSig = signals(sopDir)
    for (const frame of snapshot(sopDir)) res.write(frame)  // initial snapshot

    let sinceBeat = 0
    timer = setInterval(() => {
      // Guard the WHOLE tick: dataVersion, signals, AND the snapshot re-emit. A synchronous store/
      // liveness read error (a mid-stream corrupt/recreating state.db) must not escape the interval
      // callback and crash the broker -- skip the tick and try again next poll.
      try {
        sinceBeat += POLL_MS
        const dv = dataVersion()
        const sig = signals(sopDir)
        if (dv !== lastDv || sig !== lastSig) {
          lastDv = dv; lastSig = sig
          for (const frame of snapshot(sopDir)) res.write(frame)  // all frames on any change
        }
        if (sinceBeat >= HEARTBEAT_MS) {
          sinceBeat = 0
          res.write(sse('heartbeat', JSON.stringify({ ts: new Date().toISOString() })))
        }
      } catch (_) { /* transient read error: skip this tick */ }
    }, POLL_MS)
  } catch (_) {
    // the initial snapshot/signals read failed: tear down cleanly instead of leaking + throwing
    cleanup()
    try { res.end() } catch (_) { /* already closed */ }
  }
}

module.exports = { createEventStream, snapshot, signals }
