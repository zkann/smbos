// Read layer for the broker (Phase 3 of the switchover): serves the STATIC dashboard reads directly
// from the SQLite work-state + the plain-file substrate, so they no longer round-trip to FastAPI.
// The liveness-bearing reads (inflight/runs) and the SSE live mirror still forward -- their flock/pid
// liveness migrates with the Phase 5 native layer.
//
// `node:sqlite` is built into Node (no native module, no ABI rebuild) but needs Node >= 22.5, so the
// desktop shell pins Electron >= 42 (embeds Node 24). Verified: `ELECTRON_RUN_AS_NODE=1 electron -e
// "require('node:sqlite')"` loads under the shipped runtime. Electron 32 (Node 20) could NOT load it.
//
// Each reader mirrors its Python counterpart exactly; the parity test (store == FastAPI) is the gate.

const { DatabaseSync } = require('node:sqlite')
const path = require('path')
const fs = require('fs')

function dbPath(sopDir) { return path.join(sopDir, 'state.db') }

function withDb(sopDir, fn) {
  const db = new DatabaseSync(dbPath(sopDir), { readOnly: true })
  // Wait out a brief lock (a Python writer mid-transaction, a WAL checkpoint, an ALTER migration)
  // instead of throwing SQLITE_BUSY, matching state_store.connect's busy_timeout.
  db.exec('PRAGMA busy_timeout = 2000')
  try { return fn(db) } finally { db.close() }
}

// 'On your plate': waiting tasks, highest priority first, then oldest. Mirrors state_store.plate.
function plate(sopDir) {
  if (!fs.existsSync(dbPath(sopDir))) return []
  return withDb(sopDir, (db) =>
    db.prepare("SELECT * FROM task WHERE status='waiting' ORDER BY priority DESC, created_at ASC, id ASC").all())
}

// Queued runs (status: queued), for 'Coming up'. Mirrors dashboard_app._queue.
function queue(sopDir) {
  const qdir = path.join(sopDir, 'queue')
  let files
  try { files = fs.readdirSync(qdir).filter((f) => f.endsWith('.md')).sort() } catch (_) { return [] }
  const out = []
  for (const f of files) {
    let text
    try { text = fs.readFileSync(path.join(qdir, f), 'utf8') } catch (_) { continue }
    const m = parseFrontmatter(text)
    if (String(m.status || '').trim() !== 'queued') continue
    out.push({ file: f, sop: m.sop || f.replace(/\.md$/, ''), project: m.project ? path.basename(m.project) : '' })
  }
  return out
}

// Minimal frontmatter parser for the simple `key: value` lines we read (matches smbos_lib for these).
function parseFrontmatter(text) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text)
  const out = {}
  if (!m) return out
  for (const line of m[1].split('\n')) {
    if (line.trimStart().startsWith('#')) continue  // skip comment lines, like smbos_lib.parse_frontmatter
    const i = line.indexOf(':')
    if (i < 0) continue
    const k = line.slice(0, i).trim()
    if (k) out[k] = line.slice(i + 1).trim()
  }
  return out
}

module.exports = { plate, queue }
