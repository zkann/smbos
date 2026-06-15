/* SmbOS dashboard app.
 *
 * Structured as render functions that map 1:1 onto future React components,
 * so an eventual port is mechanical:
 *   summary()          -> <Header/> (chip, counts, mode note)
 *   renderWaiting()    -> <WaitingForYou/>   (approvals inbox + actions)
 *   renderAttention()  -> <NeedsAttention/>  (translated failures + flags)
 *   renderWork()       -> <InFlight/>        (stage boards)
 *   renderPlate()      -> <OnYourPlate/>     (queued tasks + launch)
 *   renderComing()     -> <ComingUp/>        (schedules + spend)
 *   renderMeter()      -> <GettingGoing/>
 *   render()           -> <ProceduresGrid/>  (sorted cards + legend)
 *   openDetail()       -> <ProcedureDialog/> (runBox/suggestBox/queue actions)
 *   startLiveness()    -> useLiveness() hook (ping + idle refresh)
 * Data contracts: the embedded JSON blobs (sop-data, cfg, extra) and the
 * /api/* endpoints are the stable interface; keep them framework-agnostic.
 */
const GENERATED="__GENERATED__";
const CFG=JSON.parse(document.getElementById('cfg').textContent||'{"live":false}');
let EXTRA={pending:[],costs:null,schedules:{},failures:[],work:[],queued:[],runs:[]};
try{EXTRA=Object.assign(EXTRA,JSON.parse(document.getElementById('extra').textContent));}catch(e){/* older generator */}
const dlg=document.getElementById('dlg');

