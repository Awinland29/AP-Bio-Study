/* Biosphere course resources, formal lab reports, and self-scored FRQs.
   Extends the existing app without replacing any of its study workflows. */
'use strict';
const extrasState={loaded:false,resources:{kinds:{},labs:[],frqs:[]},bank:[],labTab:'reports',labEditor:null,frqAttempt:null,showRubric:false,checks:new Set()};
const extrasKinds={notes:'Class notes',syllabus:'Class syllabus',reference:'Reference material',lab:'Lab handout / rubric',frq:'FRQ / scoring guide'};
const labParts=[
 ['question','Research question','What are you trying to determine?'],
 ['hypothesis','Hypothesis / prediction','A testable prediction supported by biological reasoning'],
 ['independent','Independent variable','What did you change? Include treatment levels/units.'],
 ['dependent','Dependent variable','What did you measure? How was it measured?'],
 ['controls','Controlled variables / comparison group','What stayed constant? What is your control?'],
 ['procedure','Methods and experimental design','Write a concise, repeatable method and sample sizes.'],
 ['data','Raw results / tables','Enter actual observations and measured values. Do not invent data.'],
 ['analysis','Data processing / analysis','Summarize patterns, calculations, uncertainty, graphs and trends.'],
 ['conclusion','Conclusion: claim, evidence, reasoning','Answer your research question and connect evidence to biology.'],
 ['limitations','Limitations and improvements','Sources of uncertainty and specific ways to improve reliability.'],
 ['sources','Sources / references','List class handouts, readings or other sources used.']
];

const baseRefresh=refresh;
refresh=async function(){await baseRefresh();await loadExtras();};
async function loadExtras(){
  try{extrasState.resources=await api('/extras/bootstrap');extrasState.loaded=true;
    const tags=extrasState.resources.kinds;
    if(state.data?.materials)for(const m of state.data.materials)m.kind=tags[m.id]||'notes';
  }catch(err){extrasState.loaded=false;console.warn('Extra study features unavailable:',err.message);}
}
const baseLibrary=library;
library=function(){return `${pageHeader('Course files','Your course documents','Keep the syllabus, reference packets and class notes in organized places.',btn('open-resources','View course resources →','primary'))}${baseLibrary().replace(/^<div class="heading-row">[\s\S]*?<\/div><\/div>/,'')}`;};
const basePractice=practicePage;
practicePage=function(){if(state.quiz)return basePractice();return `<section class="resource-promo"><div><span class="eyebrow">WRITTEN PRACTICE</span><h3>AP Biology Free-Response Questions</h3><p>Practice original data-based questions, save written responses, then use point-by-point rubrics to self-assess.</p></div>${btn('open-frqs','Practice FRQs →','primary')}</section>`+basePractice();};
const baseLabPage=labPage;
labPage=function(){
  if(extrasState.labEditor)return labReportEditor();
  const tabs=`<div class="tabs mb10"><button class="tab ${extrasState.labTab==='reports'?'active':''}" data-extras-action="lab-tab" data-tab="reports">Formal lab reports</button><button class="tab ${extrasState.labTab==='et50'?'active':''}" data-extras-action="lab-tab" data-tab="et50">ET₅₀ calculator</button></div>`;
  if(extrasState.labTab==='et50')return tabs+baseLabPage();
  const reports=extrasState.resources.labs||[];
  return pageHeader('Plan, analyze, explain','Formal Lab Reports','A focused workspace for formal write-ups using your own measurements and evidence.',btn('lab-new','+ New lab report','primary'))+tabs+
    `<div class="grid two-col"><section class="card"><h3>Lab writing checklist</h3><p class="subtle">Use your teacher’s rubric first. These prompts help organize your report; they do not generate fake results or assess scientific accuracy.</p>
      <ol class="lab-checklist"><li>State your research question and evidence-based hypothesis.</li><li>Identify independent, dependent and controlled variables.</li><li>Record actual observations and present units and graphs.</li><li>Analyze patterns, uncertainty and limitations.</li><li>Finish with a claim supported by evidence and biological reasoning.</li></ol>
      ${btn('open-resources','Find lab handouts & rubrics','secondary')}</section>
    <section class="card"><div class="card-header"><h3>Saved lab reports</h3><span class="chip">${reports.length} DRAFT${word(reports.length)}</span></div>
    ${reports.length?reports.map(x=>`<div class="list-row"><div class="item-main"><strong>${e(x.title)}</strong><small>${e(unitName(x.unit_id))} · Saved ${fmtShort(x.updated_at)}</small></div><button class="btn secondary tiny" data-extras-action="lab-open" data-id="${e(x.id)}">Open</button></div>`).join(''):empty('No lab drafts yet','Create a lab report to write and save your research sections.')}</section></div>
    <p class="small subtle mt16">Lab drafts are saved on the server and included in complete ZIP backups. This free host still requires regular backups.</p>`;
};

