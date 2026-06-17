// Pure URL/token resolution for the SmbOS desktop shell, mirroring smbos_lib.dashboard_url /
// dashboard_port / dashboard_token. No Electron dependency, so it's unit-testable without a display.
// `env` is injectable for testing; it defaults to process.env.

const path = require('path')
const os = require('os')
const fs = require('fs')

const DEFAULT_PORT = 8765  // the configured dashboard port (the cutover flipped 8765 to the FastAPI app)

function validPort(n) {
  return Number.isInteger(n) && n >= 1 && n <= 65535  // a real TCP port, not a stray/out-of-range value
}

function sopDir(env = process.env) {
  return env.SOP_DIR || path.join(os.homedir(), 'sops')
}

function dashboardPort(env = process.env) {
  const e = Number(env.SMBOS_DASHBOARD_PORT)
  if (validPort(e)) return e
  try {
    const tj = JSON.parse(fs.readFileSync(path.join(sopDir(env), 'triggers.json'), 'utf8'))
    const p = Number(tj && tj.dashboard_port)
    if (validPort(p)) return p
  } catch (_) { /* no config yet: fall through to the default */ }
  return DEFAULT_PORT  // a missing OR out-of-range/non-integer value falls back, never returned as-is
}

function token(env = process.env) {
  try {
    return fs.readFileSync(path.join(sopDir(env), '.dashboard-token'), 'utf8').trim()
  } catch (_) {
    return ''  // server not started / no token yet
  }
}

function dashboardUrl(env = process.env) {
  return `http://127.0.0.1:${dashboardPort(env)}/?t=${encodeURIComponent(token(env))}`
}

module.exports = { DEFAULT_PORT, sopDir, dashboardPort, token, dashboardUrl }