function parseSop(raw){
  const meta={}; let body=raw;
  const m=raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if(m){
    m[1].split(/\r?\n/).forEach(l=>{const i=l.indexOf(':'); if(i>0) meta[l.slice(0,i).trim()]=l.slice(i+1).trim();});
    body=m[2];
  }
  return {meta, body};
}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function sopById(id){return sops.find(x=>(x.meta.id||'')===id);}
function refLink(id){
  const t=sopById(id);
  return t?'<a class="sopref" data-id="'+esc(id)+'" tabindex="0" role="link">'+esc(t.title)+'</a>'
          :'<span class="sopref missing">'+esc(id)+' (missing)</span>';
}
function inline(s){
  return esc(s)
    .replace(/\[\[sop:([a-zA-Z0-9_-]+)\]\]/g,(m,id)=>refLink(id))
    .replace(/\[personalize:([^\]]*)\]/g,'<span class="slot">personalize:$1</span>')
    .replace(/\*\*\[APPROVAL\]\*\*/g,'<span class="approval">APPROVAL</span>')
    .replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>')
    .replace(/`([^`]+)`/g,'<code>$1</code>');
}
function mdToHtml(md){
  let out='',list=null;
  const close=()=>{if(list){out+='</'+list+'>';list=null;}};
  md.split(/\r?\n/).forEach(line=>{
    if(/^##\s/.test(line)){close();out+='<h2>'+inline(line.slice(3))+'</h2>';}
    else if(/^#\s/.test(line)){close();out+='<h1>'+inline(line.slice(2))+'</h1>';}
    else if(/^\d+\.\s/.test(line)){if(list!=='ol'){close();out+='<ol>';list='ol';}out+='<li>'+inline(line.replace(/^\d+\.\s/,''))+'</li>';}
    else if(/^[-*]\s/.test(line)){if(list!=='ul'){close();out+='<ul>';list='ul';}out+='<li>'+inline(line.slice(2))+'</li>';}
    else if(line.trim()===''){close();}
    else{close();out+='<p>'+inline(line)+'</p>';}
  });
  close();return out;
}
// The `## Candidates` json block is machine-readable data that drives the
// per-item Start buttons; keep it out of the human-rendered body so it never
// shows as raw JSON. The candidates appear as clickable rows instead.
function stripCandidatesBlock(body){
  return body.replace(/\n*##\s+Candidates\b[\s\S]*?```json[\s\S]*?```[ \t]*/i,'\n');
}
function section(body,name){
  const re=new RegExp('## '+name+'\\r?\\n([\\s\\S]*?)(?=\\r?\\n## |$)');
  const m=body.match(re);return m?m[1].trim():'';
}
function daysAgo(d){
  if(!d||d==='never')return null;
  const t=Date.parse(d);return isNaN(t)?null:Math.floor((Date.parse(GENERATED)-t)/86400000);
}
function relTime(d){
  const n=daysAgo(d);
  if(n===null)return null;
  if(n<=0)return 'today';
  if(n===1)return 'yesterday';
  if(n<30)return n+' days ago';
  return 'on '+String(d).slice(0,10);
}
const sops=JSON.parse(document.getElementById('sop-data').textContent).map(f=>{
  const {meta,body}=parseSop(f.content);
  const archived=(meta.status==='archived')||f.path.includes('archive/');
  const status=archived?'archived':(meta.status||'draft');
  const purpose=(section(body,'Purpose').split(/\r?\n/)[0]||'').trim();
  const used=daysAgo(meta.last_used);
  const created=daysAgo(meta.created);
  const hasVariants=/\n## Variants/.test(body);
  const flags=[];
  if(!archived){
    if(status==='draft'&&meta.runs==='0'&&created!==null&&created>30)flags.push('never run');
    else if(used!==null&&used>90)flags.push('stale');
    else if(meta.last_used==='never'&&created!==null&&created>30)flags.push('stale');
    if(section(body,'Notes for next revision').length>3)flags.push('pending notes');
    if(f.drift)flags.push('unrecorded changes');
  }
  return {path:f.path,drift:!!f.drift,category:f.path.split('/').length>1?f.path.split('/')[0]:'uncategorized',
    meta,body,status,purpose,flags,archived,hasVariants,
    title:meta.title||meta.id||f.path,raw:f.content};
});

/* ---------- Today tab ---------- */
function sopTitle(id){const s=sopById(id);return s?s.title:id;}
const STATUS_TIP={
  draft:"Not yet done together. Do it once with Claude and it becomes active.",
  active:"Done together at least once. Can run in the background.",
  trusted:"Ran smoothly 3+ times in a row. Safe to automate.",
  archived:"Retired. Kept for history."
};
function renderWaiting(){
  const items=(EXTRA.pending||[]).map(p=>({...p,...parseSop(p.content)}))
    .filter(p=>(p.meta.status||'pending')==='pending');
  const el=document.getElementById('waiting');
  if(!items.length){
    el.className='panel ok';
    el.innerHTML='<h2>Waiting for you</h2>Nothing needs your OK right now &#10003;';
    return;
  }
  el.className='panel';
  el.innerHTML='<h2>Waiting for you ('+items.length+')</h2><ul>'
    +items.map((p,i)=>'<li><span class="pitem" data-i="'+i+'" tabindex="0" role="button">'+esc(sopTitle(p.meta.sop)||p.path)+'</span>'
      +(p.meta.deliverable?': '+esc(p.meta.deliverable):' prepared work')
      +(p.meta.partial==='true'?' <span class="badge partial">partial</span>':'')
      +', from '+esc(p.source_plain||'an automated run')
      +(relTime(p.meta.created)?', '+relTime(p.meta.created):'')
      +(CFG.live?'<button class="pbtn okb" data-i="'+i+'" data-d="approve">Approve</button>'
                +'<button class="pbtn nob" data-i="'+i+'" data-d="discard">Discard</button>'
                +'<span class="pstatus" data-i="'+i+'"></span>':'')
      +(CFG.live&&p.candidates&&p.candidates.length&&p.next
        ? '<ul class="cands">'+p.candidates.map((c,ci)=>'<li><span class="candttl">'+esc(c.title)+'</span>'
            +(c.note?' <span class="candnote">'+esc(c.note)+'</span>':'')
            +'<button class="pbtn okb candstart" data-i="'+i+'" data-ci="'+ci+'">Start in Claude</button>'
            +'<span class="sstatus candst" data-i="'+i+'" data-ci="'+ci+'"></span></li>').join('')+'</ul>'
        : '')
      +'</li>').join('')
    +'</ul><div class="panel-note">'
    +(CFG.live?'Approve records your decision; the action itself happens in your next Claude session. Discard cancels it.'
              :'Approve or discard these in Claude: "review my pending runs".')+'</div>';
  el.querySelectorAll('.pitem').forEach(n=>{
    n.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();n.onclick();}};
    n.onclick=()=>{
    const p=items[+n.dataset.i];
    const srcSop=sopById(p.meta.sop);
    // A result and the procedure that made it are one thing seen two ways. Show
    // provenance as a breadcrumb (the procedure NAME is the link, no extra chrome),
    // and let the procedure open with a way back, so it is a loop, not a dead end.
    const openResult=()=>{
      document.getElementById('dtitle').textContent='Waiting for you: '+(sopTitle(p.meta.sop)||p.path);
      document.getElementById('dbody').innerHTML=
        (srcSop?'<div class="crumb">from <a class="crumblink" id="viewsrcsop" tabindex="0" role="link">'+esc(srcSop.title)+'</a> &rsaquo; this run</div>':'')
        +'<div class="dmeta"><span class="badge pending">pending</span>'
        +'<span class="pill">started by '+esc(p.source_plain||'an automated run')+'</span>'
        +'<span class="pill">'+esc(relTime(p.meta.created)||p.meta.created||'')+'</span></div>'
        +mdToHtml(stripCandidatesBlock(p.body));
      const v=document.getElementById('viewsrcsop');
      if(v){v.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();v.onclick();}};
            v.onclick=()=>openDetail(srcSop,{label:'the result',fn:openResult});}
      if(!dlg.open)dlg.showModal();
    };
    openResult();
  };});
  el.querySelectorAll('.pbtn[data-d]').forEach(btn=>{btn.onclick=async()=>{
    const p=items[+btn.dataset.i];
    const st=el.querySelector('.pstatus[data-i="'+btn.dataset.i+'"]');
    let reason='';
    if(btn.dataset.d==='discard'&&!btn.dataset.askedReason){
      btn.dataset.askedReason='1';
      st.innerHTML='What was off? (helps it improve; optional) <input class="reasonbox" data-i="'+btn.dataset.i+'" size="28"> ';
      btn.textContent='Discard it';
      st.querySelector('.reasonbox').focus();
      return;
    }
    if(btn.dataset.d==='discard'){
      const rb=el.querySelector('.reasonbox[data-i="'+btn.dataset.i+'"]');
      reason=rb?rb.value.trim():'';
      st.textContent='';
    }
    el.querySelectorAll('.pbtn[data-i="'+btn.dataset.i+'"]').forEach(b=>b.disabled=true);
    try{
      const r=await fetch('/api/resolve',{method:'POST',
        headers:{'Content-Type':'application/json','X-Token':CFG.token},
        body:JSON.stringify({file:p.path,decision:btn.dataset.d,reason:reason})});
      if(r.ok){
        if(btn.dataset.d==='approve'){
          st.innerHTML='Approved. <button class="pbtn okb" id="donow'+btn.dataset.i+'">Do it now in Claude</button>';
          document.getElementById('donow'+btn.dataset.i).onclick=function(){this.disabled=true;launchClaude({kind:'approved'},st);};
        }else{st.textContent='Discarded.';}
      }
      else{st.textContent='Could not save ('+r.status+').';
        el.querySelectorAll('.pbtn[data-i="'+btn.dataset.i+'"]').forEach(b=>b.disabled=false);}
    }catch(e){st.textContent='Could not reach the dashboard.';
      el.querySelectorAll('.pbtn[data-i="'+btn.dataset.i+'"]').forEach(b=>b.disabled=false);}
  };});
  // per-candidate one-click action: launch the source SOP's next: SOP on this item
  el.querySelectorAll('.candstart').forEach(b=>{b.onclick=async()=>{
    const p=items[+b.dataset.i];
    const st=el.querySelector('.candst[data-i="'+b.dataset.i+'"][data-ci="'+b.dataset.ci+'"]');
    b.disabled=true;if(st){st.className='sstatus';st.textContent='Opening…';}
    try{
      const r=await fetch('/api/apply-item',{method:'POST',headers:{'Content-Type':'application/json','X-Token':CFG.token},
        body:JSON.stringify({file:p.path,index:+b.dataset.ci})});
      if(r.ok){if(st)st.textContent='Opened a Claude window for you.';}
      else{const e=await r.json().catch(()=>({}));if(st){st.className='sstatus err';st.textContent=e.error||('Could not start ('+r.status+').');}b.disabled=false;}
    }catch(e){if(st){st.className='sstatus err';st.textContent='Could not reach the dashboard.';}b.disabled=false;}
  };});
}
function renderAttention(){
  const driftLis=sops.filter(s=>!s.archived&&s.drift&&(s.status==='active'||s.status==='trusted'))
    .map(s=>'<li><b>'+esc(s.title)+'</b> was changed outside the normal save flow. '
      +'Ask Claude to review the changes; until then it won\u2019t run on its own.</li>');
  const att=sops.map(s=>({s,fl:s.flags.filter(f=>f!=='unrecorded changes')})).filter(x=>x.fl.length);
  const failLis=(EXTRA.failures||[]).map(f=>'<li><b>'+esc(sopTitle(f.sop))+'</b> ('+esc(relTime(f.when)||f.when)+'): '
    +esc(f.plain)+'. To fix: '+esc(f.action)+'.</li>');
  const el=document.getElementById('attention');
  if(!att.length&&!failLis.length&&!driftLis.length)return;
  el.style.display='block';
  el.innerHTML='<h2>Needs attention</h2><ul>'+driftLis.join('')+failLis.join('')
    +att.map(x=>'<li>'+esc(x.s.title)+': '+x.fl.join(', ')+'</li>').join('')+'</ul>';
}
function renderWork(){
  const items=EXTRA.work||[];
  const el=document.getElementById('work');
  if(!items.length)return;
  el.style.display='block';
  el.innerHTML='<h2>In flight</h2>'+items.map(w=>{
    let passed=true;
    const chips=(w.stages.length?w.stages:[w.stage]).map(s=>{
      let cls='wstage';
      if(s===w.stage){cls+=' cur';passed=false;}
      else if(passed){cls+=' done';}
      return '<span class="'+cls+'">'+esc(s)+'</span>';
    }).join('<span class="warrow">›</span>');
    return '<div class="witem"><div class="wt">'+esc(w.title)
      +(w.status==='blocked'?'<span class="wflag">BLOCKED</span>':'')
      +(w.project?'<span class="wproj">'+esc(w.project)+'</span>':'')
      +'</div><div class="wstages">'+chips+'</div></div>';
  }).join('');
}
// Run-lifecycle: what is running right now, and what started but stopped without
// finishing (the silent-failure class made visible). Idle/done show nothing.
function renderRuns(){
  const runs=EXTRA.runs||[];
  const el=document.getElementById('runs');
  if(!runs.length){el.style.display='none';el.innerHTML='';return;}
  const running=runs.filter(r=>r.state==='running');
  const stalled=runs.filter(r=>r.state==='stalled');
  el.style.display='block';
  let html='<h2>Runs</h2><ul>';
  html+=running.map(r=>'<li><span class="runlive">running now</span> <b>'+esc(sopTitle(r.sop))+'</b>'
    +(relTime(r.started)?', started '+esc(relTime(r.started)):'')+'</li>').join('');
  html+=stalled.map(r=>'<li><span class="runstall">stopped without finishing</span> <b>'+esc(sopTitle(r.sop))+'</b>'
    +(relTime(r.started)?', started '+esc(relTime(r.started)):'')+'. Check the result, or it may have failed.'
    +(CFG.live?'<button class="pbtn nob runclr" data-f="'+esc(r.file)+'">Dismiss</button>':'')+'</li>').join('');
  html+='</ul>';
  if(stalled.length)html+='<div class="panel-note">A run that stops without finishing leaves nothing in "Waiting for you". If this keeps happening, the run is failing; check it in Claude.</div>';
  el.innerHTML=html;
  el.querySelectorAll('.runclr').forEach(b=>{b.onclick=async()=>{
    b.disabled=true;
    try{await fetch('/api/clear-run',{method:'POST',headers:{'Content-Type':'application/json','X-Token':CFG.token},body:JSON.stringify({file:b.dataset.f})});
      b.closest('li').remove();
      if(!el.querySelectorAll('li').length){el.style.display='none';}
    }catch(e){b.disabled=false;}
  };});
}
function renderPlate(){
  const items=EXTRA.queued||[];
  const el=document.getElementById('plate');
  if(!items.length)return;
  el.style.display='block';
  el.innerHTML='<h2>On your plate ('+items.length+')</h2><ul>'
    +items.map((q,i)=>'<li><b>'+esc(sopTitle(q.sop))+'</b>'
      +(q.project?': for the <b>'+esc(q.project)+'</b> folder':'')
      +(CFG.live?'<button class="pbtn okb qstart" data-i="'+i+'">Start in Claude</button>'
        +'<span class="sstatus qst" data-i="'+i+'"></span>':'')
      +'</li>').join('')
    +'</ul><div class="panel-note">These are tasks you saved to do together; they need you in the loop.'
    +(CFG.live?' "Start in Claude" opens a terminal window in the right folder with the task ready to go.':'')+'</div>';
  el.querySelectorAll('.qstart').forEach(b=>{b.onclick=()=>{
    const q=items[+b.dataset.i];b.disabled=true;
    launchClaude({kind:'queue',file:q.file},el.querySelector('.qst[data-i="'+b.dataset.i+'"]'));
  };});
}
function renderComing(){
  const sch=EXTRA.schedules||{};
  const names=Object.keys(sch);
  const c=EXTRA.costs;
  const el=document.getElementById('coming');
  if(!names.length&&!(c&&c.runs>0))return;
  el.style.display='block';
  let html='<h2>Coming up</h2>';
  if(names.length){
    html+='<ul>'+names.map(n=>{
      const s=sopById(n);
      return '<li><b>'+esc(s?s.title:n)+'</b> runs '+sch[n].map(esc).join('; ')+'</li>';
    }).join('')+'</ul>';
  }else{
    html+='<div class="quiet">Nothing is scheduled yet. Pick a recurring task and tell Claude: "run this every Monday morning".</div>';
  }
  if(c&&(c.runs>0||c.budget>0)){
    const pct=c.budget?Math.min(100,c.month_total/c.budget*100):0;
    html+='<div class="spend">Automation has used <b>$'+c.month_total.toFixed(2)+'</b>'
      +(c.budget?' of its $'+c.budget.toFixed(0)+' monthly allowance':'')
      +' ('+c.runs+' run'+(c.runs===1?'':'s')+' this month). These figures track your Claude plan usage, not separate charges.'
      +(c.budget?'<div class="spendbar"><div style="width:'+pct+'%"></div></div>':'')+'</div>';
  }
  el.innerHTML=html;
}
function renderMeter(){
  const live=sops.filter(s=>!s.archived);
  if(!live.length)return;
  const steps=[
    {label:'Library started',done:live.length>0},
    {label:'First task done together',done:live.some(s=>parseInt(s.meta.runs||'0')>0)},
    {label:'A task earned "active"',done:live.some(s=>s.status==='active'||s.status==='trusted')},
    {label:'A task earned "trusted"',done:live.some(s=>s.status==='trusted')},
    {label:'Something runs on a schedule',done:Object.keys(EXTRA.schedules||{}).length>0}
  ];
  const doneCount=steps.filter(s=>s.done).length;
  if(doneCount===steps.length)return;
  const next=steps.find(s=>!s.done);
  const wins={'First task done together':'Next time you do any of these tasks, just ask Claude in plain words; the matching procedure runs and gets verified.',
    'A task earned "active"':'Finish one task with Claude and it is promoted automatically.',
    'A task earned "trusted"':'Three smooth runs of the same task and it earns trusted (which unlocks worry-free automation).',
    'Something runs on a schedule':'Pick a recurring task and tell Claude: "run this every Monday morning".'};
  const el=document.getElementById('meter');
  el.style.display='block';
  el.innerHTML='<h2>Getting going ('+doneCount+' of '+steps.length+')</h2><div>'
    +steps.map(s=>'<span class="step'+(s.done?' done':'')+'">'+(s.done?'&#10003; ':'&#9675; ')+esc(s.label)+'</span>').join('')
    +'</div><div class="nextwin">Easiest next win: '+esc(wins[next.label]||next.label)+'</div>';
}
// One prominent "do this first" line, computed from the same priority order the panels use,
// so the owner gets a decision instead of having to scan every panel. Only shown when more
// than one area needs them (with a single area, that panel already is the answer).
function renderNextAction(){
  const el=document.getElementById('nextaction');
  if(!el)return;
  const failures=EXTRA.failures||[];
  const drift=sops.filter(s=>!s.archived&&s.drift&&(s.status==='active'||s.status==='trusted'));
  const flagged=sops.filter(s=>!s.archived&&s.flags.filter(f=>f!=='unrecorded changes').length);
  const blocked=(EXTRA.work||[]).filter(w=>w.status==='blocked');
  const waiting=(EXTRA.pending||[]).map(p=>({...p,...parseSop(p.content)})).filter(p=>(p.meta.status||'pending')==='pending');
  const plate=EXTRA.queued||[];
  const areas=[(failures.length+drift.length+flagged.length)>0,blocked.length>0,waiting.length>0,plate.length>0].filter(Boolean).length;
  let msg='',target='';
  if(failures.length){msg='Fix what broke: <b>'+esc(sopTitle(failures[0].sop))+'</b> '+esc(failures[0].plain)+'.';target='attention';}
  else if(drift.length){msg='Review the changes to <b>'+esc(drift[0].title)+'</b> so it can run again.';target='attention';}
  else if(blocked.length){msg='Unblock <b>'+esc(blocked[0].title)+'</b>: it’s waiting on you.';target='work';}
  else if(waiting.length){const d=waiting[0].meta.deliverable;msg='Approve or discard '+waiting.length+' prepared item'+(waiting.length===1?'':'s')+(d?': <b>'+esc(d)+'</b>':'')+'.';target='waiting';}
  else if(plate.length){msg='Start <b>'+esc(sopTitle(plate[0].sop))+'</b> with Claude.';target='plate';}
  if(areas<2||!msg){el.style.display='none';el.innerHTML='';return;}
  el.style.display='block';
  el.innerHTML='<div class="na-label">Do this first</div><button class="na-line" data-target="'+target+'">'+msg+'</button>';
  el.querySelector('.na-line').onclick=()=>{const t=document.getElementById(target);if(t)t.scrollIntoView({behavior:'smooth',block:'center'});};
}

