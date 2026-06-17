const test = require('node:test')
const assert = require('node:assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { DatabaseSync } = require('node:sqlite')
const store = require('./store')

function tmpSop() { return fs.mkdtempSync(path.join(os.tmpdir(), 'smbos-store-')) }

function seedTasks(dir, tasks) {
  const db = new DatabaseSync(path.join(dir, 'state.db'))
  db.exec(`CREATE TABLE task (id INTEGER PRIMARY KEY, domain TEXT, kind TEXT, subject TEXT, status TEXT,
    priority INTEGER DEFAULT 0, source_ref TEXT, created_at TEXT, updated_at TEXT)`)
  const ins = db.prepare(
    'INSERT INTO task(id,domain,kind,subject,status,priority,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)')
  for (const t of tasks) ins.run(t.id, 'ops', 'x', t.subject, t.status, t.priority || 0, t.created_at || '2026-01-01', '2026-01-01')
  db.close()
}

test('plate: only waiting tasks, ordered priority desc, then created_at asc, then id', () => {
  const d = tmpSop()
  seedTasks(d, [
    { id: 1, subject: 'a', status: 'waiting', priority: 0, created_at: '2026-01-02' },
    { id: 2, subject: 'b', status: 'in_flight', priority: 9 },                 // not waiting -> excluded
    { id: 3, subject: 'c', status: 'waiting', priority: 5, created_at: '2026-01-03' },
    { id: 4, subject: 'd', status: 'waiting', priority: 0, created_at: '2026-01-01' },
    { id: 5, subject: 'e', status: 'waiting', priority: 0, created_at: '2026-01-02' },  // ties a on prio+created_at
  ])
  // c(prio5); then prio0 oldest-first: d(01-01); then a & e tie on prio0+01-02 -> id ASC: a(1), e(5)
  assert.deepEqual(store.plate(d).map((r) => r.subject), ['c', 'd', 'a', 'e'])
  assert.equal(store.plate(tmpSop()).length, 0)  // no state.db -> empty, no throw
})

test('queue: only status:queued .md files; project is basenamed', () => {
  const d = tmpSop(); fs.mkdirSync(path.join(d, 'queue'))
  fs.writeFileSync(path.join(d, 'queue', 'a.md'), '---\nsop: weekly\nstatus: queued\nproject: /home/x/acme\n---\nbody')
  fs.writeFileSync(path.join(d, 'queue', 'b.md'), '---\nsop: skip\nstatus: done\n---\nbody')  // not queued
  assert.deepEqual(store.queue(d), [{ file: 'a.md', sop: 'weekly', project: 'acme' }])
  assert.deepEqual(store.queue(tmpSop()), [])  // no queue dir -> empty
})

test('queue: #-comment frontmatter lines are skipped (parity with smbos_lib.parse_frontmatter)', () => {
  const d = tmpSop(); fs.mkdirSync(path.join(d, 'queue'))
  fs.writeFileSync(path.join(d, 'queue', 'a.md'), '---\n# note: ignore me\nsop: weekly\nstatus: queued\n---\nbody')
  assert.deepEqual(store.queue(d), [{ file: 'a.md', sop: 'weekly', project: '' }])
})

