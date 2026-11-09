import asyncio
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from starlette.datastructures import UploadFile
import app


class UploadTests(unittest.TestCase):
    def test_analysis_runs_off_event_loop_and_persists_photo(self):
        main_thread = threading.get_ident()
        workers = []
        buffer = io.BytesIO()
        Image.new('RGB', (16, 16)).save(buffer, format='PNG')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / 'photos.db'
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE photos (id TEXT PRIMARY KEY, name TEXT, faces TEXT)')
            def analyze(contents):
                workers.append(threading.get_ident())
                return []
            with patch.object(app, 'DB', database), patch.object(app, 'PHOTOS', root), patch.object(app, 'embeddings', analyze):
                result = asyncio.run(app.upload([UploadFile(io.BytesIO(buffer.getvalue()), filename='sample.png')], user=None))
                self.assertEqual(result, [{'name': 'sample.png', 'faces': 0}])
                self.assertNotEqual(workers, [main_thread])
                with sqlite3.connect(database) as db:
                    row = db.execute('SELECT id, name, faces FROM photos').fetchone()
                self.assertTrue((root / (row[0] + '.jpg')).is_file())
                self.assertEqual(json.loads(row[2]), [])

    def test_invalid_photo_does_not_prevent_next_upload(self):
        with patch.object(app, 'embeddings', side_effect=ValueError('Invalid image')):
            files = [UploadFile(io.BytesIO(b'bad'), filename=name) for name in ['first.png', 'second.png']]
            result = asyncio.run(app.upload(files, user=None))
            self.assertEqual(len(result), 2)
            self.assertTrue(all('error' in item for item in result))