/* ---------- Procedures tab ---------- */
const RANK={trusted:0,active:1,draft:2,archived:3};
function render(){
  const q=document.getElementById('q').value.toLowerCase();
  const showArch=document.getElementById('showArchived').checked;
  const vis=sops.filter(s=>(!s.archived||showArch)&&(!q||s.raw.toLowerCase().includes(q)));
  const cats={};vis.forEach(s=>{(cats[s.category]=cats[s.category]||[]).push(s);});
  const main=document.getElementById('main');main.innerHTML='';
  if(!vis.length){main.innerHTML='<div class="empty-state">'+(sops.length?'No procedures match that search.':'Nothing here yet. Tell Claude about your business and it will set up a starter pack.')+'</div>';return;}
  const catKey=cat=>{
    const best=Math.min(...cats[cat].map(s=>RANK[s.status]??2));
    const recent=Math.min(...cats[cat].map(s=>{const n=daysAgo(s.meta.last_used);return n===null?9999:n;}));
    return [best,recent];
  };
  Object.keys(cats).sort((a,b)=>{const ka=catKey(a),kb=catKey(b);return ka[0]-kb[0]||ka[1]-kb[1]||a.localeCompare(b);})
  .forEach(cat=>{
    const h=document.createElement('h2');h.className='cat';h.textContent=cat;main.appendChild(h);
    const grid=document.createElement('div');grid.className='grid';main.appendChild(grid);
    cats[cat].sort((a,b)=>{
      const r=(RANK[a.status]??2)-(RANK[b.status]??2);if(r)return r;
      const da=daysAgo(a.meta.last_used),db=daysAgo(b.meta.last_used);
      return (da===null?9999:da)-(db===null?9999:db)||a.title.localeCompare(b.title);
    }).forEach(s=>{
      const card=document.createElement('div');card.className='card';
      card.tabIndex=0;card.setAttribute('role','button');
      card.onkeydown=e=>{if(e.target.closest('a.sopref'))return;if(e.key==='Enter'||e.key===' '){e.preventDefault();openDetail(s);}};
      const trig=(s.meta.triggers||'').split(',').map(t=>t.trim()).filter(Boolean).slice(0,4);
      const runs=parseInt(s.meta.runs||'0');
      const usedLine=runs>0?('used '+runs+' time'+(runs===1?'':'s')
          +(relTime(s.meta.last_used)?', last '+relTime(s.meta.last_used):'')):'never used yet';
      card.innerHTML='<div class="top"><h3>'+esc(s.title)+'</h3>'
        +'<span class="badge '+s.status+'" title="'+esc(STATUS_TIP[s.status]||'')+'">'+s.status+'</span></div>'
        +'<p>'+inline(s.purpose)+'</p>'
        +'<div class="stats"><span>'+usedLine+'</span>'
        +(s.hasVariants?'<span>adapts by project</span>':'')
        +(s.meta.extends?'<span>project version</span>':'')
        +s.flags.map(f=>'<span class="flag">'+f+'</span>').join('')+'</div>'
        +(trig.length?'<div class="trig">say: '+trig.map(t=>'<em>'+esc(t)+'</em>').join('')+'</div>':'')
        +((EXTRA.schedules[s.meta.id]||[]).length
          ?'<div class="trig">runs '+EXTRA.schedules[s.meta.id].map(esc).join('; ')+'</div>':'');
      card.onclick=e=>{if(e.target.closest('a.sopref'))return;openDetail(s);};
      grid.appendChild(card);
    });
  });
}

