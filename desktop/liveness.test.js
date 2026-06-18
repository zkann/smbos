const test = require('node:test')
const assert = require('node:assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { DatabaseSync } = require('node:sqlite')
const L = require('./liveness')
const store = require('./store')

function tmp() { return fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-live-')) }
const DEAD = 2147483646  // a pid that (essentially) never exists -> ESRCH

test('pidExists: this process is alive; a free high pid is gone', () => {
  assert.equal(L.pidExists(process.pid), 'alive')
  assert.equal(L.pidExists(DEAD), 'gone')
})

test('sessionState: live (our pid+sig), stalled (dead pid), null (no marker)', () => {
  const d = tmp(); fs.mkdirSync(path.join(d, 'active-sessions'))
  fs.writeFileSync(path.join(d, 'active-sessions', '1'), `${process.pid}\n${L.procStartSig(process.pid)}\n`)
  fs.writeFileSync(path.join(d, 'active-sessions', '2'), `${DEAD}\n\n`)
  assert.equal(L.sessionState(d, 1), 'live')
  assert.equal(L.sessionState(d, 2), 'stalled')
  assert.equal(L.sessionState(d, 3), null)  // no marker yet
})

test('a malformed pid is rejected, not probed as a real process (matches Python int())', () => {
  const d = tmp(); fs.mkdirSync(path.join(d, 'active-sessions')); fs.mkdirSync(path.join(d, 'active-runs'))
  fs.writeFileSync(path.join(d, 'active-sessions', '1'), '123abc\nsig\n')  // parseInt would accept 123
  assert.equal(L.sessionState(d, 1), null)  // toPid rejects -> no live session
  fs.writeFileSync(path.join(d, 'active-runs', 'a__x.json'),
    JSON.stringify({ sop: 'a', pid: '99x', proc_sig: 's', started: new Date().toISOString() }))
  assert.equal(L.activeRuns(d)[0].state, 'stalled')  // unparseable marker pid -> not running
})

test('sessionState: a positive start-sig mismatch reads as stalled (pid reused)', () => {
  const d = tmp(); fs.mkdirSync(path.join(d, 'active-sessions'))
  fs.writeFileSync(path.join(d, 'active-sessions', '1'), `${process.pid}\nNOT-THE-REAL-START-TIME\n`)
  assert.equal(L.sessionState(d, 1, true), 'stalled')   // verify -> sig mismatch -> stalled
  assert.equal(L.sessionState(d, 1, false), 'live')     // no verify -> pid alive -> live (the SSE poll)
})

test('activeRuns: running (live pid+sig) vs stalled (dead pid); stale-aged is never running', () => {
  const d = tmp(); fs.mkdirSync(path.join(d, 'active-runs'))
  const sig = L.procStartSig(process.pid)
  const now = new Date().toISOString()
  fs.writeFileSync(path.join(d, 'active-runs', `a__${process.pid}.json`),
    JSON.stringify({ sop: 'a', pid: process.pid, proc_sig: sig, started: now }))
  fs.writeFileSync(path.join(d, 'active-runs', `b__${DEAD}.json`),
    JSON.stringify({ sop: 'b', pid: DEAD, proc_sig: 'x', started: now }))
  const old = new Date(Date.now() - 2000 * 1000).toISOString()  // 2000s ago > 1200s backstop
  fs.writeFileSync(path.join(d, 'active-runs', `c__${process.pid}.json`),
    JSON.stringify({ sop: 'c', pid: process.pid, proc_sig: sig, started: old }))
  const m = Object.fromEntries(L.activeRuns(d).map((r) => [r.sop, r.state]))
  assert.equal(m.a, 'running')
  assert.equal(m.b, 'stalled')   // dead pid
  assert.equal(m.c, 'stalled')   // alive pid but aged past the backstop
})

test('runsWithLiveness: done/error from result; running only for the newest open + active SOP', () => {
  const d = tmp()
  const db = new DatabaseSync(path.join(d, 'state.db'))
  db.exec('CREATE TABLE run(id INTEGER PRIMARY KEY, sop_id TEXT, result TEXT, started_at TEXT)')
  const ins = db.prepare('INSERT INTO run(sop_id,result,started_at) VALUES(?,?,?)')
  ins.run('a', null, '2026-01-03'); ins.run('a', null, '2026-01-02')  // two open 'a' runs
  ins.run('b', 'ok', '2026-01-01'); ins.run('c', 'error', '2026-01-01')
  db.close()
  fs.mkdirSync(path.join(d, 'active-runs'))
  fs.writeFileSync(path.join(d, 'active-runs', `a__${process.pid}.json`),
    JSON.stringify({ sop: 'a', pid: process.pid, proc_sig: L.procStartSig(process.pid), started: new Date().toISOString() }))
  const byId = Object.fromEntries(L.runsWithLiveness(store, d).map((r) => [r.id, r.state]))
  assert.equal(byId[1], 'running')  // newest open 'a' + 'a' is active
  assert.equal(byId[2], 'stalled')  // older open 'a' -> not the live candidate
  assert.equal(byId[4], 'error')    // result error
  assert.equal(byId[3], 'done')     // result ok
})

test('inflightWithLiveness: annotates each in_flight task with its session state', () => {
  const d = tmp()
  const db = new DatabaseSync(path.join(d, 'state.db'))
  db.exec(`CREATE TABLE task (id INTEGER PRIMARY KEY, domain TEXT, kind TEXT, subject TEXT, status TEXT,
    priority INTEGER DEFAULT 0, source_ref TEXT, created_at TEXT, updated_at TEXT)`)
  db.exec("INSERT INTO task(id,subject,status,created_at,updated_at) VALUES(1,'live','in_flight','t','t'),(2,'stalled','in_flight','t','t')")
  db.close()
  fs.mkdirSync(path.join(d, 'active-sessions'))
  fs.writeFileSync(path.join(d, 'active-sessions', '1'), `${process.pid}\n${L.procStartSig(process.pid)}\n`)
  fs.writeFileSync(path.join(d, 'active-sessions', '2'), `${DEAD}\n\n`)
  const byId = Object.fromEntries(L.inflightWithLiveness(store, d).map((t) => [t.id, t.state]))
  assert.equal(byId[1], 'live')
  assert.equal(byId[2], 'stalled')
})
