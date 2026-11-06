/* Biosphere Google Classroom: read-only assignment syncing. */
'use strict';
const gc = {status:null,items:[],loading:false,busy:false,error:'',loaded:false};
function gcEl(tag,cls,text){
  const el=document.createElement(tag);
  if(cls)el.className=cls;
  if(text!==undefined)el.textContent=String(text);
  return el;
}
function gcControl(text,action){
  const el=gcEl('button','btn '+(action==='sync'?'primary':'secondary'),text);
  el.type='button';el.dataset.gcAction=action;return el;
}
function gcPanel(){
  const main=document.querySelector('#main');
  if(!main || state.page!=='schedule')return;
  const anchor=main.querySelector('.schedule-stats');
  if(!anchor)return;
  let panel=main.querySelector('#gc-panel');
  if(!panel){panel=gcEl('section','card gc-card');panel.id='gc-panel';anchor.parentNode.insertBefore(panel,anchor);}
  panel.replaceChildren();
  const header=gcEl('div','card-header');
  header.append(gcEl('h3','', 'Google Classroom · Live assignment sync'));
  header.append(gcEl('span','chip',gc.status?.connected?'CONNECTED':gc.status?.configured?'READY':'SETUP NEEDED'));
  panel.append(header);
  if(!gc.status){
    panel.append(gcEl('p','small subtle','Checking Google Classroom connection…'));
    return;
  }
  if(!gc.status.configured){
    panel.append(gcEl('p','small subtle','Google Classroom syncing needs one-time Google OAuth setup by the Biosphere site owner. Once enabled, connect your school Google account here without sharing your password with Biosphere.'));
  }else if(!gc.status.connected){
    panel.append(gcEl('p','small subtle','Connect your school Google account to import class names, assignments and due dates. Your connection only permits reading Classroom coursework.'));
    const link=gcEl('a','btn primary','Connect Google Classroom');
    link.href='/api/classroom/connect';
    panel.append(link);
  }else{
    panel.append(gcEl('p','small subtle','Connected with read-only access. Assignments refresh on opening this page, at most every 30 minutes, or on demand.'));
    const buttons=gcEl('div','schedule-buttons');
    const sync=gcControl(gc.busy?'Syncing…':'↻ Sync now','sync');
    sync.disabled=gc.busy;
    buttons.append(sync,gcControl('Disconnect','disconnect'));panel.append(buttons);
    const synced=gc.status.synced_at?new Date(gc.status.synced_at).toLocaleString():'Not synced yet';
    panel.append(gcEl('p','small subtle','Last sync: '+synced+' · '+gc.items.length+' assignments'));
    const today=scheduleToday();
    const upcoming=gc.items.filter(x=>!x.due_date || x.due_date>=today);
    if(!upcoming.length){
      panel.append(gcEl('p','small subtle','No upcoming assignments from Google Classroom. Select Sync now to check again.'));
    }else{
      const list=gcEl('div','gc-assignment-list');
      for(const item of upcoming.slice(0,60)){
        const row=gcEl('div','gc-assignment');
        const details=gcEl('div','');
        const date=item.due_date?niceDate(item.due_date)+(item.due_time?' · '+item.due_time:''):'No due date';
        details.append(gcEl('small','',item.course_name+' · '+date),gcEl('strong','',item.title));
        row.append(details);
        try{
          const u=new URL(item.url);
          if(u.protocol==='https:' && u.hostname==='classroom.google.com'){
            const link=gcEl('a','btn secondary tiny','Open ↗');
            link.href=u.href;link.rel='noopener noreferrer';link.target='_blank';
            row.append(link);
          }
        }catch{}
        list.append(row);
      }
      panel.append(list);
      if(upcoming.length>60)panel.append(gcEl('p','small subtle','Showing the next 60 assignments.'));
    }
  }
  if(gc.error){const error=gcEl('p','small gc-error',gc.error);error.setAttribute('role','alert');panel.append(error);}
  panel.append(gcEl('p','small subtle','Your school may restrict third-party Classroom apps. Sync does not hand in or change your assignments.'));
}
async function gcLoad(){
  if(gc.loading)return;
  gc.loading=true;
  try{
    gc.status=await api('/classroom/status');
    gc.items=gc.status.connected?(await api('/classroom/assignments')).assignments||[]:[];
    gc.loaded=true;gc.error='';
  }catch(err){gc.error=err.message||String(err);}
  finally{gc.loading=false;gcPanel();}
  if(state.page==='schedule')gcAutoSync();
}
async function gcAutoSync(){
  if(gc.busy || !gc.status?.connected || state.page!=='schedule')return;
  const last=Date.parse(gc.status.synced_at||'');
  if(Number.isFinite(last)&&Date.now()-last<30*60*1000)return;
  gc.busy=true;gcPanel();
  try{await api('/classroom/sync',{method:'POST'});gc.busy=false;await gcLoad();}
  catch(err){gc.error=err.message||String(err);gc.busy=false;gcPanel();}
}
const gcBaseRender=render;
render=function(){
  gcBaseRender();
  if(state.data&&state.page==='schedule'){
    gcPanel();
    if(!gc.loaded&&!gc.loading)gcLoad();
  }
};
document.addEventListener('click',async event=>{
  const action=event.target.closest('[data-gc-action]')?.dataset.gcAction;
  if(!action||gc.busy)return;
  event.preventDefault();
  if(action==='disconnect'){
    if(!confirm('Disconnect Google Classroom and clear synced assignments in this browser workspace?'))return;
    try{await api('/classroom/disconnect',{method:'POST'});gc.loaded=false;await gcLoad();toast('Google Classroom disconnected.');}
    catch(err){gc.error=err.message||String(err);gcPanel();toast(gc.error,true);}
  }
  if(action==='sync'){
    gc.busy=true;gcPanel();
    try{
      const result=await api('/classroom/sync',{method:'POST'});
      gc.busy=false;gc.loaded=false;await gcLoad();
      toast('Synced '+result.count+' Google Classroom assignments.');
    }catch(err){gc.error=err.message||String(err);gc.busy=false;gcPanel();toast(gc.error,true);}
  }
});
document.addEventListener('click',event=>{
  if(event.target.closest('[data-nav="schedule"]')){
    setTimeout(()=>{gcPanel();if(!gc.loaded)gcLoad();else gcAutoSync();},0);
  }
});
setInterval(()=>{if(state.page==='schedule')gcAutoSync();},5*60*1000);
const gcNotice=new URLSearchParams(window.location.search).get('classroom');
if(gcNotice){
  history.replaceState(null,'',location.pathname);
  let retries=0;
  const poll=setInterval(()=>{
    if(state.data){
      clearInterval(poll);go('schedule');gc.loaded=false;gcLoad();
      toast(gcNotice==='connected'?'Classroom connected!':'Google Classroom authorization was canceled.',gcNotice!=='connected');
    }else if(++retries>40)clearInterval(poll);
  },200);
}
