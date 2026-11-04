"""API regression coverage for Biology Studio (all tests use isolated SQLite/temp uploads)."""
from __future__ import annotations
import io
import json
import os
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
import main

SAMPLE = """Photosynthesis: A process that converts captured light energy to chemical energy in sugars.
Chlorophyll: A pigment involved in absorbing light during photosynthesis.
Stomata: Leaf pores that control exchange of gases with the environment.
Thylakoid: Membrane compartment containing components of the light reactions.
Calvin cycle: Pathway that uses ATP and NADPH to build organic molecules from carbon dioxide.
ATP synthase: Enzyme complex that uses a proton gradient to make ATP.
Proton gradient: Difference in hydrogen ion concentration across a membrane.
Electron transport chain: Set of carriers that pass electrons and help build a proton gradient.
Light-dependent reactions: Processes that convert light energy to ATP and NADPH.
Carbon fixation: Incorporation of inorganic carbon into organic compounds.
"""

@pytest.fixture
def client(tmp_path,monkeypatch):
    datadir=tmp_path/'datastore'
    uploads=datadir/'uploads'; uploads.mkdir(parents=True)
    monkeypatch.setattr(main,'DATA',datadir)
    monkeypatch.setattr(main,'DB',datadir/'study.sqlite3')
    monkeypatch.setattr(main,'UPLOADS',uploads)
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    main.init()
    with TestClient(main.app) as c:
        yield c


def upload(client, unit='', name='notes.txt', text=SAMPLE):
    result=client.post('/api/materials/upload',data={'unit_id':unit,'topic':'Cellular energetics','lesson':'Photosynthesis'},
                       files=[('files',(name,text.encode(),'text/plain'))])
    assert result.status_code==200,result.text
    return result.json()['results'][0]['id']


def unit(client):
    r=client.post('/api/units',json={'name':'Unit 3 · Cellular Energetics','description':'Photosynthesis', 'status':'current'})
    assert r.status_code==200
    return r.json()['id']


def test_home_and_organizing_materials(client):
    assert client.get('/').status_code==200
    assert client.get('/static/app.js').status_code==200
    assert client.get('/api/health').json()['ok']
    u=unit(client);m=upload(client,u)
    bootstrap=client.get('/api/bootstrap').json()
    assert bootstrap['stats']['materials']==1
    assert bootstrap['materials'][0]['text_chars']>200
    r=client.get('/api/search',params={'q':'chlorophyll'}).json()
    assert any(x['kind']=='material' for x in r['results'])
    assert client.get(f'/api/materials/{m}/text').json()['text'].startswith('Photosynthesis:')
    assert client.get(f'/api/materials/{m}/file').content.startswith(b'Photosynthesis:')
    assert client.patch(f'/api/materials/{m}',json={'unit_id':u,'topic':'Edited topic', 'lesson':'Plant cells'}).status_code==200
    assert client.get('/api/bootstrap').json()['materials'][0]['topic']=='Edited topic'
    assert client.patch(f'/api/units/{u}',json={'status':'completed'}).status_code==200
    assert client.get('/api/bootstrap').json()['units'][0]['status']=='completed'
    assert client.delete(f'/api/materials/{m}').status_code==200
    assert client.get('/api/bootstrap').json()['stats']['materials']==0


def test_source_grounded_cards_and_spaced_review(client):
    u=unit(client);m=upload(client,u)
    res=client.post('/api/cards/generate',json={'unit_id':u,'count':10})
    assert res.status_code==200,res.text
    assert res.json()['created']>=8
    cards=client.get('/api/bootstrap').json()['cards']
    assert all(x['material_id']==m for x in cards)
    assert any(c['front']=='Chlorophyll' for c in cards)
    assert not any('Complete this source sentence: ' in c['front'] for c in cards)
    c=cards[0]
    r=client.post(f'/api/cards/{c["id"]}/review',json={'rating':'good'})
    assert r.status_code==200
    assert r.json()['interval_days']>=1
    after=client.get('/api/bootstrap').json()['cards']
    assert next(x for x in after if x['id']==c['id'])['reps']==1
    assert client.patch(f'/api/cards/{c["id"]}',json={'bookmarked':True,'front':'Edited term'}).status_code==200
    assert client.get('/api/bootstrap').json()['cards'][0]['bookmarked']==1 or any(z['bookmarked'] for z in client.get('/api/bootstrap').json()['cards'])
    assert client.delete(f'/api/cards/{c["id"]}').status_code==200


