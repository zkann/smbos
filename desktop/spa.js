// The broker serves the built SPA itself (/ and /assets) instead of forwarding it to FastAPI -- the
// last piece before FastAPI is off the critical path. Mirrors dashboard_app's index + assets routes:
// / is token-gated and injects window.__SMBOS_TOKEN__ into the built index.html; /assets/* is the
// hashed, secret-free bundle served with path containment. dist defaults to ../frontend/dist, or
// $SMBOS_DIST for a packaged app.

const fs = require('fs')
const path = require('path')
const crypto = require('crypto')
const { token } = require('./resolve')

const PAGE_HEADERS = { 'referrer-policy': 'no-referrer', 'cache-control': 'no-store' }

// Friendly page when opened without a token (byte-for-byte the FastAPI _NO_TOKEN_PAGE).
const NO_TOKEN_PAGE =
  '<!doctype html><meta charset=utf-8><title>SmbOS</title><body style="margin:0;background:#09090b;' +
  "color:#fafafa;font:16px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif\">" +
  "<main style='max-width:560px;margin:0 auto;padding:48px 32px'><h1 style='font-size:20px;" +
  "font-weight:650'>SmbOS dashboard</h1><p style='color:#a1a1aa'>This dashboard needs its access " +
  'token. Open it with the full URL ending in <code>?t=&lt;token&gt;</code> from your dashboard ' +
  'launcher.</p></main>'

const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.ico': 'image/x-icon', '.webp': 'image/webp',
  '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.map': 'application/json',
}

function distDir() {
  return process.env.SMBOS_DIST || path.join(__dirname, '..', 'frontend', 'dist')
}

function tokenOk(provided, expected) {
  if (!expected || !provided) return false
  const a = Buffer.from(String(provided))
  const b = Buffer.from(String(expected))
  return a.length === b.length && crypto.timingSafeEqual(a, b)
}

// GET / : token-gated, the built index.html with the token injected before </head>.
function serveIndex(req, res, sopDir) {
  const t = new URL(req.url, 'http://x').searchParams.get('t')
  const tok = token({ SOP_DIR: sopDir })
  if (!tokenOk(t, tok)) {
    res.writeHead(401, { 'content-type': 'text/html', ...PAGE_HEADERS })
    res.end(NO_TOKEN_PAGE)
    return
  }
  let html
  try {
    html = fs.readFileSync(path.join(distDir(), 'index.html'), 'utf8')
  } catch (_) {
    res.writeHead(503, { 'content-type': 'text/plain' })
    res.end('Dashboard UI not built. Run `npm run build` in frontend/.')
    return
  }
  if (!html.includes('</head>')) {  // fail loud, not a silently tokenless (blank) dashboard
    res.writeHead(500, { 'content-type': 'text/plain' })
    res.end('Dashboard UI is missing a </head> anchor for the token; rebuild it.')
    return
  }
  // the token charset is url-safe; JSON.stringify wraps it as a JS string literal
  const inject = `<script>window.__SMBOS_TOKEN__=${JSON.stringify(tok)}</script>`
  res.writeHead(200, { 'content-type': 'text/html', ...PAGE_HEADERS })
  res.end(html.replace('</head>', inject + '</head>'))
}

// GET /assets/<path> : the hashed bundle (no secrets, so no token), path-contained against traversal.
function serveAsset(req, res, assetPath) {
  const base = path.resolve(distDir(), 'assets')
  const target = path.resolve(base, assetPath)
  if (target !== base && !target.startsWith(base + path.sep)) {  // lexical containment: no ../ escape
    res.writeHead(404); res.end(); return
  }
  let data
  try {
    // Re-check after realpath: path.resolve is purely lexical (it doesn't follow symlinks), so a
    // symlink inside assets/ pointing outside would pass the lexical check. realpath dereferences it,
    // matching Python's Path.resolve(); a link that escapes the (realpath'd) base 404s.
    const realBase = fs.realpathSync(base)
    const real = fs.realpathSync(target)
    if (real !== realBase && !real.startsWith(realBase + path.sep)) throw new Error('escapes via symlink')
    if (!fs.statSync(real).isFile()) throw new Error('not a file')
    data = fs.readFileSync(real)
  } catch (_) {
    res.writeHead(404); res.end(); return
  }
  res.writeHead(200, { 'content-type': MIME[path.extname(target).toLowerCase()] || 'application/octet-stream' })
  res.end(data)
}

module.exports = { serveIndex, serveAsset, distDir }
