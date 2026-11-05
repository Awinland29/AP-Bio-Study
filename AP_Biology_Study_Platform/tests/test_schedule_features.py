"""Real API tests of schedule/assignment CRUD, importing and backup restore."""
import io,sqlite3,zipfile
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
import main
from schedule_extras import import_csv,parse_ics

@pytest.fixture
def client(tmp_path,monkeypatch):
    data=tmp_path/'data';uploads=data/'uploads';uploads.mkdir(parents=True)
    monkeypatch.setattr(main,'DATA',data)
    monkeypatch.setattr(main,'DB',data/'study.sqlite3')
    monkeypatch.setattr(main,'UPLOADS',uploads)
    main.init()
    with TestClient(main.app) as client:yield client


def test_assignment_crud_and_schedule_order(client):
    c=client
    one=c.post('/api/schedule',json={'title':'Photosynthesis test','kind':'exam','due_date':'2026-11-15','details':'Light reactions and the Calvin cycle','url':'https://classroom.google.com/c/123'})
    assert one.status_code==200,one.text
    two=c.post('/api/schedule',json={'title':'Chapter homework','kind':'assignment','due_date':'2026-11-10'})
    assert two.status_code==200
    got=c.get('/api/schedule').json()['entries']
    assert [x['title'] for x in got]==['Chapter homework','Photosynthesis test']
    id=one.json()['id']
    assert c.patch('/api/schedule/'+id,json={'done':True,'details':'Updated notes'}).status_code==200
    assert next(x for x in c.get('/api/schedule').json()['entries'] if x['id']==id)['done']==1
    assert c.get('/api/export').json()['schedule_entries']
    main.init() # simulated restart while using persistent test directory
    assert any(x['id']==id for x in c.get('/api/schedule').json()['entries'])
    assert c.delete('/api/schedule/'+id).status_code==200
    assert c.patch('/api/schedule/'+id,json={'done':False}).status_code==404


def test_bad_dates_unsafe_links_and_invalid_types(client):
    c=client
    for payload in ({'title':'T','due_date':'2026-99-99'}, {'title':'T','due_date':'2026-11-08','url':'javascript:alert(1)'},
                    {'title':'T','due_date':'2026-11-08','url':'http://example.com'}, {'title':'T','due_date':'2026-11-08','kind':'other'},
                    {'title':'T','due_date':'2026-11-08','start_time':'15:00','end_time':'14:00'}):
        assert c.post('/api/schedule',json=payload).status_code==400
    assert c.put('/api/schedule/classroom-link',json={'url':'https://classroom.google.com.evil.com/c/123'}).status_code==400
    assert c.put('/api/schedule/classroom-link',json={'url':'https://classroom.google.com/c/123'}).status_code==200
    x=c.get('/api/schedule').json()
    assert x['classroom_url']=='https://classroom.google.com/c/123'
    assert not x['sync_enabled']
    assert c.put('/api/schedule/classroom-link',json={'url':''}).status_code==200


def test_import_csv_and_duplicate_detection(client):
    c=client
    content='Title,Due Date,Type,Start Time,End Time,Details,URL\nEnzyme Lab,11/10/2026,Assignment,,,Finish tables,\nUnit 4 Quiz,2026-11-14,Test / quiz,09:00,10:00,Study pathways,\n,2026-11-15,Assignment,,,,\n'
    def upload():return c.post('/api/schedule/import',files={'file':('assignments.csv',content.encode('utf-8'),'text/csv')})
    result=upload();assert result.status_code==200,result.text
    assert result.json()['created']==2 and result.json()['skipped']==1
    result=upload();assert result.json()['created']==0 and result.json()['duplicates']==2
    x=c.get('/api/schedule').json()['entries']
    assert x[1]['kind']=='exam' and x[0]['due_date']=='2026-11-10'