/* ---------- Detail dialog ---------- */
function openDetail(s, back){
  document.getElementById('dtitle').textContent=s.title;
  const m=s.meta;
  const improved=Math.max(0,parseInt(m.version||'1')-1);
  const runs=parseInt(m.runs||'0');
  const clean=parseInt(m.clean_runs||'0');
  document.getElementById('dbody').innerHTML=
    (back?'<a class="crumbback" id="backcrumb" tabindex="0" role="link">&lsaquo; Back to '+esc(back.label)+'</a>':'')
    +'<div class="dmeta"><span class="badge '+s.status+'" title="'+esc(STATUS_TIP[s.status]||'')+'">'+s.status+'</span>'
    +'<span class="pill">'+(runs>0?('used '+runs+' time'+(runs===1?'':'s')):'never used yet')+'</span>'
    +(relTime(m.last_used)?'<span class="pill">last '+esc(relTime(m.last_used))+'</span>':'')
    +(improved>0?'<span class="pill">improved '+improved+' time'+(improved===1?'':'s')+'</span>':'')
    +(clean>0?'<span class="pill">'+clean+' smooth run'+(clean===1?'':'s')+' in a row</span>':'')
    +'<span class="pill">v'+esc(m.version||'1')+'</span>'
    +(s.drift?'<span class="pill warn">unrecorded changes</span>':'')
    +rels('needs first',m.needs)+rels('then usually',m.next)+rels('project version of',m.extends)
    +'</div>'
    +(s.drift?'<div class="hint warnhint">This procedure was changed without the usual save. Tell Claude “review the changes to '+esc(s.title)+'” to record them'+(s.status==='trusted'?'; until then it won\u2019t run unattended':'')+'.</div>':'')
    +runBox(s)
    +suggestBox(s)
    +mdToHtml(s.body)
    +'<div class="fileline">File: '+esc(s.path)
    +(CFG.live?' <a href="#" id="openfile">open in editor</a>':'')+'</div>';
  const btn=document.getElementById('sgbtn');
  if(btn)btn.onclick=()=>submitSuggestion(s);
  const pb=document.getElementById('preparebtn');
  if(pb)pb.onclick=async()=>{
    const ri=document.getElementById('runinputs');
    const st=document.getElementById('runstatus');
    pb.disabled=true;st.className='sstatus';st.textContent='Starting…';
    try{
      const r=await fetch('/api/run',{method:'POST',
        headers:{'Content-Type':'application/json','X-Token':CFG.token},
        body:JSON.stringify({id:s.meta.id,mode:'prepare',inputs:ri?ri.value.trim():''})});
      if(r.ok){st.textContent='Working on it without you. The result lands under "Waiting for you" (you’ll get a notification).';}
      else{const e=await r.json().catch(()=>({}));st.className='sstatus err';st.textContent=e.error||('Could not start ('+r.status+').');pb.disabled=false;}
    }catch(e){st.className='sstatus err';st.textContent='Could not reach the dashboard.';pb.disabled=false;}
  };
  const qb=document.getElementById('queuebtn');
  if(qb)qb.onclick=()=>queueTask(s);
  const of=document.getElementById('openfile');
  if(of)of.onclick=(e)=>{e.preventDefault();launchClaude({kind:'open_file',id:s.meta.id},null);};
  const dn=document.getElementById('donowbtn');
  if(dn)dn.onclick=()=>{dn.disabled=true;launchClaude({kind:'sop',id:s.meta.id},document.getElementById('donowstatus'));};
  const bc=document.getElementById('backcrumb');
  if(bc){bc.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();bc.onclick();}};
         bc.onclick=()=>back.fn();}
  const ri0=document.getElementById('runinputs');
  if(pb&&ri0&&(s.meta.run_inputs||'').trim()&&!s.drift&&!s.body.includes('[personalize:')){
    ri0.addEventListener('input',()=>{
      const filled=!!ri0.value.trim();
      pb.disabled=!filled;
      const st0=document.getElementById('runstatus');
      st0.textContent=filled?'':'Fill in what it needs first';
    });
  }
  if(!dlg.open)dlg.showModal();
}
function rels(label,val){
  if(!val)return '';
  return val.split(',').map(x=>x.trim()).filter(Boolean)
    .map(id=>'<span class="pill relpill">'+label+': '+refLink(id)+'</span>').join('');
}
function runBox(s){
  if(s.archived)return '';
  if(!CFG.live)return '';
  const blocked=s.drift;
  const needsPersonalize=s.body.includes('[personalize:');
  const req=(s.meta.run_inputs||'').trim();
  const items=req?req.split(',').map(x=>x.trim()).filter(Boolean):[];
  const gate=blocked?'Record its changes first (tell Claude)'
            :(needsPersonalize?'Personalize it first (open it with Claude once)'
            :(req?'Fill in what it needs first':''));
  const deliverable=s.meta.deliverable||'';
  // State-dependent emphasis: a draft's safe first move is doing it WITH Claude, live and
  // supervised, so that earns the green primary and leads. "Do it without me" (autonomous,
  // in the cage) only takes the primary once a procedure is active/trusted. This keeps the
  // most prominent button pointed at the right action and never leaves a disabled primary.
  const isDraft=s.status==='draft';
  const prepareBtn='<button class="'+(isDraft?'pbtn':'btn-primary runbtn')+'" id="preparebtn"'+(gate?' disabled':'')+'>Do it without me</button>';
  const queueBtn='<button class="pbtn" id="queuebtn">Put it on my plate instead</button>';
  const donowBtn=isDraft?'<button class="btn-primary runbtn" id="donowbtn">Do it with Claude now</button>':'';
  return '<div class="suggest"><div class="slabel">Run this task</div>'
    +(deliverable?'<div class="hint lead">You get: '+esc(deliverable)+'</div>':'')
    +(items.length?'<div class="hint lead">Tell it: '
      +items.map(t=>'<em class="reqchip">'+esc(t)+'</em>').join('')+'</div>':'')
    +'<textarea id="runinputs" rows="2" placeholder="'
    +(items.length?'Type those here':'Anything this run should know? Optional.')
    +'"></textarea>'
    +scopeChoice()
    +'<div class="row">'+(isDraft?donowBtn+queueBtn+prepareBtn:prepareBtn+queueBtn)
    +'<span class="sstatus err" id="runstatus">'+gate+'</span>'
    +'<span class="sstatus" id="queuestatus"></span>'
    +'<span class="sstatus" id="donowstatus"></span></div>'
    +'<div class="hint">'+(isDraft?'"Do it with Claude now" opens a window and does it with you, live. ':'')
    +'"Do it without me" prepares the work in the background inside a safety cage (it can’t send, publish, or spend; it can only research the sources this procedure declares) and the result lands under "Waiting for you", with a notification. It uses a little of your Claude plan’s automation allowance; the dollar figures track that usage, not separate charges. "On my plate" does it with you, live, next time you open Claude.</div></div>';
}
function scopeChoice(){
  if(!CFG.project)return '';
  return '<div class="hint lead">When you save it, do it in: '
    +'<label><input type="radio" name="qscope" value="here" checked> '+esc(CFG.project)+' (this folder)</label>'
    +'<label><input type="radio" name="qscope" value="anywhere"> any folder</label></div>';
}
function queueDest(scope){
  if(scope==='anywhere'||!CFG.project)return 'any folder';
  return CFG.project;
}
async function launchClaude(body,st,doing){
  if(st){st.className='sstatus';st.textContent=doing||'Opening Claude...';}
  try{
    const r=await fetch('/api/launch',{method:'POST',
      headers:{'Content-Type':'application/json','X-Token':CFG.token},
      body:JSON.stringify(body)});
    if(st){
      if(r.ok){st.textContent='Opened a Claude window for you.';}
      else{const e=await r.json().catch(()=>({}));st.className='sstatus err';st.textContent=e.error||('Could not open ('+r.status+').');}
    }
  }catch(e){if(st){st.className='sstatus err';st.textContent='Could not reach the dashboard.';}}
}
async function queueTask(s){
  const qb=document.getElementById('queuebtn');
  const st=document.getElementById('queuestatus');
  const box=document.getElementById('runinputs');
  const picked=document.querySelector('input[name=qscope]:checked');
  const scope=picked?picked.value:'here';
  qb.disabled=true;
  try{
    const r=await fetch('/api/queue',{method:'POST',
      headers:{'Content-Type':'application/json','X-Token':CFG.token},
      body:JSON.stringify({id:s.meta.id,inputs:box?box.value.trim():'',scope:scope})});
    if(r.ok){const j=await r.json().catch(()=>({}));
      st.textContent='On your plate. It comes up next time you open Claude in '+(j.dest||queueDest(scope))+'.';}
    else st.textContent='Could not save ('+r.status+').';
    if(!r.ok)qb.disabled=false;
  }catch(e){st.textContent='Could not reach the dashboard.';qb.disabled=false;}
}
function suggestBox(s){
  if(s.archived)return '';
  return '<div class="suggest"><div class="slabel">Suggest a change</div>'
    +'<textarea id="sgtext" rows="2" placeholder="e.g. Payment terms are net 15 now, not net 30"></textarea>'
    +'<div class="row"><button class="btn-primary" id="sgbtn">'+(CFG.live?'Save suggestion':'Copy for Claude')+'</button>'
    +'<span class="sstatus" id="sgstatus"></span></div>'
    +'<div class="hint">'+(CFG.live
      ?'Saves into this procedure’s notes. Next session, Claude offers to turn it into an edit you approve.'
      :'Copies a ready-made request. Paste it into Claude Code and the change goes through the normal approve flow.')+'</div></div>';
}
async function copyText(t){
  try{await navigator.clipboard.writeText(t);return true;}
  catch(e){
    const ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);
    ta.select();let ok=false;try{ok=document.execCommand('copy');}catch(_){/* no-op */}
    ta.remove();return ok;
  }
}
async function submitSuggestion(s){
  const ta=document.getElementById('sgtext'),st=document.getElementById('sgstatus');
  const text=ta.value.trim();
  if(!text){st.className='sstatus err';st.textContent='Type the change first.';return;}
  if(CFG.live){
    try{
      const r=await fetch('/api/suggest',{method:'POST',
        headers:{'Content-Type':'application/json','X-Token':CFG.token},
        body:JSON.stringify({path:s.path,text:text})});
      if(r.ok){st.className='sstatus';st.textContent='Saved to this procedure’s notes.';ta.value='';}
      else{st.className='sstatus err';st.textContent='Could not save ('+r.status+').';}
    }catch(e){st.className='sstatus err';st.textContent='Could not reach the dashboard.';}
  }else{
    const msg='Update the "'+s.title+'" SOP ('+s.path+'): '+text;
    if(await copyText(msg)){st.className='sstatus';st.textContent='Copied. Paste it into Claude Code.';}
    else{st.className='sstatus err';st.textContent='Copy failed; select and copy the text yourself: '+msg;}
  }
}

