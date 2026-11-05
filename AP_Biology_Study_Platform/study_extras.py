"""Syllabus/reference resources, formal lab reports and original FRQ practice.

All saved work uses the existing server-side SQLite database and is included
in the app's complete ZIP backup. No AI API or fabricated grading is involved.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import File, Form, UploadFile

RESOURCE_KINDS = {'notes', 'syllabus', 'reference', 'lab', 'frq', 'schedule', 'assignments'}
LAB_FIELDS = ('question', 'hypothesis', 'independent', 'dependent', 'controls',
              'procedure', 'data', 'analysis', 'conclusion', 'limitations', 'sources')

# Original educational questions. They are not official College Board items.
FRQ_BANK = [
    {
        'id': 'enzyme-ph', 'title': 'Enzyme activity and pH', 'unit': 'Cellular Energetics',
        'context': 'A student studies an enzyme that breaks down a starch-like polymer. Equal samples are mixed with identical enzyme concentrations at 25°C. Initial reaction rates are 4, 16, 29, 15, and 3 arbitrary units at pH 3, 5, 7, 9, and 11, respectively. The substrate concentration and reaction time are controlled.',
        'parts': [
            {'id':'a','verb':'Identify','prompt':'Identify the independent and dependent variables in this experiment.',
             'rubric':['Identifies pH as the independent variable','Identifies initial reaction rate as the dependent variable']},
            {'id':'b','verb':'Describe','prompt':'Describe the relationship between pH and the measured reaction rate.',
             'rubric':['Recognizes a peak rate at pH 7','Describes lower rates at both more acidic and more basic pH values']},
            {'id':'c','verb':'Explain','prompt':'Explain a molecular reason the rate changes away from pH 7.',
             'rubric':['Connects pH to amino acid ionization or interactions','Explains how enzyme shape or active-site properties affect catalysis']},
            {'id':'d','verb':'Predict','prompt':'Predict how severe heating might change the results, and justify.',
             'rubric':['Predicts a reduction in activity after denaturing heat','Connects reduction to disruption of enzyme structure']}
        ]
    },
    {
        'id': 'osmosis', 'title': 'Osmosis in plant tissue', 'unit': 'Cell Structure and Function',
        'context': 'Equal-size potato tissue cylinders are placed for one hour in sucrose solutions of 0.0 M, 0.2 M, 0.4 M, and 0.6 M. Their average percent mass changes are +13%, +5%, −2%, and −11%, respectively.',
        'parts': [
            {'id':'a','verb':'Describe','prompt':'Describe the overall relationship between sucrose concentration and percent mass change.',
             'rubric':['States that mass change decreases as sucrose concentration increases','Uses a relevant value or comparison from the data']},
            {'id':'b','verb':'Explain','prompt':'Explain why tissue in 0.0 M sucrose gains mass.',
             'rubric':['Identifies net water movement into tissue by osmosis','Links movement to water potential or solute concentration difference']},
            {'id':'c','verb':'Estimate','prompt':'Estimate the isotonic sucrose concentration using the reported data.',
             'rubric':['Estimates a concentration between 0.2 M and 0.4 M','Justifies the estimate using the sign change in percent mass']},
            {'id':'d','verb':'Design','prompt':'Identify one additional controlled variable and explain why it matters.',
             'rubric':['Identifies a reasonable control such as temperature, surface area, or time','Explains how controlling it makes treatment comparisons valid']}
        ]
    },
    {
        'id': 'leaf-disk', 'title': 'Photosynthesis and leaf-disk flotation', 'unit': 'Cellular Energetics',
        'context': 'Students use 10 infiltrated spinach disks per treatment. In white light, five disks have floated after 6 minutes. In blue light, five disks float after 9 minutes. In darkness, none float within 20 minutes. The same bicarbonate solution is used throughout.',
        'parts': [
            {'id':'a','verb':'Calculate','prompt':'Determine the estimated ET₅₀ for the white-light and blue-light treatments.',
             'rubric':['Reports an ET₅₀ of 6 minutes for white light','Reports an ET₅₀ of 9 minutes for blue light']},
            {'id':'b','verb':'Interpret','prompt':'Explain what the ET₅₀ comparison suggests about these treatments.',
             'rubric':['Notes disks float sooner under white light','Connects flotation timing to oxygen production or net photosynthetic rate']},
            {'id':'c','verb':'Explain','prompt':'Explain why disks in the dark might remain submerged.',
             'rubric':['Recognizes light-dependent reactions do not proceed effectively in darkness','Explains insufficient photosynthetic oxygen accumulation for flotation']},
            {'id':'d','verb':'Evaluate','prompt':'Describe one limitation of concluding that blue light always causes slower photosynthesis.',
             'rubric':['Notes an experimental limitation such as unequal light intensity or replication','Explains how the limitation could influence observed ET₅₀']}
        ]
    },
    {
        'id': 'cell-signaling', 'title': 'Receptor signaling and feedback', 'unit': 'Cell Communication and Cell Cycle',
        'context': 'A hormone activates a membrane receptor and a kinase cascade that produces protein X. Wild-type cells have 100 relative units of X after 15 minutes. Cells treated with a kinase inhibitor have 18 units; cells missing the receptor have 4 units.',
        'parts': [
            {'id':'a','verb':'Identify','prompt':'Identify which cells provide evidence that the receptor is needed for a full response.',
             'rubric':['Identifies receptor-deficient cells','Uses the lower protein X result compared with wild type']},
            {'id':'b','verb':'Explain','prompt':'Explain how the kinase inhibitor might reduce protein X production.',
             'rubric':['References disruption of signal-transduction phosphorylation','Connects it to a reduced downstream response or expression']},
            {'id':'c','verb':'Predict','prompt':'Predict the response in cells with a receptor that is always active without hormone.',
             'rubric':['Predicts elevated baseline pathway activity relative to wild type without hormone','Justifies the prediction using constitutive receptor signaling']},
            {'id':'d','verb':'Design','prompt':'Propose an appropriate negative control for the inhibitor treatment.',
             'rubric':['Specifies untreated or vehicle-only wild-type cells','Explains how it distinguishes inhibitor effects from handling or solvent effects']}
        ]
    },
    {
        'id': 'inheritance', 'title': 'Inheritance and recombination', 'unit': 'Heredity',
        'context': 'A testcross of a heterozygous fly carrying linked genes A and B produces offspring: AB 418, ab 402, Ab 92, and aB 88. The tester parent is homozygous recessive for both genes.',
        'parts': [
            {'id':'a','verb':'Calculate','prompt':'Calculate the recombination frequency between genes A and B.',
             'rubric':['Adds recombinant types Ab and aB (180)','Divides by the total (1000) and reports 18%']},
            {'id':'b','verb':'Identify','prompt':'Identify the parental allele combinations and justify using the data.',
             'rubric':['Identifies AB and ab as parental types','Explains that they are the most frequent classes']},
            {'id':'c','verb':'Explain','prompt':'Explain the cellular event that produces recombinant gametes.',
             'rubric':['Identifies crossing over in prophase I of meiosis','Describes exchange between nonsister chromatids of homologous chromosomes']},
            {'id':'d','verb':'Predict','prompt':'Predict what results would look like if the genes assorted independently.',
             'rubric':['Predicts approximately equal proportions of the four classes','Connects expectation to independent assortment or 50% recombination']}
        ]
    },
    {
        'id': 'natural-selection', 'title': 'Natural selection in changing environments', 'unit': 'Natural Selection',
        'context': 'In an insect population, dark-bodied individuals increase from 20% to 68% over ten generations after dark volcanic soil becomes the dominant background. Birds are the main visual predators; other conditions are stable.',
        'parts': [
            {'id':'a','verb':'Describe','prompt':'Describe the change in dark-bodied frequency over ten generations.',
             'rubric':['States the frequency increased','Uses the values 20% and 68% or a 48-percentage-point increase']},
            {'id':'b','verb':'Explain','prompt':'Provide a plausible mechanism for this change involving differential survival.',
             'rubric':['Describes camouflage reducing detection by predators','Connects survival/reproduction differences to allele frequency change']},
            {'id':'c','verb':'Predict','prompt':'Predict a likely outcome if the habitat returns to light soil and visual predation continues.',
             'rubric':['Predicts selection may favor lighter insects','Justifies using a change in camouflage advantage']},
            {'id':'d','verb':'Evaluate','prompt':'Explain why these data alone do not prove body color is genetically inherited.',
             'rubric':['Distinguishes phenotype frequency changes from genetic heritability evidence','Proposes breeding/genetic evidence or controlled common-environment tests']}
        ]
    }
]


def prepare_schema(db):
    with db() as conn:
        existing={row[1] for row in conn.execute('PRAGMA table_info(materials)')}
        if 'kind' not in existing:
            conn.execute("ALTER TABLE materials ADD COLUMN kind TEXT NOT NULL DEFAULT 'notes'")
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS lab_reports (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, unit_id TEXT,
            sections_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(unit_id) REFERENCES units(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS frq_attempts (
            id TEXT PRIMARY KEY, prompt_id TEXT NOT NULL, unit_id TEXT,
            answers_json TEXT NOT NULL DEFAULT '{}', checks_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(unit_id) REFERENCES units(id) ON DELETE SET NULL
        );
        ''')


def install(app, core):
    db, items, item, die = (core[k] for k in ('db','items','item','die'))
    rid, now = core['rid'],core['now']
    upload_material=core['upload_material']
    prepare_schema(db)

    def clean_kind(kind):
        kind=str(kind or '').strip().lower()
        if kind not in RESOURCE_KINDS:die('Choose a valid material category.')
        return kind

    def valid_unit(uid):
        if uid and not item('SELECT id FROM units WHERE id=?',(uid,)):
            die('Unit not found.',404)

    @app.get('/api/extras/bootstrap')
    def extras_bootstrap():
        resource_kinds=items('SELECT id,kind FROM materials')
        labs=items('SELECT id,title,unit_id,created_at,updated_at FROM lab_reports ORDER BY updated_at DESC LIMIT 100')
        attempts=items('SELECT id,prompt_id,unit_id,status,checks_json,created_at,updated_at FROM frq_attempts ORDER BY updated_at DESC LIMIT 100')
        for a in attempts:
            a['points']=len(json.loads(a.pop('checks_json') or '[]')) if a['status']=='submitted' else None
            prompt=next((x for x in FRQ_BANK if x['id']==a['prompt_id']),None)
            a['max_points']=sum(len(p['rubric']) for p in prompt['parts']) if prompt else 0
        return {'kinds':{r['id']:r['kind'] for r in resource_kinds},'labs':labs,'frqs':attempts}

    @app.post('/api/extras/upload')
    async def resources_upload(files:list[UploadFile]=File(...),kind:str=Form('reference'),
                               unit_id:str=Form(''),topic:str=Form(''),lesson:str=Form('')):
        kind=clean_kind(kind)
        if kind=='syllabus':unit_id=''
        result=await upload_material(files,unit_id,topic,lesson)
        ids=[r['id'] for r in result['results'] if 'id' in r]
        with db() as conn:
            conn.executemany('UPDATE materials SET kind=? WHERE id=?',[(kind,x) for x in ids])
        return result

    @app.patch('/api/extras/resources/{material_id}')
    def change_resource(material_id:str,body:dict):
        kind=clean_kind(body.get('kind'))
        if not item('SELECT id FROM materials WHERE id=?',(material_id,)):
            die('File not found.',404)
        with db() as conn: conn.execute('UPDATE materials SET kind=? WHERE id=?',(kind,material_id))
        return {'ok':True,'kind':kind}

    def lab_payload(body):
        title=str(body.get('title','')).strip()[:180]
        if not title:die('Give your lab report a title.')
        unit_id=body.get('unit_id') or None;valid_unit(unit_id)
        sections=body.get('sections',{})
        if not isinstance(sections,dict):die('Invalid report sections.')
        sanitized={k:str(sections.get(k,'')).strip()[:20000] for k in LAB_FIELDS}
        return title,unit_id,json.dumps(sanitized)

    @app.post('/api/extras/labs')
    def add_lab(body:dict):
        title,unit_id,sections=lab_payload(body)
        lab_id=rid();ts=now()
        with db() as conn:conn.execute('INSERT INTO lab_reports VALUES (?,?,?,?,?,?)',
                                     (lab_id,title,unit_id,sections,ts,ts))
        return {'id':lab_id,'ok':True}

    @app.get('/api/extras/labs/{lab_id}')
    def get_lab(lab_id:str):
        lab=item('SELECT * FROM lab_reports WHERE id=?',(lab_id,))
        if not lab:die('Lab report not found.',404)
        lab['sections']=json.loads(lab.pop('sections_json'))
        return lab

    @app.patch('/api/extras/labs/{lab_id}')
    def update_lab(lab_id:str,body:dict):
        if not item('SELECT id FROM lab_reports WHERE id=?',(lab_id,)):
            die('Lab report not found.',404)
        title,unit_id,sections=lab_payload(body)
        with db() as conn:conn.execute('UPDATE lab_reports SET title=?,unit_id=?,sections_json=?,updated_at=? WHERE id=?',
                                     (title,unit_id,sections,now(),lab_id))
        return {'ok':True,'id':lab_id}

    @app.delete('/api/extras/labs/{lab_id}')
    def delete_lab(lab_id:str):
        with db() as conn:
            result=conn.execute('DELETE FROM lab_reports WHERE id=?',(lab_id,))
        if not result.rowcount:die('Lab report not found.',404)
        return {'ok':True}

    @app.get('/api/extras/frq-bank')
    def get_frq_bank():
        return {'questions':FRQ_BANK,'note':'Original AP Biology-style practice, not official College Board questions. Self-scoring is not teacher or AI grading.'}

    def valid_prompt(prompt_id):
        prompt=next((x for x in FRQ_BANK if x['id']==prompt_id),None)
        if not prompt:die('FRQ prompt not found.',404)
        return prompt

    @app.post('/api/extras/frq-attempts')
    def start_frq(body:dict):
        prompt_id=str(body.get('prompt_id',''))
        valid_prompt(prompt_id)
        unit_id=body.get('unit_id') or None;valid_unit(unit_id)
        attempt_id=rid();ts=now()
        with db() as conn:conn.execute('INSERT INTO frq_attempts VALUES (?,?,?,?,?,?,?,?)',
                                     (attempt_id,prompt_id,unit_id,'{}','[]','draft',ts,ts))
        return {'id':attempt_id,'ok':True}

    @app.get('/api/extras/frq-attempts/{attempt_id}')
    def get_attempt(attempt_id:str):
        attempt=item('SELECT * FROM frq_attempts WHERE id=?',(attempt_id,))
        if not attempt:die('FRQ attempt not found.',404)
        attempt['answers']=json.loads(attempt.pop('answers_json'))
        attempt['checks']=json.loads(attempt.pop('checks_json'))
        return attempt

    @app.patch('/api/extras/frq-attempts/{attempt_id}')
    def save_attempt(attempt_id:str,body:dict):
        attempt=item('SELECT * FROM frq_attempts WHERE id=?',(attempt_id,))
        if not attempt:die('FRQ attempt not found.',404)
        if attempt['status']!='draft':die('Submitted FRQs cannot be changed. Start a new attempt.')
        prompt=valid_prompt(attempt['prompt_id'])
        allowed={p['id'] for p in prompt['parts']}
        answers=body.get('answers',{})
        if not isinstance(answers,dict) or set(answers)-allowed:
            die('Invalid FRQ answers.')
        answers={k:str(v)[:10000] for k,v in answers.items()}
        status=str(body.get('status','draft'))
        if status not in ('draft','submitted'):die('Invalid attempt status.')
        checks=[]
        if status=='submitted':
            raw=body.get('checks',[])
            if not isinstance(raw,list):die('Invalid checklist.')
            valid={f"{p['id']}:{i}" for p in prompt['parts'] for i in range(len(p['rubric']))}
            if any(not isinstance(x,str) or x not in valid for x in raw):die('Invalid scoring criterion.')
            checks=sorted(set(raw))
        with db() as conn:conn.execute('UPDATE frq_attempts SET answers_json=?,checks_json=?,status=?,updated_at=? WHERE id=?',
                                     (json.dumps(answers),json.dumps(checks),status,now(),attempt_id))
        return {'ok':True,'id':attempt_id,'status':status,'points':len(checks),
                'max_points':sum(len(p['rubric']) for p in prompt['parts'])}

    @app.delete('/api/extras/frq-attempts/{attempt_id}')
    def delete_attempt(attempt_id:str):
        with db() as conn:result=conn.execute('DELETE FROM frq_attempts WHERE id=?',(attempt_id,))
        if not result.rowcount:die('FRQ attempt not found.',404)
        return {'ok':True}
