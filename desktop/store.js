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

// Strict UTF-8 read: THROWS on invalid bytes (Node's 'utf8' silently substitutes U+FFFD), so a
// corrupt SOP/queue file is skipped by the caller's try/catch, matching Python read_text(encoding=utf-8).
const utf8Strict = new TextDecoder('utf-8', { fatal: true })
function readTextStrict(p) {
  return utf8Strict.decode(fs.readFileSync(p))
}

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

// in_flight tasks, same ordering as the plate (mirrors state_store.in_flight). The liveness `state`
// is added by liveness.inflightWithLiveness, not here.
function inFlight(sopDir) {
  if (!fs.existsSync(dbPath(sopDir))) return []
  return withDb(sopDir, (db) =>
    db.prepare("SELECT * FROM task WHERE status='in_flight' ORDER BY priority DESC, created_at ASC, id ASC").all())
}

// Recent run rows, newest first (mirrors state_store.recent_runs). The liveness `state` is added by
// liveness.runsWithLiveness, not here.
function recentRuns(sopDir, limit = 50) {
  if (!fs.existsSync(dbPath(sopDir))) return []
  return withDb(sopDir, (db) =>
    db.prepare('SELECT * FROM run ORDER BY started_at DESC, id DESC LIMIT ?').all(limit))
}

// Queued runs (status: queued), for 'Coming up'. Mirrors dashboard_app._queue.
function queue(sopDir) {
  const qdir = path.join(sopDir, 'queue')
  let files
  try { files = fs.readdirSync(qdir).filter((f) => f.endsWith('.md')).sort() } catch (_) { return [] }
  const out = []
  for (const f of files) {
    let text
    try { text = readTextStrict(path.join(qdir, f)) } catch (_) { continue }  // skip unreadable/non-utf8
    const m = parseFrontmatter(text)
    if (String(m.status || '').trim() !== 'queued') continue
    out.push({ file: f, sop: m.sop || f.replace(/\.md$/, ''), project: m.project ? path.basename(m.project) : '' })
  }
  return out
}

// SOP files for the Procedures view, skipping runtime dirs / index / template / dotfiles (mirrors
// smbos_lib.iter_sops: rglob *.md, sorted, with the same skip set).
const SKIP_NAMES = new Set(['INDEX.md', '_template.md', 'DIGEST.md'])
const SKIP_DIRS = new Set(['pending', 'payloads', 'triggers', 'queue', 'work', 'active-runs', 'active-sessions', 'archive'])

function collectMd(dir, acc) {
  let entries
  try { entries = fs.readdirSync(dir, { withFileTypes: true }) } catch (_) { return acc }
  for (const e of entries) {
    const full = path.join(dir, e.name)
    if (e.isDirectory()) {
      if (!SKIP_DIRS.has(e.name)) collectMd(full, acc)  // prune runtime/archive dirs (don't descend)
    } else if (e.name.endsWith('.md')) {
      acc.push(full)
    }
  }
  return acc
}

function iterSops(sopDir) {
  return collectMd(sopDir, [])
    // sort by path COMPONENTS, mirroring Python's sorted(Path.rglob) tuple compare -- a full-string
    // sort orders '/' (0x2F) vs '-' (0x2D) differently, so nested-vs-prefix-sharing paths would diverge.
    .sort((a, b) => {
      const pa = path.relative(sopDir, a).split(path.sep)
      const pb = path.relative(sopDir, b).split(path.sep)
      for (let i = 0; i < Math.min(pa.length, pb.length); i++) {
        if (pa[i] < pb[i]) return -1
        if (pa[i] > pb[i]) return 1
      }
      return pa.length - pb.length
    })
    // SKIP_DIRS are already pruned above; here just drop index/template/dotfiles by name (a dot-DIR is
    // kept, matching Python iter_sops, which only skips dotfiles by filename).
    .filter((full) => {
      const name = path.basename(full)
      return !SKIP_NAMES.has(name) && !name.startsWith('.')
    })
}

// Derive a procedure's autonomy level from its frontmatter (mirrors smbos_lib.autonomy_level_from_meta).
const AUTONOMY_LEVELS = new Set(['with_me', 'prepare_ask', 'on_its_own'])
function autonomyFromMeta(meta) {
  const val = String(meta.autonomy || '').trim().toLowerCase()
  if (AUTONOMY_LEVELS.has(val)) return val
  if (['true', 'yes', '1'].includes(String(meta.interactive_only || '').trim().toLowerCase())) return 'with_me'
  const status = String(meta.status || 'draft').trim().toLowerCase()
  return (status === 'active' || status === 'trusted') ? 'on_its_own' : 'prepare_ask'
}

// Per-SOP cost estimate (MEDIAN of prior 'ok' runs) from runs.jsonl (mirrors dashboard_app._cost_estimates).
function costEstimates(sopDir) {
  let lines = []
  try { lines = fs.readFileSync(path.join(sopDir, 'runs.jsonl'), 'utf8').split('\n') } catch (_) { /* none yet */ }
  const bySop = {}
  for (const line of lines) {
    let r
    try { r = JSON.parse(line) } catch (_) { continue }
    const cost = r.cost_usd
    if (typeof cost !== 'number' || !Number.isFinite(cost) || cost < 0) continue  // typeof excludes bool
    if (r.result === 'ok') {
      const s = String(r.sop || '')
      ;(bySop[s] = bySop[s] || []).push(cost)
    }
  }
  const estimates = {}
  for (const sop of Object.keys(bySop)) {
    const costs = bySop[sop].sort((a, b) => a - b)  // NUMERIC sort (JS default is lexicographic)
    const n = costs.length
    const med = n % 2 ? costs[(n - 1) / 2] : (costs[n / 2 - 1] + costs[n / 2]) / 2
    // round-half-up vs Python's round() half-to-even can differ by $0.0001 only on an exact-half
    // median (rare; sub-cent; the UI shows cents) -- accepted tolerance, not chased to banker's rounding.
    estimates[sop] = { estimate: Math.round(med * 1e4) / 1e4, n }
  }
  return estimates
}

