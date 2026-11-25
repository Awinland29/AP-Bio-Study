/* Biosphere · Assignments & Schedule. All data is real, user-entered, and backed up. */
'use strict';
const scheduleState={loaded:false,entries:[],classroom_url:'',filter:'upcoming',editing:null,google:{configured:false,connected:false},syncing:false,lastSyncAttempt:0};
const scheduleKinds={assignment:'Assignment',exam:'Test / quiz',class:'Class meeting',event:'Other event'};
const scheduleEsc=value=>e(String(value??''));
const scheduleToday=()=>{const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');};
async function scheduleLoad(){
  try{const [x,g]=await Promise.all([api('/schedule'),api('/google-classroom/status').catch(()=>({configured:false,connected:false}))]);scheduleState.entries=x.entries;scheduleState.classroom_url=x.classroom_url||'';scheduleState.google=g;scheduleState.loaded=true;}
  catch(err){scheduleState.loaded=false;console.warn('Could not load schedule:',err.message);}
}
const previousScheduleRefresh=refresh;
refresh=async function(){await previousScheduleRefresh();await scheduleLoad();};
const previousScheduleRender=render;
render=function(){
  if(state.data && state.page==='schedule'){
    $('#breadcrumb').textContent='ASSIGNMENTS & SCHEDULE';
    $$('.nav-item[data-nav]').forEach(x=>x.classList.toggle('active',x.dataset.nav==='schedule'));
    document.title='Assignments & Schedule · Biosphere';
    $('#main').innerHTML=schedulePage();
    $('#sidebar').classList.remove('open');return;
  }
  previousScheduleRender();
};
function scheduleBadge(x){return ({assignment:'Due',exam:'Test',class:'Class',event:'Event'})[x.kind]||'Item';}
function niceDate(date){if(date==='9999-12-31')return 'No due date';try{return new Date(date+'T12:00:00').toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric'});}catch{return date;}}
function schedulePage(){
  if(!scheduleState.loaded)return pageHeader('Plan ahead','Assignments & Schedule','Could not load the tracker. Refresh the page.');
  const today=scheduleToday();const entries=scheduleState.entries;
  const pending=entries.filter(x=>!x.done), overdue=pending.filter(x=>x.due_date<today).length;
  const list=entries.filter(x=>scheduleState.filter==='all'||(scheduleState.filter==='completed'?x.done:!x.done));
  const grouped=new Map();for(const x of list){const key=x.due_date;if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(x);}
  let rows='';for(const [date,items] of grouped){rows+=`<div class="schedule-day"><div class="schedule-day-label">${scheduleEsc(niceDate(date))}${date<today?'<span class="schedule-overdue">Past date</span>':''}</div>${items.map(scheduleRow).join('')}</div>`;}
  const classroom=scheduleState.classroom_url;const gc=scheduleState.google||{};const gcLast=gc.last_sync?new Date(gc.last_sync).toLocaleString():'Not yet synced';
  const storeWarning=state.data.data_durability==='temporary'?`<div class="storage-notice"><strong>Save backups regularly.</strong><span>Free hosting can erase schedule and assignment data after a restart or deploy.</span>${btn('jump-settings','Back up','secondary tiny')}</div>`:'';
  return `${pageHeader('Never lose track of a due date','Assignments & Schedule','Add assignments, tests and class events manually or import a CSV/ICS file.')}
  ${storeWarning}
  <div class="schedule-stats"><div><strong>${pending.filter(x=>x.kind==='assignment'||x.kind==='exam').length}</strong><span>Open assignments & tests</span></div><div><strong>${overdue}</strong><span>Past due</span></div><div><strong>${entries.length}</strong><span>Total saved items</span></div></div>
  <div class="grid two-col">
  <section class="card"><h3>${scheduleState.editing?'Edit item':'Add an assignment or class event'}</h3><form data-schedule-form="item" class="stack">
    <div class="field"><label>Title</label><input class="input" name="title" required maxlength="180" placeholder="e.g., Enzyme Lab Report" value="${scheduleEsc(scheduleState.editing?.title||'')}"></div>
    <div class="form-grid"><div class="field"><label>Type</label><select class="select" name="kind">${Object.entries(scheduleKinds).map(([k,v])=>`<option value="${k}" ${k===(scheduleState.editing?.kind||'assignment')?'selected':''}>${v}</option>`).join('')}</select></div>
    <div class="field"><label>Date / due date</label><input class="input" type="date" name="due_date" value="${scheduleEsc(scheduleState.editing?.due_date||today)}" required></div>
    <div class="field"><label>Start time (optional)</label><input class="input" type="time" name="start_time" value="${scheduleEsc(scheduleState.editing?.start_time||'')}"></div>
    <div class="field"><label>End time (optional)</label><input class="input" type="time" name="end_time" value="${scheduleEsc(scheduleState.editing?.end_time||'')}"></div></div>
    <div class="field"><label>Details (optional)</label><textarea class="textarea" rows="2" name="details" maxlength="4000" placeholder="What do you need to turn in or bring?">${scheduleEsc(scheduleState.editing?.details||'')}</textarea></div>
    <div class="field"><label>Assignment link (optional)</label><input class="input" name="url" type="url" placeholder="https://classroom.google.com/..." value="${scheduleEsc(scheduleState.editing?.url||'')}"></div>
    <div class="schedule-buttons"><button type="submit" class="btn primary">${scheduleState.editing?'Save changes':'+ Add item'}</button>${scheduleState.editing?'<button type="button" class="btn secondary" data-schedule-action="cancel-edit">Cancel</button>':''}</div>
  </form></section>
  <section class="card"><h3>Import assignments or a calendar</h3><p class="small subtle">Upload a CSV list or .ics calendar export. The dates become real entries below; importing the same file again won't create duplicates.</p>
    <form data-schedule-form="import" class="stack"><div class="field"><label>File to import</label><input class="input" type="file" name="file" accept=".csv,.ics" required></div><button class="btn primary fit" type="submit">Import dates</button></form>
    <button class="btn secondary fit mt16" data-schedule-action="template">Download example CSV template</button><p class="small subtle mt16">CSV columns: Title, Due Date, Type, Start Time, End Time, Details, URL. A PDF syllabus can be saved in Course Resources, but doesn't automatically create dated events. Imports are snapshots, not live sync.</p>
    <div class="schedule-link"><h3>Google Classroom — automatic sync</h3><p class="small subtle">Connect your own Google account to import assignments, due dates, and your submission status. The connection is read-only. It refreshes when you open this page and while the page stays open.</p>
    ${!gc.configured?`<div class="gc-setup"><strong>Setup needed</strong><p class="small subtle">The website owner must register Biosphere as a Google OAuth app and enable Classroom API access. This is a one-time setup, separate from the class link below. Your school might also need to approve access.</p></div>`:gc.connected?`<div class="gc-connected"><strong>Connected to Google Classroom</strong><small>Last checked: ${scheduleEsc(gcLast)} · ${Number(gc.assignment_count)||0} assignments · ${Number(gc.course_count)||0} active classes</small></div><div class="schedule-buttons"><button type="button" class="btn primary" data-schedule-action="gc-sync" ${scheduleState.syncing?'disabled':''}>${scheduleState.syncing?'Syncing…':'Sync now'}</button><button type="button" class="btn secondary" data-schedule-action="gc-disconnect">Disconnect</button></div>${gc.last_error?`<p class="small subtle gc-error">${scheduleEsc(gc.last_error)}</p>`:''}`:`<button type="button" class="btn primary fit" data-schedule-action="gc-connect">Connect Google Classroom</button><p class="small subtle">You will choose the Google account and approve read-only access on Google's website. If your school blocks third-party apps, your administrator must approve the connection.</p>`}
    <div class="divider"></div><p class="small subtle">Optional class shortcut (not a sync connection)</p>
    <form data-schedule-form="classroom" class="stack"><div class="field"><label>Classroom link</label><input class="input" name="url" type="url" placeholder="https://classroom.google.com/c/..." value="${scheduleEsc(classroom)}"></div><div class="schedule-buttons"><button class="btn secondary" type="submit">Save shortcut</button>${classroom?`<a class="btn secondary" href="${scheduleEsc(classroom)}" rel="noreferrer noopener" target="_blank">Open Classroom ↗</a>`:''}</div></form></div>
  </section></div>
  <div class="section-heading schedule-heading"><h2>My dates</h2><div class="schedule-filters"><button class="btn ${scheduleState.filter==='upcoming'?'primary':'secondary'} tiny" data-schedule-action="filter" data-filter="upcoming">To do</button><button class="btn ${scheduleState.filter==='all'?'primary':'secondary'} tiny" data-schedule-action="filter" data-filter="all">All</button><button class="btn ${scheduleState.filter==='completed'?'primary':'secondary'} tiny" data-schedule-action="filter" data-filter="completed">Completed</button></div></div>
  <section class="card schedule-list">${rows||empty(scheduleState.filter==='completed'?'Nothing completed yet':'Nothing to show','Add an assignment or import your calendar above.')}</section>
  <p class="small subtle mt16">Biosphere only reads Google Classroom data. No assignments are submitted or changed in Classroom. Synced completion status comes from Google.</p>`;
}
function scheduleRow(x){const when=[x.start_time,x.end_time].filter(Boolean).join(' – ');
 return `<div class="schedule-item ${x.done?'schedule-done':''}"><input type="checkbox" aria-label="Mark ${scheduleEsc(x.title)} completed" data-schedule-action="toggle" data-id="${scheduleEsc(x.id)}" ${x.done?'checked':''}>
 <div class="schedule-item-info"><div class="schedule-item-top"><span class="chip">${scheduleBadge(x)}</span><strong>${scheduleEsc(x.title)}</strong></div>
 ${when?`<small>${scheduleEsc(when)}</small>`:''}${x.details?`<div class="schedule-detail">${scheduleEsc(x.details)}</div>`:''}
 <small>${x.source==='manual'?'Added manually':x.source==='google_classroom'?'Synced from Google Classroom':'Imported from '+(x.source==='csv'?'CSV':'calendar')}</small></div>
 <div class="schedule-row-actions">${x.url?`<a href="${scheduleEsc(x.url)}" target="_blank" rel="noopener noreferrer" class="btn secondary tiny">Open ↗</a>`:''}<button class="btn secondary tiny" data-schedule-action="edit" data-id="${scheduleEsc(x.id)}">Edit</button><button class="btn secondary tiny" data-schedule-action="remove" data-id="${scheduleEsc(x.id)}">Delete</button></div></div>`;
}
document.addEventListener('click',async event=>{
 const el=event.target.closest('[data-schedule-action]');if(!el)return;
 const action=el.dataset.scheduleAction,id=el.dataset.id;
 if(action==='toggle')return; // checkbox handled in change listener
 try{
   if(action==='gc-connect'){
     const result=await api('/google-classroom/connect',{method:'POST'});
     if(!result.authorization_url?.startsWith('https://accounts.google.com/o/oauth2/v2/auth?'))throw Error('Unexpected Google authorization URL.');
     window.location.assign(result.authorization_url);return;
   }
   if(action==='gc-sync'){await gcSync(true);return;}
   if(action==='gc-disconnect'){
     if(!confirm('Disconnect Google Classroom? Previously synced assignments remain in Biosphere.'))return;
     await api('/google-classroom/disconnect',{method:'POST'});await scheduleLoad();render();toast('Google Classroom disconnected.');return;
   }
   if(action==='filter'){scheduleState.filter=el.dataset.filter;render();return;}
   if(action==='cancel-edit'){scheduleState.editing=null;render();return;}
   if(action==='edit'){scheduleState.editing=scheduleState.entries.find(x=>x.id===id);render();document.querySelector('form[data-schedule-form="item"] input[name="title"]')?.focus();return;}
   if(action==='remove'){if(!confirm('Delete this schedule item?'))return;await api('/schedule/'+id,{method:'DELETE'});await scheduleLoad();render();toast('Schedule entry deleted.');return;}
   if(action==='template'){downloadText('biosphere-assignments-template.csv','Title,Due Date,Type,Start Time,End Time,Details,URL\nPhotosynthesis Quiz,2026-11-16,Test / quiz,09:00,09:50,Review light reactions,\nFormal Lab Report,2026-11-20,Assignment,,,Turn in the final draft,\n','text/csv');return;}
 }catch(err){toast(err.message||String(err),true);}
});
document.addEventListener('change',async event=>{
 const el=event.target.closest('input[data-schedule-action="toggle"]');if(!el)return;
 try{await api('/schedule/'+el.dataset.id,{method:'PATCH',body:JSON.stringify({done:el.checked})});await scheduleLoad();render();toast(el.checked?'Marked complete.':'Reopened item.');}
 catch(err){el.checked=!el.checked;toast(err.message||String(err),true);}
});
document.addEventListener('submit',async event=>{
 const form=event.target.closest('form[data-schedule-form]');if(!form)return;
 event.preventDefault();const type=form.dataset.scheduleForm,button=form.querySelector('button[type="submit"]');if(button)button.disabled=true;
 try{
  if(type==='item'){
   const fields=Object.fromEntries(new FormData(form));const id=scheduleState.editing?.id;
   await api(id?'/schedule/'+id:'/schedule',{method:id?'PATCH':'POST',body:JSON.stringify(fields)});
   scheduleState.editing=null;await scheduleLoad();render();toast(id?'Updated assignment.':'Saved to your schedule.');
  }else if(type==='classroom'){
   const result=await api('/schedule/classroom-link',{method:'PUT',body:JSON.stringify({url:new FormData(form).get('url')||''})});
   await scheduleLoad();render();toast(result.url?'Shortcut saved. Automatic sync is not enabled.':'Shortcut cleared.');
  }else if(type==='import'){
   const data=new FormData(form);if(!data.get('file')?.name)throw Error('Choose a CSV or ICS file.');
   const res=await api('/schedule/import',{method:'POST',body:data});await scheduleLoad();render();
   toast(`${res.created} imported; ${res.duplicates} duplicates; ${res.skipped} skipped.${res.warnings.length?' '+res.warnings.slice(0,2).join(' '):''}`,!!res.skipped);
  }
 }catch(err){toast(err.message||String(err),true);}
 finally{if(button)button.disabled=false;}
},true);

async function gcSync(manual=false){
  if(scheduleState.syncing||!scheduleState.google?.connected)return;
  const now=Date.now(),last=Date.parse(scheduleState.google.last_sync||'')||0;
  if(!manual&&now-last<5*60*1000)return;
  if(!manual&&now-scheduleState.lastSyncAttempt<5*60*1000)return;
  scheduleState.lastSyncAttempt=now;scheduleState.syncing=true;if(state.page==='schedule')render();
  try{
    const x=await api('/google-classroom/sync',{method:'POST'});
    await scheduleLoad();
    if(manual)toast(`Classroom synced: ${x.added} new, ${x.updated} updated.`);
  }catch(err){
    await scheduleLoad();if(manual)toast(err.message||String(err),true);
  }finally{scheduleState.syncing=false;if(state.page==='schedule')render();}
}
const originalScheduleGo=go;
go=async function(page){await originalScheduleGo(page);if(page==='schedule')gcSync(false);};
scheduleLoad().then(async()=>{
  if(state.data&&state.page==='schedule')render();
  const gc=new URLSearchParams(window.location.search).get('classroom');
  if(gc){window.history.replaceState({},'',window.location.pathname);await go('schedule');if(gc==='connected')toast('Classroom connected! Assignments are syncing.');else toast('Google did not connect. Your school may require app approval.',true);}
});
setInterval(()=>{if(state.page==='schedule'&&!document.hidden)gcSync(false);},5*60*1000);

