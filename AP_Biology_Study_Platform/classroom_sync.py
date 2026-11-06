"""Google Classroom read-only OAuth and assignment synchronization for Biosphere.

Each browser workspace has its own SQLite database; it is selected by the
existing request middleware. OAuth refresh tokens are Fernet-encrypted with a
server-only key. The integration is disabled unless credentials are configured.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request as URLRequest, urlopen

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

SCOPES = (
    'https://www.googleapis.com/auth/classroom.courses.readonly',
    'https://www.googleapis.com/auth/classroom.coursework.me.readonly',
)
OAUTH_AUTHORIZE = 'https://accounts.google.com/o/oauth2/v2/auth'
OAUTH_TOKEN = 'https://oauth2.googleapis.com/token'
CLASSROOM_API = 'https://classroom.googleapis.com/v1'
_SYNC_LOCK = threading.Lock()
MAX_COURSES = 80
MAX_COURSEWORK = 1500


def utcnow():
    return datetime.now(timezone.utc)


def config():
    """Never return credentials to the client."""
    client_id = os.environ.get('APBIO_GOOGLE_CLIENT_ID', '').strip()
    client_secret = os.environ.get('APBIO_GOOGLE_CLIENT_SECRET', '').strip()
    redirect = os.environ.get('APBIO_GOOGLE_REDIRECT_URI', '').strip()
    key = os.environ.get('APBIO_GOOGLE_TOKEN_KEY', '').strip()
    if not all((client_id, client_secret, redirect, key)):
        return None
    parsed = urlsplit(redirect)
    valid_redirect = (parsed.scheme == 'https' or (parsed.scheme == 'http' and parsed.hostname in ('localhost','127.0.0.1')))
    if not valid_redirect or parsed.path != '/api/classroom/callback' or parsed.query or parsed.fragment:
        return None
    try:
        fernet = Fernet(key.encode('ascii'))
    except (ValueError, TypeError, UnicodeError):
        return None
    return {'client_id': client_id, 'client_secret': client_secret, 'redirect_uri': redirect, 'fernet': fernet}


def prepare_schema(db):
    with db() as c:
        c.executescript('''
            CREATE TABLE IF NOT EXISTS classroom_auth (
                id TEXT PRIMARY KEY CHECK(id='google'), refresh_secret TEXT NOT NULL,
                connected_at TEXT NOT NULL, synced_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS classroom_oauth_pending (
                state_hash TEXT PRIMARY KEY, verifier TEXT NOT NULL, expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS classroom_assignments (
                course_id TEXT NOT NULL, coursework_id TEXT NOT NULL,
                course_name TEXT NOT NULL, title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                due_date TEXT NOT NULL DEFAULT '', due_time TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '', work_type TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(course_id, coursework_id)
            );
            CREATE INDEX IF NOT EXISTS classroom_due_dates ON classroom_assignments(due_date);
        ''')


def http_json(url, *, method='GET', fields=None, bearer=None):
    """Only call Google's fixed HTTPS API endpoints. Never fetch user URLs."""
    if not url.startswith(('https://classroom.googleapis.com/v1/', 'https://oauth2.googleapis.com/token')):
        raise ValueError('Untrusted Classroom API host.')
    headers = {'Accept': 'application/json', 'User-Agent': 'Biosphere-Classroom/1.0'}
    data = None
    if fields is not None:
        data = urlencode(fields).encode('utf-8')
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    if bearer:
        headers['Authorization'] = 'Bearer ' + bearer
    req = URLRequest(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=12) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise HTTPException(status_code=502, detail='Google Classroom response was too large.')
        return json.loads(raw)
    except HTTPError as exc:
        if exc.code in (400, 401):
            raise HTTPException(status_code=401, detail='Google Classroom authorization expired or was refused. Reconnect your school account.') from None
        if exc.code == 403:
            raise HTTPException(status_code=403, detail='Your school or Google account did not allow Classroom access. Ask your school administrator about third-party app access.') from None
        raise HTTPException(status_code=502, detail='Google Classroom could not return assignments right now.') from None
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise HTTPException(status_code=502, detail='Could not contact Google Classroom. Try again later.') from None


