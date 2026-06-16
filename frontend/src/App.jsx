import { useEffect, useState } from 'react'

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
  const [runs, setRuns] = useState([])
  const [stale, setStale] = useState(false)
  // per-task launch state: id -> 'launching' | 'error'. A successful launch clears via the SSE
  // plate frame moving the item to in-flight; an error stays visible so the row offers a retry.
  const [launch, setLaunch] = useState({})

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

    const es = new EventSource(`/events?t=${encodeURIComponent(token)}`)
    es.addEventListener('plate', onPlate)
    es.addEventListener('inflight', onFrame(setInflight))
    es.addEventListener('runs', onFrame(setRuns))
    es.addEventListener('heartbeat', fresh)
    es.onerror = () => setStale(true) // surface the drop; EventSource auto-reconnects
    const timer = setInterval(() => setStale(Date.now() - lastEventAt > STALE_MS), 3000)

    return () => { es.close(); clearInterval(timer) }
  }, [])

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
    </main>
  )
}