// The Procedures view: each SOP with the facts the UI needs to pick its action. Mirrors
// dashboard_app._procedures (id/title/draft/interactive/needs_inputs/cost/autonomy), sorted by title.
function procedures(sopDir) {
  const ests = costEstimates(sopDir)
  const out = []
  for (const p of iterSops(sopDir)) {
    let m
    try { m = parseFrontmatter(readTextStrict(p)) } catch (_) { continue }  // skip unreadable/non-utf8 SOP
    const sid = m.id || path.basename(p, '.md')
    out.push({
      id: sid,
      title: m.title || sid,
      draft: !['active', 'trusted'].includes(String(m.status || '').trim().toLowerCase()),
      interactive: ['true', 'yes', '1'].includes(String(m.interactive_only || '').trim().toLowerCase()),
      needs_inputs: Boolean(m.run_inputs),
      cost: Object.prototype.hasOwnProperty.call(ests, sid) ? ests[sid] : null,  // {estimate,n} or null
      autonomy: autonomyFromMeta(m),
    })
  }
  return out.sort((a, b) => (a.title.toLowerCase() < b.title.toLowerCase() ? -1 : a.title.toLowerCase() > b.title.toLowerCase() ? 1 : 0))
}

// A parked result's `## Candidates` fenced-json block as [{title,url,note}] (mirrors
// generate_dashboard.parse_candidates). Empty on absent/malformed; never throws.
function parseCandidates(content) {
  const m = /^##\s+Candidates\s*$[\s\S]*?```json\s*([\s\S]*?)```/m.exec(content)
  if (!m) return []
  let data
  // JSON.parse rejects bare NaN/Infinity (which aren't valid JSON) where Python json.loads accepts
  // them, so such a non-standard block yields [] here vs a parsed list in Python. Accepted divergence:
  // candidate fields are contract-typed strings, and regex-stripping NaN would corrupt a string value
  // that legitimately contains "NaN".
  try { data = JSON.parse(m[1]) } catch (_) { return [] }
  if (!Array.isArray(data)) return []
  const str = (v) => (typeof v === 'string' ? v : '')        // non-string field -> '' (Python str() of a
  const cut = (v, n) => Array.from(v).slice(0, n).join('')   // list/dict is junk too); truncate by CODE POINT (Python [:n])
  const out = []
  for (const d of data) {
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      out.push({
        title: cut(str(d.title) || str(d.url) || 'Item', 140),
        url: cut(str(d.url), 500),
        note: cut(str(d.note), 300),
      })
    }
  }
  return out
}

// First .md file named `${sopId}.md` anywhere under sopDir (mirrors Python rglob -- NOT pruned, so it
// finds a source SOP even outside the iter_sops set). null if none.
function findSopFile(dir, name) {
  let entries
  try { entries = fs.readdirSync(dir, { withFileTypes: true }) } catch (_) { return null }
  for (const e of entries) if (e.isFile() && e.name === name) return path.join(dir, e.name)
  for (const e of entries) {
    if (e.isDirectory()) { const f = findSopFile(path.join(dir, e.name), name); if (f) return f }
  }
  return null
}

// The first `next:` SOP id declared by sopId (mirrors generate_dashboard.sop_next).
function sopNext(sopDir, sopId) {
  if (!sopId) return null
  const p = findSopFile(sopDir, `${sopId}.md`)
  if (!p) return null
  let meta
  try { meta = parseFrontmatter(readTextStrict(p)) } catch (_) { return null }
  return String(meta.next || '').split(',')[0].trim() || null
}

// Parked results awaiting a decision (status: pending), for 'Needs your eyes'. Mirrors
// dashboard_app._pending over generate_dashboard.collect_pending: human title from the body's
// '# Pending: X' heading, the candidate list, and the downstream SOP for an apply.
function pending(sopDir) {
  const pdir = path.join(sopDir, 'pending')
  let files
  try { files = fs.readdirSync(pdir).filter((f) => f.endsWith('.md')).sort() } catch (_) { return [] }
  const out = []
  for (const f of files) {
    let content
    try { content = readTextStrict(path.join(pdir, f)) } catch (_) { continue }  // skip unreadable/non-utf8
    const meta = parseFrontmatter(content)
    if (String(meta.status || '').trim() !== 'pending') continue
    const m = /^#\s+(?:Pending:\s*)?(.+)$/m.exec(content)
    const title = m ? m[1].trim() : (meta.sop || f)
    const candidates = parseCandidates(content)
    out.push({
      file: f,
      sop: meta.sop || '',
      title,
      candidates,
      next: candidates.length ? sopNext(sopDir, meta.sop) : null,
    })
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

module.exports = { plate, queue, procedures, pending, inFlight, recentRuns }
