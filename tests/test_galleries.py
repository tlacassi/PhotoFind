import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
import app
import auth
import storage


class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        database = root / 'photos.db'
        auth.initialize(database)
        storage.initialize(database)
        for name, role in [('admin', 'admin'), ('alice', 'photographer'), ('bob', 'photographer')]:
            auth.create_user(database, name, 'test password', role)
        for obj, key, value in [(app, 'DB', database), (app, 'PHOTOS', root), (app.app.state, 'db_path', database)]:
            patcher = patch.object(obj, key, value); patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(app, 'embeddings', return_value=[[1., 0.]])
        patcher.start(); self.addCleanup(patcher.stop)
        self.admin = self.login('admin'); self.alice = self.login('alice'); self.bob = self.login('bob')
        self.a = self.alice.post('/api/galleries', json={'name':'Alice'}).json()['id']
        self.b = self.bob.post('/api/galleries', json={'name':'Bob'}).json()['id']
        buffer = io.BytesIO(); Image.new('RGB', (16, 16)).save(buffer, format='PNG'); self.image = buffer.getvalue()

    def login(self, name):
        client = TestClient(app.app)
        self.assertEqual(client.post('/api/login', json={'username':name,'password':'test password'}).status_code, 200)
        return client

    def upload(self, client, gallery):
        response = client.post('/api/photos', params={'gallery_id':gallery}, files={'files':('photo.png',self.image,'image/png')})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('error', response.json()[0])
        return client.get('/api/photos', params={'gallery_id':gallery}).json()[0]['id']

    def client_for(self, photographer, gallery):
        link = photographer.post('/api/client-links', json={'gallery_id':gallery, 'days':1}).json()['token']
        client = TestClient(app.app)
        self.assertEqual(client.post('/api/client/redeem', json={'token':link}).status_code, 200)
        return client, app.digest(link)

    def test_photographers_and_clients_are_isolated(self):
        photo_a = self.upload(self.alice, self.a); photo_b = self.upload(self.bob, self.b)
        self.assertEqual([g['id'] for g in self.alice.get('/api/galleries').json()], [self.a])
        for method, path, kwargs in [('GET','/api/photos', {'params':{'gallery_id':self.b}}), ('GET',f'/api/photos/{photo_b}/image', {}), ('DELETE',f'/api/photos/{photo_b}', {}), ('DELETE','/api/photos', {'params':{'gallery_id':self.b}}), ('POST','/api/client-links', {'json':{'gallery_id':self.b}}), ('POST','/api/photos', {'params':{'gallery_id':self.b}, 'files':{'files':('a.png',self.image)}})]:
            self.assertEqual(self.alice.request(method, path, **kwargs).status_code, 404, path)
        client_a, link_a = self.client_for(self.alice, self.a); client_b, _ = self.client_for(self.bob, self.b)
        for client, expected, forbidden in [(client_a,photo_a,photo_b), (client_b,photo_b,photo_a)]:
            self.assertEqual(client.get(f'/api/client/photos/{expected}/image').status_code, 404)
            response = client.post('/api/search', files={'file':('selfie.png', self.image)})
            self.assertEqual([row['id'] for row in response.json()], [expected])
            self.assertEqual(client.get(f'/api/client/photos/{expected}/image').status_code, 200)
            self.assertEqual(client.get(f'/api/client/photos/{forbidden}/image').status_code, 404)
            self.assertEqual(client.delete(f'/api/photos/{expected}').status_code, 401)
        self.assertEqual(self.bob.delete(f'/api/client-links/{link_a}').status_code, 404)
        self.alice.delete(f'/api/client-links/{link_a}')
        self.assertEqual(client_a.get('/api/client/session').status_code, 401)
        self.assertEqual(client_a.get(f'/api/client/photos/{photo_a}/image').status_code, 401)

    def test_gallery_creation_and_thumbnail_selection(self):
        response = self.alice.post('/api/galleries', json={'name':' New gallery '})
        self.assertEqual(response.status_code, 201)
        gallery = response.json()['id']
        self.assertEqual(response.json()['name'], 'New gallery')
        first = self.upload(self.alice, gallery)
        second = self.upload(self.alice, gallery)
        self.assertNotEqual(first, second)
        def thumbnail():
            return next(row for row in self.alice.get('/api/galleries').json() if row['id']==gallery)['thumbnail_id']
        self.assertEqual(thumbnail(), second)
        self.assertEqual(self.alice.patch(f'/api/galleries/{gallery}', json={'cover_photo_id':first}).status_code, 200)
        self.assertEqual(thumbnail(), first)
        foreign = self.upload(self.bob, self.b)
        self.assertEqual(self.alice.patch(f'/api/galleries/{gallery}', json={'cover_photo_id':foreign}).status_code, 400)
        self.alice.delete(f'/api/photos/{first}')
        self.assertEqual(thumbnail(), second)
        self.alice.patch(f'/api/galleries/{gallery}', json={'cover_photo_id':None})
        self.assertEqual(thumbnail(), second)
        self.assertEqual(self.alice.post('/api/galleries', json={'name':'   '}).status_code, 400)

    def test_archive_preserves_photos_and_revokes_links(self):
        photo = self.upload(self.alice, self.a); client, _ = self.client_for(self.alice, self.a)
        self.assertEqual(self.alice.patch(f'/api/galleries/{self.a}', json={'name':'Renamed','archived':True}).status_code, 200)
        self.assertEqual(client.get('/api/client/session').status_code, 401)
        self.assertEqual(self.alice.post('/api/client-links', json={'gallery_id':self.a}).status_code, 409)
        self.assertEqual(self.alice.delete(f'/api/photos/{photo}').status_code, 409)
        self.assertEqual(len(self.alice.get('/api/photos', params={'gallery_id':self.a}).json()), 1)
        self.alice.patch(f'/api/galleries/{self.a}', json={'archived':False})
        self.assertEqual(client.get('/api/client/session').status_code, 401)
        self.assertEqual(self.alice.get(f'/api/photos/{photo}/image').status_code, 200)

    def test_explicit_collaboration_and_revocation(self):
        self.assertEqual(self.bob.get('/api/photos', params={'gallery_id':self.a}).status_code, 404)
        self.alice.post(f'/api/galleries/{self.a}/members', json={'username':'bob'})
        self.assertEqual(self.bob.get('/api/photos', params={'gallery_id':self.a}).status_code, 200)
        self.assertEqual(self.bob.patch(f'/api/galleries/{self.a}', json={'name':'Hijack'}).status_code, 404)
        bob_id = self.bob.get('/api/me').json()['id']
        self.alice.delete(f'/api/galleries/{self.a}/members/{bob_id}')
        self.assertEqual(self.bob.get('/api/photos', params={'gallery_id':self.a}).status_code, 404)

    def test_admin_permissions_and_account_lifecycle(self):
        self.assertEqual(self.alice.get('/admin').status_code, 403)
        self.assertEqual(self.alice.get('/api/users').status_code, 403)
        users = self.admin.get('/api/users').json(); alice_id = next(u['id'] for u in users if u['username']=='alice')
        admin_id = next(u['id'] for u in users if u['username']=='admin')
        self.assertNotIn('password_hash', users[0])
        self.assertEqual(self.admin.patch(f'/api/users/{admin_id}', json={'active':False}).status_code, 400)
        self.assertEqual(self.admin.patch(f'/api/users/{admin_id}', json={'role':'photographer'}).status_code, 400)
        self.assertEqual(self.admin.patch(f'/api/users/{alice_id}', json={'can_upload':False,'can_create_galleries':False,'can_share':False,'can_delete':False}).status_code, 200)
        self.assertEqual(self.alice.get('/api/me').status_code, 401)
        self.alice = self.login('alice')
        self.assertEqual(self.alice.post('/api/galleries', json={'name':'No'}).status_code, 403)
        self.assertEqual(self.alice.post('/api/photos', params={'gallery_id':self.a}, files={'files':('a.png',self.image)}).status_code, 403)
        self.assertEqual(self.alice.post('/api/client-links', json={'gallery_id':self.a}).status_code, 403)
        self.assertEqual(self.alice.delete('/api/photos', params={'gallery_id':self.a}).status_code, 403)
        self.admin.patch(f'/api/users/{alice_id}', json={'password':'new test password', 'active':False})
        self.assertEqual(self.alice.get('/api/me').status_code, 401)
        self.assertEqual(TestClient(app.app).post('/api/login', json={'username':'alice','password':'new test password'}).status_code, 401)
        self.admin.patch(f'/api/users/{alice_id}', json={'active':True})
        self.assertEqual(TestClient(app.app).post('/api/login', json={'username':'alice','password':'test password'}).status_code, 401)
        client = TestClient(app.app)
        self.assertEqual(client.post('/api/login', json={'username':'alice','password':'new test password'}).status_code, 200)
        self.admin.delete(f'/api/users/{alice_id}/sessions')
        self.assertEqual(client.get('/api/me').status_code, 401)

    def test_login_rate_limit_and_secure_cookies(self):
        client = TestClient(app.app)
        for _ in range(10):
            self.assertEqual(client.post('/api/login', json={'username':'missing','password':'wrong'}).status_code, 401)
        self.assertEqual(client.post('/api/login', json={'username':'missing','password':'wrong'}).status_code, 429)
        with patch.dict('os.environ', {'SECURE_COOKIES':'true'}):
            response = client.post('/api/login', json={'username':'admin','password':'test password'})
            self.assertIn('Secure', response.headers['set-cookie'])
            self.assertIn('HttpOnly', response.headers['set-cookie'])
            self.assertIn('SameSite=strict', response.headers['set-cookie'])


class MigrationTests(unittest.TestCase):
    def test_legacy_photo_and_link_migrate_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'photos.db'
            auth.initialize(path); auth.create_user(path, 'admin', 'test password', 'admin')
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE photos (id TEXT PRIMARY KEY,name TEXT,faces TEXT)')
                db.execute("INSERT INTO photos VALUES ('old','Existing','[[1,0]]')")
                db.execute('CREATE TABLE client_links (token_hash TEXT PRIMARY KEY,expires INTEGER)')
                db.execute("INSERT INTO client_links VALUES ('old-link',9999999999)")
            storage.initialize(path); storage.initialize(path)
            with storage.connect(path) as db:
                self.assertEqual(db.execute('SELECT gallery_id FROM photos').fetchone()[0], 'legacy')
                self.assertEqual(db.execute('SELECT faces FROM photos').fetchone()[0], '[[1,0]]')
                self.assertEqual(db.execute('SELECT gallery_id FROM client_links').fetchone()[0], 'legacy')
                self.assertEqual(db.execute('SELECT owner_id FROM galleries').fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT count(*) FROM galleries').fetchone()[0], 1)
