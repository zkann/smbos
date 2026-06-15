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

  onMount(() => {
    es = new EventSource(`/events?t=${encodeURIComponent(token)}`);
    es.addEventListener('plate', (e) => { plate = JSON.parse(e.data); fresh(); });
    es.addEventListener('runs', (e) => { runs = JSON.parse(e.data); fresh(); });
    es.addEventListener('heartbeat', fresh);
    // EventSource auto-reconnects on error; the staleness banner covers the gap.
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

  <header><span class="dot live"></span><h1>SmbOS</h1></header>

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
            <span class="dot {runState(r)}"></span>
            <span class="subj">{r.sop_id}</span>
            <span class="chip">{r.result || 'running'}</span>
          </li>
        {/each}
      </ul>
    {/if}
  </section>
</main>
