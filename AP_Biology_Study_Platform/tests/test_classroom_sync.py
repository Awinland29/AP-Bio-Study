import json
import os
import sqlite3
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import classroom_sync as gc


@pytest.fixture
def site(tmp_path, monkeypatch):
    for key in ('APBIO_GOOGLE_CLIENT_ID','APBIO_GOOGLE_CLIENT_SECRET','APBIO_GOOGLE_REDIRECT_URI','APBIO_GOOGLE_TOKEN_KEY'):
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('APBIO_GOOGLE_CLIENT_ID','fake-client.apps.googleusercontent.com')
    monkeypatch.setenv('APBIO_GOOGLE_CLIENT_SECRET','not-a-real-secret')
    monkeypatch.setenv('APBIO_GOOGLE_REDIRECT_URI','http://localhost/api/classroom/callback')
    monkeypatch.setenv('APBIO_GOOGLE_TOKEN_KEY',Fernet.generate_key().decode())
    database=tmp_path/'test.db'
    def db():
        c=sqlite3.connect(database)
        c.row_factory=sqlite3.Row
        return c
    def die(text,status=400):raise HTTPException(status_code=status,detail=text)
    app=FastAPI()
    gc.install(app,dict(db=db,die=die,now=lambda:gc.utcnow().isoformat()))
    return TestClient(app,base_url='http://localhost'),db


def test_disabled(site,monkeypatch):
    client,db=site
    monkeypatch.delenv('APBIO_GOOGLE_TOKEN_KEY')
    s=client.get('/api/classroom/status').json()
    assert not s['configured'] and not s['connected']
    assert client.get('/api/classroom/connect',follow_redirects=False).status_code==503


def test_oauth_pkce_sync_and_disconnect(site,monkeypatch):
    client,db=site
    visits=[]
    def mocked(url,*,method='GET',fields=None,bearer=None):
        visits.append((url,method,fields))
        if url==gc.OAUTH_TOKEN and fields['grant_type']=='authorization_code':
            assert fields['code_verifier']
            return {'access_token':'short-lived','refresh_token':'private-refresh'}
        if url==gc.OAUTH_TOKEN:
            assert fields['refresh_token']=='private-refresh'
            return {'access_token':'short-lived'}
        if '/courses?' in url:
            return {'courses':[{'id':'12345','name':'AP Biology','courseState':'ACTIVE'}]}
        if '/courseWork?' in url:
            return {'courseWork':[{
                'id':'456','title':'Cell Respiration FRQ','description':'Answer all parts',
                'dueDate':{'year':2026,'month':11,'day':20},
                'dueTime':{'hours':22,'minutes':30},
                'state':'PUBLISHED','workType':'ASSIGNMENT',
                'alternateLink':'https://classroom.google.com/c/123/a/456',
            },{'id':'789','title':'Untimed reading','state':'PUBLISHED',
              'workType':'ASSIGNMENT','alternateLink':'https://evil.example/fake'}]}
        raise AssertionError('Unexpected API URL: '+url)
    monkeypatch.setattr(gc,'http_json',mocked)
    auth=client.get('/api/classroom/connect',follow_redirects=False)
    assert auth.status_code==303
    url=auth.headers['location']
    assert urlsplit(url).hostname=='accounts.google.com'
    params=parse_qs(urlsplit(url).query)
    assert 'code_challenge' in params and params['code_challenge_method']==['S256']
    assert not any('classroom.coursework.me' == x for x in params['scope'])
    assert all('readonly' in scope for scope in params['scope'][0].split())
    state=params['state'][0]
    assert client.get('/api/classroom/callback',params={'code':'ok','state':'incorrect'},follow_redirects=False).status_code==400
    result=client.get('/api/classroom/callback',params={'code':'ok','state':state},follow_redirects=False)
    assert result.status_code==303 and result.headers['location']=='/?classroom=connected'
    assert client.get('/api/classroom/callback',params={'code':'ok','state':state},follow_redirects=False).status_code==400
    with db() as c:
        data=c.execute('SELECT refresh_secret FROM classroom_auth').fetchone()[0]
    assert 'private-refresh' not in data
    assert client.get('/api/classroom/status').json()['connected']
    data=client.post('/api/classroom/sync')
    assert data.status_code==200 and data.json()['count']==2
    saved=client.get('/api/classroom/assignments').json()['assignments']
    assert len(saved)==2 and saved[0]['due_date']=='2026-11-20'
    assert saved[0]['due_time']=='22:30'
    assert saved[1]['url']==''
    assert client.post('/api/classroom/disconnect').json()['ok']
    assert not client.get('/api/classroom/status').json()['connected']
    assert client.get('/api/classroom/assignments').json()['assignments']==[]


def test_failed_sync_preserves_prior_data(site,monkeypatch):
    client,db=site
    key=gc.config()['fernet']
    with db() as c:
        c.execute("INSERT INTO classroom_auth VALUES ('google',?,?,'')",(key.encrypt(b'key').decode(),gc.utcnow().isoformat()))
        c.execute("INSERT INTO classroom_assignments VALUES (?,?,?,?,?,?,?,?,?,?)",('1','2','Biology','Old assignment','','2026-12-01','','','ASSIGNMENT',gc.utcnow().isoformat()))
    def fail(url,*,method='GET',fields=None,bearer=None):
        if 'token' in url:return {'access_token':'abc'}
        raise HTTPException(403,'School blocked')
    monkeypatch.setattr(gc,'http_json',fail)
    assert client.post('/api/classroom/sync').status_code==403
    assert client.get('/api/classroom/assignments').json()['assignments'][0]['title']=='Old assignment'


def test_invalid_classroom_links_are_dropped():
    assert gc._safe_classroom_link('https://classroom.google.com/c/123')
    for url in ['https://classroom.google.com.evil.example/','http://classroom.google.com/c/1','https://notclassroom.google.com/c/1']:
        assert gc._safe_classroom_link(url)==''


def test_source_has_no_write_google_scopes():
    assert all(scope.endswith('.readonly') for scope in gc.SCOPES)
    assert 'classroom.coursework.me.readonly' in gc.SCOPES[1]
