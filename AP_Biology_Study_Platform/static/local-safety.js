/* Browser-local safety copy for ephemeral free hosting. No third-party services. */
(function(){
'use strict';
var dbName='biosphere-recovery-v1',storeName='archives';
var identity=null,dbPromise=null,busy=false,pending=false,timer=null,blocked=false,initialized=false;
var banner=null,saveMessage='';

function openDB(){
 if(dbPromise)return dbPromise;
 dbPromise=new Promise(function(resolve,reject){
  if(!('indexedDB' in window)){reject(Error('Browser-local storage is unavailable.'));return;}
  var req=indexedDB.open(dbName,1);
  req.onupgradeneeded=function(){var db=req.result;if(!db.objectStoreNames.contains(storeName))db.createObjectStore(storeName,{keyPath:'key'});};
  req.onsuccess=function(){resolve(req.result);};
  req.onerror=function(){reject(req.error||Error('Could not open browser storage.'));};
 });
 return dbPromise;
}
async function recordGet(key){
 var db=await openDB();
 return new Promise(function(resolve,reject){
  var req=db.transaction(storeName,'readonly').objectStore(storeName).get(key);
  req.onsuccess=function(){resolve(req.result||null);};
  req.onerror=function(){reject(req.error||Error('Could not read saved copy.'));};
 });
}
async function recordPut(value){
 var db=await openDB();
 return new Promise(function(resolve,reject){
  var tx=db.transaction(storeName,'readwrite');
  tx.objectStore(storeName).put(value);
  tx.oncomplete=function(){resolve();};
  tx.onerror=function(){reject(tx.error||Error('Could not save recovery copy.'));};
  tx.onabort=function(){reject(tx.error||Error('Browser storage quota may be full.'));};
 });
}
function panel(){
 if(banner)return banner;
 banner=document.createElement('div');
 banner.setAttribute('role','status');
 banner.setAttribute('aria-live','polite');
 banner.style.cssText='position:fixed;z-index:5000;bottom:18px;right:18px;width:min(410px,calc(100% - 36px));box-sizing:border-box;padding:16px 18px;border-radius:15px;border:1px solid #77bda2;background:#f5fff9;color:#123429;box-shadow:0 12px 36px rgba(0,0,0,.24);font:14px/1.5 system-ui,sans-serif';
 document.body.appendChild(banner);
 return banner;
}
function message(title,description,actions){
 var p=panel();
 p.replaceChildren();
 var h=document.createElement('strong');h.textContent=title;h.style.display='block';h.style.marginBottom='5px';p.appendChild(h);
 var copy=document.createElement('div');copy.textContent=description;p.appendChild(copy);
 if(actions){
  var foot=document.createElement('div');foot.style.cssText='display:flex;gap:8px;flex-wrap:wrap;margin-top:10px';
  actions.forEach(function(a){
   var button=document.createElement('button');button.type='button';button.textContent=a.label;
   button.style.cssText='cursor:pointer;border-radius:8px;border:1px solid #3c866b;padding:7px 12px;background:'+(a.primary?'#187a59':'white')+';color:'+(a.primary?'white':'#15462e')+';font:600 13px system-ui';
   button.addEventListener('click',a.action);foot.appendChild(button);
  });p.appendChild(foot);
 }
 p.hidden=false;
}
function hide(){if(banner)banner.hidden=true;}
function errorNotice(error){
 message('Automatic local backup unavailable',String(error&&error.message||error)+'. Download a complete ZIP from Settings & Backup to keep your materials safe.',[
  {label:'Dismiss',action:hide}
 ]);
}
async function save(){
 if(!initialized||blocked)return;
 if(busy){pending=true;return;}
 busy=true;
 try{
  var response=await fetch('/api/backup/download',{method:'POST',credentials:'same-origin',cache:'no-store'});
  if(!response.ok)throw Error('Backup request failed ('+response.status+')');
  var blob=await response.blob();
  if(blob.size<100)throw Error('The backup ZIP was empty');
  // Never overwrite a recovery archive made by a different server epoch.
  var old=await recordGet(identity.workspace_id);
  if(old&&old.epoch!==identity.epoch){blocked=true;showRecovery(old);return;}
  await recordPut({key:identity.workspace_id,epoch:identity.epoch,
                   blob:blob,savedAt:Date.now(),bytes:blob.size});
  saveMessage='Automatic browser recovery copy saved';
  document.dispatchEvent(new CustomEvent('biosphere:local-backup-saved'));
 }catch(err){errorNotice(err);}
 finally{
  busy=false;
  if(pending&&!blocked){pending=false;queue(150);}
 }
}
function queue(delay){
 if(!initialized||blocked)return;
 if(timer)clearTimeout(timer);
 timer=setTimeout(function(){timer=null;save();},delay||500);
}
async function recover(old){
 var yes=window.confirm('Restore your last browser-saved copy? This replaces the current workspace data. Your original ZIP downloads are not changed.');
 if(!yes)return;
 try{
  message('Restoring your saved work','Restoring the browser recovery ZIP to Biosphere...');
  var data=new FormData();
  data.append('confirmation','RESTORE');
  data.append('file',new File([old.blob],'biosphere-recovery.zip',{type:'application/zip'}));
  var r=await fetch('/api/backup/restore',{method:'POST',body:data,credentials:'same-origin'});
  if(!r.ok){
   var detail='Restore failed ('+r.status+')';
   try{var j=await r.json();detail=j.detail||detail;}catch(_){}
   throw Error(detail);
  }
  window.location.reload();
 }catch(err){showRecovery(old,String(err.message||err));}
}
function showRecovery(old,error){
 blocked=true;
 var timestamp=new Date(old.savedAt).toLocaleString();
 message('Your saved materials can be recovered',
  (error?error+' ':'')+'The server workspace was reset. A complete copy from '+timestamp+' is saved in this browser ('+Math.round(old.bytes/1024)+' KB). Restore it or keep the new workspace.',[
    {label:'Restore saved copy',primary:true,action:function(){recover(old);}},
    {label:'Keep current workspace',action:async function(){
      if(!window.confirm('Keep this newer workspace instead? The older browser recovery copy will be replaced after the next save.'))return;
      blocked=false;hide();queue(100);
    }}
  ]);
}
async function initialize(){
 if(initialized)return;
 try{
  // Initial app bootstrap sets the HttpOnly visitor cookie before this request.
  var r=await fetch('/api/workspace-identity',{credentials:'same-origin',cache:'no-store'});
  if(!r.ok)throw Error('Could not identify browser workspace');
  identity=await r.json();
  if(!identity.workspace_id||!identity.epoch)throw Error('Incomplete workspace identity');
  var previous=await recordGet(identity.workspace_id);
  initialized=true;
  if(previous&&previous.epoch!==identity.epoch&&previous.blob){showRecovery(previous);return;}
  if(!previous){queue(350);} // Capture existing files when protection is first enabled.
  // If the app was closed immediately after a mutation, existing archives are still usable.
  if(!previous){
    message('Local recovery is enabled','This browser will keep a separate backup copy after changes. Clearing browser data or switching devices can erase that copy.',[{label:'Got it',action:hide}]);
  }
 }catch(error){initialized=true;blocked=true;errorNotice(error);}
}
function markChanged(path){
 if(path==='/google-classroom/sync')return; // Sync writes are also snapshotted by regular schedules.
 queue(path&&/upload|restore|import/.test(path)?200:650);
}
window.BiosphereSafety={initialize:initialize,markChanged:markChanged,backupNow:function(){queue(50);},get status(){return saveMessage;}};
})();
