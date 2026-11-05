"""No-login public access must never turn a personal database into shared data."""
import base64
import io
import zipfile

import pytest
from fastapi.testclient import TestClient
import main


@pytest.fixture
def public_app(tmp_path, monkeypatch):
    base=tmp_path/'data';(base/'uploads').mkdir(parents=True)
    monkeypatch.setattr(main, 'PUBLIC_MODE', True)
    monkeypatch.setattr(main, 'DATA', base)
    monkeypatch.setattr(main, 'UPLOADS', base/'uploads')
    monkeypatch.setattr(main, 'DB', base/'study.sqlite3')
    monkeypatch.setattr(main, 'VISITOR_ROOT', base/'visitors')
    monkeypatch.setattr(main, 'ADMIN_USERNAME', 'student')
    monkeypatch.setattr(main, 'ADMIN_PASSWORD', 'abcdefghijklmnopqrstuvwxyz')
    monkeypatch.setenv('OPENAI_API_KEY','test-secret-never-send-to-visitor')
    main.init()
    with main.db() as c:
        c.execute('INSERT INTO units (id,name,description,status,created_at) VALUES (?,?,?,?,?)',('owner-only','Private owner notes','', 'current',main.now()))
    yield main.app


def test_anyone_opens_home_without_login_and_gets_cookie(public_app):
    with TestClient(public_app) as a:
        result=a.get('/')
        assert result.status_code==200
        assert 'www-authenticate' not in result.headers
        assert a.cookies.get('biosphere_visitor')
        bootstrap=a.get('/api/bootstrap').json()
        assert bootstrap['units']==[]
        assert bootstrap['ai_enabled'] is False
        assert not bootstrap['materials']
        assert a.get('/healthz').status_code==200


def test_visitors_have_isolated_documents_and_assignments(public_app):
    with TestClient(public_app) as a, TestClient(public_app) as b:
        a.get('/');b.get('/')
        assert a.cookies['biosphere_visitor']!=b.cookies['biosphere_visitor']
        u=a.post('/api/units',json={'name':'A private biology unit'}).json()['id']
        upload=a.post('/api/materials/upload',files={'files':('notes.txt',b'Sensitive lesson notes for A.','text/plain')},data={'unit_id':u})
        assert upload.status_code==200, upload.text
        mid=upload.json()['results'][0]['id']
        a.post('/api/schedule',json={'title':'Private quiz deadline','kind':'exam','due_date':'2026-11-10'})
        assert len(a.get('/api/bootstrap').json()['materials'])==1
        assert b.get('/api/bootstrap').json()['units']==[]
        assert b.get('/api/materials/'+mid+'/file').status_code==404
        assert b.get('/api/schedule').json()['entries']==[]
        backup=b.post('/api/backup/download')
        assert backup.status_code==200
        with zipfile.ZipFile(io.BytesIO(backup.content)) as z:
            assert z.namelist().count('study.sqlite3')==1
            assert not any(x.startswith('uploads/') for x in z.namelist())
        assert len(a.get('/api/bootstrap').json()['materials'])==1


def test_owner_archive_stays_protected(public_app):
    with TestClient(public_app) as guest, TestClient(public_app) as owner:
        assert guest.get('/owner').status_code==401
        assert guest.get('/api/bootstrap').json()['units']==[]
        basic='Basic '+base64.b64encode(b'student:abcdefghijklmnopqrstuvwxyz').decode()
        r=owner.get('/owner',headers={'Authorization':basic},follow_redirects=False)
        assert r.status_code==303
        assert owner.cookies.get('biosphere_owner')
        assert owner.get('/api/bootstrap').json()['units'][0]['id']=='owner-only'
        assert guest.get('/api/bootstrap').json()['units']==[]
        owner.get('/owner/logout',follow_redirects=False)
        assert owner.get('/api/bootstrap').json()['units']==[]


def test_untrusted_websites_cannot_modify_anonymous_workspace(public_app):
    with TestClient(public_app) as a:
        a.get('/')
        assert a.post('/api/units',json={'name':'External change'},headers={'Origin':'https://random.website'}).status_code==403
        assert a.post('/api/units',json={'name':'External change'},headers={'sec-fetch-site':'cross-site'}).status_code==403
        assert a.get('/api/bootstrap').json()['units']==[]
        assert a.post('/api/ai/chat',json={'message':'Use paid API'}).status_code==403


def test_fresh_browser_restore_stays_in_own_workspace(public_app):
    with TestClient(public_app) as a, TestClient(public_app) as b:
        a.post('/api/units',json={'name':'Keep in A only'})
        backup=a.post('/api/backup/download').content
        assert b.post('/api/backup/restore',data={'confirmation':'RESTORE'},files={'file':('backup.zip',backup,'application/zip')}).status_code==200
        assert len(b.get('/api/bootstrap').json()['units'])==1
        b.delete('/api/units/'+b.get('/api/bootstrap').json()['units'][0]['id'])
        assert len(a.get('/api/bootstrap').json()['units'])==1


def test_invalid_visitor_cookie_cannot_escape_workspace_folder(public_app):
    with TestClient(public_app) as a:
        a.cookies.set('biosphere_visitor','../bad', domain='testserver.local', path='/')
        a.get('/')
        assert len(a.cookies['biosphere_visitor'])==48
        assert '/' not in a.cookies['biosphere_visitor']
