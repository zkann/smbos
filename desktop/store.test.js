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

function seedTrackers(dir, rows) {
  const db = new DatabaseSync(path.join(dir, 'state.db'))
  db.exec(`CREATE TABLE tracker (id INTEGER PRIMARY KEY, domain TEXT, kind TEXT, title TEXT, status TEXT,
    next_at TEXT, next_label TEXT, url TEXT, priority INTEGER DEFAULT 0, source_ref TEXT, dossier TEXT,
    assembled_at TEXT, archived INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT)`)
  const ins = db.prepare('INSERT INTO tracker(id,domain,kind,title,status,next_at,priority,dossier,archived,created_at,updated_at)'
    + ' VALUES(?,?,?,?,?,?,?,?,?,?,?)')
  for (const t of rows) ins.run(t.id, 'deals', 'deal', t.title, t.status || null, t.next_at || null,
    t.priority || 0, t.dossier || null, t.archived || 0, '2026-01-01', '2026-01-01')
  db.close()
}

test('trackers: active only, soonest next_at first (nulls last) then priority; dossier omitted', () => {
  const d = tmpSop()
  seedTrackers(d, [
    { id: 1, title: 'Later', next_at: '2026-07-01' },
    { id: 2, title: 'Sooner', next_at: '2026-06-25' },
    { id: 3, title: 'NoDate', priority: 5, dossier: 'X' },
    { id: 4, title: 'Archived', archived: 1 },                 // excluded from the active list
  ])
  const rows = store.trackers(d)
  assert.deepEqual(rows.map((r) => r.title), ['Sooner', 'Later', 'NoDate'])
  assert.equal('dossier' in rows[0], false)                    // the list omits the heavy blob
  assert.equal(store.trackers(tmpSop()).length, 0)             // no db -> empty, no throw
  const taskOnly = tmpSop()
  seedTasks(taskOnly, [{ id: 1, subject: 'a', status: 'waiting' }])
  assert.equal(store.trackers(taskOnly).length, 0)             // pre-v10 db (no tracker table) -> empty, no throw
})