const baseRender=render;
render=function(){
  if(!state.data)return;
  if(state.page==='resources'||state.page==='frqs'){
    $('#breadcrumb').textContent=state.page==='resources'?'COURSE RESOURCES':'FRQ PRACTICE';
    $$('.nav-item[data-nav]').forEach(x=>x.classList.toggle('active',x.dataset.nav===state.page));
    document.title=(state.page==='resources'?'Course Resources':'FRQ Practice')+' · Biosphere';
    $('#main').innerHTML=state.page==='resources'?resourcesPage():frqsPage();
    $('#sidebar').classList.remove('open');
    return;
  }
  baseRender();
};

function resourcesPage(){
  if(!extrasState.loaded)return pageHeader('Course files','Course Resources','Could not load resource information. Refresh the website and try again.');
  const materials=state.data.materials;
  const syllabus=materials.filter(x=>x.kind==='syllabus');
  const refs=materials.filter(x=>['reference','lab','frq'].includes(x.kind));
  const resourceRow=m=>`<div class="list-row resource-row"><span class="unit-mark">${m.kind==='syllabus'?'§':m.kind==='frq'?'✎':m.kind==='lab'?'⚗':'▤'}</span>
    <div class="item-main"><strong>${e(m.filename)}</strong><small>${e(extrasKinds[m.kind])} · ${e(unitName(m.unit_id))}${m.text_chars?' · searchable text':' · original file saved (not text-searchable)'}</small></div>
    <div class="actions">${btn('view-file','View','secondary tiny',`data-id="${m.id}"`)}<a class="btn secondary tiny" href="/api/materials/${m.id}/file">Download</a><button class="btn secondary tiny" data-extras-action="resource-kind" data-id="${m.id}" title="Change category">⋯</button></div></div>`;
  return pageHeader('Keep course material organized','Course Resources','Upload the syllabus, reference downloads, lab handouts and FRQ packets here.')+
  `${state.data.data_durability==='temporary'?'<div class="storage-notice"><strong>Back up your uploads.</strong><span>Render Free storage is temporary. Original files and saved work may disappear after redeployment.</span>'+btn('jump-settings','Download backup','secondary tiny')+'</div>':''}
  <div class="grid two-col"><section class="card resource-feature"><div class="card-header"><h3>Class syllabus</h3><span class="chip">${syllabus.length} FILE${word(syllabus.length)}</span></div>
    <p class="small subtle">Keep the course overview and policies here so they’re easy to find.</p>
    ${syllabus.length?syllabus.map(resourceRow).join(''):empty('No syllabus uploaded','Choose “Class syllabus” below and upload the file from your computer.')}</section>
  <section class="card"><h3>Add course files</h3><form data-extras-form="resource-upload" class="stack">
    <div class="field"><label for="ex-kind">File category</label><select id="ex-kind" class="select" name="kind"><option value="syllabus">Class syllabus</option><option value="reference" selected>Reference material</option><option value="lab">Lab handout / rubric</option><option value="frq">FRQ / scoring guide</option></select></div>
    <div class="field"><label>Unit (optional)</label><select class="select" name="unit_id">${unitOptions('','Course-wide / no unit')}</select></div>
    <div class="field"><label>Topic / label (optional)</label><input class="input" name="topic" placeholder="e.g., Unit 3 equations" maxlength="150"></div>
    <div class="field"><label>Choose download(s) from your computer</label><input class="input" type="file" name="files" multiple required accept=".pdf,.pptx,.docx,.txt,.md,.csv,.json,.png,.jpg,.jpeg,.webp"></div>
    <button class="btn primary fit" type="submit">Upload files</button><p class="small subtle">Maximum 20 MB each. Image-only PDFs and diagrams are saved but may not be text-searchable. Nothing syncs automatically from your Downloads folder.</p>
    </form></section></div>
  <div class="section-heading"><h2>Reference downloads <span class="subtle">(${refs.length})</span></h2></div><section class="card">${refs.length?refs.map(resourceRow).join(''):empty('No reference files yet','Upload formula sheets, AP Biology resources, diagrams, lab rubrics or FRQ documents above.')}</section>
  <p class="small subtle mt16">Reference materials and class notes can be used as sources for the existing study tools. Syllabi, lab handouts and FRQ packets are excluded from automatic question generation unless you select them explicitly.</p>`;
}

