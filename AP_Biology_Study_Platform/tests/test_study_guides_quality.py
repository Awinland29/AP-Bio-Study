"""Regression tests for Unit 3 guide quality and honest source handling."""
import pytest
from fastapi.testclient import TestClient
import main

@pytest.fixture
def client(tmp_path,monkeypatch):
    data=tmp_path/'data'
    (data/'uploads').mkdir(parents=True)
    monkeypatch.setattr(main,'DATA',data)
    monkeypatch.setattr(main,'DB',data/'study.sqlite3')
    monkeypatch.setattr(main,'UPLOADS',data/'uploads')
    main.init()
    with TestClient(main.app) as c:
        yield c

def unit(c,name):
    response=c.post('/api/units',json={'name':name})
    assert response.status_code==200,response.text
    return response.json()['id']

def upload(c,u,name,text):
    response=c.post('/api/materials/upload',data={'unit_id':u},files={'files':(name,text.encode(),'text/plain')})
    assert response.status_code==200,response.text
    return response.json()['results'][0]['id']

def test_unit3_objective_upload_produces_substantive_explanations(client):
    c=client
    u=unit(c,'Unit 3 Cellular Energetics')
    text='3.1 Explain how enzymes affect chemical reactions.\n3.4 Describe the photosynthetic stroma and thylakoids.\n3.5 Explain how glycolysis produces ATP.'
    upload(c,u,'AP Biology Topic 3.4 Objectives.txt',text)
    r=c.post('/api/guides',json={'unit_id':u,'mode':'detailed'})
    assert r.status_code==200,r.text
    x=r.json()
    g=x['markdown']
    assert x['generator']=='curated'
    assert 'supplemental' in g.lower()
    assert 'NOT a set of answers extracted' not in g or 'original' in g.lower()
    for term in ('3.1 Enzymes','3.2 Environmental','3.3 Cellular','3.4 Photosynthesis','3.5 Cellular','glycolysis','Calvin cycle','Chlorophyll','ATP synthase','activation energy'):
        assert term.lower() in g.lower(),term
    assert 'Explain how enzymes affect chemical reactions' in g
    assert 'AP Biology Topic 3.4 Objectives.txt' in g
    assert '## Source excerpts' not in g
    assert 'Which description matches' not in g
    assert len(g)>5500
    loaded=c.get('/api/guides/'+x['id'])
    assert loaded.status_code==200
    assert loaded.json()['markdown']==g

def test_review_modes_are_different_and_exam_is_practical(client):
    c=client
    u=unit(c,'Unit 3')
    guides=[]
    for mode in ('concise','detailed','exam'):
        r=c.post('/api/guides',json={'unit_id':u,'mode':mode})
        assert r.status_code==200,r.text
        guides.append(r.json()['markdown'])
    concise,detailed,exam=guides
    assert len(concise)<len(detailed)
    assert 'How and why it works' not in concise
    assert 'High-yield comparisons' in detailed
    assert 'Written-response practice' in exam
    assert 'H+ gradient' in exam
    assert all('Source excerpts' not in x for x in guides)

def test_nonunit3_objectives_get_explicit_checklist_not_fake_answers(client):
    c=client
    u=unit(c,'Unit 4 Cell Communication')
    upload(c,u,'unit4-objectives.txt','Explain how receptors recognize signaling molecules.\nDescribe signal transduction by phosphorylation.\nCompare positive and negative feedback systems.')
    r=c.post('/api/guides',json={'unit_id':u,'mode':'exam'})
    assert r.status_code==200,r.text
    g=r.json()['markdown']
    assert r.json()['generator']=='local'
    assert 'Learning objectives to review' in g
    assert 'receptors recognize signaling molecules' in g
    assert 'Objectives are goals' in g
    assert 'Photosystem II' not in g
    assert 'random' not in g.lower()

def test_nonunit3_notes_keep_real_definitions_and_provenance(client):
    c=client
    u=unit(c,'Unit 2 Cell Structure')
    upload(c,u,'membranes.txt','Osmosis: The net movement of water across a selectively permeable membrane down its water potential gradient.\nDiffusion: The passive movement of particles down their concentration gradient without direct ATP use.')
    r=c.post('/api/guides',json={'unit_id':u,'mode':'detailed'})
    assert r.status_code==200,r.text
    g=r.json()['markdown']
    assert 'Osmosis' in g and 'water potential' in g
    assert 'Diffusion' in g and 'membranes.txt' in g
    assert '3.4 Photosynthesis' not in g

def test_mismatched_material_filter_is_still_rejected(client):
    c=client
    a=unit(c,'Unit 3');b=unit(c,'Unit 4')
    mid=upload(c,b,'unit4.txt','Describe the stages of cell signaling.')
    r=c.post('/api/guides',json={'unit_id':a,'material_ids':[mid]})
    assert r.status_code==400,r.text