/* ---------- Header, tabs, liveness ---------- */
function summary(){
  const live=sops.filter(s=>!s.archived);
  const n=k=>live.filter(s=>s.status===k).length;
  const countPill=(k,label)=>{const c=n(k);
    return '<span class="pill'+(c?' '+k:'')+'"><b>'+c+'</b> '+label+'</span>';};
  document.getElementById('counts').innerHTML=
    '<span class="pill"><b>'+live.length+'</b> procedures</span>'
    +countPill('trusted','trusted')
    +countPill('active','active')
    +countPill('draft','drafts')
    +(sops.length-live.length?'<span class="pill">'+(sops.length-live.length)+' archived</span>':'');
  const chip=document.getElementById('modechip');
  if(CFG.live){
    chip.className='chip live';
    chip.textContent='Live'+(CFG.project?' · '+CFG.project:'');
  }else{
    chip.className='chip';
    chip.textContent='Snapshot · taken '+(relTime(GENERATED)||'')+' at '+new Date(GENERATED).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'});
  }
  document.getElementById('modeNote').textContent=CFG.live
    ?(CFG.project?' Tasks you put on your plate default to the '+CFG.project+' folder.':' Tasks you put on your plate run in any folder.')
    :' This page is a snapshot; ask Claude for your dashboard to get a fresh one.';
  renderSettings();
}
const PERM_OPTIONS=[
  ['ask','Ask me before everything','Claude checks with you before every action.'],
  ['trust','Ask before running things','Claude applies edits on its own but checks before running commands or fetching the web. The safe default.'],
  ['skip','Don\u2019t ask, just run it','No prompts at all. Fast, but the only thing watching is you. Best only when you\u2019re sitting with it.']
];
async function saveSetting(key,value,st,okmsg){
  st.className='sstatus';st.textContent='Saving\u2026';
  try{
    const r=await fetch('/api/settings',{method:'POST',
      headers:{'Content-Type':'application/json','X-Token':CFG.token},
      body:JSON.stringify({key:key,value:value})});
    const j=await r.json().catch(()=>({}));
    if(r.ok&&j.ok){st.className='sstatus';st.textContent=okmsg;return j;}
    st.className='sstatus err';st.textContent=(j&&j.error)||('Could not save ('+r.status+').');return null;
  }catch(e){st.className='sstatus err';st.textContent='Could not reach the dashboard.';return null;}
}
function renderSettings(){
  const el=document.getElementById('settings');
  if(!el)return;
  if(!CFG.live){el.innerHTML='';return;}
  const cur=CFG.launch_permission||'trust';
  const permdesc=(PERM_OPTIONS.find(o=>o[0]===cur)||PERM_OPTIONS[1])[2];
  const term=CFG.terminal||'terminal';
  const budget=(CFG.budget!=null?CFG.budget:20);
  const dtime=CFG.digest_time||'';
  const dnotify=CFG.digest_notify!==false;
  el.innerHTML='<details class="settings"><summary>Settings</summary>'
    +'<div class="setrow"><label>When I open Claude for a task'
    +'<select id="permsel">'+PERM_OPTIONS.map(o=>'<option value="'+o[0]+'"'+(o[0]===cur?' selected':'')+'>'+esc(o[1])+'</option>').join('')+'</select></label>'
    +'<span class="setdesc'+(cur==='skip'?' setwarn':'')+'" id="permdesc">'+esc(permdesc)+'</span>'
    +'<span class="sstatus" id="permstatus"></span></div>'
    +'<div class="setrow"><label>Monthly automation budget $'
    +'<input id="budgetin" type="number" min="0" step="1" value="'+esc(String(budget))+'"></label>'
    +'<span class="setdesc">Caps what background runs may spend against your plan\u2019s allowance. The meter on Today tracks usage against it.</span>'
    +'<span class="sstatus" id="budgetstatus"></span></div>'
    +'<div class="setrow"><label>Open Claude in'
    +'<select id="termsel"><option value="terminal"'+(term==='terminal'?' selected':'')+'>Terminal</option>'
    +'<option value="iterm"'+(term==='iterm'?' selected':'')+'>iTerm2</option></select></label>'
    +'<span class="setdesc">Which terminal the launch buttons open.</span>'
    +'<span class="sstatus" id="termstatus"></span></div>'
    +'<div class="setrow"><label>Daily summary at'
    +'<input id="digesttime" type="time" value="'+esc(dtime)+'">'
    +'<button class="pbtn" id="digestoff"'+(dtime?'':' style="display:none"')+'>off</button></label>'
    +'<label class="setinline"><input type="checkbox" id="digestnotify"'+(dnotify?' checked':'')+'> also notify me</label>'
    +'<span class="setdesc">A once-a-day rundown of what\u2019s waiting, ran, and cost. The time sets a schedule on this Mac (it runs when the Mac is awake).</span>'
    +'<span class="sstatus" id="digeststatus"></span></div>'
    +'</details>';
  // launch_permission has its own endpoint (separate from /api/settings)
  document.getElementById('permsel').onchange=async function(){
    const v=this.value;const st=document.getElementById('permstatus');const d=document.getElementById('permdesc');
    st.className='sstatus';st.textContent='Saving\u2026';
    try{const r=await fetch('/api/launch-permission',{method:'POST',headers:{'Content-Type':'application/json','X-Token':CFG.token},body:JSON.stringify({value:v})});
      if(r.ok){CFG.launch_permission=v;d.textContent=(PERM_OPTIONS.find(o=>o[0]===v)||PERM_OPTIONS[1])[2];d.className='setdesc'+(v==='skip'?' setwarn':'');st.textContent='Saved. Applies the next time you open Claude.';}
      else st.className='sstatus err',st.textContent='Could not save.';}
    catch(e){st.className='sstatus err';st.textContent='Could not reach the dashboard.';}
  };
  document.getElementById('budgetin').onchange=async function(){
    const j=await saveSetting('budget',this.value,document.getElementById('budgetstatus'),'Saved.');
    if(j&&j.budget!=null){CFG.budget=j.budget;this.value=j.budget;}
  };
  document.getElementById('termsel').onchange=function(){
    saveSetting('terminal',this.value,document.getElementById('termstatus'),'Saved.').then(j=>{if(j)CFG.terminal=j.terminal;});
  };
  document.getElementById('digestnotify').onchange=function(){
    saveSetting('digest_notify',this.checked,document.getElementById('digeststatus'),'Saved.');
  };
  const dt=document.getElementById('digesttime'),doff=document.getElementById('digestoff');
  dt.onchange=async function(){
    const j=await saveSetting('digest_time',this.value,document.getElementById('digeststatus'),'Saved. You\u2019ll get the summary daily at '+this.value+'.');
    if(j){CFG.digest_time=this.value;doff.style.display=this.value?'':'none';}
  };
  doff.onclick=async function(){
    const j=await saveSetting('digest_time','',document.getElementById('digeststatus'),'Daily summary turned off.');
    if(j){CFG.digest_time='';dt.value='';doff.style.display='none';}
  };
}
document.querySelectorAll('.tab').forEach(b=>{b.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));
  document.getElementById('tab-today').style.display=b.dataset.tab==='today'?'':'none';
  document.getElementById('tab-procedures').style.display=b.dataset.tab==='procedures'?'':'none';
};});
document.getElementById('dclose').addEventListener('click',()=>dlg.close());
document.getElementById('q').addEventListener('input',render);
document.getElementById('showArchived').addEventListener('change',render);
function followSopref(e){
  const a=e.target.closest('a.sopref');if(!a)return false;
  const t=sopById(a.dataset.id);if(t)openDetail(t);
  return true;
}
document.addEventListener('click',followSopref);
document.addEventListener('keydown',e=>{
  if(e.key==='Enter'||e.key===' '){if(followSopref(e))e.preventDefault();}
});
let connDead=false;
function startLiveness(){
  if(!CFG.live)return;
  setInterval(async()=>{
    try{
      const r=await fetch('/api/ping',{headers:{'X-Token':CFG.token}});
      if(!r.ok)throw new Error();
      if(connDead){location.reload();}
    }catch(e){
      connDead=true;
      document.getElementById('connbanner').className='show';
      document.getElementById('modechip').className='chip';
      document.getElementById('modechip').textContent='Disconnected';
    }
  },15000);
  setInterval(()=>{
    if(connDead||dlg.open)return;
    if(document.getElementById('q').value)return;
    if(document.activeElement&&['TEXTAREA','INPUT'].includes(document.activeElement.tagName))return;
    location.reload();
  },90000);
}
summary();
renderWaiting();renderAttention();renderRuns();renderWork();renderPlate();renderComing();renderMeter();renderNextAction();
render();
startLiveness();
