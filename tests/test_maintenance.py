import json
import tempfile
import unittest
from pathlib import Path

import auth
import maintenance
import storage


class MaintenanceTests(unittest.TestCase):
    def test_restore_and_detect_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); data = root / 'data'; data.mkdir(); (data / 'photos').mkdir()
            auth.initialize(data / 'photos.db'); storage.initialize(data / 'photos.db')
            photo_id = 'a' * 32
            (data / 'photos' / (photo_id + '.jpg')).write_bytes(b'fixture-photo')
            with storage.connect(data / 'photos.db') as db:
                db.execute("INSERT INTO galleries(id,name,owner_id,archived) VALUES ('g','Gallery',NULL,0)")
                db.execute('INSERT INTO photos VALUES (?,?,?,?)', (photo_id,'Saved','[]','g'))
            maintenance.backup(data, root / 'backup')
            maintenance.restore(root / 'backup', root / 'restored')
            storage.initialize(root / 'restored' / 'photos.db')
            self.assertEqual((root / 'restored' / 'photos' / (photo_id + '.jpg')).read_bytes(), b'fixture-photo')
            with self.assertRaises(ValueError):
                maintenance.restore(root / 'backup', data)
            (root / 'backup' / 'photos' / (photo_id + '.jpg')).write_bytes(b'corrupt')
            with self.assertRaises(ValueError):
                maintenance.restore(root / 'backup', root / 'bad-restore')

    def test_refuse_backup_while_running(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with storage.application_lock(root):
                with self.assertRaises(RuntimeError):
                    maintenance.backup(root, root.parent / 'should-not-exist')
