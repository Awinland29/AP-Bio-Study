"""Workspace identity and browser-local recovery compatibility tests."""
from pathlib import Path
from fastapi.testclient import TestClient
import main
import subprocess,os,sys

def test_epoch_stable_and_restored(tmp_path,monkeypatch):
    root=tmp_path/'data';(root/'uploads').mkdir(parents=True)
    monkeypatch.setattr(main,'DATA',root)
    monkeypatch.setattr(main,'DB',root/'study.sqlite3')
    monkeypatch.setattr(main,'UPLOADS',root/'uploads')
    main.init()
    with TestClient(main.app) as c:
        ident=c.get('/api/workspace-identity')
        assert ident.status_code==200, ident.text
        before=ident.json()
        assert before['workspace_id']=='local' and len(before['epoch'])>=16
        u=c.post('/api/units',json={'name':'My saved Unit 3'})
        assert u.status_code==200
        zip_data=c.post('/api/backup/download')
        assert zip_data.status_code==200 and zip_data.content.startswith(b'PK')
        main.init()
        assert c.get('/api/workspace-identity').json()==before
        c.delete('/api/units/'+u.json()['id'])
        restored=c.post('/api/backup/restore',data={'confirmation':'RESTORE'},
                        files={'file':('saved.zip',zip_data.content,'application/zip')})
        assert restored.status_code==200, restored.text
        assert c.get('/api/workspace-identity').json()['epoch']==before['epoch']
        assert any(x['name']=='My saved Unit 3' for x in c.get('/api/bootstrap').json()['units'])

def test_guest_identifier_is_not_a_cookie_and_visitors_are_separate(tmp_path):
    env=dict(os.environ,APBIO_PUBLIC='1',
             APBIO_ADMIN_USERNAME='student',
             APBIO_ADMIN_PASSWORD='test-very-long-private-example-password',
             APBIO_DATA_DIR=str(tmp_path/'public'))
    script="""from fastapi.testclient import TestClient
from main import app
a,b=TestClient(app),TestClient(app)
a.get('/api/bootstrap');b.get('/api/bootstrap')
ida=a.get('/api/workspace-identity').json()
idb=b.get('/api/workspace-identity').json()
assert ida['workspace_id']!=idb['workspace_id']
assert ida['epoch']!=idb['epoch']
assert a.cookies.get('biosphere_visitor') not in str(ida)
assert len(ida['workspace_id'])>30
assert a.get('/api/workspace-identity').json()==ida
o=TestClient(app)
auth=('student','test-very-long-private-example-password')
assert o.get('/owner',auth=auth,follow_redirects=False).status_code==303
assert o.get('/api/workspace-identity').json()['workspace_id']=='owner'
"""
    r=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,
         cwd=str(Path(__file__).resolve().parents[1]),env=env)
    assert r.returncode==0,r.stderr

def test_local_recovery_hooks_are_present_and_stay_manual_on_restore():
    root=Path(__file__).resolve().parents[1]/'static'
    s=(root/'local-safety.js').read_text()
    app=(root/'app.js').read_text()
    html=(root/'index.html').read_text()
    assert 'indexedDB.open' in s
    assert "/api/backup/download" in s
    assert "/api/backup/restore" in s
    assert 'window.confirm' in s
    assert 'old.epoch!==identity.epoch' in s
    assert 'BiosphereSafety?.markChanged(path)' in app
    assert '/static/local-safety.js' in html
