"""Public-hosting safety regression tests; run in subprocesses to isolate env."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap


def test_public_mode_protects_each_browser_workspace_without_signin(tmp_path):
    env = dict(os.environ, APBIO_PUBLIC='1', APBIO_ADMIN_USERNAME='student',
               APBIO_ADMIN_PASSWORD='test-password-very-long-random-82',
               APBIO_DATA_DIR=str(tmp_path / 'persist'))
    code = textwrap.dedent('''
        from fastapi.testclient import TestClient
        from main import app
        visitor1 = TestClient(app)
        visitor2 = TestClient(app)
        assert visitor1.get('/healthz').status_code == 200
        for path in ('/', '/static/app.js', '/api/bootstrap', '/api/export'):
            assert visitor1.get(path).status_code == 200, path
        # GET is no longer a download endpoint. This prevents repeated downloads.
        assert visitor1.get('/api/backup').status_code == 405
        assert visitor1.post('/api/backup/download').status_code == 200
        assert visitor2.get('/api/bootstrap').status_code == 200
        # Separate browsers must not see each other's uploaded materials or units.
        created = visitor1.post('/api/units',json={'name':'Private to first visitor'})
        assert created.status_code == 200
        assert any(x['name']=='Private to first visitor' for x in visitor1.get('/api/bootstrap').json()['units'])
        assert not any(x['name']=='Private to first visitor' for x in visitor2.get('/api/bootstrap').json()['units'])
        # CSRF guard still prevents cross-site writes.
        blocked=visitor1.post('/api/units',json={'name':'Blocked'},
                              headers={'origin':'https://untrusted.example','host':'testserver'})
        assert blocked.status_code == 403
        allowed=visitor1.post('/api/units',json={'name':'Allowed'},
                              headers={'origin':'https://testserver','host':'testserver'})
        assert allowed.status_code == 200
        # The separate, original owner archive still requires owner credentials.
        assert visitor1.get('/owner',follow_redirects=False).status_code == 401
        owner=visitor1.get('/owner',auth=('student','test-password-very-long-random-82'),follow_redirects=False)
        assert owner.status_code == 303
        assert not any(x['name']=='Private to first visitor' for x in visitor1.get('/api/bootstrap').json()['units'])
    ''')
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                       cwd=os.path.dirname(os.path.dirname(__file__)), env=env)
    assert r.returncode == 0, r.stderr

def test_public_mode_fails_closed_without_strong_password(tmp_path):
    env = dict(os.environ, APBIO_PUBLIC='1', APBIO_ADMIN_PASSWORD='short',
               APBIO_DATA_DIR=str(tmp_path / 'persist'))
    r = subprocess.run([sys.executable, '-c', 'import main'], capture_output=True, text=True,
                       cwd=os.path.dirname(os.path.dirname(__file__)), env=env)
    assert r.returncode != 0
    assert '16 characters' in r.stderr
