"""Public-hosting safety regression tests; run in subprocesses to isolate env."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap


def test_public_mode_protects_resources_and_writes(tmp_path):
    env = dict(os.environ, APBIO_PUBLIC='1', APBIO_ADMIN_USERNAME='student',
               APBIO_ADMIN_PASSWORD='test-password-very-long-random-82',
               APBIO_DATA_DIR=str(tmp_path / 'persist'))
    code = textwrap.dedent('''
        from fastapi.testclient import TestClient
        from main import app
        c = TestClient(app)
        assert c.get('/healthz').status_code == 200
        for path in ('/', '/static/app.js', '/api/bootstrap', '/api/backup', '/api/export'):
            assert c.get(path).status_code == 401, path
            assert c.get(path, auth=('student', 'test-password-very-long-random-82')).status_code == 200
        assert c.get('/api/bootstrap', auth=('student', 'wrong')).status_code == 401
        x=c.post('/api/units',json={'name':'Unit'},auth=('student', 'test-password-very-long-random-82'),
            headers={'origin':'https://untrusted.example','host':'testserver'})
        assert x.status_code == 403
        x=c.post('/api/units',json={'name':'Unit'},auth=('student','test-password-very-long-random-82'),
            headers={'origin':'https://testserver','host':'testserver'})
        assert x.status_code == 200
        assert c.get('/api/bootstrap',auth=('student','test-password-very-long-random-82')).json()['public_mode']
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