function labReportEditor(){const x=extrasState.labEditor,sections=x.sections||{};
  return `${pageHeader('Formal Lab Reports',e(x.id?'Edit your report':'New lab report'),'Write from your own observations. Follow any required teacher format.',btn('lab-close','← Back to labs','secondary'))}
  <form id="lab-report-form" data-extras-form="lab-editor" class="stack"><section class="card"><div class="form-grid"><div class="field"><label>Report title</label><input class="input" name="title" value="${e(x.title||'')}" placeholder="e.g., Effect of pH on enzyme activity" required maxlength="180"></div><div class="field"><label>Related unit</label><select class="select" name="unit_id">${unitOptions(x.unit_id||'','General / course-wide')}</select></div></div></section>
  <div class="grid two-col">${labParts.map(([key,name,hint])=>`<section class="card lab-field"><div class="field"><label for="lab-${key}">${name}</label><small class="subtle">${e(hint)}</small><textarea id="lab-${key}" class="textarea" rows="5" name="${key}" maxlength="20000" placeholder="Write your own work here…">${e(sections[key]||'')}</textarea></div></section>`).join('')}</div>
  <div class="lab-editor-actions"><button class="btn primary" type="submit">Save report</button>${x.id?'<button class="btn secondary" type="button" data-extras-action="lab-export">Export as Markdown</button><button class="btn danger" type="button" data-extras-action="lab-delete">Delete report</button>':''}</div>
  <p class="small subtle">Save before leaving this page. Claims and calculations are yours to verify; the app does not invent experimental results or grade your report.</p></form>`;
}

function frqsPage(){
  if(extrasState.frqAttempt)return frqEditor();
  const attempts=extrasState.resources.frqs||[],questions=extrasState.bank||[];
  return `${pageHeader('Writing and scientific reasoning','Practice FRQs','Original AP Biology-style prompts, written responses and honest self-assessment.')}
  <div class="resource-promo"><div><strong>How scoring works</strong><p>Write your answers first, reveal point-by-point guidance, then check the criteria you actually met. Scores are self-reported and not official AP scores.</p></div></div>
  <div class="grid two-col">${questions.map(q=>`<section class="card frq-card"><span class="chip dim">${e(q.unit.toUpperCase())}</span><h3>${e(q.title)}</h3><p class="small subtle">Four written parts · ${q.parts.reduce((sum,p)=>sum+p.rubric.length,0)} possible rubric points</p>
  <button class="btn primary" data-extras-action="frq-start" data-prompt="${e(q.id)}">Start new FRQ →</button></section>`).join('')}</div>
  <div class="section-heading"><h2>Your FRQ attempts</h2></div><section class="card">${attempts.length?attempts.map(a=>{const q=questions.find(x=>x.id===a.prompt_id);return `<div class="list-row"><div class="item-main"><strong>${e(q?.title||a.prompt_id)}</strong><small>${fmtShort(a.updated_at)} · ${a.status==='submitted'?'Self-assessed':'Draft saved'}</small></div>${a.status==='submitted'?`<span class="chip">${a.points}/${a.max_points} self-scored</span>`:'<span class="chip gold">DRAFT</span>'}<button class="btn secondary tiny" data-extras-action="frq-open" data-id="${e(a.id)}">${a.status==='submitted'?'Review':'Continue'}</button></div>`;}).join(''):empty('No FRQs yet','Choose a question above to begin writing.')}</section>
  <p class="small subtle mt16">These questions are original practice, not copied official College Board FRQs. Your teacher’s FRQ PDFs can be saved under Course Resources.</p>`;
}

