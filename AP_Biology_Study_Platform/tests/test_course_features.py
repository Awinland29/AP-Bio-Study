"""Course resources, authentic report drafts, FRQ self-rating, and backup compatibility."""
import io,sqlite3,zipfile,json
import pytest
from fastapi.testclient import TestClient
import main

@pytest.fixture
def client(tmp_path,monkeypatch):
    data=tmp_path/'data';uploads=data/'uploads';uploads.mkdir(parents=True)
    monkeypatch.setattr(main,'DATA',data)
    monkeypatch.setattr(main,'DB',data/'study.sqlite3')
    monkeypatch.setattr(main,'UPLOADS',uploads)
    main.init()
    with TestClient(main.app) as c:yield c

def putfile(c,kind,name,text,unit_id=''):
    r=c.post('/api/extras/upload',data={'kind':kind,'unit_id':unit_id},
            files={'files':(name,text.encode(),'text/plain')})
    assert r.status_code==200,r.text
    return r.json()['results'][0]['id']

def test_syllabus_and_references_are_real_files_and_categorized(client):
    c=client
    unit=c.post('/api/units',json={'name':'Unit 3'}).json()['id']
    syllabus=putfile(c,'syllabus','syllabus.txt','Grade scale, calendar and policies.',unit)
    ref=putfile(c,'reference','formula-sheet.txt','Enzyme: A biological catalyst.',unit)
    assert c.get('/api/materials/'+syllabus+'/file').content==b'Grade scale, calendar and policies.'
    r=c.get('/api/extras/bootstrap').json()['kinds']
    assert r[syllabus]=='syllabus' and r[ref]=='reference'
    assert next(m for m in c.get('/api/bootstrap').json()['materials'] if m['id']==syllabus)['unit_id'] is None
    assert [x['id'] for x in main.source_rows()]==[ref]
    assert [x['id'] for x in main.source_rows(None,[syllabus])]==[syllabus]
    assert c.patch('/api/extras/resources/'+ref,json={'kind':'lab'}).status_code==200
    assert not main.source_rows()
    assert c.patch('/api/extras/resources/'+ref,json={'kind':'invalid'}).status_code==400


def test_lab_reports_create_edit_persist_export_and_delete(client):
    c=client
    unit=c.post('/api/units',json={'name':'Enzyme lab'}).json()['id']
    payload={'title':'Effect of pH','unit_id':unit,'sections':{'question':'What is the rate?','hypothesis':'Rate changes with pH.','data':'Real observations only.'}}
    r=c.post('/api/extras/labs',json=payload);assert r.status_code==200,r.text
    lid=r.json()['id']
    got=c.get('/api/extras/labs/'+lid).json()
    assert got['sections']['data']=='Real observations only.'
    assert got['sections']['analysis']==''
    payload['sections']['analysis']='Rates peaked at neutral pH.'
    assert c.patch('/api/extras/labs/'+lid,json=payload).status_code==200
    assert c.get('/api/extras/labs/'+lid).json()['sections']['analysis']=='Rates peaked at neutral pH.'
    main.init() # simulates a restart
    assert any(x['id']==lid for x in c.get('/api/extras/bootstrap').json()['labs'])
    assert any(x['id']==lid for x in c.get('/api/export').json()['lab_reports'])
    assert c.delete('/api/extras/labs/'+lid).status_code==200
    assert c.get('/api/extras/labs/'+lid).status_code==404


def test_frq_draft_self_assessment_honest_and_immutable(client):
    c=client;bank=c.get('/api/extras/frq-bank').json()['questions']
    assert len(bank)>=6 and all(len(q['parts'])>=4 for q in bank)
    pid=bank[0]['id']
    r=c.post('/api/extras/frq-attempts',json={'prompt_id':pid})
    assert r.status_code==200,r.text
    aid=r.json()['id']
    draft=c.patch('/api/extras/frq-attempts/'+aid,json={'answers':{'a':'pH was varied; enzyme reaction rate measured.'}})
    assert draft.status_code==200 and draft.json()['status']=='draft'
    read=c.get('/api/extras/frq-attempts/'+aid).json()
    assert read['answers']['a'].startswith('pH was varied')
    assert read['checks']==[] and read['status']=='draft'
    invalid=c.patch('/api/extras/frq-attempts/'+aid,json={'answers':{'a':'answer'},'status':'submitted','checks':['a:999']})
    assert invalid.status_code==400
    submitted=c.patch('/api/extras/frq-attempts/'+aid,json={'answers':{'a':'pH was varied; enzyme reaction rate measured.'},'status':'submitted','checks':['a:0']})
    assert submitted.json()['points']==1
    assert c.patch('/api/extras/frq-attempts/'+aid,json={'answers':{'a':'changed'}}).status_code==400
    state=c.get('/api/extras/bootstrap').json()['frqs']
    assert state[0]['points']==1 and state[0]['status']=='submitted'
    assert 'check' not in state[0]
    assert any(x['id']==aid for x in c.get('/api/export').json()['frq_attempts'])


