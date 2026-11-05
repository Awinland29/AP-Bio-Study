"""AP Biology Study Platform: a local-first, source-grounded FastAPI application."""
from __future__ import annotations

import io
import base64
import binascii
import json
import os
import random
import re
import secrets
import shutil
import sqlite3
import tempfile
import textwrap
import threading
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('APBIO_DATA_DIR', ROOT / 'data')).resolve()
UPLOADS = DATA / 'uploads'
DATA.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)
DB = DATA / 'study.sqlite3'
RESTORE_LOCK = threading.Lock()
AI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4.1-mini')
PUBLIC_MODE = os.environ.get('APBIO_PUBLIC', '').lower() in {'1', 'true', 'yes'}
ADMIN_USERNAME = os.environ.get('APBIO_ADMIN_USERNAME', 'student')
ADMIN_PASSWORD = os.environ.get('APBIO_ADMIN_PASSWORD', '')
if PUBLIC_MODE and (len(ADMIN_PASSWORD) < 16 or not ADMIN_USERNAME.strip()):
    raise RuntimeError('Public hosting requires APBIO_ADMIN_USERNAME and an APBIO_ADMIN_PASSWORD of at least 16 characters.')
if PUBLIC_MODE and 'APBIO_DATA_DIR' not in os.environ:
    raise RuntimeError('Public hosting requires a persistent APBIO_DATA_DIR, e.g. /var/data on Render.')
ALLOWED = {'.pdf', '.pptx', '.docx', '.txt', '.md', '.csv', '.json', '.png', '.jpg', '.jpeg', '.webp'}
MAX_UPLOAD = 20 * 1024 * 1024
STOPWORDS = set('the an a and or of by in on at is are for with from to as be was were it this that which into onto through can will do does been have has had their there these those what when where who why how you your we our'.split())


def now():
    return datetime.now(timezone.utc).isoformat()


def dt(s):
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def rid():
    return uuid.uuid4().hex[:16]


