"""Browser UI audit with the real app script against the real FastAPI TestClient.
Network navigation is restricted here, so HTML/assets are injected locally and
fetch() is bridged to an isolated server process in memory. No live user data.
"""
from __future__ import annotations
import json,os,sys,tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1]
SAMPLE='''Photosynthesis: A process that converts captured light energy to chemical energy in sugars.
Chlorophyll: A pigment involved in absorbing light during photosynthesis.
Stomata: Leaf pores that control exchange of gases with the environment.
Thylakoid: Membrane compartment containing components of the light reactions.
Calvin cycle: Pathway that uses ATP and NADPH to build organic molecules from carbon dioxide.
ATP synthase: Enzyme complex that uses a proton gradient to make ATP.
Proton gradient: Difference in hydrogen ion concentration across a membrane.
Electron transport chain: Set of carriers that pass electrons and help build a proton gradient.
Light-dependent reactions: Processes that convert light energy to ATP and NADPH.
Carbon fixation: Incorporation of inorganic carbon into organic compounds.'''
SHIM=r'''(function(){
const storage=new Map(); Object.defineProperty(window,'localStorage',{value:{getItem:k=>storage.has(k)?storage.get(k):null,setItem:(k,v)=>storage.set(k,String(v)),removeItem:k=>storage.delete(k),clear:()=>storage.clear()}});
window.fetch=async function(path,opts={}){
 let kind='json',body=null;
 if(opts.body instanceof FormData){kind='form';body=[];for(let [key,val] of opts.body.entries()){
  if(val instanceof File){body.push({key,file:true,name:val.name,mime:val.type,bytes:Array.from(new Uint8Array(await val.arrayBuffer()))});}
  else body.push({key,value:val});}}
 else if(opts.body!==undefined){body=String(opts.body);}
 const r=await window.__bridge({path:String(path),method:opts.method||'GET',kind,body});
 return new Response(r.body,{status:r.status,headers:{'Content-Type':r.contentType||'application/json'}});
};
})();'''

