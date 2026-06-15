<script>
  import { onMount, onDestroy } from 'svelte';

  // Live-mirror state, fed by the SSE stream (/events). The dashboard's whole job is to be
  // trusted as current, so a dead/quiet stream surfaces a staleness banner.
  let plate = $state([]);
  let runs = $state([]);
  let stale = $state(false);
  let lastEventAt = Date.now();
  let es;
  let staleTimer;
  const STALE_MS = 15000; // ~1.5 missed heartbeats (server beats every ~10s)
  const token = window.__SMBOS_TOKEN__ || '';

  function fresh() {
    lastEventAt = Date.now();
    stale = false;
  }

  // A malformed frame must not throw out of the listener (it would drop the frame AND skip
  // fresh(), so the banner could fire on a live stream). Parse defensively; the arrival of
  // ANY frame still means the stream is alive, so fresh() runs regardless.
  function onFrame(setter) {
    return (e) => {
      try { setter(JSON.parse(e.data)); } catch (_) { /* keep last good data */ }
      fresh();
    };
  }

  onMount(() => {
    es = new EventSource(`/events?t=${encodeURIComponent(token)}`);
    es.addEventListener('plate', onFrame((v) => { plate = v; }));
    es.addEventListener('runs', onFrame((v) => { runs = v; }));
    es.addEventListener('heartbeat', fresh);
    es.onerror = () => { stale = true; };  // surface the drop; EventSource auto-reconnects
    staleTimer = setInterval(() => { stale = Date.now() - lastEventAt > STALE_MS; }, 3000);
  });
  onDestroy(() => { es?.close(); clearInterval(staleTimer); });

  // running = open run (no end recorded); done/error from the result. (Stalled detection
  // needs flock-derived liveness in the API; a follow-up.)
  function runState(r) {
    if (r.result === 'error') return 'err';
    if (r.result) return 'done';
    return 'live';
  }
</script>

<main>
  {#if stale}
    <div class="banner" role="status">Reconnecting, data may be stale</div>
  {/if}

  <header><span class="dot live" aria-hidden="true"></span><h1>SmbOS</h1></header>

  <section class="panel">
    <div class="overline">On your plate</div>
    {#if plate.length === 0}
      <p class="empty">Nothing waiting for you right now.</p>
    {:else}
      <ol class="list">
        {#each plate as t}
          <li>
            <span class="subj">{t.subject}</span>
            <span class="chip chip-{t.status}">{t.status}</span>
          </li>
        {/each}
      </ol>
    {/if}
  </section>

  <section class="panel">
    <div class="overline">Recent runs</div>
    {#if runs.length === 0}
      <p class="empty">No runs yet.</p>
    {:else}
      <ul class="list">
        {#each runs as r}
          <li>
            <span class="dot {runState(r)}" aria-hidden="true"></span>
            <span class="subj">{r.sop_id}</span>
            <span class="chip">{r.result || 'running'}</span>
          </li>
        {/each}
      </ul>
    {/if}
  </section>
</main>
