import { useEffect, useRef, useState } from 'react'

// Live-mirror dashboard. Subscribes to the SSE stream (/events) and renders the command-center
// plate + what's in flight + run history. The whole job is to be trusted as current, so a
// dead/quiet stream surfaces a staleness banner. Each plate item can be picked up: that POSTs
// /api/launch, which opens a Claude session primed for the task and moves it to "in flight".
const STALE_MS = 15000 // ~1.5 missed heartbeats (server beats every ~10s)
const token = window.__SMBOS_TOKEN__ || ''

// The server annotates each run with a flock-derived `state` (running/stalled/done/error): a
// run hard-killed without recording its finish reads as 'stalled' rather than a false 'running'.
function runDot(r) {
  if (r.state === 'running') return 'live'
  if (r.state === 'stalled') return 'stalled'
  if (r.state === 'error' || r.result === 'error') return 'err'
  return 'done'
}
function runLabel(r) {
  if (r.result) return r.result          // recorded outcome: ok / parked / error / ...
  return r.state === 'stalled' ? 'stalled' : 'running'
}

export default function App() {
  const [plate, setPlate] = useState([])
  const [inflight, setInflight] = useState([])
  const [pending, setPending] = useState([])
  const [queued, setQueued] = useState([])
  const [runs, setRuns] = useState([])
  const [stale, setStale] = useState(false)
  // per queued-run cancel state: file -> 'canceling' | 'error'. Clears via the SSE queue frame.
  const [qbusy, setQbusy] = useState({})
  // per-task launch state: id -> 'launching' | 'error'. A successful launch clears via the SSE
  // plate frame moving the item to in-flight; an error stays visible so the row offers a retry.
  const [launch, setLaunch] = useState({})
  // per parked-result action state: file -> 'approve'|'discard'|'error', or `${file}#${i}` ->
  // 'applying'|'error'. Success clears via the SSE pending frame dropping the resolved item.
  const [pend, setPend] = useState({})
  // settings is owner-controlled config (not live-mirror state), so it's fetched once on mount
  // and updated from each write's echoed state, not streamed. confirmSkip gates the one
  // dangerous value (Skip all approvals) behind an inline confirm.
  const [settings, setSettings] = useState(null)
  const [budgetInput, setBudgetInput] = useState('')
  const [confirmSkip, setConfirmSkip] = useState(false)
  // the SOP library (fetched once on mount; the server re-gates at run time). procBusy: sop id ->
  // 'running'|'preparing'|'queuing'|'launching'|'error'. procInputs: sop id -> the inputs text.
  const [procedures, setProcedures] = useState([])
  const [procBusy, setProcBusy] = useState({})
  const [procInputs, setProcInputs] = useState({})
  const [procErr, setProcErr] = useState({})  // sop id -> the server's refusal reason (the 409 detail)

  useEffect(() => {
    // NOTE: do NOT strip ?t= from the URL. The page itself is token-gated (GET / requires ?t=
    // to serve the token-injected HTML), so the token must stay in the address bar or a
    // reload/refresh/bookmark of the now-bare URL 401s. Leak via Referer is already prevented by
    // the page's Referrer-Policy: no-referrer + Cache-Control: no-store headers.
    let lastEventAt = Date.now()
    const fresh = () => { lastEventAt = Date.now(); setStale(false) }
    // a malformed frame must not throw out of the listener (it would drop the frame AND skip
    // fresh(), so the banner could fire on a live stream); any frame means the stream is alive
    const onFrame = (set) => (e) => {
      try { set(JSON.parse(e.data)) } catch (_) { /* keep last good data */ }
      fresh()
    }

    // the plate frame also prunes launch state: an id no longer on the plate (it succeeded into
    // in-flight, or resolved elsewhere) shouldn't keep a stale 'launching'/'error' on a row
    // that's gone. An errored id that's still waiting stays, so the row keeps its retry.
    const onPlate = (e) => {
      let next
      try { next = JSON.parse(e.data) } catch (_) { fresh(); return }
      setPlate(next)
      const ids = new Set(next.map((t) => t.id))
      setLaunch((s) => {
        const n = {}
        for (const k of Object.keys(s)) if (ids.has(Number(k))) n[k] = s[k]
        return n
      })
      fresh()
    }

    // the pending frame prunes parked-result action state for files that resolved away (same
    // reason as onPlate's launch prune); an errored action on a file that's still pending stays.
    const onPending = (e) => {
      let next
      try { next = JSON.parse(e.data) } catch (_) { fresh(); return }
      setPending(next)
      const files = new Set(next.map((it) => it.file))
      setPend((s) => {
        const n = {}
        for (const k of Object.keys(s)) if (files.has(k.split('#')[0])) n[k] = s[k]
        return n
      })
      fresh()
    }

    // the queue frame prunes cancel state for runs that left the queue (canceled or started)
    const onQueue = (e) => {
      let next
      try { next = JSON.parse(e.data) } catch (_) { fresh(); return }
      setQueued(next)
      const files = new Set(next.map((q) => q.file))
      setQbusy((s) => { const n = {}; for (const k of Object.keys(s)) if (files.has(k)) n[k] = s[k]; return n })
      fresh()
    }

    const es = new EventSource(`/events?t=${encodeURIComponent(token)}`)
    es.addEventListener('plate', onPlate)
    es.addEventListener('inflight', onFrame(setInflight))
    es.addEventListener('pending', onPending)
    es.addEventListener('queue', onQueue)
    es.addEventListener('runs', onFrame(setRuns))
    es.addEventListener('heartbeat', fresh)
    es.onerror = () => setStale(true) // surface the drop; EventSource auto-reconnects
    const timer = setInterval(() => setStale(Date.now() - lastEventAt > STALE_MS), 3000)

    return () => { es.close(); clearInterval(timer) }
  }, [])

  // settings + the procedures library: fetched once on mount (config/catalog, not streamed; the
  // server re-gates a run at request time, so a stale list is safe)
  useEffect(() => {
    fetch(`/api/settings?t=${encodeURIComponent(token)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) { setSettings(d.settings); setBudgetInput(String(d.settings.budget)) } })
      .catch(() => {})
    refreshProcedures()
  }, [])

  const refreshProcedures = () =>
    fetch(`/api/procedures?t=${encodeURIComponent(token)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setProcedures(d.procedures) })
      .catch(() => {})

  // POST a procedure action (run/queue/prepare/pick-up) with the header token. busyVal marks the
  // row in flight; success clears it (the action's effect shows in Recent runs / a new session).
  // On a refusal the server's reason (the 409 detail, e.g. "changed outside the save flow, review
  // it first" or "needs information") is surfaced inline so the row isn't a silent dead-end.
  async function procPost(url, body, sid, busyVal) {
    setProcBusy((s) => ({ ...s, [sid]: busyVal }))
    setProcErr((s) => { const n = { ...s }; delete n[sid]; return n })
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-SMBOS-Token': token },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        let detail = `Couldn't do that (${res.status}).`
        try { const d = await res.json(); if (d && d.detail) detail = d.detail } catch (_) { /* keep generic */ }
        throw new Error(detail)
      }
      setProcBusy((s) => { const n = { ...s }; delete n[sid]; return n })
    } catch (e) {
      setProcBusy((s) => ({ ...s, [sid]: 'error' }))
      setProcErr((s) => ({ ...s, [sid]: e.message }))
    }
  }
  const runSop = (id, opts = {}) =>
    procPost('/api/run', { id, inputs: opts.inputs || undefined, mode: opts.prepare ? 'prepare' : undefined },
      id, opts.prepare ? 'preparing' : 'running')
  const queueSop = (id) => procPost('/api/queue', { id, inputs: procInputs[id] || undefined }, id, 'queuing')
  const launchSop = (id) => procPost('/api/launch-sop', { id }, id, 'launching')

  // apply-on-change write of one setting; the response echoes the full new config to resync. On
  // failure, re-fetch so a rejected value snaps the control back to what actually persisted. A
  // monotonic seq discards a stale echo: two near-simultaneous saves can resolve out of order, and
  // applying the earlier one last would overwrite the newer state.
  const latestSave = useRef(0)
  async function saveSetting(key, value) {
    const seq = ++latestSave.current
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-SMBOS-Token': token },
        body: JSON.stringify({ key, value }),
      })
      if (!res.ok) throw new Error(String(res.status))
      const d = await res.json()
      if (seq !== latestSave.current) return  // a newer save superseded this; ignore its echo
      setSettings(d.settings)
      setBudgetInput(String(d.settings.budget))
      setConfirmSkip(false)  // clear AFTER the write lands, not before (see onConfirmSkip)
    } catch (_) {
      if (seq !== latestSave.current) return
      setConfirmSkip(false)
      fetch(`/api/settings?t=${encodeURIComponent(token)}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (d && seq === latestSave.current) {
            setSettings(d.settings); setBudgetInput(String(d.settings.budget))
          }
        })
        .catch(() => {})
    }
  }

  // the launch-permission select: 'skip' (remove every safeguard) routes through an inline
  // confirm; trust/ask apply immediately.
  function onPermission(v) {
    if (v === 'skip') setConfirmSkip(true)
    else { setConfirmSkip(false); saveSetting('launch_permission', v) }
  }
  // confirm the dangerous skip. Keep confirmSkip TRUE through the round-trip so the select stays
  // on 'skip' (with the warning) instead of snapping back to the old value mid-flight; saveSetting
  // clears it once the write lands (success -> settings shows skip; failure -> reverts to persisted).
  const onConfirmSkip = () => saveSetting('launch_permission', 'skip')

  // Pick up a task: open a primed Claude session for it. The token rides in a custom header (a
  // cross-origin POST with one forces a CORS preflight the server's GET-only policy blocks).
  async function pickUp(id) {
    if (id == null) return
    setLaunch((s) => ({ ...s, [id]: 'launching' }))
    // bound the request: the server spawns osascript (up to ~20s); without a ceiling a stuck
    // launch would leave the button disabled+'launching…' forever with no recovery but reload.
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 25000)
    try {
      const res = await fetch('/api/launch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-SMBOS-Token': token },
        body: JSON.stringify({ task_id: id }),
        signal: ctrl.signal,
      })
      if (!res.ok) throw new Error(String(res.status))
      // success: the SSE plate frame will drop this item (it's now in flight); clear local state
      setLaunch((s) => { const n = { ...s }; delete n[id]; return n })
    } catch (_) {
      setLaunch((s) => ({ ...s, [id]: 'error' }))
    } finally {
      clearTimeout(timer)
    }
  }

  function pickupLabel(id) {
    if (launch[id] === 'launching') return 'launching…'
    if (launch[id] === 'error') return 'retry'
    return 'Pick up ▶'
  }

  // POST a JSON body with the header token (same CSRF posture as Pick up). `busyVal` marks the
  // row in flight. On success: resolve clears the key (the SSE pending frame then drops the whole
  // item), but apply-item only LAUNCHES a session, it doesn't resolve the file, so there's no SSE
  // removal; it sets a sticky `successVal` ('applied') instead, so the button can't be re-clicked
  // into a duplicate launch. An error leaves a retry.
  async function postAction(url, body, busyKey, busyVal, successVal) {
    setPend((s) => ({ ...s, [busyKey]: busyVal }))
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 25000)
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-SMBOS-Token': token },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      })
      if (!res.ok) throw new Error(String(res.status))
      setPend((s) => {
        if (successVal) return { ...s, [busyKey]: successVal }
        const n = { ...s }; delete n[busyKey]; return n
      })
    } catch (_) {
      setPend((s) => ({ ...s, [busyKey]: 'error' }))
    } finally {
      clearTimeout(timer)
    }
  }
  const resolve = (file, decision) => postAction('/api/resolve', { file, decision }, file, decision)
  const applyItem = (file, index) =>
    postAction('/api/apply-item', { file, index }, `${file}#${index}`, 'applying', 'applied')

  // cancel a queued run; the SSE queue frame drops it on success, an error leaves a retry.
  async function dequeue(file) {
    setQbusy((s) => ({ ...s, [file]: 'canceling' }))
    try {
      const res = await fetch('/api/dequeue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-SMBOS-Token': token },
        body: JSON.stringify({ file }),
      })
      if (!res.ok) throw new Error(String(res.status))
      setQbusy((s) => { const n = { ...s }; delete n[file]; return n })
    } catch (_) {
      setQbusy((s) => ({ ...s, [file]: 'error' }))
    }
  }

  return (
    <main>
      {stale && <div className="banner" role="status">Reconnecting, data may be stale</div>}

      <header><span className="dot live" aria-hidden="true"></span><h1>SmbOS</h1></header>

      <section className="panel">
        <div className="overline">On your plate</div>
        {plate.length === 0 ? (
          <p className="empty">Nothing waiting for you right now.</p>
        ) : (
          <ol className="list">
            {plate.map((t, i) => (
              <li key={t.id ?? i}>
                <span className="subj">{t.subject}</span>
                <span className={`chip chip-${t.status}`}>{t.status}</span>
                <button
                  className={`pickup${launch[t.id] === 'error' ? ' pickup-err' : ''}`}
                  onClick={() => pickUp(t.id)}
                  disabled={t.id == null || launch[t.id] === 'launching'}
                >
                  {pickupLabel(t.id)}
                </button>
              </li>
            ))}
          </ol>
        )}
      </section>

      {pending.length > 0 && (
        <section className="panel">
          <div className="overline">Needs your eyes</div>
          <ol className="list">
            {pending.map((it, i) => (
              <li key={it.file ?? i} className="pending-li">
                <div className="pending-head">
                  <span className="subj">{it.title}</span>
                  <span className="chip chip-pending">pending</span>
                  {it.candidates.length === 0 ? (
                    <>
                      <button className="act act-primary" onClick={() => resolve(it.file, 'approve')}
                        disabled={pend[it.file] === 'approve' || pend[it.file] === 'discard'}>
                        {pend[it.file] === 'approve' ? 'approving…' : 'Approve'}
                      </button>
                      <button className={`act${pend[it.file] === 'error' ? ' act-err' : ''}`}
                        onClick={() => resolve(it.file, 'discard')}
                        disabled={pend[it.file] === 'approve' || pend[it.file] === 'discard'}>
                        {pend[it.file] === 'discard' ? 'discarding…' : pend[it.file] === 'error' ? 'retry' : 'Reject'}
                      </button>
                    </>
                  ) : (
                    <span className="chip">{it.candidates.length} to pick</span>
                  )}
                </div>
                {it.candidates.length > 0 && (
                  <ul className="candidates">
                    {it.candidates.map((c, j) => {
                      const key = `${it.file}#${j}`
                      return (
                        <li key={j}>
                          <span className="subj cand">{c.title}</span>
                          <button className={`act${pend[key] === 'error' ? ' act-err' : ''}`}
                            onClick={() => applyItem(it.file, j)}
                            disabled={pend[key] === 'applying' || pend[key] === 'applied'}>
                            {pend[key] === 'applying' ? 'applying…'
                              : pend[key] === 'applied' ? 'applied ✓'
                              : pend[key] === 'error' ? 'retry' : 'Apply'}
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      {inflight.length > 0 && (
        <section className="panel">
          <div className="overline">In flight</div>
          <ol className="list">
            {inflight.map((t, i) => (
              <li key={t.id ?? i}>
                <span className="dot live" aria-hidden="true"></span>
                <span className="subj">{t.subject}</span>
                <span className="chip chip-inflight">in flight</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {queued.length > 0 && (
        <section className="panel">
          <div className="overline">Coming up</div>
          <ol className="list">
            {queued.map((q, i) => (
              <li key={q.file ?? i}>
                <span className="subj">{q.sop}{q.project ? ` · ${q.project}` : ''}</span>
                <span className="chip">queued</span>
                <button className={`act${qbusy[q.file] === 'error' ? ' act-err' : ''}`}
                  onClick={() => dequeue(q.file)} disabled={qbusy[q.file] === 'canceling'}>
                  {qbusy[q.file] === 'canceling' ? 'canceling…' : qbusy[q.file] === 'error' ? 'retry' : 'Cancel'}
                </button>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="panel">
        <div className="overline">Recent runs</div>
        {runs.length === 0 ? (
          <p className="empty">No runs yet.</p>
        ) : (
          <ul className="list">
            {runs.map((r, i) => {
              const dot = runDot(r)
              return (
                <li key={r.id ?? i}>
                  <span className={`dot ${dot}`} aria-hidden="true"></span>
                  <span className="subj">{r.sop_id}</span>
                  <span className={`chip${dot === 'stalled' ? ' chip-stalled' : ''}`}>{runLabel(r)}</span>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {procedures.length > 0 && (
        <details className="panel procedures" onToggle={(e) => { if (e.target.open) refreshProcedures() }}>
          <summary className="overline">Procedures</summary>
          <ol className="list">
            {procedures.map((p, i) => {
              const b = procBusy[p.id]
              const err = b === 'error'
              return (
                <li key={p.id ?? i}>
                  <span className="subj">{p.title}{p.draft ? ' · draft' : ''}</span>
                  {p.interactive ? (
                    <button className={`act${err ? ' act-err' : ''}`} onClick={() => launchSop(p.id)}
                      disabled={b === 'launching'}>
                      {b === 'launching' ? 'launching…' : err ? 'retry' : 'Pick up ▶'}
                    </button>
                  ) : p.draft ? (
                    <button className={`act${err ? ' act-err' : ''}`} onClick={() => runSop(p.id, { prepare: true })}
                      disabled={b === 'preparing'}>
                      {b === 'preparing' ? 'preparing…' : err ? 'retry' : 'Prepare'}
                    </button>
                  ) : (
                    <>
                      {p.needs_inputs && (
                        <input className="proc-inputs" placeholder="inputs…" value={procInputs[p.id] || ''}
                          onChange={(e) => setProcInputs((s) => ({ ...s, [p.id]: e.target.value }))} />
                      )}
                      <button className="act act-primary" onClick={() => runSop(p.id, { inputs: procInputs[p.id] })}
                        disabled={b === 'running'}>
                        {b === 'running' ? 'running…' : err ? 'retry' : 'Run'}
                      </button>
                      <button className={`act${err ? ' act-err' : ''}`} onClick={() => queueSop(p.id)}
                        disabled={b === 'queuing'}>
                        {b === 'queuing' ? 'queuing…' : 'Queue'}
                      </button>
                    </>
                  )}
                  {procErr[p.id] && <span className="proc-err">{procErr[p.id]}</span>}
                </li>
              )
            })}
          </ol>
        </details>
      )}

      {settings && (
        <details className="panel settings">
          <summary className="overline">Settings</summary>
          <div className="setrow">
            <label htmlFor="perm">When I launch a session</label>
            <select id="perm" value={confirmSkip ? 'skip' : settings.launch_permission}
              onChange={(e) => onPermission(e.target.value)}>
              <option value="trust">Trust edits, ask before commands</option>
              <option value="ask">Ask every time</option>
              <option value="skip">Skip all approvals</option>
            </select>
          </div>
          {confirmSkip && (
            <div className="setwarn-row">
              <span className="setwarn">Skips every check. This removes a safeguard.</span>
              <button className="act act-danger" onClick={onConfirmSkip}>
                Yes, skip every check
              </button>
              <button className="act" onClick={() => setConfirmSkip(false)}>Cancel</button>
            </div>
          )}
          {!confirmSkip && settings.launch_permission === 'skip' && (
            <span className="setwarn">Skipping every check. This removes a safeguard.</span>
          )}
          <div className="setrow">
            <label htmlFor="term">Terminal</label>
            <select id="term" value={settings.terminal}
              onChange={(e) => saveSetting('terminal', e.target.value)}>
              <option value="terminal">Terminal</option>
              <option value="iterm">iTerm</option>
            </select>
          </div>
          <div className="setrow">
            <label htmlFor="budget">Monthly budget</label>
            <span className="prefix">$</span>
            <input id="budget" type="number" min="0" step="1" value={budgetInput}
              onChange={(e) => setBudgetInput(e.target.value)}
              onBlur={() => saveSetting('budget', Number(budgetInput) || 0)} />
          </div>
        </details>
      )}
    </main>
  )
}
