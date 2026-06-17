const test = require('node:test')
const assert = require('node:assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const R = require('./resolve')

test('resolves port + token + url from the SOP dir, mirroring smbos_lib', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-resolve-'))
  fs.writeFileSync(path.join(dir, '.dashboard-token'), 'tok123\n')   // trailing newline is trimmed
  fs.writeFileSync(path.join(dir, 'triggers.json'), JSON.stringify({ dashboard_port: 9999 }))
  const env = { SOP_DIR: dir }
  assert.equal(R.dashboardPort(env), 9999)
  assert.equal(R.token(env), 'tok123')
  assert.equal(R.dashboardUrl(env), 'http://127.0.0.1:9999/?t=tok123')
})

test('$SMBOS_DASHBOARD_PORT overrides triggers.json', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-resolve-'))
  fs.writeFileSync(path.join(dir, 'triggers.json'), JSON.stringify({ dashboard_port: 9999 }))
  assert.equal(R.dashboardPort({ SOP_DIR: dir, SMBOS_DASHBOARD_PORT: '8000' }), 8000)
})

test('falls back to the default port and empty token when nothing is configured', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-resolve-'))  // no triggers.json, no token
  assert.equal(R.dashboardPort({ SOP_DIR: dir }), R.DEFAULT_PORT)
  assert.equal(R.token({ SOP_DIR: dir }), '')
  assert.equal(R.dashboardUrl({ SOP_DIR: dir }), `http://127.0.0.1:${R.DEFAULT_PORT}/?t=`)
})

test('a malformed triggers.json or bad port falls back to the default, never throws', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-resolve-'))
  fs.writeFileSync(path.join(dir, 'triggers.json'), '{ not json')
  assert.equal(R.dashboardPort({ SOP_DIR: dir }), R.DEFAULT_PORT)
  fs.writeFileSync(path.join(dir, 'triggers.json'), JSON.stringify({ dashboard_port: 'nope' }))
  assert.equal(R.dashboardPort({ SOP_DIR: dir }), R.DEFAULT_PORT)
})

test('out-of-range / non-integer ports are rejected, not returned', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-resolve-'))
  for (const bad of ['0', '-1', '70000', '80.5', '99999999']) {
    assert.equal(R.dashboardPort({ SOP_DIR: dir, SMBOS_DASHBOARD_PORT: bad }), R.DEFAULT_PORT, bad)
  }
  for (const bad of [0, 70000, 80.5, -5]) {
    fs.writeFileSync(path.join(dir, 'triggers.json'), JSON.stringify({ dashboard_port: bad }))
    assert.equal(R.dashboardPort({ SOP_DIR: dir }), R.DEFAULT_PORT, String(bad))
  }
  // a valid in-range port is still honored
  assert.equal(R.dashboardPort({ SOP_DIR: dir, SMBOS_DASHBOARD_PORT: '8080' }), 8080)
})

test('the token is URL-encoded into the dashboard URL', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-resolve-'))
  fs.writeFileSync(path.join(dir, '.dashboard-token'), 'a b/c')  // chars that must be escaped
  assert.ok(R.dashboardUrl({ SOP_DIR: dir }).endsWith('/?t=a%20b%2Fc'))
})
