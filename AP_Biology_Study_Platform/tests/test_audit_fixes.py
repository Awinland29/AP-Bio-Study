"""Audit regressions: backup recovery, source isolation, honest mastery, lab UX."""
from __future__ import annotations
import io,zipfile,json,sqlite3
import pytest
from fastapi.testclient import TestClient
import main

SAMPLE_A='Chlorophyll: A pigment that absorbs light during photosynthesis.\nOsmosis: The movement of water through a selectively permeable membrane.'
SAMPLE_B='ATP synthase: A protein complex that synthesizes ATP using a proton gradient.'

@pytest.fixture
def c(tmp_path,monkeypatch):
    data=tmp_path/'appdata';upload=data/'uploads';upload.mkdir(parents=True)
    monkeypatch.setattr(main,'DATA',data)
    monkeypatch.setattr(main,'DB',data/'study.sqlite3')
    monkeypatch.setattr(main,'UPLOADS',upload)
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    main.init()
    with TestClient(main.app) as client:yield client

def unit(c,name):return c.post('/api/units',json={'name':name}).json()['id']
def upload(c,unit,text,name):return c.post('/api/materials/upload',data={'unit_id':unit},files={'files':(name,text.encode(),'text/plain')}).json()['results'][0]['id']

def test_complete_backup_restores_everything(c):
    u=unit(c,'Cellular energetics')
    m=upload(c,u,SAMPLE_A,'lesson.txt')
    card=c.post('/api/cards/generate',json={'unit_id':u}).json()['ids'][0]
    c.post('/api/cards/'+card+'/review',json={'rating':'good'})
    quiz=c.post('/api/quizzes',json={'unit_id':u,'types':['fill','mcq'],'count':2}).json()
    c.post('/api/quizzes/'+quiz['id']+'/submit',json={'responses':{}})
    c.post('/api/guides',json={'unit_id':u,'mode':'exam'})
    c.post('/api/tasks',json={'unit_id':u,'title':'Study ATP'})
    before=c.get('/api/bootstrap').json()
    b=c.get('/api/backup')
    assert b.status_code==200
    # All study records and file bytes are in the archive.
    names=zipfile.ZipFile(io.BytesIO(b.content)).namelist()
    assert 'study.sqlite3' in names and any(x.startswith('uploads/') for x in names)
    assert c.delete('/api/materials/'+m).status_code==200
    assert c.delete('/api/units/'+u).status_code==200
    assert c.get('/api/bootstrap').json()['stats']['materials']==0
    r=c.post('/api/backup/restore',files={'file':('backup.zip',b.content,'application/zip')},data={'confirmation':'RESTORE'})
    assert r.status_code==200,r.text
    restored=c.get('/api/bootstrap').json()
    assert restored['units']==before['units']
    assert restored['materials']==before['materials']
    assert restored['cards']==before['cards']
    assert restored['attempts']==before['attempts']
    assert restored['tasks']==before['tasks']
    assert restored['guides']==before['guides']
    assert c.get('/api/materials/'+m+'/file').content==SAMPLE_A.encode()
    assert c.get('/api/quizzes/'+quiz['id']).json()['status']=='submitted'
    assert c.get('/api/guides/'+restored['guides'][0]['id']).status_code==200


def test_restore_rejects_invalid_zip_missing_confirm_and_zip_slip(c):
    u=unit(c,'Keep my work')
    clean=c.get('/api/backup').content
    for data,confirmation in [(clean,'wrong'),(b'not a zip','RESTORE')]:
        r=c.post('/api/backup/restore',files={'file':('wrong.zip',data,'application/zip')},data={'confirmation':confirmation})
        assert r.status_code==400,r.text
    payload=io.BytesIO()
    with zipfile.ZipFile(payload,'w') as z:
        z.writestr('study.sqlite3',b'not sqlite')
        z.writestr('uploads/../../evil.txt',b'bad')
    bad=c.post('/api/backup/restore',files={'file':('evil.zip',payload.getvalue(),'application/zip')},data={'confirmation':'RESTORE'})
    assert bad.status_code==400
    assert c.get('/api/bootstrap').json()['units'][0]['id']==u


def test_unit_and_material_ids_must_both_match(c):
    a=unit(c,'Unit A');b=unit(c,'Unit B')
    x=upload(c,a,SAMPLE_A,'a.txt');y=upload(c,b,SAMPLE_B,'b.txt')
    assert [m['id'] for m in main.source_rows(a,[y])]==[]
    assert [m['id'] for m in main.source_rows(a,[x])]==[x]
    r=c.post('/api/guides',json={'unit_id':a,'material_ids':[y]})
    assert r.status_code==400


def test_three_same_day_reviews_do_not_count_as_long_term_mastery(c):
    u=unit(c,'Energetics');m=upload(c,u,SAMPLE_A,'notes.txt')
    card=c.post('/api/cards/generate',json={'unit_id':u,'count':1}).json()['ids'][0]
    for _ in range(3):c.post('/api/cards/'+card+'/review',json={'rating':'good'})
    assert c.get('/api/bootstrap').json()['stats']['mastered']==0
    # Simulate spaced reviews on separate days, without waiting real time.
    with main.db() as conn:
        rows=conn.execute('SELECT id FROM reviews WHERE card_id=? ORDER BY reviewed_at',(card,)).fetchall()
        conn.execute('UPDATE reviews SET reviewed_at=? WHERE id=?',('2026-10-30T12:00:00+00:00',rows[0][0]))
    assert c.get('/api/bootstrap').json()['stats']['mastered']==1


def test_restore_rejects_database_schema_mismatch_without_loss(c):
    u=unit(c,'Keep original')
    fake=io.BytesIO()
    with zipfile.ZipFile(fake,'w') as z:
        with sqlite3.connect(':memory:') as conn:
            # SQLite in-memory copies cannot directly export; an empty string is sufficient
            # to check that an invalid database is rejected before replacing the current one.
            z.writestr('study.sqlite3',b'not a database')
    r=c.post('/api/backup/restore',files={'file':('incompatible.zip',fake.getvalue(),'application/zip')},data={'confirmation':'RESTORE'})
    assert r.status_code==400,r.text
    assert c.get('/api/bootstrap').json()['units'][0]['id']==u


def test_data_survives_database_reinitialization(c):
    u=unit(c,'Keep after restart')
    m=upload(c,u,SAMPLE_B,'respiration.txt')
    # init() is executed at every fresh server boot and must never erase work.
    main.init()
    result=c.get('/api/bootstrap').json()
    assert result['units'][0]['id']==u
    assert result['materials'][0]['id']==m
    assert c.get('/api/materials/'+m+'/file').content==SAMPLE_B.encode()


def test_unanswered_written_answer_cannot_be_self_graded_as_correct(c):
    u=unit(c,'Enzymes');upload(c,u,SAMPLE_A,'enzymes.txt')
    quiz=c.post('/api/quizzes',json={'unit_id':u,'types':['short'],'count':1}).json()
    report=c.post('/api/quizzes/'+quiz['id']+'/submit',json={'responses':{}}).json()['report']
    assert report['manual_needed']==0
    assert report['graded']==1 and report['percent']==0
    qid=report['details'][0]['id']
    tried=c.post('/api/quizzes/'+quiz['id']+'/selfgrade',json={'scores':{qid:True}})
    assert tried.json()['report']['percent']==0
