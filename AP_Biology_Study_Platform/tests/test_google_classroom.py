"""No real Google credentials or network access are used in these tests."""
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit,parse_qs

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

@pytest.fixture
def system(tmp_path,monkeypatch):
    data=tmp_path/'gclassroom';data.mkdir();(data/'uploads').mkdir()
    monkeypatch.setenv('GOOGLE_CLASSROOM_CLIENT_ID','fake.apps.googleusercontent.com')
    monkeypatch.setenv('GOOGLE_CLASSROOM_CLIENT_SECRET','fake-google-client-secret')
    monkeypatch.setenv('GOOGLE_CLASSROOM_TOKEN_KEY',Fernet.generate_key().decode('ascii'))
    import main,google_classroom as gc
    monkeypatch.setattr(main,'PUBLIC_MODE',True)
    monkeypatch.setattr(main,'ADMIN_USERNAME','student')
    monkeypatch.setattr(main,'ADMIN_PASSWORD','this-password-is-strong-enough')
    monkeypatch.setattr(main,'DATA',data)
    monkeypatch.setattr(main,'UPLOADS',data/'uploads')
    monkeypatch.setattr(main,'DB',data/'study.sqlite3')
    monkeypatch.setattr(main,'VISITOR_ROOT',data/'visitors')
    main.init()
    return main,gc


def authorize(client,monkeypatch,gc):
    r=client.post('/api/google-classroom/connect')
    assert r.status_code==200,r.text
    url=r.json()['authorization_url']
    u=urlsplit(url);q=parse_qs(u.query)
    assert u.netloc=='accounts.google.com'
    assert q['access_type']==['offline']
    assert q['code_challenge_method']==['S256']
    assert 'classroom.coursework.me.readonly' in q['scope'][0]
    assert len(q['state'][0])>30
    monkeypatch.setattr(gc,'google_post',lambda url,body:{'refresh_token':'opaque-very-private-refresh-token','access_token':'temporary-token'})
    r=client.get('/api/google-classroom/callback',params={'state':q['state'][0],'code':'fake-authorization-code'},follow_redirects=False)
    assert r.status_code==303 and 'classroom=connected' in r.headers['location']
    return q['state'][0]


def test_connection_only_after_consent(system,monkeypatch):
    main,gc=system
    c=TestClient(main.app,base_url='https://testserver')
    st=c.get('/api/google-classroom/status').json()
    assert st['configured'] and not st['connected']
    state=authorize(c,monkeypatch,gc)
    assert c.get('/api/google-classroom/status').json()['connected']
    assert c.get('/api/google-classroom/callback',params={'state':state,'code':'again'},follow_redirects=False).headers['location']=='/?classroom=denied'
    guest_db=main.VISITOR_ROOT/c.cookies.get('biosphere_visitor')/'study.sqlite3'
    assert guest_db.exists()
    assert b'opaque-very-private-refresh-token' not in guest_db.read_bytes()
    c.close()


def test_sync_courses_due_dates_submissions_and_dedupe(system,monkeypatch):
    main,gc=system
    c=TestClient(main.app,base_url='https://testserver')
    authorize(c,monkeypatch,gc)
    calls=[]
    def mock_pages(path,token,field,params=None,limit=1000):
        assert token=='temporary-token'
        calls.append(path)
        if field=='courses':return [{'id':'42','name':'AP Biology'}]
        if field=='courseWork':
            return [
                {'id':'19','title':'Enzymes Lab','state':'PUBLISHED','description':'Write conclusion',
                 'dueDate':{'year':2026,'month':11,'day':9},
                 'dueTime':{'hours':18,'minutes':0},
                 'alternateLink':'https://classroom.google.com/c/42/a/19/details'},
                {'id':'20','title':'Photosynthesis Quiz','state':'PUBLISHED'},
            ]
        if field=='studentSubmissions':return [{'courseWorkId':'19','state':'TURNED_IN'}, {'courseWorkId':'20','state':'ASSIGNED'}]
        raise AssertionError(path)
    monkeypatch.setattr(gc,'pages',mock_pages)
    a=c.post('/api/google-classroom/sync')
    assert a.status_code==200,a.text
    assert a.json()['added']==2 and a.json()['courses']==1
    data=c.get('/api/schedule').json()['entries']
    assert len(data)==2
    assert any(i['title']=='Enzymes Lab' and i['done'] and i['source']=='google_classroom' for i in data)
    assert any(i['title']=='Photosynthesis Quiz' and i['due_date']=='9999-12-31' and not i['done'] for i in data)
    b=c.post('/api/google-classroom/sync')
    assert b.status_code==200 and b.json()['added']==0 and b.json()['updated']==0
    # Once the cooldown passes, it re-syncs existing IDs instead of duplicating.
    import sqlite3
    location=main.VISITOR_ROOT/c.cookies.get('biosphere_visitor')/'study.sqlite3'
    with sqlite3.connect(location) as db:db.execute("UPDATE gc_authorization SET last_sync='2000-01-01T00:00:00+00:00'")
    b=c.post('/api/google-classroom/sync')
    assert b.status_code==200 and b.json()['added']==0 and b.json()['updated']==2
    assert len(c.get('/api/schedule').json()['entries'])==2
    assert gc.local_due_date({'dueDate':{'year':2026,'month':11,'day':6},'dueTime':{'hours':2,'minutes':0}})==('2026-11-05','20:00')
    assert len(calls)==6
    c.close()


def test_browser_workspaces_are_isolated(system,monkeypatch):
    main,gc=system
    a=TestClient(main.app,base_url='https://testserver');b=TestClient(main.app,base_url='https://testserver')
    authorize(a,monkeypatch,gc)
    assert a.get('/api/google-classroom/status').json()['connected']
    assert not b.get('/api/google-classroom/status').json()['connected']
    assert b.post('/api/google-classroom/sync').status_code==409
    a.close();b.close()


def test_missing_config_prevents_connection_without_google_credential_leak(system,monkeypatch):
    main,gc=system
    c=TestClient(main.app,base_url='https://testserver')
    monkeypatch.delenv('GOOGLE_CLASSROOM_CLIENT_SECRET')
    assert c.get('/api/google-classroom/status').json()['configured'] is False
    x=c.post('/api/google-classroom/connect')
    assert x.status_code==503
    assert 'fake-google-client-secret' not in x.text
    c.close()