function frqEditor(){const a=extrasState.frqAttempt, q=extrasState.bank.find(x=>x.id===a.prompt_id);
  if(!q)return empty('Question unavailable','Return to the FRQ bank.');
  const submitted=a.status==='submitted'; const guide=submitted||extrasState.showRubric;
  const selected= new Set(submitted?a.checks:[...extrasState.checks]);
  return `${pageHeader('Free-response practice',e(q.title),'Work through all four parts, then self-assess against the scoring guidance.',btn('frq-back','← All FRQs','secondary'))}
  <div class="resource-promo"><div><strong>Stimulus / data</strong><p>${e(q.context)}</p></div></div>
  <form id="frq-editor" class="stack">${q.parts.map(p=>`<section class="card frq-part"><div class="row between"><h3>${p.id.toUpperCase()}. ${e(p.verb)}</h3><span class="chip">${p.rubric.length} pts</span></div><p>${e(p.prompt)}</p><textarea class="textarea" data-frq-part="${p.id}" rows="5" placeholder="Write a complete biological explanation using evidence…" ${submitted?'readonly':''}>${e(a.answers?.[p.id]||'')}</textarea>
    ${guide?`<div class="rubric"><strong>${submitted?'Your scoring guide':'Check only points your answer genuinely earns'}:</strong>${p.rubric.map((r,i)=>{const id=p.id+':'+i;return `<label class="checkline"><input type="checkbox" data-frq-check="${id}" ${selected.has(id)?'checked':''} ${submitted?'disabled':''}> ${e(r)}</label>`;}).join('')}</div>`:''}</section>`).join('')}</form>
  ${submitted?`<div class="card"><h3>Self-assessment: ${a.checks.length} / ${q.parts.reduce((t,p)=>t+p.rubric.length,0)} points</h3><p>Points were awarded by you using the rubric above. This is not automated grading or a predicted AP exam score.</p>${btn('frq-back','← Back to question bank','secondary')}</div>`:
  `<div class="lab-editor-actions">${btn('frq-save','Save draft','secondary')}${guide?btn('frq-finish','Finish self-assessment','primary'):btn('frq-reveal','Save & show scoring guide','primary')}</div><p class="small subtle">Drafts are saved only when you select Save. Keep complete ZIP backups on free hosting.</p>`}`;
}

function collectLab(){const form=$('#lab-report-form');return {title:form.elements.title.value,unit_id:form.elements.unit_id.value||null,sections:Object.fromEntries(labParts.map(([key])=>[key,form.elements[key].value]))};}
async function extrasUpdate(){await refresh();render();}
async function saveFrq(status){const a=extrasState.frqAttempt;
  const answers=a.status==='submitted'?a.answers:Object.fromEntries($$('[data-frq-part]').map(x=>[x.dataset.frqPart,x.value]));
  const checks=status==='submitted'?[...extrasState.checks]:[];
  const res=await api('/extras/frq-attempts/'+a.id,{method:'PATCH',body:JSON.stringify({answers,status,checks})});
  a.answers=answers;a.status=res.status;a.checks=checks;
  await loadExtras();return res;
}

