import os
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import auth


class AccountTests(unittest.TestCase):
    def test_admin_and_photographer_separation(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'photos.db'
            auth.initialize(db)
            auth.create_user(db, 'admin', 'a sufficiently long password', 'admin', initial=True)
            with self.assertRaises(ValueError):
                auth.create_user(db, 'second', 'another long password', 'admin', initial=True)
            self.assertIsNone(auth.authenticate(db, 'admin', 'incorrect password'))
            self.assertEqual(auth.authenticate(db, 'admin', 'a sufficiently long password')['role'], 'admin')
            env = dict(os.environ, DATA_DIR=directory)
            server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', '18979'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    try:
                        urllib.request.urlopen('http://127.0.0.1:18979/login', timeout=1)
                        break
                    except (OSError, urllib.error.URLError):
                        time.sleep(0.1)
                def call(path, method='GET', payload=None, cookie=None):
                    headers = {'Content-Type':'application/json'}
                    if cookie:
                        headers['Cookie'] = cookie
                    request = urllib.request.Request('http://127.0.0.1:18979' + path, method=method, headers=headers, data=json.dumps(payload).encode() if payload is not None else None)
                    try:
                        return urllib.request.urlopen(request)
                    except urllib.error.HTTPError as error:
                        return error
                self.assertEqual(call('/api/photos').status, 401)
                self.assertEqual(call('/api/photos', 'DELETE').status, 401)
                self.assertEqual(call('/api/users', 'POST', {'username':'user', 'password':'long password 123'}).status, 401)
                login = call('/api/login', 'POST', {'username':'admin','password':'a sufficiently long password'})
                self.assertEqual(login.status, 200)
                admin_cookie = login.headers['Set-Cookie'].split(';')[0]
                self.assertEqual(call('/api/users', 'POST', {'username':'user','password':'long password 123'}, admin_cookie).status, 201)
                photographer = call('/api/login', 'POST', {'username':'user','password':'long password 123'})
                user_cookie = photographer.headers['Set-Cookie'].split(';')[0]
                self.assertEqual(call('/api/users', 'POST', {'username':'other','password':'long password 123'}, user_cookie).status, 403)
                self.assertEqual(call('/api/photos', cookie=user_cookie).status, 200)
                self.assertEqual(call('/api/logout', 'POST', cookie=admin_cookie).status, 200)
                self.assertEqual(call('/api/me', cookie=admin_cookie).status, 401)
            finally:
                server.terminate()
                server.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