test('getTracker: one row WITH its dossier; null on bad id / absent / missing table', () => {
  const d = tmpSop()
  seedTrackers(d, [{ id: 7, title: 'Acme', dossier: 'the assembled context' }])
  assert.equal(store.getTracker(d, 7).dossier, 'the assembled context')
  assert.equal(store.getTracker(d, '7').title, 'Acme')         // string id coerced to int
  assert.equal(store.getTracker(d, 999), null)                 // absent
  assert.equal(store.getTracker(d, 'abc'), null)               // non-numeric id
  assert.equal(store.getTracker(d, '7abc'), null)              // partial-numeric id rejected
  assert.equal(store.getTracker(tmpSop(), 1), null)            // no db -> null, no throw
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

test('procedures: derives autonomy, computes the cost median, skips INDEX, sorts by title', () => {
  const d = tmpSop(); fs.mkdirSync(path.join(d, 'ops'))
  const sop = (sid, title, status, extra = '') => fs.writeFileSync(path.join(d, 'ops', sid + '.md'),
    `---\nid: ${sid}\ntitle: ${title}\nstatus: ${status}\n${extra}---\n# ${title}\n`)
  sop('b-weekly', 'Weekly', 'active', 'autonomy: on_its_own\n')
  sop('a-draft', 'Draft proc', 'draft')
  sop('c-inter', 'Inbox', 'active', 'interactive_only: true\n')
  fs.writeFileSync(path.join(d, 'INDEX.md'), 'skip me')  // iter_sops skips INDEX.md
  fs.writeFileSync(path.join(d, 'runs.jsonl'), [
    { sop: 'b-weekly', result: 'ok', cost_usd: 0.1 },
    { sop: 'b-weekly', result: 'ok', cost_usd: 0.3 },
    { sop: 'b-weekly', result: 'error', cost_usd: 9 },  // non-ok -> excluded from the median
  ].map((r) => JSON.stringify(r)).join('\n'))
  const procs = store.procedures(d)
  assert.deepEqual(procs.map((p) => p.title), ['Draft proc', 'Inbox', 'Weekly'])  // sorted by title.lower()
  const weekly = procs.find((p) => p.id === 'b-weekly')
  assert.equal(weekly.autonomy, 'on_its_own'); assert.equal(weekly.draft, false)
  assert.deepEqual(weekly.cost, { estimate: 0.2, n: 2 })          // median of 0.1, 0.3
  const draft = procs.find((p) => p.id === 'a-draft')
  assert.equal(draft.autonomy, 'prepare_ask'); assert.equal(draft.cost, null)  // draft, no runs
  const inter = procs.find((p) => p.id === 'c-inter')
  assert.equal(inter.interactive, true); assert.equal(inter.autonomy, 'with_me')  // interactive_only -> with_me
})

test('procedures: same-title tie-break follows Python path-component order (nested before prefix-sibling)', () => {
  const d = tmpSop(); fs.mkdirSync(path.join(d, 'clients'))
  fs.writeFileSync(path.join(d, 'clients', 'nested.md'), '---\nid: nested\ntitle: Same\nstatus: active\n---\n')
  fs.writeFileSync(path.join(d, 'clients-flat.md'), '---\nid: flat\ntitle: Same\nstatus: active\n---\n')
  // Python sorted(rglob) compares components: 'clients' < 'clients-flat.md', so the nested file is
  // first; a full-string sort would put 'clients-flat.md' first ('-' < '/'). Stable title sort keeps it.
  assert.deepEqual(store.procedures(d).map((p) => p.id), ['nested', 'flat'])
})

test('procedures/queue skip a non-UTF-8 file (parity: Python read_text raises -> skipped)', () => {
  const d = tmpSop(); fs.mkdirSync(path.join(d, 'ops')); fs.mkdirSync(path.join(d, 'queue'))
  fs.writeFileSync(path.join(d, 'ops', 'good.md'), '---\nid: good\ntitle: Good\nstatus: active\n---\n')
  fs.writeFileSync(path.join(d, 'ops', 'bad.md'), Buffer.from([0x2d, 0x2d, 0x2d, 0x0a, 0xff, 0xfe, 0x0a, 0x2d, 0x2d, 0x2d]))
  fs.writeFileSync(path.join(d, 'queue', 'q.md'), Buffer.from([0xff, 0xfe]))  // invalid UTF-8
  assert.deepEqual(store.procedures(d).map((p) => p.id), ['good'])  // bad.md skipped, not garbled-in
  assert.deepEqual(store.queue(d), [])                              // bad queue file skipped
})

test('pending: status-pending files, with title, candidates, and next', () => {
  const d = tmpSop(); fs.mkdirSync(path.join(d, 'pending')); fs.mkdirSync(path.join(d, 'ops'))
  fs.writeFileSync(path.join(d, 'ops', 'dedupe.md'), '---\nid: dedupe\nnext: apply-dedupe, other\n---\n')
  fs.writeFileSync(path.join(d, 'pending', 'p1.md'),
    '---\nstatus: pending\nsop: dedupe\n---\n# Pending: Review 3 dupes\n\n## Candidates\n```json\n' +
    '[{"title":"A","url":"http://a","note":"n"},{"url":"http://b"}]\n```\n')
  fs.writeFileSync(path.join(d, 'pending', 'p2.md'), '---\nstatus: approved\nsop: x\n---\n# Done\n')  // not pending
  const items = store.pending(d)
  assert.equal(items.length, 1)
  assert.equal(items[0].file, 'p1.md')
  assert.equal(items[0].sop, 'dedupe')
  assert.equal(items[0].title, 'Review 3 dupes')  // '# Pending: ' prefix stripped
  assert.deepEqual(items[0].candidates, [
    { title: 'A', url: 'http://a', note: 'n' },
    { title: 'http://b', url: 'http://b', note: '' },  // title falls back to url
  ])
  assert.equal(items[0].next, 'apply-dedupe')  // first id of the source SOP's next: list
})

test('pending candidates: a non-string field coerces to empty; title falls back to url', () => {
  const d = tmpSop(); fs.mkdirSync(path.join(d, 'pending'))
  fs.writeFileSync(path.join(d, 'pending', 'p.md'),
    '---\nstatus: pending\nsop: s\n---\n# T\n## Candidates\n```json\n' +
    '[{"title":["a","b"],"url":"http://u","note":42}]\n```\n')  // title is a list, note a number
  assert.deepEqual(store.pending(d)[0].candidates, [{ title: 'http://u', url: 'http://u', note: '' }])
})

test('pending: no candidates -> next null; plain heading -> title; no dir -> empty', () => {
  const d = tmpSop(); fs.mkdirSync(path.join(d, 'pending'))
  fs.writeFileSync(path.join(d, 'pending', 'p.md'), '---\nstatus: pending\nsop: s\n---\n# Just a note\n')
  const items = store.pending(d)
  assert.equal(items[0].title, 'Just a note')
  assert.deepEqual(items[0].candidates, []); assert.equal(items[0].next, null)
  assert.deepEqual(store.pending(tmpSop()), [])
})

