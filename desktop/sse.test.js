const test = require('node:test')
const assert = require('node:assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { DatabaseSync } = require('node:sqlite')
const sse = require('./sse')

function seeded() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-sse-'))
  const db = new DatabaseSync(path.join(d, 'state.db'))
  db.exec(`CREATE TABLE task (id INTEGER PRIMARY KEY, domain TEXT, kind TEXT, subject TEXT, status TEXT,
    priority INTEGER DEFAULT 0, source_ref TEXT, created_at TEXT, updated_at TEXT)`)
  db.exec(`CREATE TABLE run (id INTEGER PRIMARY KEY, sop_id TEXT, result TEXT, started_at TEXT)`)
  db.exec("INSERT INTO task(id,subject,status,created_at,updated_at) VALUES(1,'waiting one','waiting','t','t')")
  db.close()
  return d
}

test('snapshot: five frames, each a BARE array (not a {key: ...} wrapper)', () => {
  const d = seeded()
  const frames = sse.snapshot(d)
  assert.equal(frames.length, 5)
  for (const ev of ['plate', 'inflight', 'pending', 'queue', 'runs']) {
    const frame = frames.find((f) => f.startsWith(`event: ${ev}\n`))
    assert.ok(frame, `has a ${ev} frame`)
    assert.ok(frame.endsWith('\n\n'), 'frame is terminated')
    const data = JSON.parse(frame.match(/data: (.*)/)[1])
    assert.ok(Array.isArray(data), `${ev} data is a bare array`)
  }
  // the seeded waiting task shows up in the plate frame
  const plate = JSON.parse(frames.find((f) => f.startsWith('event: plate\n')).match(/data: (.*)/)[1])
  assert.equal(plate[0].subject, 'waiting one')
})

test('snapshot is resilient to a missing state.db: five empty-array frames, no throw', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-sse-'))  // a fresh SOP dir, no state.db yet
  const frames = sse.snapshot(d)
  assert.equal(frames.length, 5)
  for (const ev of ['plate', 'inflight', 'pending', 'queue', 'runs']) {
    const data = JSON.parse(frames.find((f) => f.startsWith(`event: ${ev}\n`)).match(/data: (.*)/)[1])
    assert.deepEqual(data, [])  // the stream still opens; the held connection reopens when the db appears
  }
})

test('signals: change when a pending/queue file appears (data_version is blind to files)', () => {
  const d = seeded()
  const s0 = sse.signals(d)
  fs.mkdirSync(path.join(d, 'pending'))
  fs.writeFileSync(path.join(d, 'pending', 'x.md'), '---\nstatus: pending\n---\n# X\n')
  const s1 = sse.signals(d)
  assert.notEqual(s0, s1)  // a parked result appearing must move the signal
  fs.mkdirSync(path.join(d, 'queue'))
  fs.writeFileSync(path.join(d, 'queue', 'q.md'), '---\nstatus: queued\n---\n')
  assert.notEqual(s1, sse.signals(d))  // a queued run appearing too
})