// Capture only extras-specific actions; other controls keep the original event handlers.
document.addEventListener('click',async ev=>{
  const t=ev.target.closest('[data-extras-action],[data-action]');
  if(!t)return;
  const action=t.dataset.extrasAction||t.dataset.action;
  try{
    if(action==='open-resources'){await go('resources');return;}
    if(action==='open-frqs'){await go('frqs');return;}
    if(action==='lab-tab'){extrasState.labTab=t.dataset.tab;extrasState.labEditor=null;render();return;}
    if(action==='lab-new'){extrasState.labEditor={title:'',sections:{},unit_id:''};extrasState.labTab='reports';render();return;}
    if(action==='lab-close'){extrasState.labEditor=null;render();return;}
    if(action==='lab-open'){extrasState.labEditor=await api('/extras/labs/'+t.dataset.id);render();return;}
    if(action==='lab-export'){const x=extrasState.labEditor;const fields=collectLab();const text='# '+fields.title+'\n\n'+labParts.map(([key,title])=>'## '+title+'\n\n'+(fields.sections[key]||'')+'\n').join('\n');downloadText((fields.title||'biology-lab').toLowerCase().replace(/[^a-z0-9]+/g,'-').slice(0,55)+'.md',text,'text/markdown');return;}
    if(action==='lab-delete'){if(!confirm('Delete this saved lab report?'))return;await api('/extras/labs/'+extrasState.labEditor.id,{method:'DELETE'});extrasState.labEditor=null;await extrasUpdate();toast('Lab report deleted.');return;}
    if(action==='frq-start'){const r=await api('/extras/frq-attempts',{method:'POST',body:JSON.stringify({prompt_id:t.dataset.prompt})});extrasState.frqAttempt=await api('/extras/frq-attempts/'+r.id);extrasState.showRubric=false;extrasState.checks=new Set();await extrasUpdate();return;}
    if(action==='frq-open'){extrasState.frqAttempt=await api('/extras/frq-attempts/'+t.dataset.id);extrasState.showRubric=extrasState.frqAttempt.status==='submitted';extrasState.checks=new Set(extrasState.frqAttempt.checks);render();return;}
    if(action==='frq-back'){extrasState.frqAttempt=null;extrasState.showRubric=false;render();return;}
    if(action==='frq-save'){await saveFrq('draft');toast('FRQ draft saved.');return;}
    if(action==='frq-reveal'){await saveFrq('draft');extrasState.showRubric=true;render();toast('Draft saved. Compare your answer with the scoring guide.');return;}
    if(action==='frq-finish'){if(!confirm('Finish this FRQ? Your checked rubric points are self-awarded.'))return;const r=await saveFrq('submitted');render();toast(`Self-assessment saved: ${r.points}/${r.max_points} rubric points.`);return;}
    if(action==='resource-kind'){const m=state.data.materials.find(x=>x.id===t.dataset.id);const sel=Object.entries(extrasKinds).map(([k,v])=>`<option value="${k}" ${m.kind===k?'selected':''}>${e(v)}</option>`).join('');showModal('Organize this file',`<p class="small subtle">${e(m.filename)}</p><form data-extras-form="resource-kind" data-id="${m.id}" class="stack"><div class="field"><label>Category</label><select class="select" name="kind">${sel}</select></div><button type="submit" class="btn primary">Save category</button></form>`);return;}
  }catch(err){toast(err.message||String(err),true);}
},true);

document.addEventListener('change',ev=>{if(ev.target.dataset.frqCheck){const key=ev.target.dataset.frqCheck;if(ev.target.checked)extrasState.checks.add(key);else extrasState.checks.delete(key);}});

document.addEventListener('submit',async ev=>{
  const form=ev.target.closest('[data-extras-form]');if(!form)return;
  ev.preventDefault();const type=form.dataset.extrasForm;const button=$('button[type=submit]',form);if(button)button.disabled=true;
  try{
    if(type==='resource-upload'){const f=new FormData(form);if(!f.getAll('files').some(x=>x?.name))throw Error('Select files to upload.');const res=await api('/extras/upload',{method:'POST',body:f});const saved=res.results.filter(x=>x.id).length;const errors=res.results.filter(x=>x.error).map(x=>x.filename+': '+x.error);await extrasUpdate();toast(saved+' file'+word(saved)+' saved.'+(errors.length?' '+errors.join(' '):''),!!errors.length);}
    else if(type==='resource-kind'){await api('/extras/resources/'+form.dataset.id,{method:'PATCH',body:JSON.stringify({kind:new FormData(form).get('kind')})});closeModal();await extrasUpdate();toast('File category updated.');}
    else if(type==='lab-editor'){const payload=collectLab(),x=extrasState.labEditor;const r=await api(x.id?'/extras/labs/'+x.id:'/extras/labs',{method:x.id?'PATCH':'POST',body:JSON.stringify(payload)});extrasState.labEditor=await api('/extras/labs/'+r.id);await extrasUpdate();toast('Lab report saved.');}
  }catch(err){toast(err.message||String(err),true);}finally{if(button)button.disabled=false;}
},true);

// The original app is async-initialized; populate extras independently on load.
Promise.all([api('/extras/bootstrap'),api('/extras/frq-bank')]).then(([res,bank])=>{
  extrasState.resources=res;extrasState.bank=bank.questions;extrasState.loaded=true;
  if(state.data?.materials)for(const m of state.data.materials)m.kind=res.kinds[m.id]||'notes';
  if(state.data)render();
}).catch(err=>console.warn('Could not initialize course resources:',err.message));
