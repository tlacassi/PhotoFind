import io
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import httpx
from PIL import Image
import auth

ROOT = Path(__file__).resolve().parents[1]


class PersistenceTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / 'models' / 'face_recognition_sface_2021dec.onnx').is_file(), 'Download models to run the real OpenCV restart test.')
    def test_real_upload_survives_server_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            auth.initialize(Path(directory) / 'photos.db')
            auth.create_user(Path(directory) / 'photos.db', 'admin', 'test password', 'admin')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            env = dict(os.environ, DATA_DIR=directory, SECURE_COOKIES='false')
            def start():
                server = subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port',str(port)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for _ in range(100):
                    try:
                        if httpx.get(f'http://127.0.0.1:{port}/login', timeout=1).status_code == 200:
                            return server
                    except httpx.TransportError:
                        pass
                    time.sleep(.05)
                server.terminate(); server.wait(timeout=5)
                self.fail('Server failed to start')
            server = start()
            try:
                with httpx.Client(base_url=f'http://127.0.0.1:{port}') as client:
                    self.assertEqual(client.post('/api/login',json={'username':'admin','password':'test password'}).status_code,200)
                    gallery = client.post('/api/galleries',json={'name':'Persistent'}).json()['id']
                    image = io.BytesIO(); Image.new('RGB',(32,32)).save(image,format='PNG')
                    response = client.post('/api/photos',params={'gallery_id':gallery},files={'files':('blank.png',image.getvalue(),'image/png')},timeout=30)
                    self.assertEqual(response.json(),[{'name':'blank.png','faces':0}])
                    server.terminate(); server.wait(timeout=5); server = start()
                    photos = client.get('/api/photos',params={'gallery_id':gallery}).json()
                    self.assertEqual(len(photos),1)
                    self.assertEqual(client.get(f"/api/photos/{photos[0]['id']}/image").status_code,200)
            finally:
                server.terminate(); server.wait(timeout=5)
