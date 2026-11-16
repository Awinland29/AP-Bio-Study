"""Assessment structure: MCQ-only quizzes and 18–20 MCQ + two 4-part FRQ tests."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
import main

@pytest.fixture
def client(tmp_path,monkeypatch):
    root=tmp_path/'study'
    (root/'uploads').mkdir(parents=True)
    monkeypatch.setattr(main,'DATA',root)
    monkeypatch.setattr(main,'DB',root/'study.sqlite3')
    monkeypatch.setattr(main,'UPLOADS',root/'uploads')
    main.init()
    with TestClient(main.app) as c:
        yield c

def make_unit(client,name):
    r=client.post('/api/units',json={'name':name})
    assert r.status_code==200,r.text
    return r.json()['id']

def test_every_new_quiz_is_mcq_only(client):
    unit=make_unit(client,'Unit 3 – Cellular Energetics')
    for types in (['mcq'],['tf','fill','short','matching'],[]):
        r=client.post('/api/quizzes',json={'mode':'quiz','unit_id':unit,'count':10,'types':types})
        assert r.status_code==200,r.text
        assert len(r.json()['questions'])==10
        assert all(q['type']=='mcq' and len(q['options'])==4 for q in r.json()['questions'])

@pytest.mark.parametrize('count',[18,19,20])
def test_practice_test_shape_and_hidden_rubric(client,count):
    unit=make_unit(client,'Unit 3')
    r=client.post('/api/quizzes',json={'mode':'test','unit_id':unit,'count':count,'types':['tf','short']})
    assert r.status_code==200,r.text
    questions=r.json()['questions']
    assert len(questions)==count+2
    assert all(q['type']=='mcq' for q in questions[:count])
    frqs=questions[count:]
    assert len(frqs)==2
    assert all(q['type']=='frq' and len(q['parts'])==4 for q in frqs)
    assert all([p['id'] for p in q['parts']]==['a','b','c','d'] for q in frqs)
    assert all(q['context'] for q in frqs)
    assert all('answer' not in q and 'rubric' not in q for q in frqs)
    assert r.json()['mode']=='test'

def test_part_by_part_self_scoring_and_persistence(client):
    unit=make_unit(client,'Cellular Energetics')
    r=client.post('/api/quizzes',json={'mode':'test','unit_id':unit,'count':18})
    assert r.status_code==200,r.text
    quiz=r.json()
    frq=quiz['questions'][-1]
    p=frq['parts']
    answers={frq['id']:{p[0]['id']:'A relevant written explanation',p[1]['id']:'Second explanation'}}
    result=client.post('/api/quizzes/'+quiz['id']+'/submit',json={'responses':answers})
    assert result.status_code==200,result.text
    report=result.json()['report']
    assert report['graded']==18
    assert report['frq_parts_total']==8
    assert report['frq_points_possible']==16
    assert report['frq_points_earned']==0
    assert report['manual_needed']==2
    d=next(x for x in report['details'] if x['id']==frq['id'])
    assert len(d['rubric'])==4 and len(d['parts'])==4
    r1=client.post('/api/quizzes/'+quiz['id']+'/selfgrade',json={
        'scores':{frq['id']:{'a':2}}})
    assert r1.status_code==200,r1.text
    r2=client.post('/api/quizzes/'+quiz['id']+'/selfgrade',json={
        'scores':{frq['id']:{'b':1}}})
    assert r2.status_code==200,r2.text
    current=client.get('/api/quizzes/'+quiz['id']).json()['report']
    assert current['frq_points_earned']==3
    assert current['frq_parts_scored']==2
    score=next(x for x in current['details'] if x['id']==frq['id'])['part_scores']
    assert score=={'a':2,'b':1}
    # Invalid scores must not overwrite valid saved points.
    bad=client.post('/api/quizzes/'+quiz['id']+'/selfgrade',json={
        'scores':{frq['id']:{'a':99,'b':True}}})
    assert bad.json()['report']['frq_points_earned']==3
    assert bad.json()['report']['frq_parts_scored']==2

def test_non_unit3_refuses_unverified_questions(client):
    unit=make_unit(client,'Unit 2: Cell Structure')
    for mode in ('quiz','test'):
        r=client.post('/api/quizzes',json={'mode':mode,'unit_id':unit,'count':20})
        assert r.status_code==400
        assert 'question bank' in str(r.json()).lower() or 'frq' in str(r.json()).lower()

def test_frontend_exposes_real_frq_fields_and_rubrics():
    from pathlib import Path
    ui=(Path(__file__).parent.parent/'static'/'app.js').read_text()
    for needed in ('[18,19,20]',"const types=['mcq']",'data-answer="frq"',
                   'data-part=',"action==='frq-grade'",'function frqReviewDetail'):
        assert needed in ui,needed
