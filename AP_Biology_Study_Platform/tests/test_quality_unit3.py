"""Regression tests for quality-first AP Biology practice generation."""
import json
import pytest
import main
import study_bank3
from fastapi.testclient import TestClient

@pytest.fixture
def c(tmp_path,monkeypatch):
    root=tmp_path/'site';(root/'uploads').mkdir(parents=True)
    monkeypatch.setattr(main,'DATA',root)
    monkeypatch.setattr(main,'DB',root/'study.sqlite3')
    monkeypatch.setattr(main,'UPLOADS',root/'uploads')
    main.init()
    with TestClient(main.app) as client:yield client

def unit(c,name):
    r=c.post('/api/units',json={'name':name});assert r.status_code==200,r.text
    return r.json()['id']

def upload(c,u,txt,name='objectives.txt'):
    r=c.post('/api/materials/upload',data={'unit_id':u},
             files={'files':(name,txt.encode(),'text/plain')})
    assert r.status_code==200,r.text

def test_standalone_objectives_never_make_random_cloze_cards(c):
    u=unit(c,'Unit 4')
    upload(c,u,'Explain how receptors detect chemical signals.\nDescribe the steps involved in a response.\nInterpret a diagram of signaling.','learning-objectives.txt')
    r=c.post('/api/cards/generate',json={'unit_id':u,'count':10})
    assert r.status_code==400,r.text
    assert 'objectives' in r.json()['detail'].lower() or 'learning objectives' in r.json()['detail'].lower()
    quiz=c.post('/api/quizzes',json={'unit_id':u,'count':10,'types':['mcq','fill']})
    assert quiz.status_code==400,quiz.text

def test_original_unit3_card_quality(c):
    u=unit(c,'Unit 3 - Cellular Energetics')
    upload(c,u,'3.1 Explain how enzymes affect reaction rates.\n3.4 Explain how plants capture energy.\n3.5 Describe respiration.','unit3-objectives.txt')
    r=c.post('/api/cards/generate',json={'unit_id':u,'count':25})
    assert r.status_code==200,r.text
    assert r.json()['created']>=20
    cards=c.get('/api/bootstrap').json()['cards']
    assert all('Complete this source sentence' not in x['front'] for x in cards)
    assert all('___' not in x['front'] for x in cards)
    assert len({x['front'] for x in cards})==len(cards)
    assert any('Photosynthesis' in x['topic'] for x in cards)
    assert any('Respiration' in x['topic'] for x in cards)

def test_unit3_quiz_is_real_multiple_choice_not_stitched_source_text(c):
    u=unit(c,'Cellular Energetics')
    upload(c,u,'3.1 Explain enzyme specificity.\n3.4 Describe photosynthesis.\n3.5 Describe respiration.','objectives.txt')
    r=c.post('/api/quizzes',json={'unit_id':u,'count':15,'types':['mcq','tf','fill']})
    assert r.status_code==200,r.text
    q=r.json()
    assert len(q['questions'])==15
    assert all(x['type']=='mcq' and len(x['options'])==4 for x in q['questions'])
    assert all('source sentence' not in x['prompt'].lower() for x in q['questions'])
    assert all('supplemental' in x['source_name'] for x in q['questions'])
    with main.db() as conn:
        hidden=json.loads(conn.execute('SELECT question_json FROM quizzes WHERE id=?',(q['id'],)).fetchone()[0])
    assert len({x['prompt'] for x in hidden})==15
    assert len({x['topic'] for x in hidden})>=5
    assert all(0<=x['answer']<4 and x['explanation'] for x in hidden)
    assert all('answer' not in x for x in q['questions'])

def test_unit3_always_uses_mcq_regardless_of_old_client_types(c):
    u=unit(c,'Unit 3')
    r=c.post('/api/quizzes',json={'unit_id':u,'count':3,'types':['fill','tf']})
    assert r.status_code==200,r.text
    assert len(r.json()['questions'])==3
    assert all(q['type']=='mcq' for q in r.json()['questions'])

def test_other_units_refuse_unreviewed_mcq_distractors(c):
    u=unit(c,'Unit 2')
    upload(c,u,'Osmosis: The passive movement of water across a selectively permeable membrane.\nDiffusion: The net movement of particles down a concentration gradient.','unit2-notes.txt')
    r=c.post('/api/cards/generate',json={'unit_id':u,'count':3})
    assert r.status_code==200 and r.json()['created']==2,r.text
    q=c.post('/api/quizzes',json={'unit_id':u,'count':2,'types':['mcq','fill','tf']})
    assert q.status_code==400,q.text
    assert 'question bank' in q.json()['detail'].lower() or 'multiple-choice' in q.json()['detail'].lower()
