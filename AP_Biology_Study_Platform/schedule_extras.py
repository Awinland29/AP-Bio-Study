"""Manual schedule/assignment tracker plus safe CSV / ICS imports.

A Google Classroom link here is a shortcut only; no credentials are collected,
no private Google data is fetched, and nothing is described as synced.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import UploadFile, File

VALID_KINDS = {'assignment', 'exam', 'class', 'event'}
MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000


def prepare_schema(db):
    with db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS schedule_entries (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL,
                due_date TEXT NOT NULL, start_time TEXT NOT NULL DEFAULT '',
                end_time TEXT NOT NULL DEFAULT '', details TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '', done INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'manual', source_key TEXT UNIQUE,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS schedule_entries_dates ON schedule_entries(due_date, done);
            CREATE TABLE IF NOT EXISTS schedule_links (
                id TEXT PRIMARY KEY, url TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        ''')


def valid_date(raw):
    s = str(raw or '').strip()
    if not s:
        raise ValueError('Date is required.')
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError('Use YYYY-MM-DD or MM/DD/YYYY for dates.')


def valid_time(raw):
    s = str(raw or '').strip()
    if not s:
        return ''
    for fmt in ('%H:%M', '%H:%M:%S', '%I:%M %p', '%I %p'):
        try:
            return datetime.strptime(s.upper(), fmt).strftime('%H:%M')
        except ValueError:
            pass
    raise ValueError('Use a time like 08:30 or 2:30 PM.')


def safe_url(raw):
    value = str(raw or '').strip()
    if not value:
        return ''
    p = urlsplit(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or len(value) > 1200:
        raise ValueError('Links must be valid HTTPS addresses.')
    return value


def classroom_url(raw):
    value = safe_url(raw)
    if value and urlsplit(value).hostname != 'classroom.google.com':
        raise ValueError('Use a Google Classroom link from classroom.google.com.')
    return value


def clean_entry(body):
    if not isinstance(body, dict):
        raise ValueError('Invalid entry.')
    title = str(body.get('title') or '').strip()[:180]
    if not title:
        raise ValueError('Give this item a title.')
    kind = str(body.get('kind') or 'assignment').strip().lower()
    if kind not in VALID_KINDS:
        raise ValueError('Choose Assignment, Test, Class, or Event.')
    due_date = valid_date(body.get('due_date') or body.get('date'))
    start = valid_time(body.get('start_time'))
    end = valid_time(body.get('end_time'))
    if start and end and end < start:
        raise ValueError('End time must be after start time on the same day.')
    return {'title': title, 'kind': kind, 'due_date': due_date,
            'start_time': start, 'end_time': end,
            'details': str(body.get('details') or '')[:4000],
            'url': safe_url(body.get('url'))}


def normalize_import_row(row):
    # Case-insensitive, whitespace-insensitive headers. Aliases support exports
    # from school calendars, assignments sheets and basic spreadsheet software.
    data = {re.sub(r'[^a-z0-9]', '', str(k).lower()): v for k,v in row.items() if k}
    def first(*names):
        for name in names:
            v = data.get(name)
            if v is not None and str(v).strip():
                return str(v).strip()
        return ''
    title = first('title','name','summary','assignment','task','event')
    kind = first('type','kind','category').lower()
    if kind in {'homework','due','coursework','task','project'}: kind='assignment'
    elif kind in {'test','quiz','assessment','test / quiz','exam / quiz'}: kind='exam'
    elif kind in {'lesson','classschedule','classmeeting'}: kind='class'
    elif kind not in VALID_KINDS: kind='assignment'
    return clean_entry({'title':title,'kind':kind,
          'due_date':first('duedate','date','startdate','day'),
          'start_time':first('starttime','time'),
          'end_time':first('endtime'),
          'details':first('details','description','notes','location'),
          'url':first('url','link','classroomlink')})


def import_csv(text):
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or len(reader.fieldnames)>40:
        raise ValueError('CSV must have a header row such as Title,Due Date,Type.')
    result=[]; skipped=[]
    for index, row in enumerate(reader, 2):
        if index>MAX_ROWS+1: raise ValueError('Import at most 1,000 rows at a time.')
        if not any((v or '').strip() for v in row.values() if isinstance(v,str)):
            continue
        try: result.append(normalize_import_row(row))
        except (ValueError, TypeError) as exc:skipped.append(f'Row {index}: {str(exc)}')
    return result,skipped


def ics_datetime(value, key):
    """Parse common ICS DATE and DATE-TIME values (no recurring expansion)."""
    raw=value.strip()
    if re.fullmatch(r'\d{8}',raw):
        return {'date':datetime.strptime(raw,'%Y%m%d').date().isoformat(),'time':''}
    m=re.fullmatch(r'(\d{8}T\d{6})(Z?)',raw)
    if not m: raise ValueError('Unsupported calendar date/time format.')
    d=datetime.strptime(m.group(1),'%Y%m%dT%H%M%S')
    if m.group(2):
        d=d.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('America/Chicago'))
    else:
        tz=re.search(r'TZID=([^;:]+)',key,re.I)
        if tz:
            try: d=d.replace(tzinfo=ZoneInfo(tz.group(1))).astimezone(ZoneInfo('America/Chicago'))
            except ZoneInfoNotFoundError:raise ValueError('Unknown calendar timezone.')
    return {'date':d.date().isoformat(),'time':d.strftime('%H:%M')}


def parse_ics(text):
    unfolded=[]
    for line in text.replace('\r\n','\n').replace('\r','\n').split('\n'):
        if line.startswith((' ','\t')) and unfolded: unfolded[-1]+=line[1:]
        else: unfolded.append(line)
    events=[]; skipped=[]; cur=None
    for line in unfolded:
        if line=='BEGIN:VEVENT':
            cur={};continue
        if line=='END:VEVENT' and cur is not None:
            try:
                starts=[(k,v) for k,v in cur.items() if k.startswith('DTSTART')]
                if not starts:raise ValueError('Calendar event has no start date.')
                stamp=ics_datetime(starts[0][1],starts[0][0])
                ends=[(k,v) for k,v in cur.items() if k.startswith('DTEND')]
                ending=ics_datetime(ends[0][1],ends[0][0]) if ends else None
                if ending and ending['date']!=stamp['date']:ending=None
                summary=cur.get('SUMMARY','').replace('\\n',' ')
                description=cur.get('DESCRIPTION','').replace('\\n','\n')
                if 'RRULE' in cur:description += '\nRecurring event: only this occurrence was imported.'
                ev=clean_entry({'title':summary,'kind':'assignment' if any(w in summary.lower() for w in ('due','assignment','homework')) else 'event',
                          'due_date':stamp['date'],'start_time':stamp['time'],
                          'end_time':ending['time'] if ending else '',
                          'details':description+'\n'+cur.get('LOCATION','').replace('\\,',',') if cur.get('LOCATION') else description,
                          'url':cur.get('URL','')})
                events.append(ev)
            except (ValueError,TypeError) as exc:skipped.append('Calendar event: '+str(exc))
            if len(events)+len(skipped)>MAX_ROWS:raise ValueError('Import at most 1,000 calendar events.')
            cur=None;continue
        if cur is not None and ':' in line:
            key,val=line.split(':',1)
            prefix,sep,params=key.partition(';')
            cur[prefix.upper()+(sep+params if sep else '')]=val.replace('\\,',',').replace('\\;',';')
    return events,skipped


def install(app, core):
    db,items,item,die=(core[k] for k in ('db','items','item','die'))
    rid,now=core['rid'],core['now']
    prepare_schema(db)

    def error_safe(fn,*args):
        try:return fn(*args)
        except (ValueError,TypeError) as exc:die(str(exc),400)

    @app.get('/api/schedule')
    def get_schedule():
        return {'entries':items('SELECT * FROM schedule_entries ORDER BY due_date ASC,start_time ASC,created_at DESC'),
                'classroom_url':(item("SELECT url FROM schedule_links WHERE id='classroom'") or {}).get('url',''),
                'sync_enabled':False,'note':'Google Classroom is a saved shortcut, not connected or synced.'}

    @app.post('/api/schedule')
    def add_entry(body:dict):
        data=error_safe(clean_entry,body);eid=rid();ts=now()
        with db() as conn:
            conn.execute('INSERT INTO schedule_entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (eid,data['title'],data['kind'],data['due_date'],data['start_time'],data['end_time'],data['details'],data['url'],0,'manual',None,ts,ts))
        return {'ok':True,'id':eid}

    @app.patch('/api/schedule/{entry_id}')
    def update_entry(entry_id:str,body:dict):
        existing=item('SELECT * FROM schedule_entries WHERE id=?',(entry_id,))
        if not existing:die('Schedule entry not found.',404)
        data=error_safe(clean_entry,{**existing,**body})
        done=existing['done'] if 'done' not in body else int(bool(body['done']))
        with db() as conn:
            conn.execute('''UPDATE schedule_entries SET title=?,kind=?,due_date=?,start_time=?,
                       end_time=?,details=?,url=?,done=?,updated_at=? WHERE id=?''',
                       (data['title'],data['kind'],data['due_date'],data['start_time'],data['end_time'],data['details'],data['url'],done,now(),entry_id))
        return {'ok':True}

    @app.delete('/api/schedule/{entry_id}')
    def delete_entry(entry_id:str):
        with db() as conn: result=conn.execute('DELETE FROM schedule_entries WHERE id=?',(entry_id,))
        if not result.rowcount:die('Entry not found.',404)
        return {'ok':True}

    @app.put('/api/schedule/classroom-link')
    def save_classroom_link(body:dict):
        url=error_safe(classroom_url,body.get('url',''))
        with db() as conn:
            conn.execute('''INSERT INTO schedule_links VALUES ('classroom',?,?)
                          ON CONFLICT(id) DO UPDATE SET url=excluded.url,updated_at=excluded.updated_at''',(url,now()))
        return {'ok':True,'url':url,'sync_enabled':False}

    @app.post('/api/schedule/import')
    async def upload_schedule(file:UploadFile=File(...)):
        filename=(file.filename or '').lower()
        if not filename.endswith(('.csv','.ics')):die('Upload a .csv assignment list or .ics calendar file.')
        raw=await file.read(MAX_IMPORT_BYTES+1)
        if len(raw)>MAX_IMPORT_BYTES:die('File must be 2 MB or less.')
        try:text=raw.decode('utf-8-sig')
        except UnicodeDecodeError:die('Use a UTF-8 CSV or ICS file.')
        try:
            entries,warnings=import_csv(text) if filename.endswith('.csv') else parse_ics(text)
        except (ValueError,TypeError,csv.Error) as exc:die(str(exc))
        created=0;duplicates=0;stamp=now()
        with db() as conn:
            for data in entries:
                # Hash source + normalized fields so re-imports are idempotent.
                source='calendar' if filename.endswith('.ics') else 'csv'
                canonical='\x1f'.join(data[k] for k in ('title','kind','due_date','start_time','end_time','details','url'))
                key=hashlib.sha256((source+'\x00'+canonical).encode('utf-8')).hexdigest()
                r=conn.execute('''INSERT OR IGNORE INTO schedule_entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (rid(),data['title'],data['kind'],data['due_date'],data['start_time'],data['end_time'],data['details'],data['url'],0,source,key,stamp,stamp))
                if r.rowcount:created+=1
                else:duplicates+=1
        return {'created':created,'duplicates':duplicates,'skipped':len(warnings),
                'warnings':warnings[:8],
                'note':'Imported files are a snapshot. They will not auto-sync when your school calendar changes.'}
