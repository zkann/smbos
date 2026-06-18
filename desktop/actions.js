// Invoke the Python engine-action CLI (scripts/engine_action.py) from the broker, so a write/action
// reuses the exact stdlib engine logic (gate + spawn) rather than re-implementing it in Node. The CLI
// is stdlib-only and runs under the system python3.
//
// The CLI's exit code carries the HTTP status: 0 -> 200 (stdout JSON body), 3 -> 409 (refused,
// {detail}), anything else -> 500. Configurable for tests via $SMBOS_PYTHON / $SMBOS_ENGINE.

const { spawn } = require('child_process')
const path = require('path')

function pythonBin() {
  return process.env.SMBOS_PYTHON || 'python3'
}

function enginePath() {
  return process.env.SMBOS_ENGINE || path.join(__dirname, '..', 'scripts', 'engine_action.py')
}

// Run `engine_action <argv...>`, writing `input` to its stdin (owner inputs ride here, not argv, so
// they're unbounded + can't be misparsed as options). Resolves { code, json } -- code is the exit
// code (or 1 on a spawn failure / timeout), json is the parsed stdout (or null). Never rejects.
function runAction(argv, input = '') {
  return new Promise((resolve) => {
    let child
    try {
      child = spawn(pythonBin(), [enginePath(), ...argv], { timeout: 30000 })
    } catch (_) {
      return resolve({ code: 1, json: null })
    }
    let stdout = ''
    child.stdout.on('data', (d) => { stdout += d })
    child.on('error', () => resolve({ code: 1, json: null }))  // ENOENT etc.
    child.on('close', (code) => {
      let json = null
      try { json = JSON.parse(stdout) } catch (_) { /* non-JSON -> null */ }
      resolve({ code: code === null ? 1 : code, json })  // timeout kills with code null -> 1 -> 500
    })
    child.stdin.on('error', () => { /* child gone before we finished writing: handled by close/error */ })
    child.stdin.end(input)
  })
}

module.exports = { runAction, pythonBin, enginePath }
