// Liveness in Node (Phase 5 pulled forward): the broker derives run + session liveness itself, no
// FastAPI dependency.
//
// Session liveness is a faithful port of smbos_lib.session_state -- pid existence (process.kill(pid,0))
// plus a ps start-time signature to defend against pid reuse.
//
// Run liveness: Python's authority is the flock on triggers/<sop>.lock, which pure Node can't probe
// (no flock syscall without a native addon, which would break the test-vs-Electron ABI). The marker
// active-runs/<sop>__<pid>.json already records the runner's pid; run_sop now also records its
// `proc_sig`. Since the SAME run_sop process holds the flock AND wrote the marker, "marker pid alive
// (with a matching start-sig)" is equivalent to "flock held" -- so this reproduces active_runs'
// running/stalled split without the flock. The flock stays as the run GATE; this only reads liveness.

const fs = require('fs')
const path = require('path')
const { execFileSync } = require('child_process')

const RUN_STALE_AFTER_S = 1200  // smbos_lib._RUN_STALE_AFTER_S
const STARTUP_GRACE_SECONDS = (() => {
  const v = Number(process.env.SMBOS_INFLIGHT_GRACE)
  return Number.isFinite(v) && v > 0 ? v : 120  // dashboard_app.STARTUP_GRACE_SECONDS default
})()

// A clean non-negative integer pid, or null -- matching Python int(): "123abc"/"1e3"/"0x10" are
// rejected (parseInt would silently accept them and probe the wrong process).
function toPid(v) {
  const s = String(v).trim()
  if (!/^\d+$/.test(s)) return null
  const n = Number(s)
  return Number.isSafeInteger(n) ? n : null
}

// Opaque start-time string for pid from ps, or null (mirrors smbos_lib._proc_start_sig).
function procStartSig(pid) {
  try {
    return execFileSync('ps', ['-o', 'lstart=', '-p', String(toPid(pid))],
      { timeout: 5000, encoding: 'utf8' }).trim() || null
  } catch (_) {
    return null
  }
}

// Is `pid` a zombie (exited, not yet reaped)? A zombie still answers kill(0) and ps lstart, but the
// run's flock was released the instant it exited -- so for RUN liveness (which the flock authoritatively
// gates) a zombie must read as not-running, or Node would say 'running' where Python says 'stalled'.
function isZombie(pid) {
  try {
    return execFileSync('ps', ['-o', 'state=', '-p', String(toPid(pid))],
      { timeout: 5000, encoding: 'utf8' }).trim().startsWith('Z')
  } catch (_) {
    return false  // ps can't answer -> inconclusive, don't force stalled
  }
}

// 'gone' (no such process) | 'alive' (ours) | 'other' (exists, not ours -- still alive).
function pidExists(pid) {
  try { process.kill(pid, 0); return 'alive' } catch (e) { return e.code === 'EPERM' ? 'other' : 'gone' }
}

// Is the run recorded by this marker still alive? pid existence + (when verifying) NOT a zombie and a
// start-sig match. Equivalent to the flock being held: the flock releases on exit (even into a zombie),
// so the zombie guard is what keeps a just-crashed run from reading 'running'.
function runnerAlive(marker, verify) {
  const pid = toPid(marker.pid)
  if (pid === null) return false
  if (pidExists(pid) === 'gone') return false
  if (verify) {
    if (isZombie(pid)) return false  // flock would already be released
    if (marker.proc_sig) {
      const cur = procStartSig(pid)
      if (cur !== null && cur !== marker.proc_sig) return false  // positive mismatch only: pid recycled
    }
  }
  return true
}

// sop_id -> 'running'|'stalled' for the active-runs markers (mirrors smbos_lib.active_runs, pid+sig
// in place of the flock). Age-bounded by the stale backstop like the Python.
function activeRuns(sopDir, verify = true) {
  const d = path.join(sopDir, 'active-runs')
  let files
  try { files = fs.readdirSync(d).filter((f) => f.endsWith('.json')).sort() } catch (_) { return [] }
  const now = Date.now()
  const out = []
  for (const f of files) {
    let m
    try { m = JSON.parse(fs.readFileSync(path.join(d, f), 'utf8')) } catch (_) { continue }
    let age = (now - Date.parse(m.started)) / 1000
    if (!Number.isFinite(age)) age = RUN_STALE_AFTER_S + 1
    const running = age <= RUN_STALE_AFTER_S && runnerAlive(m, verify)
    out.push({ sop: m.sop || f.replace(/__\d+\.json$/, ''), state: running ? 'running' : 'stalled' })
  }
  return out
}

// Liveness of the picked-up session for taskId: 'live' | 'stalled' | null (no marker yet). Faithful
// port of smbos_lib.session_state.
function sessionState(sopDir, taskId, verify = true) {
  let raw
  try {
    raw = fs.readFileSync(path.join(sopDir, 'active-sessions', String(parseInt(taskId, 10))), 'utf8').split('\n')
  } catch (_) {
    return null
  }
  if (!raw.length || !raw[0]) return null
  const pid = toPid(raw[0])
  if (pid === null) return null  // unparseable pid -> no live session (matches Python int() raising)
  const recordedSig = raw.length > 1 ? raw[1] : ''
  const exists = pidExists(pid)
  if (exists === 'gone') return 'stalled'
  if (verify && recordedSig) {
    const cur = procStartSig(pid)
    if (cur !== null && cur !== recordedSig) return 'stalled'  // pid recycled into another process
  }
  return 'live'
}

// Derived liveness for one in_flight task (mirrors dashboard_app._task_state): the session's state,
// or -- before any marker is recorded -- 'live' within the startup grace, then 'stalled'.
function taskState(sopDir, task, verify = true) {
  const s = sessionState(sopDir, task.id, verify)
  if (s !== null) return s
  const t = Date.parse(task.updated_at)
  if (!Number.isFinite(t)) return 'live'  // can't age it: don't cry stalled
  return (Date.now() - t) / 1000 < STARTUP_GRACE_SECONDS ? 'live' : 'stalled'
}

// in_flight rows, each annotated with a derived `state` (mirrors dashboard_app._inflight_with_liveness).
function inflightWithLiveness(store, sopDir, verify = true) {
  const rows = store.inFlight(sopDir)
  for (const t of rows) t.state = taskState(sopDir, t, verify)
  return rows
}

// Recent runs, each annotated with a derived `state` (mirrors dashboard_app._runs_with_liveness):
// done/error from the recorded result, else 'running' only if the SOP's run is live AND it's the
// newest open run for that SOP, else 'stalled'.
function runsWithLiveness(store, sopDir) {
  const runs = store.recentRuns(sopDir)
  const active = {}
  for (const r of activeRuns(sopDir)) active[r.sop] = r.state  // sop -> running/stalled
  const seenOpen = new Set()  // recentRuns is newest-first: first open row per SOP is the live candidate
  for (const r of runs) {
    const result = r.result
    if (result === 'error') r.state = 'error'
    else if (result) r.state = 'done'
    else {
      const sop = r.sop_id
      const newestOpen = !seenOpen.has(sop)
      seenOpen.add(sop)
      r.state = (newestOpen && active[sop] === 'running') ? 'running' : 'stalled'
    }
  }
  return runs
}

module.exports = { activeRuns, sessionState, taskState, inflightWithLiveness, runsWithLiveness, procStartSig, pidExists }