def oauth_url(cfg, state, verifier):
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).decode('ascii').rstrip('=')
    return OAUTH_AUTHORIZE + '?' + urlencode({
        'client_id': cfg['client_id'], 'redirect_uri': cfg['redirect_uri'],
        'response_type': 'code', 'scope': ' '.join(SCOPES),
        'access_type': 'offline', 'prompt': 'consent',
        'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
    })


def _date_and_time(work):
    raw = work.get('dueDate') or {}
    if not raw:
        return '', ''
    try:
        val = datetime(int(raw['year']), int(raw['month']), int(raw['day']))
    except (ValueError, KeyError, TypeError, OverflowError):
        return '', ''
    due = work.get('dueTime') or {}
    try:
        hh, mm = int(due.get('hours',0)), int(due.get('minutes',0))
        tm = f'{hh:02d}:{mm:02d}' if 0 <= hh <= 23 and 0 <= mm <= 59 and due else ''
    except (ValueError,TypeError):
        tm = ''
    return val.strftime('%Y-%m-%d'), tm


def _safe_classroom_link(raw):
    try:
        p = urlsplit(str(raw or ''))
        if p.scheme == 'https' and p.hostname == 'classroom.google.com' and not p.username and not p.password:
            return str(raw)[:1200]
    except ValueError:
        pass
    return ''


def fetch_all_assignments(access_token):
    """Complete fetch first; callers commit results only if no request failed."""
    courses = []
    page_token = ''
    while True:
        q = {'pageSize': 100, 'studentId': 'me'}
        if page_token: q['pageToken'] = page_token
        data = http_json(CLASSROOM_API + '/courses?' + urlencode(q), bearer=access_token)
        courses.extend(c for c in data.get('courses', []) if c.get('courseState') == 'ACTIVE')
        if len(courses) > MAX_COURSES:
            raise HTTPException(status_code=400, detail='Too many active courses for one import.')
        page_token = data.get('nextPageToken','')
        if not page_token: break

    saved = []
    stamp = utcnow().isoformat()
    for course in courses:
        course_id = str(course.get('id',''))
        if not course_id.isdecimal(): continue
        page_token = ''
        while True:
            q = {'pageSize': 100}
            if page_token: q['pageToken'] = page_token
            path = f'/courses/{course_id}/courseWork?{urlencode(q)}'
            data = http_json(CLASSROOM_API + path, bearer=access_token)
            for work in data.get('courseWork',[]):
                if work.get('state') != 'PUBLISHED': continue
                work_id = str(work.get('id',''))
                if not work_id: continue
                due_date, due_time = _date_and_time(work)
                saved.append((
                    course_id, work_id, str(course.get('name',''))[:180],
                    str(work.get('title',''))[:240], str(work.get('description',''))[:3000],
                    due_date, due_time, _safe_classroom_link(work.get('alternateLink')),
                    str(work.get('workType',''))[:40], stamp,
                ))
                if len(saved) > MAX_COURSEWORK:
                    raise HTTPException(status_code=400, detail='Too many Classroom assignments for one sync.')
            page_token = data.get('nextPageToken','')
            if not page_token: break
    return saved


