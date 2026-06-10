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
let EXTRA={pending:[],costs:null,schedules:{},failures:[],work:[],queued:[]};
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
  }
  return {path:f.path,category:f.path.split('/').length>1?f.path.split('/')[0]:'uncategorized',
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
      +' prepared work, started by '+esc(p.source_plain||'an automated run')
      +(relTime(p.meta.created)?', '+relTime(p.meta.created):'')
      +(CFG.live?'<button class="pbtn okb" data-i="'+i+'" data-d="approve">Approve</button>'
                +'<button class="pbtn nob" data-i="'+i+'" data-d="discard">Discard</button>'
                +'<span class="pstatus" data-i="'+i+'"></span>':'')
      +'</li>').join('')
    +'</ul><div class="panel-note">'
    +(CFG.live?'Approve records your decision; the action itself happens in your next Claude session. Discard cancels it.'
              :'Approve or discard these in Claude: "review my pending runs".')+'</div>';
  el.querySelectorAll('.pitem').forEach(n=>{
    n.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();n.onclick();}};
    n.onclick=()=>{
    const p=items[+n.dataset.i];
    document.getElementById('dtitle').textContent='Waiting for you: '+(sopTitle(p.meta.sop)||p.path);
    document.getElementById('dbody').innerHTML=
      '<div class="dmeta"><span class="badge pending">pending</span>'
      +'<span class="pill">started by '+esc(p.source_plain||'an automated run')+'</span>'
      +'<span class="pill">'+esc(relTime(p.meta.created)||p.meta.created||'')+'</span></div>'
      +mdToHtml(p.body);
    dlg.showModal();
  };});
  el.querySelectorAll('.pbtn').forEach(btn=>{btn.onclick=async()=>{
    const p=items[+btn.dataset.i];
    const st=el.querySelector('.pstatus[data-i="'+btn.dataset.i+'"]');
    el.querySelectorAll('.pbtn[data-i="'+btn.dataset.i+'"]').forEach(b=>b.disabled=true);
    try{
      const r=await fetch('/api/resolve',{method:'POST',
        headers:{'Content-Type':'application/json','X-Token':CFG.token},
        body:JSON.stringify({file:p.path,decision:btn.dataset.d})});
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
}
function renderAttention(){
  const att=sops.filter(s=>s.flags.length);
  const failLis=(EXTRA.failures||[]).map(f=>'<li><b>'+esc(sopTitle(f.sop))+'</b> ('+esc(relTime(f.when)||f.when)+'): '
    +esc(f.plain)+'. To fix: '+esc(f.action)+'.</li>');
  const el=document.getElementById('attention');
  if(!att.length&&!failLis.length)return;
  el.style.display='block';
  el.innerHTML='<h2>Needs attention</h2><ul>'+failLis.join('')
    +att.map(s=>'<li>'+esc(s.title)+': '+s.flags.join(', ')+'</li>').join('')+'</ul>';
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
      card.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openDetail(s);}};
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
      card.onclick=()=>openDetail(s);
      grid.appendChild(card);
    });
  });
}

