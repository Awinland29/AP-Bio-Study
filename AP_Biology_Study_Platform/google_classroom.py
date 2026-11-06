"""Google Classroom OAuth and read-only assignment synchronization for Biosphere.

Only the browser workspace that performed Google's OAuth consent can read its
own connection. Refresh tokens are encrypted at rest, never exposed to the UI.
No Classroom writes, submissions, grades changes, or impersonation are used.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode, quote
from urllib.request import Request as URLRequest, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse

GOOGLE_AUTH = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN = 'https://oauth2.googleapis.com/token'
GOOGLE_REVOKE = 'https://oauth2.googleapis.com/revoke'
CLASSROOM_API = 'https://classroom.googleapis.com/v1'
SCOPES = (
    'https://www.googleapis.com/auth/classroom.courses.readonly',
    'https://www.googleapis.com/auth/classroom.coursework.me.readonly',
)
DUELESS = '9999-12-31'  # Explicitly displayed as 'No due date' in the UI.


def configuration():
    client_id = os.environ.get('GOOGLE_CLASSROOM_CLIENT_ID', '').strip()
    secret = os.environ.get('GOOGLE_CLASSROOM_CLIENT_SECRET', '').strip()
    key = os.environ.get('GOOGLE_CLASSROOM_TOKEN_KEY', '').strip()
    callback = os.environ.get('GOOGLE_CLASSROOM_REDIRECT_URI',
        'https://ap-biology-study-studio.onrender.com/api/google-classroom/callback').strip()
    if not all((client_id, secret, key)):
        return None
    if not callback.startswith('https://') or callback.count('/') < 3:
        return None
    try:
        cipher = Fernet(key.encode('ascii'))
    except (ValueError, TypeError, UnicodeError):
        return None
    return client_id, secret, cipher, callback


def prepare_schema(db):
    with db() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS gc_authorization (
            id INTEGER PRIMARY KEY CHECK (id=1),
            refresh_ciphertext TEXT NOT NULL,
            last_sync TEXT NOT NULL DEFAULT '',
            course_count INTEGER NOT NULL DEFAULT 0,
            assignment_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS gc_oauth_pending (
            nonce TEXT PRIMARY KEY, verifier TEXT NOT NULL,
            expires TEXT NOT NULL
        );
        ''')


def google_post(url, fields):
    body = urlencode(fields).encode('ascii')
    request = URLRequest(url, data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded',
                 'Accept': 'application/json'}, method='POST')
    return _network_json(request)


def _network_json(request):
    try:
        with urlopen(request, timeout=15) as response:
            data = response.read(2_000_001)
            if len(data) > 2_000_000:
                raise ValueError('Google returned a response that was too large.')
            return json.loads(data.decode('utf-8'))
    except HTTPError as exc:
        if exc.code in (400, 401):
            raise ValueError('Google authorization expired or was revoked. Reconnect Google Classroom.') from None
        if exc.code == 403:
            raise ValueError('Google denied Classroom access. Your school may need to approve Biosphere.') from None
        raise ValueError('Google Classroom is unavailable right now. Try again later.') from None
    except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError('Could not reach Google Classroom. Try again later.') from None


def google_get(path, access_token, params=None):
    url = CLASSROOM_API + path
    if params:
        url += '?' + urlencode(params)
    req = URLRequest(url, headers={'Authorization':'Bearer '+access_token,
          'Accept':'application/json'}, method='GET')
    return _network_json(req)


def pages(path, token, field, params=None, limit=1000):
    all_rows=[]
    query=dict(params or {})
    for _ in range(20):
        query['pageSize']=100
        data=google_get(path,token,query)
        all_rows += data.get(field,[])
        if len(all_rows)>limit:
            raise ValueError('Too many Classroom items to import at once.')
        page=data.get('nextPageToken')
        if not page:
            return all_rows
        query['pageToken']=page
    raise ValueError('Classroom returned too many pages. Please try again later.')


def local_due_date(work):
    due=work.get('dueDate') or {}
    if not due:
        return DUELESS, ''
    try:
        year=int(due['year']);month=int(due['month']);day=int(due['day'])
        clock=work.get('dueTime')
        if clock:
            utc_dt=datetime(year,month,day,int(clock.get('hours',0)),
                            int(clock.get('minutes',0)),int(clock.get('seconds',0)),tzinfo=timezone.utc)
            local=utc_dt.astimezone(ZoneInfo('America/Chicago'))
            return local.date().isoformat(),local.strftime('%H:%M')
        return datetime(year,month,day).date().isoformat(),''
    except (ValueError, TypeError, KeyError, OverflowError):
        return DUELESS, ''


def install(app, core):
    db, now, rid, die = (core[k] for k in ('db', 'now', 'rid', 'die'))
    prepare_schema(db)

    def connection():
        with db() as conn:
            row=conn.execute('SELECT * FROM gc_authorization WHERE id=1').fetchone()
        return dict(row) if row else None

    def require_config():
        cfg=configuration()
        if cfg is None:
            die('Google Classroom needs a Google OAuth client configured by the site administrator.',503)
        return cfg

    @app.get('/api/google-classroom/status')
    def status():
        link=connection()
        cfg=configuration()
        return {'configured':bool(cfg),'connected':bool(link),
                'last_sync':link['last_sync'] if link else '',
                'course_count':link['course_count'] if link else 0,
                'assignment_count':link['assignment_count'] if link else 0,
                'last_error':link['last_error'] if link else '',
                'mode':'Read-only; refreshes when you open Assignments & Schedule.'}

    @app.post('/api/google-classroom/connect')
    def connect():
        client_id,_,_,callback=require_config()
        nonce=secrets.token_urlsafe(32)
        verifier=secrets.token_urlsafe(64)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')
        expiry=(datetime.now(timezone.utc)+timedelta(minutes=12)).isoformat()
        with db() as conn:
            conn.execute('DELETE FROM gc_oauth_pending WHERE expires<?',(datetime.now(timezone.utc).isoformat(),))
            conn.execute('INSERT INTO gc_oauth_pending VALUES (?,?,?)',(nonce,verifier,expiry))
        parameters={'client_id':client_id,'redirect_uri':callback,'response_type':'code',
                    'scope':' '.join(SCOPES),'access_type':'offline','prompt':'consent',
                    'include_granted_scopes':'false','state':nonce,
                    'code_challenge':challenge,'code_challenge_method':'S256'}
        return {'authorization_url':GOOGLE_AUTH+'?'+urlencode(parameters)}

    @app.get('/api/google-classroom/callback')
    def callback(state:str='',code:str='',error:str=''):
        if not state or len(state)>200:
            return RedirectResponse('/?classroom=error',status_code=303)
        with db() as conn:
            row=conn.execute('SELECT * FROM gc_oauth_pending WHERE nonce=?',(state,)).fetchone()
            conn.execute('DELETE FROM gc_oauth_pending WHERE nonce=?',(state,))
        if not row or row['expires'] < datetime.now(timezone.utc).isoformat() or error or not code:
            return RedirectResponse('/?classroom=denied',status_code=303)
        cfg=configuration()
        if cfg is None:
            return RedirectResponse('/?classroom=setup',status_code=303)
        cid,secret,cipher,callback_url=cfg
        try:
            payload=google_post(GOOGLE_TOKEN,{'client_id':cid,'client_secret':secret,
                'code':code,'code_verifier':row['verifier'],
                'redirect_uri':callback_url,'grant_type':'authorization_code'})
            refresh=payload.get('refresh_token','')
            granted=set(payload.get('scope','').split())
            if not refresh or (granted and not set(SCOPES).issubset(granted)):
                raise ValueError('Google did not provide the permissions needed to sync.')
            ciphertext=cipher.encrypt(refresh.encode('utf-8')).decode('ascii')
            with db() as conn:
                conn.execute('''INSERT INTO gc_authorization(id,refresh_ciphertext) VALUES(1,?)
                    ON CONFLICT(id) DO UPDATE SET refresh_ciphertext=excluded.refresh_ciphertext,
                    last_sync='',course_count=0,assignment_count=0,last_error='' ''',(ciphertext,))
            return RedirectResponse('/?classroom=connected',status_code=303)
        except (ValueError,KeyError,TypeError):
            return RedirectResponse('/?classroom=error',status_code=303)

    @app.post('/api/google-classroom/sync')
    def sync():
        cfg=require_config()
        current=connection()
        if not current:
            die('Connect your Google Classroom account first.',409)
        if current['last_sync']:
            try:
                since=(datetime.now(timezone.utc)-datetime.fromisoformat(current['last_sync'])).total_seconds()
                if since<45:
                    return {'added':0,'updated':0,'courses':current['course_count'],
                            'assignments':current['assignment_count'],'warnings':[],
                            'last_sync':current['last_sync'],'note':'Recently synced; no new request needed.'}
            except ValueError:
                pass
        _,client_secret,cipher,_=cfg
        try:
            refresh=cipher.decrypt(current['refresh_ciphertext'].encode('ascii')).decode('utf-8')
        except (InvalidToken,ValueError,UnicodeError):
            die('Your Classroom connection could not be read. Reconnect your account.',409)
        try:
            new=google_post(GOOGLE_TOKEN,{'client_id':cfg[0],'client_secret':client_secret,
                      'refresh_token':refresh,'grant_type':'refresh_token'})
            token=new.get('access_token')
            if not token:
                raise ValueError('Google did not return an access token. Reconnect your account.')
            courses=pages('/courses',token,'courses',{'studentId':'me','courseStates':'ACTIVE'},limit=100)
            collected=[]; warnings=[]
            for course in courses:
                course_id=str(course.get('id',''))
                if not re.fullmatch(r'[\w-]{1,128}',course_id):
                    continue
                name=str(course.get('name') or 'Class')[:160]
                coursework=pages('/courses/'+quote(course_id,safe='')+'/courseWork',token,'courseWork',limit=500)
                try:
                    submissions=pages('/courses/'+quote(course_id,safe='')+'/courseWork/-/studentSubmissions',
                        token,'studentSubmissions',{'userId':'me'},limit=1000)
                    by_work={str(x.get('courseWorkId')):x.get('state','') for x in submissions}
                except ValueError:
                    # Coursework still syncs, but never claim it is complete.
                    by_work={};warnings.append('Submission status unavailable for '+name)
                for work in coursework:
                    if work.get('state') not in (None,'PUBLISHED'):
                        continue
                    work_id=str(work.get('id',''))
                    if not re.fullmatch(r'[\w-]{1,128}',work_id):continue
                    title=str(work.get('title') or 'Untitled assignment')[:180]
                    due,clock=local_due_date(work)
                    kind='exam' if re.search(r'\b(test|quiz|exam)\b',title,re.I) else 'assignment'
                    details=('Class: '+name+'\n'+str(work.get('description') or '')[:3700])[:4000]
                    link=str(work.get('alternateLink') or '')
                    if not (link.startswith('https://classroom.google.com/') and len(link)<1200):link=''
                    state=by_work.get(work_id,'')
                    done=1 if state in ('TURNED_IN','RETURNED') else 0
                    collected.append((title,kind,due,clock,details,link,done,
                        'google_classroom',f'classroom:{course_id}:{work_id}'))
                    if len(collected)>=1500:
                        raise ValueError('This account has too many assignments for one sync.')
            stamp=now()
            added=0;changed=0
            with db() as conn:
                for title,kind,due,clock,details,link,done,source,key in collected:
                    exists=conn.execute('SELECT id FROM schedule_entries WHERE source_key=?',(key,)).fetchone()
                    if exists:
                        conn.execute('''UPDATE schedule_entries SET title=?,kind=?,due_date=?,
                            start_time=?,end_time='',details=?,url=?,done=?,updated_at=? WHERE source_key=?''',
                            (title,kind,due,clock,details,link,done,stamp,key))
                        changed+=1
                    else:
                        conn.execute('''INSERT INTO schedule_entries
                            (id,title,kind,due_date,start_time,end_time,details,url,done,source,source_key,created_at,updated_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                            (rid(),title,kind,due,clock,'',details,link,done,source,key,stamp,stamp))
                        added+=1
                # Keep previously synced work if a course is removed or archived; never
                # unexpectedly erase the user's history on a transient API failure.
                conn.execute('''UPDATE gc_authorization SET last_sync=?,course_count=?,
                    assignment_count=?,last_error=? WHERE id=1''',
                    (stamp,len(courses),len(collected),'; '.join(warnings[:4])))
            return {'added':added,'updated':changed,'courses':len(courses),
                    'assignments':len(collected),'warnings':warnings[:4], 'last_sync':stamp}
        except ValueError as exc:
            with db() as conn:
                conn.execute('UPDATE gc_authorization SET last_error=? WHERE id=1',(str(exc)[:250],))
            die(str(exc),503)

    @app.post('/api/google-classroom/disconnect')
    def disconnect():
        existing=connection()
        if existing:
            cfg=configuration()
            if cfg:
                try:
                    token=cfg[2].decrypt(existing['refresh_ciphertext'].encode('ascii')).decode('utf-8')
                    google_post(GOOGLE_REVOKE,{'token':token})
                except (ValueError, InvalidToken,UnicodeError):
                    pass
        with db() as conn:
            conn.execute('DELETE FROM gc_authorization')
            conn.execute('DELETE FROM gc_oauth_pending')
        return {'ok':True,'note':'Google disconnected. Previously synchronized assignments remain until deleted.'}