def main():
 with tempfile.TemporaryDirectory() as tmp:
  os.environ['APBIO_DATA_DIR']=str(Path(tmp)/'data')
  os.environ.pop('APBIO_PUBLIC',None)
  os.environ.pop('OPENAI_API_KEY',None)
  sys.path.insert(0,str(ROOT))
  import main as server
  client=TestClient(server.app)
  html=(ROOT/'static/index.html').read_text()
  css=(ROOT/'static/styles.css').read_text()
  appjs=(ROOT/'static/app.js').read_text()
  html=html.replace('<link rel="stylesheet" href="/static/styles.css" />',f'<style>{css}</style>')
  html=html.replace('<script src="/static/app.js" defer></script>',f'<script>{SHIM}</script><script>{appjs}</script>')
  events=[]
  def bridge(source,payload):
   path=payload['path'];method=payload['method']
   if payload['kind']=='form':
    data={};files=[]
    for v in payload['body']:
     if v.get('file'):files.append((v['key'],(v['name'],bytes(v['bytes']),v.get('mime') or 'application/octet-stream')))
     else:data[v['key']]=v['value']
    if files:res=client.request(method,path,data=data,files=files)
    else:res=client.request(method,path,data=data)
   else:res=client.request(method,path,content=payload.get('body'),headers={'content-type':'application/json'})
   return {'status':res.status_code,'body':res.content.decode('utf-8',errors='replace'),'contentType':res.headers.get('content-type','application/json')}
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
   page=browser.new_page(viewport={'width':1440,'height':900},device_scale_factor=1)
   page.expose_binding('__bridge',bridge)
   page.on('pageerror',lambda err:events.append(str(err)))
   page.on('dialog',lambda dialog:dialog.accept())
   page.set_content(html,wait_until='load')
   page.get_by_role('heading',name='Good to see you.').wait_for(timeout=10000)
   print('PASS Overview and JS bootstrap')
   page.locator('[data-nav="library"]').click()
   page.locator('[data-action="new-unit"]').first.click()
   page.locator('form[data-form="save-unit"] [name="name"]').fill('Unit 3 — Cellular Energetics')
   page.locator('form[data-form="save-unit"] button[type="submit"]').click()
   page.locator('.list-row strong').filter(has_text='Unit 3 — Cellular Energetics').first.wait_for()
   page.locator('#upload-unit').select_option(label='Unit 3 — Cellular Energetics')
   page.locator('#file-upload').set_input_files({'name':'class-notes.txt','mimeType':'text/plain','buffer':SAMPLE.encode()})
   page.locator('form[data-form="upload"] button[type="submit"]').click()
   page.locator('#library-table strong').filter(has_text='class-notes.txt').first.wait_for()
   assert client.get('/api/bootstrap').json()['stats']['materials']==1
   # The full-text search queries extracted source text.
   page.locator('#fulltext-search').fill('chlorophyll')
   page.locator('[data-action="fulltext-search"]').click()
   page.locator('#fulltext-results').get_by_text('class-notes.txt').first.wait_for()
   print('PASS Library, unit, file upload, search')
   page.locator('[data-nav="cards"]').click()
   page.locator('[data-action="generate-cards"]').first.click()
   page.locator('form[data-form="generate-cards"] button[type="submit"]').click()
   page.locator('.flashcard').wait_for()
   initial=page.locator('.flashcard h2').inner_text()
   page.locator('[data-action="flip-card"]').first.click()
   page.locator('[data-action="rate-card"][data-rating="good"]').click()
   page.get_by_text('Review saved. Moving to the next card.').wait_for()
   assert page.locator('.flashcard h2').inner_text()!=initial
   print('PASS Flashcard generation, review, navigation')
   page.locator('[data-nav="practice"]').click()
   page.locator('form[data-form="create-quiz"] [name="unit_id"]').select_option(label='Unit 3 — Cellular Energetics')
   assert not page.locator('details.advanced-settings').evaluate('(el)=>el.open')
   page.locator('form[data-form="create-quiz"] button[type="submit"]').click()
   page.locator('.question-card').wait_for()
   page.locator('[data-action="flag-question"]').click()
   assert page.locator('.question-nav button.flagged').count()==1
   page.locator('[data-action="exit-quiz"]').click()
   page.locator('[data-action="review-attempt"]').first.click()
   page.locator('.question-card').wait_for(timeout=6000)
   assert page.locator('.question-nav button.flagged').count()==1
   page.locator('[data-action="submit-quiz"]').click()
   page.get_by_role('heading',name='Your results').wait_for(timeout=10000)
   print('PASS Quiz generation, flag preservation, grading, results')
   page.locator('[data-nav="guides"]').click()
   page.locator('form[data-form="guide"] button[type="submit"]').click()
   page.locator('.guide-preview').get_by_text('Chlorophyll').first.wait_for(timeout=5000)
   page.locator('[data-nav="overview"]').click()
   page.locator('[data-nav="guides"]').click()
   page.locator('[data-action="open-guide"]').first.click()
   page.locator('.guide-preview').get_by_text('Chlorophyll').first.wait_for(timeout=5000)
   print('PASS Saved study guide creation and reopening')
   page.locator('[data-nav="progress"]').click()
   page.get_by_role('heading',name='Assessment record').wait_for()
   print('PASS Progress dashboard')
   page.locator('[data-nav="planner"]').click()
   page.locator('form[data-form="task"] [name="title"]').fill('Review photosynthesis')
   page.locator('form[data-form="task"] button[type="submit"]').click()
   page.get_by_text('Review photosynthesis').first.wait_for()
   page.locator('[data-role="task-toggle"]').first.check()
   print('PASS Study planner')
   page.locator('[data-nav="tutor"]').click()
   page.get_by_text('AI CONNECTION NEEDED').first.wait_for()
   assert page.locator('form[data-form="tutor"] button[type=submit]').is_disabled()
   print('PASS Disabled AI tutor does not simulate replies')
   page.locator('[data-nav="lab"]').click()
   page.get_by_text('Not reached').wait_for()
   page.locator('[data-action="demo-lab"]').click()
   assert 'min' in page.locator('#et50-result').inner_text()
   print('PASS Leaf disk ET50 lab')
   page.locator('[data-nav="settings"]').click()
   page.locator('form[data-form="restore-backup"]').wait_for()
   page.locator('[data-action="theme"]').first.click()
   assert page.evaluate('document.documentElement.dataset.theme')=='dark'
   page.locator('[data-action="theme"]').first.click()
   assert page.evaluate('document.documentElement.dataset.theme')=='light'
   print('PASS Settings, restore UI, dark mode toggle')
   page.screenshot(path=str(ROOT.parent/'audit_desktop.png'),full_page=True)
   mobile=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1)
   mobile.expose_binding('__bridge',bridge)
   mobile.on('pageerror',lambda err:events.append(str(err)))
   mobile.set_content(html,wait_until='load')
   mobile.locator('#menu-toggle').click()
   mobile.locator('[data-nav="practice"]').click()
   mobile.get_by_role('heading',name='Practice & Tests').wait_for()
   mobile.wait_for_timeout(400)
   assert not mobile.locator('#sidebar').evaluate('(el)=>el.classList.contains("open")')
   overflow=mobile.evaluate('document.documentElement.scrollWidth > window.innerWidth + 3')
   assert not overflow,'Mobile horizontal overflow'
   print('PASS Mobile menu, no page overflow')
   mobile.screenshot(path=str(ROOT.parent/'audit_mobile.png'),full_page=True)
   if events:raise AssertionError('Browser JS errors: '+repr(events))
   print('PASS No browser JS exceptions')
   browser.close()
if __name__=='__main__':main()