/* ---------- Detail dialog ---------- */
function openDetail(s){
  document.getElementById('dtitle').textContent=s.title;
  const m=s.meta;
  const improved=Math.max(0,parseInt(m.version||'1')-1);
  const runs=parseInt(m.runs||'0');
  const clean=parseInt(m.clean_runs||'0');
  document.getElementById('dbody').innerHTML=
    '<div class="dmeta"><span class="badge '+s.status+'" title="'+esc(STATUS_TIP[s.status]||'')+'">'+s.status+'</span>'
    +'<span class="pill">'+(runs>0?('used '+runs+' time'+(runs===1?'':'s')):'never used yet')+'</span>'
    +(relTime(m.last_used)?'<span class="pill">last '+esc(relTime(m.last_used))+'</span>':'')
    +(improved>0?'<span class="pill">improved '+improved+' time'+(improved===1?'':'s')+'</span>':'')
    +(clean>0?'<span class="pill">'+clean+' smooth run'+(clean===1?'':'s')+' in a row</span>':'')
    +rels('needs first',m.needs)+rels('then usually',m.next)+rels('project version of',m.extends)
    +'</div>'
    +runBox(s)
    +suggestBox(s)
    +mdToHtml(s.body)
    +'<div class="fileline">File: '+esc(s.path)
    +(CFG.live?' <a href="#" id="openfile">open in editor</a>':'')+'</div>';
  const btn=document.getElementById('sgbtn');
  if(btn)btn.onclick=()=>submitSuggestion(s);
  const qb=document.getElementById('queuebtn');
  if(qb)qb.onclick=()=>queueTask(s);
  const of=document.getElementById('openfile');
  if(of)of.onclick=(e)=>{e.preventDefault();launchClaude({kind:'open_file',id:s.meta.id},null);};
  const dn=document.getElementById('donowbtn');
  if(dn)dn.onclick=()=>{dn.disabled=true;launchClaude({kind:'sop',id:s.meta.id},document.getElementById('donowstatus'));};
  const rb=document.getElementById('runbtn');
  const ri0=document.getElementById('runinputs');
  if(rb&&ri0&&(s.meta.run_inputs||'').trim()){
    ri0.addEventListener('input',()=>{
      const filled=!!ri0.value.trim();
      rb.disabled=!filled;
      const st0=document.getElementById('runstatus');
      st0.textContent=filled?'':'Fill in what it needs first';
    });
  }
  if(rb)rb.onclick=async()=>{
    rb.disabled=true;
    const st=document.getElementById('runstatus');
    st.className='sstatus';
    try{
      const ri=document.getElementById('runinputs');
      const r=await fetch('/api/run',{method:'POST',
        headers:{'Content-Type':'application/json','X-Token':CFG.token},
        body:JSON.stringify({id:s.meta.id,inputs:ri?ri.value.trim():''})});
      st.textContent=r.ok?'Started. Check back in a minute or two; if it needs your OK it will appear under "Waiting for you".':'Could not start ('+r.status+').';
    }catch(e){st.textContent='Could not reach the dashboard.';rb.disabled=false;}
  };
  dlg.showModal();
}
function rels(label,val){
  if(!val)return '';
  return val.split(',').map(x=>x.trim()).filter(Boolean)
    .map(id=>'<span class="pill relpill">'+label+': '+refLink(id)+'</span>').join('');
}
function runBox(s){
  if(s.archived)return '';
  if(s.status==='draft'){
    const trig=(s.meta.triggers||'').split(',')[0].trim();
    return '<div class="suggest"><div class="slabel">Run this task</div>'
      +'<div class="hint lead">This task hasn’t been done together yet, so it can’t run in the background. '
      +'Do it once with Claude'+(trig?' (just say “'+esc(trig)+'”)':'')+' and the Run button appears here afterward.'+'</div>'
      +(CFG.live?'<div class="row lead"><button class="btn-primary runbtn" id="donowbtn">Do it with Claude now</button>'
        +'<span class="sstatus" id="donowstatus"></span></div>'
        +'<textarea id="queueinputs" rows="2" placeholder="Anything Claude should know when you do it together? Optional."></textarea>'
        +scopeChoice()
        +'<div class="row"><button class="pbtn" id="queuebtn">Put it on my plate for later</button>'
        +'<span class="sstatus" id="queuestatus"></span></div>':'')
      +'</div>';
  }
  if(!CFG.live)return '';
  const req=(s.meta.run_inputs||'').trim();
  const items=req?req.split(',').map(x=>x.trim()).filter(Boolean):[];
  return '<div class="suggest"><div class="slabel">Run this task</div>'
    +(items.length?'<div class="hint lead">Tell it: '
      +items.map(t=>'<em class="reqchip">'+esc(t)+'</em>').join('')+'</div>':'')
    +'<textarea id="runinputs" rows="2" placeholder="'
    +(items.length?'Type those here':'Anything this run should know? Optional.')
    +'"></textarea>'
    +scopeChoice()
    +'<div class="row"><button class="btn-primary runbtn" id="runbtn"'+(req?' disabled':'')+'>Run this now</button>'
    +'<button class="pbtn" id="queuebtn">Put it on my plate instead</button>'
    +'<span class="sstatus err" id="runstatus">'+(req?'Fill in what it needs first':'')+'</span>'
    +'<span class="sstatus" id="queuestatus"></span></div>'
    +'<div class="hint">Run now happens in the background using a little of your Claude plan’s automation allowance (the dollar figures track that usage, not separate charges), and stops for your approval before anything is sent. "On my plate" does it with you, live, next time you open Claude; pick that for anything that needs you mid-task.</div></div>';
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
  const box=document.getElementById('queueinputs')||document.getElementById('runinputs');
  const picked=document.querySelector('input[name=qscope]:checked');
  const scope=picked?picked.value:'here';
  qb.disabled=true;
  try{
    const r=await fetch('/api/queue',{method:'POST',
      headers:{'Content-Type':'application/json','X-Token':CFG.token},
      body:JSON.stringify({id:s.meta.id,inputs:box?box.value.trim():'',scope:scope})});
    st.textContent=r.ok?'On your plate. It comes up next time you open Claude in '+queueDest(scope)+'.':'Could not save ('+r.status+').';
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
  const a=e.target.closest('a.sopref');if(!a)return;
  const t=sopById(a.dataset.id);if(t)openDetail(t);
}
document.getElementById('dbody').addEventListener('click',followSopref);
document.getElementById('dbody').addEventListener('keydown',e=>{
  if(e.key==='Enter'||e.key===' '){followSopref(e);}
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
renderWaiting();renderAttention();renderWork();renderPlate();renderComing();renderMeter();
render();
startLiveness();