def test_quiz_answer_secrecy_scoring_and_progress(client):
    u=unit(client);upload(client,u)
    # Create bank of cards to make all supported local question types viable.
    client.post('/api/cards/generate',json={'unit_id':u,'count':10})
    r=client.post('/api/quizzes',json={'unit_id':u,'types':['mcq','multi','tf','fill','matching','short'], 'count':6,'minutes':20,'mode':'test'})
    assert r.status_code==200,r.text
    q=r.json();qid=q['id']
    assert q['mode']=='test' and q['status']=='active'
    assert all('answer' not in x and 'explanation' not in x for x in q['questions'])
    assert all('answer' not in x for x in client.get(f'/api/quizzes/{qid}').json()['questions'])
    # Inspect private keys in the test only to supply correct answers.
    dbquiz=main.item('SELECT * FROM quizzes WHERE id=?',(qid,))
    private=json.loads(dbquiz['question_json'])
    response={x['id']:x['answer'] for x in private if x['type'] not in ('short',)}
    # One manually graded answer, objective answers all correct.
    response.update({x['id']:'I need to compare with rubric.' for x in private if x['type']=='short'})
    result=client.post(f'/api/quizzes/{qid}/submit',json={'responses':response})
    assert result.status_code==200
    report=result.json()['report']
    assert report['graded']+report['manual_needed']==len(private)
    assert report['percent']==100,report
    assert report['manual_needed']==sum(x['type']=='short' for x in private)
    if report['manual_needed']:
        short=next(x for x in private if x['type']=='short')
        graded=client.post(f'/api/quizzes/{qid}/selfgrade',json={'scores':{short['id']:False}})
        assert graded.status_code==200
        assert graded.json()['report']['manual_needed']==0
    assert client.get('/api/progress').status_code==200
    assert client.get('/api/bootstrap').json()['stats']['completed']==1
    assert client.post(f'/api/quizzes/{qid}/submit',json={'responses':{}}).status_code==400
    issue=client.post(f'/api/quizzes/{qid}/issues',json={'question_id':private[0]['id'], 'details':'Check the wording of this item.'})
    assert issue.status_code==200
    assert client.get('/api/issues').json()['issues']


def test_cloze_question_is_not_malformed(client):
    # This note has no colon-definitions, so its deterministic fallback is a cloze.
    note='During photosynthesis the chloroplast converts energy from light into chemical energy that cells can use.\n'
    m=upload(client,text=note)
    created=client.post('/api/cards/generate',json={'material_ids':[m], 'count':3})
    assert created.json()['created']>=1
    card=client.get('/api/bootstrap').json()['cards'][0]
    assert card['front'].startswith('Complete this source sentence:')
    q=client.post('/api/quizzes',json={'types':['matching'],'count':5})
    assert q.status_code==200,q.text
    x=q.json()['questions'][0]
    assert x['type']=='fill' and '____' in x['statement']
    assert 'answer' not in x


def test_study_guides_planner_export_backup(client):
    u=unit(client);m=upload(client,u)
    guide=client.post('/api/guides',json={'unit_id':u,'mode':'exam'})
    assert guide.status_code==200
    assert 'Chlorophyll' in guide.json()['markdown']
    assert 'notes.txt' in guide.json()['markdown']
    t=client.post('/api/tasks',json={'title':'Review photosynthesis','unit_id':u,'due_date':'2026-12-12'}).json()['id']
    assert client.patch(f'/api/tasks/{t}',json={'done':True}).status_code==200
    assert client.get('/api/bootstrap').json()['tasks'][0]['done']==1
    exp=client.get('/api/export')
    assert exp.status_code==200 and json.loads(exp.content)['materials'][0]['id']==m
    b=client.get('/api/backup')
    assert b.status_code==200
    z=zipfile.ZipFile(io.BytesIO(b.content))
    assert 'study.sqlite3' in z.namelist()
    assert len([x for x in z.namelist() if x.startswith('uploads/')])==1
    assert client.delete(f'/api/tasks/{t}').status_code==200


def test_disabled_ai_is_honest(client):
    u=unit(client);upload(client,u)
    r=client.post('/api/ai/chat',json={'unit_id':u,'message':'Teach me about chlorophyll.'})
    assert r.status_code==503 and 'OPENAI_API_KEY' in r.text
    r2=client.post('/api/quizzes',json={'unit_id':u,'generator':'ai','types':['mcq']})
    assert r2.status_code==503
    assert not main.items('SELECT id FROM quizzes')
    r3=client.post('/api/ai/guide',json={'unit_id':u})
    assert r3.status_code==503