def db():
    c = sqlite3.connect(DB, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c


def init():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS units (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT DEFAULT '',
          status TEXT NOT NULL DEFAULT 'current', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS materials (
          id TEXT PRIMARY KEY, unit_id TEXT, topic TEXT DEFAULT '', lesson TEXT DEFAULT '',
          filename TEXT NOT NULL, store_name TEXT NOT NULL, text TEXT NOT NULL DEFAULT '',
          extraction_status TEXT DEFAULT 'ready', size_bytes INTEGER DEFAULT 0,
          created_at TEXT NOT NULL,
          FOREIGN KEY(unit_id) REFERENCES units(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS cards (
          id TEXT PRIMARY KEY, unit_id TEXT, material_id TEXT, topic TEXT DEFAULT '',
          front TEXT NOT NULL, back TEXT NOT NULL, source_excerpt TEXT DEFAULT '',
          created_at TEXT NOT NULL, due_at TEXT NOT NULL, reps INTEGER DEFAULT 0,
          interval_days INTEGER DEFAULT 0, ease REAL DEFAULT 2.5,
          lapses INTEGER DEFAULT 0, bookmarked INTEGER DEFAULT 0,
          FOREIGN KEY(unit_id) REFERENCES units(id) ON DELETE SET NULL,
          FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS quizzes (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, mode TEXT DEFAULT 'quiz',
          unit_id TEXT, question_json TEXT NOT NULL, responses_json TEXT DEFAULT '{}',
          report_json TEXT DEFAULT 'null', status TEXT DEFAULT 'active',
          minutes INTEGER DEFAULT 0, created_at TEXT NOT NULL, submitted_at TEXT,
          FOREIGN KEY(unit_id) REFERENCES units(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS guides (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, unit_id TEXT,
          mode TEXT NOT NULL, generator TEXT NOT NULL,
          markdown TEXT NOT NULL, source_ids TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL,
          FOREIGN KEY(unit_id) REFERENCES units(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, due_date TEXT DEFAULT '',
          unit_id TEXT, done INTEGER DEFAULT 0, created_at TEXT NOT NULL,
          FOREIGN KEY(unit_id) REFERENCES units(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS chat (
          id TEXT PRIMARY KEY, mode TEXT NOT NULL, role TEXT NOT NULL,
          content TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS issues (
          id TEXT PRIMARY KEY, quiz_id TEXT NOT NULL, question_id TEXT NOT NULL,
          details TEXT DEFAULT '', created_at TEXT NOT NULL, resolved INTEGER DEFAULT 0,
          FOREIGN KEY(quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS reviews (
          id TEXT PRIMARY KEY, card_id TEXT, rating TEXT NOT NULL,
          reviewed_at TEXT NOT NULL, FOREIGN KEY(card_id) REFERENCES cards(id) ON DELETE SET NULL
        );
        ''')

    from study_extras import prepare_schema
    prepare_schema(db)
    from schedule_extras import prepare_schema as prepare_schedule_schema
    prepare_schedule_schema(db)

init()
app = FastAPI(title='AP Biology Study Studio', version='1.0.0')


@app.middleware('http')
async def private_study_access(request: Request, call_next):
    """Password-gate all personal data when the app is deployed publicly.

    No secrets are sent to client JavaScript. The hosting platform must provide
    HTTPS; browser Basic authentication is never intended for plain HTTP.
    """
    if PUBLIC_MODE:
        if request.url.path != '/healthz':
            encoded = request.headers.get('authorization', '')
            valid = False
            if encoded.lower().startswith('basic '):
                try:
                    decoded = base64.b64decode(encoded.split(' ', 1)[1], validate=True).decode('utf-8')
                    username, password = decoded.split(':', 1)
                    valid = (secrets.compare_digest(username, ADMIN_USERNAME)
                             and secrets.compare_digest(password, ADMIN_PASSWORD))
                except (ValueError, UnicodeError, binascii.Error):
                    pass
            if not valid:
                return Response('Authentication required.', status_code=401,
                    headers={'WWW-Authenticate':'Basic realm="AP Biology Study Studio", charset="UTF-8"',
                             'Cache-Control':'no-store'})

            # Prevent another website from making an authenticated browser submit
            # a form or XMLHttpRequest that changes personal study data.
            if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                origin = request.headers.get('origin')
                host = request.headers.get('host', '')
                if request.headers.get('sec-fetch-site') == 'cross-site':
                    return Response('Cross-site changes are blocked.', status_code=403)
                if origin:
                    from urllib.parse import urlsplit
                    parsed = urlsplit(origin)
                    if parsed.scheme not in {'http', 'https'} or parsed.netloc.lower() != host.lower():
                        return Response('Cross-site changes are blocked.', status_code=403)
    response = await call_next(request)
    if PUBLIC_MODE:
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
    return response


@app.get('/healthz')
def hosting_health():
    return {'ok': True}


def items(query, args=()):
    with db() as c:
        return [dict(r) for r in c.execute(query, args).fetchall()]


def item(query, args=()):
    with db() as c:
        r = c.execute(query, args).fetchone()
        return dict(r) if r else None


def die(message, code=400):
    raise HTTPException(status_code=code, detail=message)


def valid_unit(unit_id):
    if unit_id and not item('SELECT id FROM units WHERE id=?', (unit_id,)):
        die('The selected unit does not exist.', 404)


def clean(s: str):
    return re.sub(r'\s+', ' ', (s or '')).strip()


def normalize(s):
    return re.sub(r'[^a-z0-9]+', '', str(s or '').lower())


def extract_file(filename: str, data: bytes):
    """Returns (extracted text, processing status), preserving the original upload."""
    ext = Path(filename).suffix.lower()
    try:
        if ext == '.pdf':
            import fitz
            doc = fitz.open(stream=data, filetype='pdf')
            txt = '\n'.join(page.get_text(sort=True) for page in doc)
            if not clean(txt):
                return '', 'No selectable text found. Scanned PDF OCR is not supported in this build.'
            return txt[:900_000], 'ready'
        if ext == '.docx':
            from docx import Document
            d = Document(io.BytesIO(data))
            lines = [p.text for p in d.paragraphs]
            for table in d.tables:
                for row in table.rows:
                    lines.append(' | '.join(cell.text for cell in row.cells))
            return '\n'.join(lines)[:900_000], 'ready'
        if ext == '.pptx':
            from pptx import Presentation
            d = Presentation(io.BytesIO(data))
            lines = []
            for i, slide in enumerate(d.slides):
                lines.append(f'Slide {i+1}')
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        lines.extend(p.text for p in shape.text_frame.paragraphs)
                    if shape.has_table:
                        for row in shape.table.rows:
                            lines.append(' | '.join(cell.text for cell in row.cells))
            return '\n'.join(lines)[:900_000], 'ready'
        if ext in ('.txt', '.md', '.csv', '.json'):
            return data.decode('utf-8-sig', errors='replace')[:900_000], 'ready'
        if ext in ('.png', '.jpg', '.jpeg', '.webp'):
            try:
                import pytesseract
                from PIL import Image, ImageOps
                im = Image.open(io.BytesIO(data))
                im = ImageOps.exif_transpose(im)
                result = pytesseract.image_to_string(im)
                if clean(result):
                    return result[:900_000], 'ready (OCR; verify against image)'
                return '', 'Image saved, but no readable text was detected by OCR.'
            except Exception:
                return '', 'Image saved. OCR unavailable on this computer.'
    except Exception as exc:
        return '', f'File saved, but text extraction failed: {str(exc)[:180]}'
    return '', 'Unsupported format'


def source_rows(unit_id=None, material_ids=None):
    if material_ids is not None:
        if not material_ids:
            return []
        placeholders = ','.join('?' for _ in material_ids)
        # Preserve the unit constraint even if the client supplies file IDs;
        # otherwise an apparently unit-specific guide or quiz can mix units.
        query='SELECT * FROM materials WHERE id IN (' + placeholders + ')'
        args=list(material_ids)
        if unit_id:
            query+=' AND unit_id=?'
            args.append(unit_id)
        return items(query, tuple(args))
    if unit_id:
        return items("SELECT * FROM materials WHERE unit_id=? AND kind IN ('notes','reference')", (unit_id,))
    return items("SELECT * FROM materials WHERE kind IN ('notes','reference')")


def candidates(rows, max_count=140):
    """Conservative, extractive prompt/answer candidates—no invented biological facts."""
    output, seen = [], set()
    patterns = [
        re.compile(r'^\s*(.{3,84}?)\s*(?::|\s[–—]\s|\s+-\s+)\s*(.{12,500})\s*$'),
        re.compile(r'^\s*([A-Z][^.!?]{2,70}?)\s+(?:is|are|means|refers to)\s+(.{15,450})$', re.I),
    ]
    for m in rows:
        raw_lines = m['text'].splitlines()
        lines = [clean(x).lstrip('•*-0123456789. )') for x in raw_lines]
        for line in lines:
            if len(line) < 26 or len(line) > 570:
                continue
            if line.lower().startswith(('http:', 'https:', 'slide ', 'page ', 'table of contents')):
                continue
            term, definition = None, None
            for pattern in patterns:
                match = pattern.match(line)
                if match:
                    term, definition = [clean(x) for x in match.groups()]
                    break
            if not term:
                continue
            term = term.strip('". -')
            definition = definition.strip('"- ')
            if not (3 <= len(term) <= 85 and 12 <= len(definition) <= 450):
                continue
            if term.lower() in STOPWORDS or len(term.split()) > 11:
                continue
            if normalize(term) in seen:
                continue
            seen.add(normalize(term))
            output.append({'term':term,'definition':definition,'material_id':m['id'],
                           'unit_id':m['unit_id'],'topic':m['topic'] or term,
                           'source_name':m['filename'], 'excerpt':line[:600]})
            if len(output) >= max_count:
                return output
    return output


def source_sentences(rows, max_count=80):
    """Create a cloze candidate using an actual non-definition source sentence.

    Deliberately exclude term: definition lines to avoid mangling otherwise good
    flashcards into bizarre clozes. Students can inspect all generated content.
    """
    output=[]
    seen=set()
    definition_rx=re.compile(r'^.{3,85}?\s*(?::|[–—]| - )\s*.{12,}$')
    for material in rows:
        for line in material['text'].splitlines():
            for sentence in re.split(r'(?<=[.!?])\s+', clean(line)):
                sentence=clean(sentence)
                if not (55 <= len(sentence) <= 280 and len(sentence.split()) >= 9):
                    continue
                if definition_rx.match(sentence) or sentence.startswith(('#','http','www.')):
                    continue
                if normalize(sentence) in seen:
                    continue
                words=re.findall(r"\b[A-Za-z]{7,}\b",sentence)
                words=[word for word in words if word.lower() not in STOPWORDS]
                if not words:continue
                # Longest word is a deterministic cloze, not a fabricated answer.
                keyword=max(words,key=len)
                seen.add(normalize(sentence))
                output.append({'term':keyword,'definition':sentence,'material_id':material['id'],
                               'unit_id':material['unit_id'],'topic':material['topic'] or material['filename'],
                               'source_name':material['filename'],'excerpt':sentence,'cloze':True})
                if len(output)>=max_count:return output
    return output


def material_selection(payload):
    mids = payload.get('material_ids')
    if mids is not None and not isinstance(mids, list):die('material_ids must be a list.')
    return source_rows(payload.get('unit_id'), mids)


def public_quiz(q):
    safe=[]
    for question in json.loads(q['question_json']):
        d={k:v for k,v in question.items() if k not in ('answer','explanation')}
        safe.append(d)
    return {'id':q['id'],'title':q['title'],'mode':q['mode'],'status':q['status'],
            'minutes':q['minutes'],'created_at':q['created_at'],'questions':safe,
            'responses':json.loads(q['responses_json'] or '{}') if q['status']=='submitted' else {},
            'report':json.loads(q['report_json'] or 'null') if q['status']=='submitted' else None}


def qbank(cards, mode, requested, count, target_topics=None):
    """Generate valid, source-linked practice items from saved evidence.

    AI-free questions intentionally emphasize identification, matching and recall;
    application questions require the optional AI generator.
    """
    if not cards:die('Add materials with extractable facts or create flashcards first.')
    target_topics={clean(t).lower() for t in (target_topics or [])}
    # Prioritize repeatedly missed topics without claiming a single correct answer
    # proves mastery. Mix priority cards and other topics, to avoid tunnel vision.
    random.shuffle(cards)
    priority=[c for c in cards if clean(c.get('topic','')).lower() in target_topics]
    rest=[c for c in cards if c not in priority]
    cards=(priority+rest) if priority else cards
    normal=[c for c in cards if not c['front'].startswith('Complete this source sentence: ')]
    defs=list({c['back'] for c in normal})
    questions=[]
    for idx in range(min(count,len(cards))):
        c=cards[idx];term,definition=c['front'],c['back']
        cloze=term.startswith('Complete this source sentence: ')
        typ='fill' if cloze else requested[idx % len(requested)]
        alternatives=[x for x in defs if normalize(x)!=normalize(definition)]
        if typ == 'mcq' and len(alternatives)<2:typ='fill'
        if typ in ('tf','multi') and len(alternatives)<(1 if typ=='tf' else 2):typ='fill'
        if typ=='matching' and len(normal)<3:typ='fill'
        q={'id':rid(),'type':typ,'topic':c.get('topic','') or (term if not cloze else 'Source comprehension'),
           'unit_id':c.get('unit_id'),'material_id':c.get('material_id'),
           'source_name':c.get('source_name') or 'Your saved flashcards',
           'explanation':f'Source-supported answer: {term} — {definition}'}
        if cloze:
            q.update(type='fill',prompt='Complete this sentence from your source:',
                     statement=term.removeprefix('Complete this source sentence: '),answer=definition)
        elif typ=='mcq':
            options=random.sample(alternatives,min(3,len(alternatives)))+[definition]
            random.shuffle(options)
            q.update(prompt=f'Which description matches “{term}” in your materials?',options=options,
                     answer=options.index(definition))
        elif typ=='tf':
            truth=bool(random.getrandbits(1))
            shown=definition if truth else random.choice(alternatives)
            q.update(prompt=f'In your materials, is this the description of “{term}”?',
                     statement=shown,options=['True','False'],answer='True' if truth else 'False')
        elif typ=='multi':
            # Choose a second genuinely correct term, then distinct distractors.
            other=[x for x in normal if x['front']!=term and x['back']!=definition]
            if not other:
                q.update(type='fill',prompt='Enter the term described by this excerpt:',statement=definition,answer=term)
            else:
                pair=random.choice(other)
                wrong=[d for d in defs if d not in (definition,pair['back'])]
                if len(wrong)<1:
                    q.update(type='fill',prompt='Enter the term described by this excerpt:',statement=definition,answer=term)
                else:
                    options=[definition,pair['back']]+random.sample(wrong,min(2,len(wrong)))
                    random.shuffle(options)
                    q.update(prompt=f'Select ALL descriptions that correspond to “{term}” or “{pair["front"]}”.',
                             options=options,answer=sorted([options.index(definition),options.index(pair['back'])]),
                             explanation=f'{term}: {definition}\n{pair["front"]}: {pair["back"]}')
        elif typ=='matching':
            eligible=[x for x in normal if x['front']!=term and x['back']!=definition]
            choices=random.sample(eligible,min(3,len(eligible)))+[c]
            # Enforce one-to-one matching, otherwise fall back to definition recall.
            if len({normalize(x['front']) for x in choices})!=len(choices) or len({normalize(x['back']) for x in choices})!=len(choices):
                q.update(type='fill',prompt='Enter the term described by this excerpt:',statement=definition,answer=term)
            else:
                left=[x['front'] for x in choices];right=[x['back'] for x in choices]
                random.shuffle(left);random.shuffle(right)
                q.update(prompt='Match each term with its source description.',terms=left,options=right,
                         answer={t:next(x['back'] for x in choices if x['front']==t) for t in left})
        elif typ=='short':
            q.update(prompt=f'Explain “{term}” using your class materials.',answer=definition,
                     rubric=f'Compare your explanation with the exact source wording of {term}.')
        else:
            q.update(type='fill',prompt='Enter the term described by this source excerpt:',
                     statement=definition,answer=term)
        questions.append(q)
    return questions


@app.get('/api/health')
def health():
    return {'ok':True,'ai_enabled':bool(os.environ.get('OPENAI_API_KEY')),'model':AI_MODEL}


@app.get('/api/bootstrap')
def bootstrap():
    units=items('SELECT * FROM units ORDER BY CASE status WHEN "current" THEN 0 ELSE 1 END,created_at DESC')
    materials=items('SELECT id,unit_id,topic,lesson,filename,extraction_status,size_bytes,created_at,length(text) AS text_chars FROM materials ORDER BY created_at DESC')
    cards=items('SELECT * FROM cards ORDER BY created_at DESC')
    attempts=items('SELECT id,title,mode,status,report_json,created_at,submitted_at,unit_id FROM quizzes ORDER BY created_at DESC LIMIT 60')
    for a in attempts:
        a['report']=json.loads(a.pop('report_json') or 'null')
    tasks=items('SELECT * FROM tasks ORDER BY done,due_date,created_at DESC')
    guides=items('SELECT id,title,unit_id,mode,generator,created_at FROM guides ORDER BY created_at DESC LIMIT 100')
    now_str=now()
    due=sum(c['due_at']<=now_str for c in cards)
    reviewed=sum(c['reps']>0 for c in cards)
    # A count of button clicks is NOT evidence of mastery. Require three
    # successful recent reviews on at least two separate dates.
    recent=items('SELECT card_id,rating,reviewed_at FROM reviews ORDER BY reviewed_at DESC')
    by_card={}
    for r in recent:
        if r['card_id'] and len(by_card.get(r['card_id'],[]))<3:
            by_card.setdefault(r['card_id'],[]).append(r)
    mastered=sum(len(by_card.get(c['id'],[]))==3
                 and all(r['rating'] in ('good','easy') for r in by_card[c['id']])
                 and len({r['reviewed_at'][:10] for r in by_card[c['id']]})>=2
                 for c in cards)
    completed=[a for a in attempts if a['status']=='submitted' and a.get('report')]
    scores=[a['report']['percent'] for a in completed if a['report'].get('percent') is not None]
    # /tmp is ephemeral on common free hosts (including Render free). This is
    # informational, never a promise that a given provider will retain data.
    durability=('temporary' if PUBLIC_MODE and (str(DATA).startswith('/tmp/') or DATA == Path('/tmp'))
                else 'unverified' if PUBLIC_MODE else 'local')
    return {'units':units,'materials':materials,'cards':cards,'attempts':attempts,'tasks':tasks,'guides':guides,
            'stats':{'materials':len(materials),'cards':len(cards),'due':due,'reviewed':reviewed,
                     'mastered':mastered,'completed':len(completed),'average':round(sum(scores)/len(scores)) if scores else None},
            'ai_enabled':bool(os.environ.get('OPENAI_API_KEY')), 'public_mode':PUBLIC_MODE,
            'data_durability':durability}


@app.post('/api/units')
async def add_unit(body:dict):
    name=clean(body.get('name',''))
    if not name:die('Unit name is required.')
    id=rid();status=body.get('status','current')
    if status not in ('current','completed'):die('Invalid unit status.')
    with db() as c:c.execute('INSERT INTO units VALUES (?,?,?,?,?)',(id,name,clean(body.get('description','')),status,now()))
    return {'id':id}


@app.patch('/api/units/{unit_id}')
async def edit_unit(unit_id:str, body:dict):
    valid_unit(unit_id)
    old=item('SELECT * FROM units WHERE id=?',(unit_id,))
    name=clean(body.get('name',old['name']))
    status=body.get('status',old['status'])
    if not name or status not in ('current','completed'):die('Invalid unit name or status.')
    with db() as c:c.execute('UPDATE units SET name=?,description=?,status=? WHERE id=?',
                            (name,clean(body.get('description',old['description'])),status,unit_id))
    return {'ok':True}


@app.delete('/api/units/{unit_id}')
async def delete_unit(unit_id:str):
    valid_unit(unit_id)
    with db() as c:c.execute('DELETE FROM units WHERE id=?',(unit_id,))
    return {'ok':True,'note':'Associated materials and cards remain, but are unassigned.'}


@app.post('/api/materials/upload')
async def upload_material(files:list[UploadFile]=File(...),unit_id:str=Form(''),topic:str=Form(''),lesson:str=Form('')):
    valid_unit(unit_id)
    results=[]
    for file in files:
        name=Path(file.filename or '').name
        ext=Path(name).suffix.lower()
        if ext not in ALLOWED:
            results.append({'filename':name,'error':'File type not supported'});continue
        content=await file.read(MAX_UPLOAD+1)
        if len(content)>MAX_UPLOAD:
            results.append({'filename':name,'error':'File exceeds 20 MB limit'});continue
        if not content:
            results.append({'filename':name,'error':'File is empty'});continue
        fid=rid(); store=fid+ext
        (UPLOADS/store).write_bytes(content)
        txt,status=extract_file(name,content)
        with db() as c:
            c.execute('INSERT INTO materials(id,unit_id,topic,lesson,filename,store_name,text,extraction_status,size_bytes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                      (fid,unit_id or None,clean(topic)[:150],clean(lesson)[:150],name,store,txt,status,len(content),now()))
        results.append({'id':fid,'filename':name,'extraction_status':status,'text_chars':len(txt)})
    return {'results':results}


@app.patch('/api/materials/{id}')
def update_material(id:str,body:dict):
    old=item('SELECT * FROM materials WHERE id=?',(id,))
    if not old:die('Material not found.',404)
    new_unit=body.get('unit_id',old['unit_id']) or None
    valid_unit(new_unit)
    topic=clean(body.get('topic',old['topic']))[:150]
    lesson=clean(body.get('lesson',old['lesson']))[:150]
    with db() as c:
        c.execute('UPDATE materials SET unit_id=?,topic=?,lesson=? WHERE id=?',
                  (new_unit,topic,lesson,id))
    return {'ok':True}


@app.get('/api/materials/{id}/file')
def download_material(id:str):
    m=item('SELECT * FROM materials WHERE id=?',(id,))
    if not m:die('Material not found.',404)
    file=(UPLOADS/m['store_name']).resolve()
    if not file.is_relative_to(UPLOADS) or not file.exists():die('Stored file is missing.',404)
    return FileResponse(file,filename=m['filename'])


@app.get('/api/materials/{id}/text')
def material_text(id:str):
    m=item('SELECT * FROM materials WHERE id=?',(id,))
    if not m:die('Material not found.',404)
    return {'id':m['id'],'filename':m['filename'],'text':m['text'],'extraction_status':m['extraction_status']}


@app.delete('/api/materials/{id}')
def delete_material(id:str):
    m=item('SELECT * FROM materials WHERE id=?',(id,))
    if not m:die('Material not found.',404)
    with db() as c:c.execute('DELETE FROM materials WHERE id=?',(id,))
    (UPLOADS/m['store_name']).unlink(missing_ok=True)
    return {'ok':True}


@app.get('/api/search')
def search(q:str=''):
    q=clean(q)
    if len(q)<2:return {'results':[]}
    found=[]
    for row in items('SELECT id,filename,unit_id,topic,text FROM materials'):
        i=row['text'].lower().find(q.lower())
        if i>=0 or q.lower() in row['filename'].lower():
            found.append({'kind':'material','id':row['id'],'title':row['filename'],
                          'subtitle':row['topic'],'excerpt':clean(row['text'][max(0,i-90):i+200]) if i>=0 else ''})
    for row in items('SELECT id,front,back,topic FROM cards'):
        if q.lower() in (row['front']+' '+row['back']).lower():
            found.append({'kind':'card','id':row['id'],'title':row['front'],
                          'subtitle':row['topic'],'excerpt':row['back'][:180]})
    return {'results':found[:80]}


@app.post('/api/cards/generate')
def generate_cards(body:dict):
    rows=material_selection(body)
    if not rows:die('Upload or select materials before generating cards.')
    count=max(1,min(80,int(body.get('count',20))))
    cand=candidates(rows,max_count=count)
    if len(cand)<count:
        cand+=source_sentences(rows,max_count=count-len(cand))
    if not cand:die('The selected files contain no usable text. Try a text-based PDF, notes, DOCX or PPTX.')
    created=[]
    existing={normalize(x['front']+'|'+x['back']) for x in items('SELECT front,back FROM cards')}
    with db() as c:
        for x in cand:
            front=('Complete this source sentence: '+x['definition'].replace(x['term'],'____',1)) if x.get('cloze') else x['term']
            back=x['term'] if x.get('cloze') else x['definition']
            if normalize(front+'|'+back) in existing:continue
            id=rid()
            c.execute('INSERT INTO cards(id,unit_id,material_id,topic,front,back,source_excerpt,created_at,due_at) VALUES (?,?,?,?,?,?,?,?,?)',
                      (id,x['unit_id'],x['material_id'],x['topic'],front,back,x['excerpt'],now(),now()))
            created.append(id)
    return {'created':len(created),'ids':created,'note':'Cards use extracted source text; inspect generated wording before relying on it.'}


@app.post('/api/cards')
def add_card(body:dict):
    front=clean(body.get('front',''));back=clean(body.get('back',''))
    if not front or not back:die('Both sides are required.')
    unit_id=body.get('unit_id') or None;valid_unit(unit_id)
    material_id=body.get('material_id') or None
    if material_id and not item('SELECT id FROM materials WHERE id=?',(material_id,)):die('Material not found.',404)
    id=rid()
    with db() as c:
        c.execute('INSERT INTO cards(id,unit_id,material_id,topic,front,back,source_excerpt,created_at,due_at) VALUES (?,?,?,?,?,?,?,?,?)',
                  (id,unit_id,material_id,clean(body.get('topic','')),front,back,clean(body.get('source_excerpt','')),now(),now()))
    return {'id':id}


@app.patch('/api/cards/{id}')
def edit_card(id:str, body:dict):
    old=item('SELECT * FROM cards WHERE id=?',(id,))
    if not old:die('Card not found.',404)
    front=clean(body.get('front',old['front']));back=clean(body.get('back',old['back']))
    if not front or not back:die('Both sides are required.')
    with db() as c:c.execute('UPDATE cards SET front=?,back=?,bookmarked=?,topic=? WHERE id=?',
                            (front,back,int(bool(body.get('bookmarked',old['bookmarked']))),clean(body.get('topic',old['topic'])),id))
    return {'ok':True}


@app.delete('/api/cards/{id}')
def delete_card(id:str):
    with db() as c:
        count=c.execute('DELETE FROM cards WHERE id=?',(id,)).rowcount
    if not count:die('Card not found.',404)
    return {'ok':True}


@app.post('/api/cards/{id}/review')
def review_card(id:str, body:dict):
    c=item('SELECT * FROM cards WHERE id=?',(id,))
    if not c:die('Card not found.',404)
    rating=body.get('rating')
    if rating not in ('again','hard','good','easy'):die('Choose again, hard, good, or easy.')
    reps=c['reps']+1
    ease=float(c['ease']); interval=c['interval_days']; lapses=c['lapses']
    if rating=='again':interval=0; ease=max(1.3,ease-0.2);lapses+=1; due=datetime.now(timezone.utc)+timedelta(minutes=10)
    elif rating=='hard':interval=1 if interval<1 else max(1,round(interval*1.2));ease=max(1.3,ease-0.12);due=datetime.now(timezone.utc)+timedelta(days=interval)
    elif rating=='good':interval=1 if interval<1 else max(interval+1,round(interval*ease));due=datetime.now(timezone.utc)+timedelta(days=interval)
    else:interval=3 if interval<1 else max(interval+1,round(interval*ease*1.35));ease=min(3.2,ease+0.15);due=datetime.now(timezone.utc)+timedelta(days=interval)
    with db() as con:
        con.execute('UPDATE cards SET reps=?,interval_days=?,ease=?,lapses=?,due_at=? WHERE id=?',
                    (reps,interval,ease,lapses,due.isoformat(),id))
        con.execute('INSERT INTO reviews VALUES (?,?,?,?)',(rid(),id,rating,now()))
    return {'ok':True,'due_at':due.isoformat(),'interval_days':interval}


def make_ai_questions(body,rows):
    """Optional, teacher-source-led AI generator with schema checks, not fake AI."""
    source_blocks='\n\n'.join(f'[SOURCE: {r["filename"]}]\n{r["text"][:5500]}' for r in rows if r['text'])[:22000]
    if not source_blocks:die('The selected materials contain no readable text.')
    count=max(1,min(30,int(body.get('count',10))))
    accepted=[x for x in (body.get('types') or ['mcq','fill','short','tf','multi'])
              if x in ('mcq','tf','fill','short','multi')]
    if not accepted:die('Select a supported AI question type.')
    difficulty=body.get('difficulty','standard')
    if difficulty not in ('basic','standard','challenge'):difficulty='standard'
    emphasis=body.get('emphasis','mixed')
    if emphasis not in ('knowledge','understanding','application','mixed'):emphasis='mixed'
    prompt=('Make a rigorous and accurate AP Biology practice assessment grounded ONLY in supplied sources. '
            f'Write up to {count} non-duplicated {difficulty} level questions, with {emphasis} emphasis, '
            f'using only these types: {", ".join(accepted)}. '
            'Favor biological reasoning, scientific data analysis where the source provides data, experimental design, '
            'and application when supported. No fabricated figures, results or unsupported source claims. '
            'Output ONLY JSON with a "questions" array. Every object requires '
            '"type", "prompt", "answer", "explanation", "source_name", "topic". '
            'For mcq: options (array 4 distinct strings), answer integer zero-based. '
            'For multi: options (4 distinct strings), answer array of 2 or more distinct integer indices. '
            'For tf: statement string, answer "True" or "False". '
            'For fill: statement string, answer a short term. '
            'For short: answer is a model answer and provide a rubric string; do not grade automatically. '
            'source_name MUST be the exact name of one of the provided files. '
            'Return fewer questions if the source is not sufficient.')
    raw=ai_completion(prompt,'SOURCES:\n'+source_blocks)
    try:
        parsed=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',raw.strip()))['questions']
        if not isinstance(parsed,list):raise ValueError()
    except (ValueError,KeyError,TypeError):die('AI returned invalid question data. No assessment was saved.',502)
    sources={x['filename']:x for x in rows if x['text']}
    valid=[]
    for x in parsed[:count]:
        if not isinstance(x,dict):continue
        typ=x.get('type');src=x.get('source_name')
        if typ not in accepted or src not in sources:continue
        prompt=clean(x.get('prompt',''))[:1000];expl=clean(x.get('explanation',''))[:1800]
        topic=clean(x.get('topic',''))[:120]
        answer=x.get('answer');options=x.get('options')
        if not prompt or not expl or not topic:continue
        if typ in ('mcq','multi'):
            if not isinstance(options,list) or len(options)<3 or len(options)>6 or not all(isinstance(z,str) and clean(z) for z in options):continue
            if len({normalize(z) for z in options})!=len(options):continue
            if typ=='mcq' and (type(answer)!=int or answer not in range(len(options))):continue
            if typ=='multi' and (not isinstance(answer,list) or len(answer)<2 or any(type(a)!=int or a not in range(len(options)) for a in answer) or len(set(answer))!=len(answer)):continue
        elif typ=='tf':
            if answer not in ('True','False') or not clean(x.get('statement','')):continue
        elif typ=='fill':
            if not isinstance(answer,str) or not clean(answer) or not clean(x.get('statement','')):continue
        else:
            if not isinstance(answer,str) or not clean(answer):continue
        row=sources[src]
        q={'id':rid(),'type':typ,'prompt':prompt,'topic':topic,'answer':answer,
           'explanation':expl,'source_name':src,'unit_id':row['unit_id'],'material_id':row['id']}
        if typ in ('mcq','multi'):q['options']=[clean(z)[:450] for z in options]
        if typ=='tf':q.update(statement=clean(x['statement']),options=['True','False'])
        if typ=='fill':q['statement']=clean(x['statement'])
        if typ=='short':q['rubric']=clean(x.get('rubric','Compare your answer to the source-based model answer.'))[:1000]
        valid.append(q)
    if not valid:die('AI did not provide valid, source-attributed questions. No assessment was saved.',502)
    return valid


@app.post('/api/quizzes')
def create_quiz(body:dict):
    unit_id=body.get('unit_id') or None;valid_unit(unit_id)
    ids=body.get('material_ids')
    if ids is not None and not isinstance(ids,list):die('material_ids must be a list.')
    mode=body.get('mode','quiz')
    if mode not in ('quiz','test'):die('Invalid practice mode.')
    count=max(1,min(60,int(body.get('count',10))))
    requested=body.get('types') or ['mcq','tf','fill','short','matching','multi']
    allowed={'mcq','tf','fill','short','matching','multi'}
    requested=[x for x in requested if x in allowed]
    if not requested:die('Select at least one supported question format.')
    cards=items('SELECT * FROM cards WHERE '+('unit_id=?' if unit_id else '1=1'),(unit_id,) if unit_id else ())
    if ids is not None:cards=[x for x in cards if x['material_id'] in ids]
    elif not unit_id: pass
    if not cards:
        rows=source_rows(unit_id,ids)
        cs=candidates(rows)
        if len(cs)<count:cs+=source_sentences(rows,max_count=count-len(cs))
        cards=[{'front':('Complete this source sentence: '+x['definition'].replace(x['term'],'____',1)) if x.get('cloze') else x['term'],
                'back':x['term'] if x.get('cloze') else x['definition'],
                'unit_id':x['unit_id'],'material_id':x['material_id'],
                'topic':x['topic'],'source_name':x['source_name']} for x in cs]
    else:
        id_to_name={x['id']:x['filename'] for x in items('SELECT id,filename FROM materials')}
        for x in cards:x['source_name']=id_to_name.get(x.get('material_id'),'Your saved flashcards')
    generator=body.get('generator','local')
    if generator not in ('local','ai'):die('Unknown quiz generator.')
    if generator=='ai':
        questions=make_ai_questions(body,source_rows(unit_id,ids))
    else:
        if not cards:die('No source material is available for questions. Upload a lesson or create cards.')
        count=min(count,len(cards))
        target_topics=[]
        if body.get('prioritize_mistakes'):
            profile=progress()['topics']
            target_topics=[r['topic'] for r in profile if r['incorrect']>0 and r['incorrect']>=r['correct']]
        questions=qbank(cards,mode,requested,count,target_topics)
    id=rid()
    title=clean(body.get('title','')) or ('Practice test' if mode=='test' else 'Practice quiz')
    minutes=max(0,min(180,int(body.get('minutes',0))))
    with db() as c:c.execute('INSERT INTO quizzes(id,title,mode,unit_id,question_json,minutes,created_at) VALUES (?,?,?,?,?,?,?)',
                            (id,title,mode,unit_id,json.dumps(questions),minutes,now()))
    return public_quiz(item('SELECT * FROM quizzes WHERE id=?',(id,)))


@app.get('/api/quizzes/{id}')
def get_quiz(id:str):
    quiz=item('SELECT * FROM quizzes WHERE id=?',(id,))
    if not quiz:die('Quiz not found.',404)
    return public_quiz(quiz)


def eval_question(q, value):
    typ=q['type'];ans=q['answer']
    if typ=='mcq':return type(value) is int and value==ans
    if typ=='tf':return value==ans
    if typ=='multi':return isinstance(value,list) and sorted(set(value))==sorted(ans)
    if typ=='fill':return normalize(value)==normalize(ans)
    if typ=='matching':return isinstance(value,dict) and len(value)==len(ans) and all(value.get(k)==v for k,v in ans.items())
    return None


def make_report(questions,responses,manual_scores=None):
    manual_scores=manual_scores or {}
    details=[]
    for q in questions:
        resp=responses.get(q['id'])
        correct=eval_question(q,resp)
        # A blank written answer is not awaiting self-review; it is unanswered.
        if q['type']=='short':
            correct=manual_scores.get(q['id']) if clean(str(resp or '')) else False
        details.append({'id':q['id'],'type':q['type'],'prompt':q['prompt'],'topic':q['topic'],
                        'source_name':q['source_name'],'material_id':q.get('material_id'),
                        'response':resp,'correct':correct,'answer':q['answer'],
                        'explanation':q['explanation'],'rubric':q.get('rubric')})
    graded=[x for x in details if x['correct'] is not None]
    percentage=round(sum(bool(x['correct']) for x in graded)/len(graded)*100) if graded else None
    misses=[x['topic'] for x in details if x['correct'] is False]
    return {'percent':percentage,'graded':len(graded),'total':len(details),
            'manual_needed':sum(x['correct'] is None for x in details),
            'correct':sum(x['correct'] is True for x in details),'missed_topics':list(dict.fromkeys(misses)),
            'details':details}


@app.post('/api/quizzes/{id}/submit')
def submit_quiz(id:str,body:dict):
    q=item('SELECT * FROM quizzes WHERE id=?',(id,))
    if not q:die('Quiz not found.',404)
    if q['status']=='submitted':die('This assessment has already been submitted.')
    responses=body.get('responses',{})
    if not isinstance(responses,dict):die('Responses must be a mapping.')
    questions=json.loads(q['question_json'])
    valid_ids={x['id'] for x in questions}
    responses={str(k):v for k,v in responses.items() if k in valid_ids}
    report=make_report(questions,responses)
    with db() as c:
        c.execute('UPDATE quizzes SET responses_json=?,report_json=?,status="submitted",submitted_at=? WHERE id=?',
                  (json.dumps(responses),json.dumps(report),'%s'%now(),id))
    return public_quiz(item('SELECT * FROM quizzes WHERE id=?',(id,)))


@app.post('/api/quizzes/{id}/selfgrade')
def selfgrade_quiz(id:str,body:dict):
    q=item('SELECT * FROM quizzes WHERE id=?',(id,))
    if not q or q['status']!='submitted':die('Submitted assessment not found.',404)
    questions=json.loads(q['question_json']); scores=body.get('scores',{})
    if not isinstance(scores,dict):die('scores must be a mapping.')
    old_report=json.loads(q['report_json']); old_scores={d['id']:d['correct'] for d in old_report['details'] if d['type']=='short'}
    for x in questions:
        if x['type']=='short' and x['id'] in scores and isinstance(scores[x['id']],bool):old_scores[x['id']]=scores[x['id']]
    report=make_report(questions,json.loads(q['responses_json']),old_scores)
    with db() as c:c.execute('UPDATE quizzes SET report_json=? WHERE id=?',(json.dumps(report),id))
    return public_quiz(item('SELECT * FROM quizzes WHERE id=?',(id,)))


def store_guide(title, markdown, rows, unit_id, mode, generator):
    gid=rid()
    with db() as c:
        c.execute('INSERT INTO guides(id,title,unit_id,mode,generator,markdown,source_ids,created_at) VALUES (?,?,?,?,?,?,?,?)',
                  (gid,title,unit_id or None,mode,generator,markdown,json.dumps([r['id'] for r in rows]),now()))
    return gid


@app.get('/api/guides/{guide_id}')
def get_saved_guide(guide_id:str):
    record=item('SELECT * FROM guides WHERE id=?',(guide_id,))
    if not record:die('Saved study guide not found.',404)
    sources=source_rows(material_ids=json.loads(record['source_ids']))
    return {'id':record['id'],'title':record['title'],'markdown':record['markdown'],
            'mode':record['mode'],'generator':record['generator'],'created_at':record['created_at'],
            'sources':[{'id':r['id'],'filename':r['filename']} for r in sources]}


@app.delete('/api/guides/{guide_id}')
def delete_saved_guide(guide_id:str):
    with db() as c:deleted=c.execute('DELETE FROM guides WHERE id=?',(guide_id,)).rowcount
    if not deleted:die('Saved study guide not found.',404)
    return {'ok':True}


@app.post('/api/guides')
def make_guide(body:dict):
    rows=material_selection(body)
    if not rows:die('Choose materials to build a guide.')
    mode=body.get('mode','concise')
    if mode not in ('concise','detailed','exam'):die('Invalid guide mode.')
    c=candidates(rows,max_count=60 if mode=='detailed' else 25)
    parts=[f'# AP Biology · {"Detailed guide" if mode=="detailed" else "Exam review sheet" if mode=="exam" else "Quick study guide"}',
           '',f'Generated from {len(rows)} uploaded source(s): '+', '.join(r['filename'] for r in rows),'',
           '_This is an extractive outline, not a verified teacher-created answer key. Review each source._','']
    if c:
        parts+=['## Key definitions and concepts','']
        for x in c:parts += [f'**{x["term"]}** — {x["definition"]}',f'  *Source: {x["source_name"]}*','']
    else:
        parts+=['## Source excerpts','']
        for x in source_sentences(rows,15):parts += [f'- {x["definition"]} (*{x["source_name"]}*)']
    if mode in ('detailed','exam'):
        parts+=['','## Active recall prompts','']
        for x in c[:16]:parts += [f'- Explain **{x["term"]}** without looking, then check {x["source_name"]}.']
    if mode=='exam':parts+=['','## Before the assessment','','- Explain key processes in your own words.','- Practice interpreting graphs and experimental controls.','- Revisit every topic you missed on prior quizzes.']
    title=parts[0].lstrip('# ')
    content='\n'.join(parts)
    gid=store_guide(title,content,rows,body.get('unit_id'),mode,'local')
    return {'id':gid,'title':title,'markdown':content,'sources':[{'id':m['id'],'filename':m['filename']} for m in rows]}


@app.post('/api/ai/guide')
def make_ai_guide(body:dict):
    rows=material_selection(body)
    if not rows:die('Select uploaded sources before asking for an AI study guide.')
    blocks='\n\n'.join(f'[SOURCE: {r["filename"]}]\n{r["text"][:5500]}' for r in rows if r['text'])[:22000]
    if not blocks:die('Selected sources have no extractable text.')
    mode=body.get('mode','detailed')
    if mode not in ('concise','detailed','exam'):die('Invalid guide type.')
    guide=ai_completion('You are an AP Biology curriculum tutor. Generate a '+mode+
          ' study guide from ONLY the provided classroom source text. Use Markdown with headings, key definitions, '
          'cause-and-effect reasoning, accurate processes, worked questions if sources support them, '
          'common errors, and active recall prompts. Cite the exact source filename in each section. '
          'If something is missing in the notes, do not invent it. No fake quotes or page numbers. '
          'Output Markdown only.','SOURCE DOCUMENTS:\n'+blocks)
    if not clean(guide):die('The AI returned an empty guide.',502)
    gid=store_guide('AP Biology AI study guide',guide,rows,body.get('unit_id'),mode,'ai')
    return {'id':gid,'title':'AP Biology AI study guide','markdown':guide,'sources':[{'id':m['id'],'filename':m['filename']} for m in rows],
            'notice':'AI-generated: verify every important claim with your class materials.'}


@app.post('/api/quizzes/{id}/issues')
def report_question(id:str,body:dict):
    q=item('SELECT * FROM quizzes WHERE id=?',(id,))
    if not q:die('Quiz not found.',404)
    question_id=body.get('question_id')
    if question_id not in {x['id'] for x in json.loads(q['question_json'])}:die('Question not found.',404)
    details=clean(body.get('details',''))[:1000]
    if not details:die('Describe the issue with this question.')
    with db() as c:
        c.execute('INSERT INTO issues VALUES (?,?,?,?,?,?)',(rid(),id,question_id,details,now(),0))
    return {'ok':True,'note':'Flag saved locally for your review. No external report was sent.'}


@app.get('/api/issues')
def list_issues():
    return {'issues':items('SELECT * FROM issues ORDER BY created_at DESC')}


@app.get('/api/progress')
def progress():
    reviews=items('SELECT * FROM reviews ORDER BY reviewed_at DESC LIMIT 100')
    attempts=items('SELECT id,unit_id,title,mode,report_json,created_at FROM quizzes WHERE status="submitted" ORDER BY created_at ASC')
    performance={}
    for a in attempts:
        report=json.loads(a['report_json'] or 'null') or {}
        for d in report.get('details',[]):
            topic=d.get('topic') or 'Uncategorized'; record=performance.setdefault(topic,{'topic':topic,'correct':0,'incorrect':0,'manual':0})
            if d['correct'] is True:record['correct']+=1
            elif d['correct'] is False:record['incorrect']+=1
            else:record['manual']+=1
    history=[{'id':a['id'],'name':a['title'],'date':a['created_at'],'score':(json.loads(a['report_json']) or {}).get('percent')} for a in attempts]
    return {'topics':sorted(performance.values(),key=lambda x:(-x['incorrect'],x['correct'])),
            'history':history,'reviews':reviews}


@app.post('/api/tasks')
def add_task(body:dict):
    title=clean(body.get('title',''))
    if not title:die('Task title is required.')
    unit_id=body.get('unit_id') or None;valid_unit(unit_id)
    d=body.get('due_date','')
    if d:
        try:datetime.strptime(d,'%Y-%m-%d')
        except:die('Use YYYY-MM-DD for the due date.')
    id=rid()
    with db() as c:c.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?)',(id,title,d,unit_id,0,now()))
    return {'id':id}


@app.patch('/api/tasks/{id}')
def update_task(id:str,body:dict):
    t=item('SELECT * FROM tasks WHERE id=?',(id,))
    if not t:die('Task not found.',404)
    with db() as c:c.execute('UPDATE tasks SET title=?,due_date=?,done=? WHERE id=?',
                            (clean(body.get('title',t['title'])),body.get('due_date',t['due_date']),int(bool(body.get('done',t['done']))),id))
    return {'ok':True}


@app.delete('/api/tasks/{id}')
def delete_task(id:str):
    with db() as c:c.execute('DELETE FROM tasks WHERE id=?',(id,))
    return {'ok':True}


def ai_completion(system,user):
    if not os.environ.get('OPENAI_API_KEY'):
        die('AI tutor is not connected. Add OPENAI_API_KEY to the server environment (ChatGPT Plus does not include API credits).',503)
    try:
        from openai import OpenAI
        client=OpenAI(api_key=os.environ['OPENAI_API_KEY'],timeout=40,max_retries=1)
        result=client.chat.completions.create(model=AI_MODEL,temperature=0.3,
            messages=[{'role':'system','content':system},{'role':'user','content':user}])
        return result.choices[0].message.content or ''
    except Exception as e:
        die('The AI service could not respond: '+str(e)[:200],502)


@app.post('/api/ai/chat')
def ai_tutor(body:dict):
    question=clean(body.get('message',''))
    if not question:die('Ask a question to begin.')
    if len(question)>6000:die('Question is too long.')
    mode=body.get('mode','Explain it simply')
    rows=material_selection(body)
    if not rows:die('Upload source material before using the source-grounded AI tutor.')
    sources=[]
    for n,m in enumerate(rows[:12],1):
        txt=m['text'][:2000]
        if txt:sources.append(f'[SOURCE {n}: {m["filename"]}]\n{txt}')
    if not sources:die('Selected materials contain no extracted text.')
    context='\n\n'.join(sources)[:19000]
    system=('You are a careful AP Biology high-school tutor. Treat supplied teacher materials as the primary source. '
            'Do not invent facts, pages, quotations or citations. Answer using the supplied sources, citing source names plainly. '
            'If the sources do not contain the answer, say exactly what is missing; you may include clearly labeled Supplemental context if useful. '
            'Use your selected teaching mode. Avoid excessive verbosity; check comprehension using one question at the end. '
            'Avoid giving a final answer immediately if the user asks for hints.')
    answer=ai_completion(system,f'Mode: {mode}\n\nTEACHER SOURCES:\n{context}\n\nSTUDENT MESSAGE:\n{question}')
    with db() as c:
        c.execute('INSERT INTO chat VALUES (?,?,?,?,?)',(rid(),mode,'user',question,now()))
        c.execute('INSERT INTO chat VALUES (?,?,?,?,?)',(rid(),mode,'assistant',answer,now()))
    return {'answer':answer,'source_names':[m['filename'] for m in rows if m['text']]}


@app.get('/api/chat/history')
def chat_history():
    return {'messages':items('SELECT * FROM chat ORDER BY created_at ASC LIMIT 200')}


@app.post('/api/ai/cards')
def ai_cards(body:dict):
    rows=material_selection(body)
    if not rows:die('Select sources first.')
    blocks='\n\n'.join(f'[{r["filename"]}]\n{r["text"][:4000]}' for r in rows if r['text'])[:18000]
    if not blocks:die('No extractable text in the selected sources.')
    count=max(1,min(25,int(body.get('count',12))))
    system=('Generate accurate AP Biology flashcards using ONLY the provided material. '
            'Return JSON only, no markdown. Shape: {"cards":[{"front":"...","back":"...","source_name":"..."}]} '
            'Exactly one clear fact/concept per card. If material is too thin, generate fewer cards. '
            'Never invent material or citations.')
    answer=ai_completion(system,f'Up to {count} cards based on:\n'+blocks)
    try:
        data=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',answer.strip()))
        cards=data['cards']
        if not isinstance(cards,list):raise ValueError()
    except Exception:die('The AI returned an invalid card format. No cards were saved.',502)
    ids=[]
    name_to_row={r['filename']:r for r in rows}
    with db() as c:
        for x in cards[:count]:
            if not isinstance(x,dict):continue
            front=clean(str(x.get('front','')))[:300];back=clean(str(x.get('back','')))[:1200]
            if not front or not back:continue
            r=name_to_row.get(x.get('source_name'),rows[0]);id=rid()
            c.execute('INSERT INTO cards(id,unit_id,material_id,topic,front,back,source_excerpt,created_at,due_at) VALUES (?,?,?,?,?,?,?,?,?)',
                      (id,r['unit_id'],r['id'],r['topic'],front,back,'AI generated: verify with uploaded source',now(),now()))
            ids.append(id)
    return {'created':len(ids),'ids':ids,'note':'AI-generated cards are not guaranteed correct; review them against the sources.'}


@app.get('/api/export')
def export_json():
    content={table:items(f'SELECT * FROM {table}') for table in ('units','materials','cards','quizzes','reviews','tasks','chat','issues','guides','lab_reports','frq_attempts','schedule_entries','schedule_links')}
    return Response(json.dumps(content,indent=2),media_type='application/json',
                    headers={'Content-Disposition':'attachment; filename="ap-bio-study-export.json"'})


@app.get('/api/backup')
def export_backup():
    mem=io.BytesIO()
    with zipfile.ZipFile(mem,'w',zipfile.ZIP_DEFLATED) as z:
        # SQLite connection backup produces consistent snapshot while app is running.
        temp=sqlite3.connect(':memory:')
        with db() as conn:conn.backup(temp)
        # Use a temporary copy so large upload binaries need not be loaded into RAM.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            bak=Path(td)/'study.sqlite3'; backcon=sqlite3.connect(bak);temp.backup(backcon);backcon.close()
            z.write(bak,'study.sqlite3')
        temp.close()
        for f in UPLOADS.iterdir():
            if f.is_file():z.write(f,'uploads/'+f.name)
        z.writestr('RESTORE.txt','Stop the server. Replace data/study.sqlite3 and data/uploads/ with these archive contents. Restart the server.\n')
    return Response(mem.getvalue(),media_type='application/zip',
                    headers={'Content-Disposition':'attachment; filename="ap-bio-backup.zip"'})


@app.post('/api/backup/restore')
async def restore_backup(file: UploadFile=File(...), confirmation: str=Form('')):
    """Restore one previously exported complete backup, with validation.

    This is an intentional replace operation for one-person installations,
    not a merge of unrelated users' data. We never extract arbitrary ZIP paths.
    """
    if confirmation != 'RESTORE':die('Type RESTORE to confirm replacing study data.')
    archive=await file.read(125*1024*1024+1)
    if not archive or len(archive)>125*1024*1024:
        die('Backup ZIP is empty or exceeds 125 MB.')
    required={'units','materials','cards','quizzes','guides','reviews','tasks','chat','issues'}
    with RESTORE_LOCK:
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as z, tempfile.TemporaryDirectory(dir=DATA) as td:
                target=Path(td)
                info=z.infolist()
                if len(info)>3000 or sum(x.file_size for x in info)>300*1024*1024:
                    die('Backup contains too many or too-large files.')
                names={x.filename for x in info if not x.is_dir()}
                if len(names)!=sum(not x.is_dir() for x in info):
                    die('Backup has duplicate file entries.')
                if 'study.sqlite3' not in names:
                    die('Not an AP Biology complete backup (database missing).')
                for entry in info:
                    name=entry.filename
                    # Only the database, a restore note, and safe upload filenames
                    # are part of our own full backups.
                    allowed=name in ('study.sqlite3','RESTORE.txt','uploads/') or bool(
                        re.fullmatch(r'uploads/[a-f0-9]{16}\.(?:pdf|pptx|docx|txt|md|csv|json|png|jpg|jpeg|webp)',name))
                    if not allowed or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                        die('Backup has an unexpected or unsafe file.')
                snapshot=target/'study.sqlite3'
                snapshot.write_bytes(z.read('study.sqlite3'))
                new_uploads=target/'new_uploads';new_uploads.mkdir()
                for entry in info:
                    if entry.filename.startswith('uploads/') and not entry.is_dir():
                        (new_uploads/Path(entry.filename).name).write_bytes(z.read(entry))
                try:
                    with sqlite3.connect(f'file:{snapshot}?mode=ro',uri=True) as c:
                        c.row_factory=sqlite3.Row
                        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                            die('Backup database failed integrity verification.')
                        existing={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                        if not required.issubset(existing):
                            die('Backup is missing required study tables.')
                        with db() as current:
                            for table in required:
                                restored_cols=[r[1] for r in c.execute('PRAGMA table_info('+table+')')]
                                current_cols=[r[1] for r in current.execute('PRAGMA table_info('+table+')')]
                                if restored_cols!=current_cols and not (table=='materials' and restored_cols==[x for x in current_cols if x!='kind']):
                                    die('Backup uses an incompatible study database version.')
                        stored={r[0] for r in c.execute('SELECT store_name FROM materials')}
                        if stored!={p.name for p in new_uploads.iterdir()}:
                            die('Backup is incomplete: material files do not match its database.')
                except sqlite3.DatabaseError:
                    die('Backup database is invalid or damaged.')
                # Preserve an immediate rollback snapshot until the replacement
                # has completed. Existing app connections are short-lived.
                previous=target/'previous.sqlite3'
                with sqlite3.connect(previous) as old, db() as original:
                    original.backup(old)
                previous_uploads=target/'previous_uploads'
                UPLOADS.rename(previous_uploads)
                try:
                    new_uploads.rename(UPLOADS)
                    with sqlite3.connect(snapshot) as source, db() as current:
                        source.backup(current)
                except Exception:
                    if UPLOADS.exists():shutil.rmtree(UPLOADS)
                    previous_uploads.rename(UPLOADS)
                    with sqlite3.connect(previous) as source, db() as current:
                        source.backup(current)
                    raise
        except zipfile.BadZipFile:
            die('Not a valid ZIP backup.')
    from study_extras import prepare_schema
    prepare_schema(db)  # Upgrade legacy backups without losing existing study work.
    from schedule_extras import prepare_schema as prepare_schedule_schema
    prepare_schedule_schema(db)
    return {'ok':True,'note':'Complete backup restored. Refresh the page to view the restored data.'}


from study_extras import install as install_study_extras
install_study_extras(app, globals())
from schedule_extras import install as install_schedule_extras
install_schedule_extras(app, globals())

app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

@app.get('/')
def index():
    return FileResponse(ROOT/'static'/'index.html')
