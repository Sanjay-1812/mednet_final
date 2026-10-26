'use strict';
const $ = id => document.getElementById(id);
const policyNames = {fifo:'FIFO', priority:'Fixed priority', mednet:'MedNet'};
const colors = {fifo:'#517ca1', priority:'#bb882b', mednet:'#087e83'};
const policies = Object.keys(policyNames);
const kinds = ['emergency','monitoring','video','images','records','admin'];
let info, current, scenario = 'congested', busy = false, dirty = false;
const fmt = (n, d=0) => Number(n).toLocaleString('en-US', {minimumFractionDigits:d, maximumFractionDigits:d});
const title = s => s.charAt(0).toUpperCase() + s.slice(1);
const text = (id, value) => $(id).textContent = value;
const rowFor = (policy, kind='ALL') => current.metrics.find(r=>r.scenario===scenario && r.policy===policy && r.traffic_class===kind);
function cell(tr, value, tag='td') { const c=document.createElement(tag);c.textContent=value;tr.append(c);return c; }
function row(body, values) {const tr=document.createElement('tr');values.forEach(v=>cell(tr,v));body.append(tr);return tr;}
function resetSettings(){for(const [key,value] of Object.entries(info.defaults)) $(key).value=value;$('source').value='generate';$('dataset').value='';toggleSource();}
function toggleSource(){const replay=$('source').value==='replay';$('upload').hidden=!replay;document.querySelectorAll('.generation').forEach(el=>{el.hidden=replay;el.querySelectorAll('input').forEach(i=>i.disabled=replay);});}
function markDirty(){if(current&&!busy){dirty=true;text('status','Settings changed. Run comparison to update the results below.');}}
function payload(){const data={mode:$('source').value};Object.keys(info.defaults).forEach(key=>data[key]=Number($(key).value));return data;}
async function run(mode){
  if(busy)return;
  $('error').hidden=true;
  if(mode==='example')resetSettings();
  if(!$('experiment').reportValidity())return;
  const data=payload();
  if(mode==='example') data.mode='example';
  if(data.mode==='replay'){
    const file=$('dataset').files[0];
    if(!file){showError('Select a trace CSV before running replay.');return;}
    if(file.size>3*1024*1024){showError('Select a CSV smaller than 3 MB for dashboard replay.');return;}
    data.dataset_csv=await file.text();
  }
  busy=true;
  document.querySelectorAll('#experiment input, #experiment select').forEach(el=>el.disabled=true);
  $('run').disabled=$('example').disabled=$('reset').disabled=true;
  text('run','Running comparison…');text('status','Simulating the same traffic through FIFO, fixed priority, and MedNet…');
  try{
    const response=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'The experiment could not run.');
    current=result;dirty=false;render();$('empty').hidden=true;$('results-content').hidden=false;
    text('status',`Comparison complete · ${fmt(rowTotal('normal')+rowTotal('congested'))} input packets · 3 schedulers · ${result.mode==='generate'?'Generated traffic':'CSV dataset replay'}`);
  }catch(error){showError(error.message==='Failed to fetch'?'Cannot reach Python. Keep the MedNet terminal open and try again.':error.message);text('status',current?'The last successful result is still displayed.':'Ready for an experiment.');if(!current)$('empty').hidden=false;}
  finally{busy=false;document.querySelectorAll('#experiment input, #experiment select').forEach(el=>el.disabled=false);toggleSource();$('run').disabled=$('example').disabled=$('reset').disabled=false;text('run','Run comparison →');}
}
function showError(message){text('error',message);$('error').hidden=false;}
function rowTotal(s){return current.metrics.find(r=>r.scenario===s&&r.policy==='mednet'&&r.traffic_class==='ALL').generated;}
function render(){
  const cfg=current.config, m=rowFor('mednet'), f=rowFor('fifo');
  const s=cfg.scenarios.find(s=>s.scenario===scenario);
  text('result-title',`${title(scenario)} scenario`);
  document.querySelectorAll('[data-scenario]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.scenario===scenario)));
  text('run-context',`${cfg.input_origin==='generated'?`Seed ${cfg.seed}`:'Replayed CSV'} · ${fmt(cfg.arrival_horizon_s,1)} s of arrivals · ${fmt(cfg.link_bps/1e6,2)} Mbps link · ${cfg.waiting_capacity_packets} waiting slots · queues drain after arrivals stop`);
  text('packet-count',fmt(m.generated));text('offered-load',`${fmt(s.offered_mbps,3)} Mbps`);
  text('load-detail',`${fmt(s.offered_mbps/(cfg.link_bps/1e6)*100,1)}% of configured link rate`);
  text('success',m.generated?`${fmt(m.on_time_success_pct,2)}%`:'—');
  const delta=m.on_time_success_pct-f.on_time_success_pct;
  text('success-detail',m.generated?`${delta>=0?'+':''}${fmt(delta,2)} percentage points vs FIFO`:'No packets in this scenario');
  chart();
  $('summary-body').replaceChildren();
  policies.forEach(p=>{const r=rowFor(p);row($('summary-body'),[policyNames[p],fmt(r.delivered_on_time),fmt(r.delivered_late),fmt(r.buffer_dropped),r.delivered?`${fmt(r.mean_delay_ms,2)} ms`:'—',`${fmt(r.throughput_mbps,3)} Mbps`]);});
  classTable();packetTable();
  $('download').href=`/download/${current.run_id}/results.zip`;
  $('metrics-download').href=`/download/${current.run_id}/metrics.csv`;
  text('fingerprint',`Trace SHA-256: ${cfg.trace_sha256} · Downloads remain available for the eight most recent runs while Python is open.`);
}
function chart(){
  const width=780,height=210,left=150,right=65,top=25,plot=width-left-right;
  const ns='http://www.w3.org/2000/svg';const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('role','img');
  svg.setAttribute('aria-label',policies.map(p=>`${policyNames[p]} on-time success ${fmt(rowFor(p).on_time_success_pct,2)} percent`).join('; '));
  function el(tag,attrs,content){const e=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);if(content!==undefined)e.textContent=content;svg.append(e);return e;}
  [0,25,50,75,100].forEach(n=>{const x=left+n/100*plot;el('line',{x1:x,y1:top-3,x2:x,y2:top+145,stroke:'#e7ede8','stroke-dasharray':'3 4'});el('text',{x,y:192,fill:'#7b8c87','font-size':11,'text-anchor':'middle'},`${n}%`);});
  policies.forEach((p,i)=>{const r=rowFor(p),y=top+i*50;el('text',{x:left-16,y:y+21,fill:'#425c66','font-size':12,'text-anchor':'end'},policyNames[p]);el('rect',{x:left,y,width:plot,height:32,rx:5,fill:'#f0f4f0'});el('rect',{x:left,y,width:Math.max(0,r.on_time_success_pct)/100*plot,height:32,rx:5,fill:colors[p]});el('text',{x:width-20,y:y+21,fill:colors[p],'font-size':12,'font-weight':650,'text-anchor':'end'},r.generated?`${fmt(r.on_time_success_pct,1)}%`:'—');});
  $('chart').replaceChildren(svg);
  const m=rowFor('mednet'),p=rowFor('priority');
  text('chart-note',m.generated?`MedNet: ${fmt(m.delivered_on_time)} on time, ${fmt(m.delivered_late)} late, ${fmt(m.buffer_dropped)} dropped. Fixed priority: ${fmt(p.on_time_success_pct,2)}% on time. Compare class-level tradeoffs below.`:'This scenario contains no packets. Percentages and delay comparisons are undefined.');
}
function classTable(){const body=$('class-body');body.replaceChildren();const metric=$('class-metric').value;kinds.forEach(k=>{const vals=policies.map(p=>{const r=rowFor(p,k);if(metric.includes('delay')&&!r.delivered||metric==='on_time_success_pct'&&!r.generated)return '—';return fmt(r[metric],metric==='buffer_dropped'?0:2);});row(body,[title(k),fmt(rowFor('mednet',k).generated),...vals]);});}
function packetTable(){const body=$('packet-body');body.replaceChildren();const p=$('packet-policy').value;const rows=current.previews[scenario+'/'+p]||[];rows.forEach(r=>{const delivered=r.status==='delivered',late=delivered&&Number(r.finish_s)>Number(r.deadline_s)+1e-12;const tr=row(body,[r.packet_id,title(r.kind),fmt(r.arrival_s,4),delivered?fmt((Number(r.finish_s)-Number(r.arrival_s))*1000,2):'—']);const c=cell(tr,'');const b=document.createElement('span');b.className='badge'+(!delivered?' drop':late?' late':'');b.textContent=!delivered?'Dropped':late?'Late':'On time';c.append(b);});if(!rows.length)row(body,['—','No packets','—','—','—']);}
async function init(){
  try{const res=await fetch('/api/info');if(!res.ok)throw new Error('Could not load settings.');info=await res.json();resetSettings();
    const table=document.createElement('table');const head=document.createElement('thead');row(head,['Class','Priority','Deadline']);table.append(head);const body=document.createElement('tbody');Object.entries(info.classes).forEach(([k,v])=>row(body,[title(k),v.priority,`${v.deadline_ms} ms`]));table.append(body);$('class-definitions').append(table);
    await run('example');
  }catch(e){showError('Cannot connect to the local Python app. Start app.py and refresh this page.');text('status','Connection unavailable.');}
}
$('experiment').addEventListener('submit',e=>{e.preventDefault();run();});
$('example').addEventListener('click',()=>run('example'));
$('reset').addEventListener('click',()=>{resetSettings();markDirty();});
$('source').addEventListener('change',toggleSource);
$('experiment').addEventListener('input',markDirty);
document.querySelectorAll('[data-scenario]').forEach(button=>button.addEventListener('click',()=>{scenario=button.dataset.scenario;if(current)render();}));
$('class-metric').addEventListener('change',()=>{if(current)classTable();});
$('packet-policy').addEventListener('change',()=>{if(current)packetTable();});
$('about-toggle').addEventListener('click',()=>{const open=$('class-definitions').hidden;$('class-definitions').hidden=!open;$('about-toggle').setAttribute('aria-expanded',String(open));text('about-toggle',open?'Hide traffic classes ↑':'View traffic classes ↓');});
init();
