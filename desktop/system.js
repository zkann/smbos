// System status for the dashboard's System view. The health/flow picture spans the jobs.d registry,
// per-job liveness-file mtimes, AND the routing store -- not a pure state.db read, so (like the broker
// already does for /api/settings) it reuses the tested Python aggregator rather than re-porting the
// aggregation into Node. It's slow-changing (jobs run hourly/daily), so the SSE emits it on its own
// cadence. Any failure resolves to null and the dashboard simply skips the System frame.

const { execFile } = require('child_process')
const path = require('path')

const SCRIPT = path.join(__dirname, '..', 'scripts', 'system_status.py')
const PYTHON = process.env.SMBOS_PYTHON || '/usr/bin/python3'

function defaultRun(sopDir) {
  return new Promise((resolve, reject) => {
    execFile(PYTHON, [SCRIPT, '--json'],
      { timeout: 10000, maxBuffer: 1 << 20, env: { ...process.env, SOP_DIR: sopDir } },
      (err, stdout) => (err ? reject(err) : resolve(stdout)))
  })
}

// Resolve the parsed system-status object, or null on any failure (spawn error, timeout, bad JSON).
// `run` is injectable for tests.
function compute(sopDir, run = defaultRun) {
  return Promise.resolve()
    .then(() => run(sopDir))
    .then((stdout) => { try { return JSON.parse(stdout) } catch (_) { return null } })
    .catch(() => null)
}

module.exports = { compute }