def install(app, core):
    db, die, now = (core[k] for k in ('db','die','now'))
    prepare_schema(db)

    @app.get('/api/classroom/status')
    def get_status():
        cfg = config()
        if not cfg:
            return {'configured':False,'connected':False,'synced_at':'',
                    'message':'Google OAuth is not configured by the Biosphere site owner yet.'}
        with db() as c:
            auth = c.execute("SELECT * FROM classroom_auth WHERE id='google'").fetchone()
            count = c.execute('SELECT COUNT(*) FROM classroom_assignments').fetchone()[0]
        return {'configured':True, 'connected':bool(auth),
                'synced_at':auth['synced_at'] if auth else '', 'assignment_count':count}

    @app.get('/api/classroom/assignments')
    def get_assignments():
        with db() as c:
            rows = c.execute('''SELECT course_id,coursework_id,course_name,title,description,
                due_date,due_time,url,work_type FROM classroom_assignments
                ORDER BY (due_date='') ASC,due_date ASC,due_time ASC,course_name ASC''').fetchall()
        return {'assignments':[dict(row) for row in rows]}

    @app.get('/api/classroom/connect')
    def connect(request:Request):
        cfg=config()
        if not cfg: die('Google Classroom syncing needs Google OAuth setup by the site owner.',503)
        # Require the public origin to match the configured redirect endpoint.
        if str(request.base_url).rstrip('/') != cfg['redirect_uri'].rsplit('/api/classroom/callback',1)[0]:
            die('Google Classroom redirect configuration does not match this website.',400)
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        expires = (utcnow()+timedelta(minutes=10)).isoformat()
        with db() as c:
            c.execute('DELETE FROM classroom_oauth_pending WHERE expires_at < ?', (utcnow().isoformat(),))
            c.execute('INSERT INTO classroom_oauth_pending VALUES (?,?,?)',
                      (hashlib.sha256(state.encode('ascii')).hexdigest(),verifier,expires))
        result = RedirectResponse(oauth_url(cfg,state,verifier),status_code=303)
        result.headers['Cache-Control']='no-store'
        result.headers['Referrer-Policy']='no-referrer'
        return result

    @app.get('/api/classroom/callback')
    def callback(request:Request, code:str='', state:str='', error:str=''):
        cfg=config()
        if not cfg: die('Classroom syncing is not configured.',503)
        if error:
            return RedirectResponse('/?classroom=denied',status_code=303)
        if len(state)>200 or len(code)>2000 or not state or not code:
            die('Missing Google authorization response.',400)
        key=hashlib.sha256(state.encode('utf-8')).hexdigest()
        with db() as c:
            auth=c.execute('SELECT verifier,expires_at FROM classroom_oauth_pending WHERE state_hash=?',(key,)).fetchone()
            c.execute('DELETE FROM classroom_oauth_pending WHERE state_hash=?',(key,))
        if not auth or auth['expires_at']<utcnow().isoformat():
            die('Google authorization request expired or does not match this browser.',400)
        data=http_json(OAUTH_TOKEN,method='POST',fields={
            'code':code, 'client_id':cfg['client_id'], 'client_secret':cfg['client_secret'],
            'redirect_uri':cfg['redirect_uri'],'grant_type':'authorization_code',
            'code_verifier':auth['verifier'],
        })
        refresh=data.get('refresh_token','')
        if not refresh:
            die('Google did not provide continued access. Disconnect and try connecting again.',400)
        encrypted=cfg['fernet'].encrypt(refresh.encode('utf-8')).decode('ascii')
        with db() as c:
            c.execute("""INSERT INTO classroom_auth (id,refresh_secret,connected_at,synced_at)
                VALUES ('google',?,?, '') ON CONFLICT(id) DO UPDATE SET
                refresh_secret=excluded.refresh_secret,connected_at=excluded.connected_at,synced_at=''""",
                (encrypted,now()))
        return RedirectResponse('/?classroom=connected',status_code=303)

    @app.post('/api/classroom/sync')
    def sync():
        cfg=config()
        if not cfg: die('Classroom OAuth is not configured.',503)
        with _SYNC_LOCK:
            with db() as c:
                auth=c.execute("SELECT refresh_secret FROM classroom_auth WHERE id='google'").fetchone()
            if not auth: die('Connect Google Classroom first.',400)
            try:
                refresh=cfg['fernet'].decrypt(auth['refresh_secret'].encode('ascii')).decode('utf-8')
            except (InvalidToken,ValueError,UnicodeError):
                die('Stored Google authorization could not be read. Reconnect Classroom.',401)
            token=http_json(OAUTH_TOKEN,method='POST',fields={
                'client_id':cfg['client_id'],'client_secret':cfg['client_secret'],
                'grant_type':'refresh_token','refresh_token':refresh})
            access=token.get('access_token','')
            if not access: die('Google did not return an access token.',502)
            assignments=fetch_all_assignments(access)
            # The list is committed atomically, leaving existing data unchanged
            # if Google rate-limits or refuses any part of the fetch.
            with db() as c:
                c.execute('DELETE FROM classroom_assignments')
                c.executemany('''INSERT INTO classroom_assignments
                (course_id,coursework_id,course_name,title,description,due_date,due_time,url,work_type,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',assignments)
                c.execute("UPDATE classroom_auth SET synced_at=? WHERE id='google'",(now(),))
            return {'ok':True,'count':len(assignments),'message':'Google Classroom assignments synced.'}

    @app.post('/api/classroom/disconnect')
    def disconnect():
        with db() as c:
            c.execute('DELETE FROM classroom_auth')
            c.execute('DELETE FROM classroom_oauth_pending')
            c.execute('DELETE FROM classroom_assignments')
        return {'ok':True}