def test_import_ics_calendar_dates_and_no_recurring_hallucinations(client):
    c=client
    ics='''BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:frq-1\nSUMMARY:FRQ homework due\nDTSTART;VALUE=DATE:20261121\nDESCRIPTION:Complete parts a-d\nEND:VEVENT\nBEGIN:VEVENT\nSUMMARY:Bio weekly class\nDTSTART;TZID=America/Chicago:20261123T090000\nDTEND;TZID=America/Chicago:20261123T100000\nRRULE:FREQ=WEEKLY;COUNT=4\nEND:VEVENT\nEND:VCALENDAR'''
    r=c.post('/api/schedule/import',files={'file':('bio.ics',ics.encode(),'text/calendar')})
    assert r.status_code==200,r.text
    assert r.json()['created']==2
    assert len(c.get('/api/schedule').json()['entries'])==2
    assert 'only this occurrence' in c.get('/api/schedule').json()['entries'][1]['details']


def test_backup_restores_schedules_and_upgrades_legacy(client):
    c=client
    eid=c.post('/api/schedule',json={'title':'Final','due_date':'2026-12-15','kind':'exam'}).json()['id']
    c.put('/api/schedule/classroom-link',json={'url':'https://classroom.google.com/c/124'})
    backup=c.post('/api/backup/download').content
    c.delete('/api/schedule/'+eid)
    assert c.post('/api/backup/restore',data={'confirmation':'RESTORE'},files={'file':('backup.zip',backup,'application/zip')}).status_code==200
    assert any(x['id']==eid for x in c.get('/api/schedule').json()['entries'])
    assert c.get('/api/schedule').json()['classroom_url'].endswith('124')
    # Older backups without schedule tables must still restore successfully.
    old=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(backup)) as z,zipfile.ZipFile(old,'w',zipfile.ZIP_DEFLATED) as out:
        for f in z.infolist():
            data=z.read(f.filename)
            if f.filename=='study.sqlite3':
                import tempfile,os
                with tempfile.NamedTemporaryFile(suffix='.sqlite3') as tmp:
                    tmp.write(data);tmp.flush()
                    with sqlite3.connect(tmp.name) as db:
                        db.execute('DROP TABLE schedule_entries')
                        db.execute('DROP TABLE schedule_links')
                    data=open(tmp.name,'rb').read()
            out.writestr(f,data)
    r=c.post('/api/backup/restore',data={'confirmation':'RESTORE'},files={'file':('old-backup.zip',old.getvalue(),'application/zip')})
    assert r.status_code==200,r.text
    assert c.get('/api/schedule').json()['entries']==[]
    assert 'schedule_entries' in c.get('/api/export').json()


def test_upload_schedule_as_reference(client):
    c=client
    r=c.post('/api/extras/upload',data={'kind':'schedule'},files={'files':('class-times.txt',b'Period 1 at 8:00 AM','text/plain')})
    assert r.status_code==200,r.text
    id=r.json()['results'][0]['id']
    assert c.get('/api/extras/bootstrap').json()['kinds'][id]=='schedule'
    assert c.get('/api/materials/'+id+'/file').content==b'Period 1 at 8:00 AM'


def test_backup_requires_explicit_post_and_returns_single_valid_archive(client):
    """A speculative GET or HEAD cannot trigger a file attachment."""
    c=client
    for method in ("GET","HEAD"):
        r=c.request(method,"/api/backup")
        assert r.status_code == 405
        assert "attachment" not in r.headers.get("content-disposition","")
    r=c.post("/api/backup/download")
    assert r.status_code==200
    assert r.headers.get("content-type")=="application/zip"
    assert "attachment" in r.headers.get("content-disposition","")
    assert r.headers.get("cache-control")=="no-store"
    with zipfile.ZipFile(io.BytesIO(r.content)) as backup:
        assert "study.sqlite3" in backup.namelist()

def test_backup_button_has_no_downloadable_get_url():
    from pathlib import Path
    appjs=(Path(__file__).parent.parent/"static/app.js").read_text()
    assert 'data-action="download-backup"' in appjs
    assert 'href="/api/backup"' not in appjs
    assert "if(backupDownloading)return;" in appjs
    assert "method:'POST',cache:'no-store'" in appjs
