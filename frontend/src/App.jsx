import { useEffect, useState } from 'react'

// Live-mirror dashboard. Subscribes to the SSE stream (/events) and renders the command-center
// plate + run history. The whole job is to be trusted as current, so a dead/quiet stream
// surfaces a staleness banner.
const STALE_MS = 15000 // ~1.5 missed heartbeats (server beats every ~10s)
const token = window.__SMBOS_TOKEN__ || ''

// running = open run (no end recorded); done/error from the result. (Stalled detection needs
// flock-derived liveness in the API; a follow-up.)
function runState(r) {
  if (r.result === 'error') return 'err'
  if (r.result) return 'done'
  return 'live'
}

export default function App() {
  const [plate, setPlate] = useState([])
  const [runs, setRuns] = useState([])
  const [stale, setStale] = useState(false)

  useEffect(() => {
    // the token arrived via /?t=...; the SPA uses the injected window.__SMBOS_TOKEN__, so drop
    // ?t= from the address bar/history to cut leakage via screenshots, copy/paste, and logs
    const u = new URL(window.location.href)
    if (u.searchParams.has('t')) {
      u.searchParams.delete('t')
      history.replaceState(null, '', `${u.pathname}${u.search}${u.hash}`)
    }

    let lastEventAt = Date.now()
    const fresh = () => { lastEventAt = Date.now(); setStale(false) }
    // a malformed frame must not throw out of the listener (it would drop the frame AND skip
    // fresh(), so the banner could fire on a live stream); any frame means the stream is alive
    const onFrame = (set) => (e) => {
      try { set(JSON.parse(e.data)) } catch (_) { /* keep last good data */ }
      fresh()
    }

    const es = new EventSource(`/events?t=${encodeURIComponent(token)}`)
    es.addEventListener('plate', onFrame(setPlate))
    es.addEventListener('runs', onFrame(setRuns))
    es.addEventListener('heartbeat', fresh)
    es.onerror = () => setStale(true) // surface the drop; EventSource auto-reconnects
    const timer = setInterval(() => setStale(Date.now() - lastEventAt > STALE_MS), 3000)

    return () => { es.close(); clearInterval(timer) }
  }, [])

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
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="panel">
        <div className="overline">Recent runs</div>
        {runs.length === 0 ? (
          <p className="empty">No runs yet.</p>
        ) : (
          <ul className="list">
            {runs.map((r, i) => (
              <li key={r.id ?? i}>
                <span className={`dot ${runState(r)}`} aria-hidden="true"></span>
                <span className="subj">{r.sop_id}</span>
                <span className="chip">{r.result || 'running'}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}