def test_ai_question_validation_without_external_call(client,monkeypatch):
    u=unit(client);upload(client,u)
    mock={'questions':[{'type':'mcq','prompt':'Which pigment absorbs light?','options':['Chlorophyll','Glucose','NADPH','Carbon dioxide'],
                        'answer':0,'explanation':'The source states that chlorophyll absorbs light.',
                        'source_name':'notes.txt','topic':'Photosynthesis'},
                        {'type':'multi','prompt':'Select the two descriptions from the source.',
                        'options':['Chlorophyll absorbs light','Thylakoids are membrane compartments','Sugar is a gas','ATP is sunlight'],
                        'answer':[0,1],'explanation':'Both statements are supported by the source.',
                        'source_name':'notes.txt','topic':'Photosynthesis'}]}
    monkeypatch.setattr(main,'ai_completion',lambda system,user:json.dumps(mock))
    r=client.post('/api/quizzes',json={'unit_id':u,'generator':'ai','count':5,'types':['mcq','multi'],'difficulty':'challenge','emphasis':'application'})
    assert r.status_code==200,r.text
    qs=r.json()['questions']
    assert len(qs)==2 and all('answer' not in q for q in qs)
    private=json.loads(main.item('SELECT question_json FROM quizzes WHERE id=?',(r.json()['id'],))['question_json'])
    correct={q['id']:q['answer'] for q in private}
    sub=client.post(f'/api/quizzes/{r.json()["id"]}/submit',json={'responses':correct})
    assert sub.json()['report']['percent']==100
    # Wrong source name must fail schema validation, not add imaginary citations.
    mock['questions'][0]['source_name']='nonexistent-book.pdf'
    mock['questions']=mock['questions'][:1]
    bad=client.post('/api/quizzes',json={'unit_id':u,'generator':'ai','types':['mcq']})
    assert bad.status_code==502


def test_validation_errors(client):
    assert client.post('/api/cards/generate',json={'count':10}).status_code==400
    assert client.post('/api/materials/upload',data={'unit_id':'no-such-unit'},files={'files':('notes.txt',b'abc','text/plain')}).status_code==404
    assert client.post('/api/materials/upload',files={'files':('executable.exe',b'123','application/octet-stream')}).json()['results'][0]['error']
    assert client.get('/api/materials/nonexistent/file').status_code==404


def test_saved_guides_survive_reloads_and_export(client):
    u=unit(client);upload(client,u)
    made=client.post('/api/guides',json={'unit_id':u,'mode':'detailed'})
    assert made.status_code==200
    guide=made.json()
    assert guide['id'] and 'Calvin cycle' in guide['markdown']
    newer=client.get('/api/bootstrap').json()
    assert any(x['id']==guide['id'] for x in newer['guides'])
    restored=client.get('/api/guides/'+guide['id']).json()
    assert restored['markdown']==guide['markdown']
    assert restored['sources'][0]['filename']=='notes.txt'
    exported=client.get('/api/export').json()
    assert exported['guides'][0]['id']==guide['id']
    assert client.delete('/api/guides/'+guide['id']).status_code==200
    assert client.get('/api/guides/'+guide['id']).status_code==404


def test_specific_source_flashcards(client):
    u=unit(client)
    a=upload(client,u,name='first.txt',text='Chlorophyll: Green pigment that absorbs light energy for photosynthesis.')
    b=upload(client,u,name='second.txt',text='Osmosis: Passive diffusion of water across a selectively permeable membrane.')
    generated=client.post('/api/cards/generate',json={'unit_id':u,'material_ids':[b], 'count':10})
    assert generated.status_code==200 and generated.json()['created']==1
    cs=client.get('/api/bootstrap').json()['cards']
    assert len(cs)==1 and cs[0]['material_id']==b and 'Osmosis' in cs[0]['front']
    assert all(c['material_id']!=a for c in cs)


def test_pdf_docx_and_pptx_text_extraction(client):
    import fitz
    from docx import Document
    from pptx import Presentation
    from pptx.util import Inches
    pdf=fitz.open();pg=pdf.new_page();pg.insert_text((60,90),'ATP synthase: Enzyme that produces ATP using a proton gradient.')
    doc=Document();doc.add_paragraph('Mitochondrion: Organelle involved in aerobic cellular respiration.')
    f=io.BytesIO();doc.save(f)
    ppt=Presentation();slide=ppt.slides.add_slide(ppt.slide_layouts[6]);box=slide.shapes.add_textbox(Inches(1), Inches(1), Inches(7), Inches(1));box.text='Thylakoid: Membranous compartment containing proteins used in light reactions.'
    x=io.BytesIO();ppt.save(x)
    response=client.post('/api/materials/upload',files=[('files',('biolesson.pdf',pdf.tobytes(),'application/pdf')),('files',('biolesson.docx',f.getvalue(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document')),('files',('biolesson.pptx',x.getvalue(),'application/vnd.openxmlformats-officedocument.presentationml.presentation'))])
    assert response.status_code==200, response.text
    result=response.json()['results'];assert len(result)==3
    assert all(m['text_chars']>30 and m['extraction_status']=='ready' for m in result),result
    texts=[client.get('/api/materials/'+r['id']+'/text').json()['text'] for r in result]
    assert 'ATP synthase' in texts[0]
    assert 'Mitochondrion' in texts[1]
    assert 'Thylakoid' in texts[2]