def test_backup_restores_extra_tables_and_resource_categories(client):
    c=client
    fileid=putfile(c,'syllabus','my-syllabus.txt','Do honest work.')
    lab=c.post('/api/extras/labs',json={'title':'Osmosis report','sections':{'data':'Measured 2.5%'}}).json()['id']
    frq=c.post('/api/extras/frq-attempts',json={'prompt_id':'osmosis'}).json()['id']
    c.patch('/api/extras/frq-attempts/'+frq,json={'answers':{'a':'Mass gain decreases.'}})
    backup=c.post('/api/backup/download').content
    assert 'study.sqlite3' in zipfile.ZipFile(io.BytesIO(backup)).namelist()
    assert c.delete('/api/materials/'+fileid).status_code==200
    assert c.delete('/api/extras/labs/'+lab).status_code==200
    assert c.delete('/api/extras/frq-attempts/'+frq).status_code==200
    r=c.post('/api/backup/restore',data={'confirmation':'RESTORE'},files={'file':('backup.zip',backup,'application/zip')})
    assert r.status_code==200,r.text
    state=c.get('/api/extras/bootstrap').json()
    assert state['kinds'][fileid]=='syllabus' and state['labs'][0]['id']==lab and state['frqs'][0]['id']==frq
    assert c.get('/api/materials/'+fileid+'/file').content==b'Do honest work.'


def test_backup_restores_legacy_material_column_without_losing_files(client):
    c=client
    fileid=putfile(c,'reference','reference.txt','Before the upgrade.')
    snap=io.BytesIO()
    with sqlite3.connect(':memory:') as dummy:
        pass
    # Copy a real backup, then remove the *new* column/tables to emulate old archives.
    backup=c.post('/api/backup/download').content
    with zipfile.ZipFile(io.BytesIO(backup)) as zin, zipfile.ZipFile(snap,'w',zipfile.ZIP_DEFLATED) as zout:
        for entry in zin.infolist():
            if entry.filename=='study.sqlite3':
                from tempfile import NamedTemporaryFile
                with NamedTemporaryFile(suffix='.sqlite3') as f:
                    f.write(zin.read(entry));f.flush()
                    with sqlite3.connect(f.name) as db:
                        db.execute('DROP TABLE lab_reports')
                        db.execute('DROP TABLE frq_attempts')
                        db.execute('ALTER TABLE materials DROP COLUMN kind')
                    zout.writestr('study.sqlite3',open(f.name,'rb').read())
            else: zout.writestr(entry,zin.read(entry.filename))
    r=c.post('/api/backup/restore',data={'confirmation':'RESTORE'},files={'file':('old.zip',snap.getvalue(),'application/zip')})
    assert r.status_code==200,r.text
    assert c.get('/api/extras/bootstrap').json()['kinds'][fileid]=='notes' # legacy defaults to notes
    assert c.get('/api/materials/'+fileid+'/file').status_code==200
    assert 'lab_reports' in c.get('/api/export').json()


def test_invalid_lab_and_frq_inputs_rejected(client):
    c=client
    assert c.post('/api/extras/labs',json={'title':'','sections':{}}).status_code==400
    assert c.post('/api/extras/labs',json={'title':'Lab','sections':'not a dict'}).status_code==400
    assert c.post('/api/extras/frq-attempts',json={'prompt_id':'not-real'}).status_code==404
    frq=c.post('/api/extras/frq-attempts',json={'prompt_id':'enzyme-ph'}).json()['id']
    assert c.patch('/api/extras/frq-attempts/'+frq,json={'answers':{'invalidpart':'x'}}).status_code==400
