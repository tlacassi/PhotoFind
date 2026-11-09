import io
import shutil
import logging
import json
import os
import sqlite3
import threading
import uuid
import secrets
import hashlib
import time
from typing import Literal

import auth
import storage
from pathlib import Path

import cv2
import numpy as np
import qrcode
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, Query
from fastapi.responses import FileResponse, Response, RedirectResponse
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('DATA_DIR', ROOT / 'data'))
MODELS = Path(os.environ.get('MODEL_DIR', ROOT / 'models'))
PHOTOS = DATA / 'photos'
PHOTOS.mkdir(parents=True, exist_ok=True)
DB = DATA / 'photos.db'
_application_lock = storage.application_lock(DATA)
THRESHOLD = float(os.environ.get('MATCH_THRESHOLD', '0.363'))
MAX_BYTES = 20 * 1024 * 1024
lock = threading.Lock()
ANALYSIS_WORKERS = max(1, int(os.environ.get('ANALYSIS_WORKERS', '2')))
analysis_slots = threading.BoundedSemaphore(ANALYSIS_WORKERS)
# Avoid multiplying OpenCV's internal threads for each concurrent image.
cv2.setNumThreads(max(1, int(os.environ.get('OPENCV_THREADS', '1'))))
app = FastAPI(title='PhotoFind')
app.state.db_path = DB
auth.initialize(DB)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


def connect():
    return storage.connect(DB)


storage.initialize(DB)
storage.organize_photos(DB, PHOTOS)


def read_image(contents):
    if len(contents) > MAX_BYTES:
        raise ValueError('Image trop volumineuse (maximum 20 Mo).')
    try:
        with Image.open(io.BytesIO(contents)) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((2400, 2400))
            return cv2.cvtColor(np.array(img.convert('RGB')), cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError('Format non pris en charge. Utilisez une image JPEG, PNG ou WebP.')


def embeddings(contents):
    image = read_image(contents)
    detector_path = MODELS / 'face_detection_yunet_2023mar.onnx'
    recognizer_path = MODELS / 'face_recognition_sface_2021dec.onnx'
    if not detector_path.is_file() or not recognizer_path.is_file():
        raise RuntimeError('Modèles absents. Lancez d’abord : python download_models.py')
    # OpenCV objects have mutable internal state; each request gets its own instances.
    detector = cv2.FaceDetectorYN.create(str(detector_path), '', (image.shape[1], image.shape[0]), 0.9, 0.3, 5000)
    recognizer = cv2.FaceRecognizerSF.create(str(recognizer_path), '')
    _, faces = detector.detect(image)
    if faces is None:
        return []
    result = []
    for face in faces:
        aligned = recognizer.alignCrop(image, face)
        feature = recognizer.feature(aligned).flatten()
        norm = np.linalg.norm(feature)
        if norm:
            result.append((feature / norm).tolist())
    return result


async def image_bytes(file):
    contents = await file.read(MAX_BYTES + 1)
    if not contents:
        raise HTTPException(400, 'Image vide.')
    if len(contents) > MAX_BYTES:
        raise HTTPException(400, 'Image trop volumineuse (maximum 20 Mo).')
    return contents


class Credentials(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


@app.get('/')
def index(request: Request):
    try:
        auth.current_user(request)
    except HTTPException:
        return RedirectResponse('/login', status_code=303)
    return FileResponse(ROOT / 'static' / 'index.html')


@app.get('/login')
def login_page():
    return FileResponse(ROOT / 'static' / 'login.html')


@app.post('/api/login')
def login(credentials: Credentials, request: Request, response: Response):
    auth.login_allowed(DB, credentials.username)
    user = auth.authenticate(DB, credentials.username, credentials.password)
    if not user:
        raise HTTPException(401, 'Identifiant ou mot de passe incorrect.')
    auth.clear_attempts(DB, credentials.username)
    token = auth.new_session(DB, user['id'])
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite='strict', secure=os.environ.get('SECURE_COOKIES', '').lower() == 'true' or request.url.scheme == 'https', max_age=auth.SESSION_SECONDS, path='/')
    return auth.public_user(user)


@app.post('/api/logout')
def logout(request: Request, response: Response, user=Depends(auth.current_user)):
    token = request.cookies.get(auth.COOKIE, '')
    import hashlib
    with auth.connect(DB) as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(auth.COOKIE, path='/')
    return {'ok': True}


@app.get('/api/me')
def me(user=Depends(auth.current_user)):
    with connect() as db:
        return dict(auth.public_user(user), used_bytes=auth.storage_usage(db, user['id']))




class AccountCreate(Credentials):
    role: str = 'photographer'
    quota_bytes: int | None = Field(default=5 * 1024**3, ge=0)


class AccountUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=64)
    role: str | None = None
    active: bool | None = None
    can_create_galleries: bool | None = None
    can_upload: bool | None = None
    can_delete: bool | None = None
    can_share: bool | None = None
    quota_bytes: int | None = Field(default=None, ge=0)
    password: str | None = Field(default=None, min_length=8, max_length=256)


@app.get('/admin')
def admin_page(request: Request):
    auth.admin_user(request)
    return FileResponse(ROOT / 'static' / 'admin.html', headers={'Cache-Control': 'no-store'})


@app.get('/api/users')
def users(user=Depends(auth.admin_user)):
    with connect() as db:
        return [dict(auth.public_user(row), used_bytes=auth.storage_usage(db, row['id'])) for row in db.execute('SELECT * FROM users ORDER BY username')]


@app.post('/api/users', status_code=201)
def create_account(payload: AccountCreate, user=Depends(auth.admin_user)):
    if payload.role not in ('admin', 'photographer'):
        raise HTTPException(400, 'Rôle invalide.')
    try:
        auth.create_user(DB, payload.username, payload.password, payload.role, quota_bytes=payload.quota_bytes)
    except ValueError as error:
        raise HTTPException(400, str(error))
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Cet identifiant existe déjà.')
    return {'username': payload.username, 'role': payload.role}


@app.patch('/api/users/{user_id}')
def update_account(user_id: int, payload: AccountUpdate, user=Depends(auth.admin_user)):
    values = payload.model_dump(exclude_none=True)
    if 'quota_bytes' in payload.model_fields_set:
        values['quota_bytes'] = payload.quota_bytes
    if 'role' in values and values['role'] not in ('admin', 'photographer'):
        raise HTTPException(400, 'Rôle invalide.')
    try:
        if 'username' in values:
            auth.validate_credentials(values['username'], 'validation-only')
        if 'password' in values:
            values['password_hash'] = auth.hash_password(values.pop('password'))
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            target = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            if target is None:
                raise HTTPException(404, 'Compte introuvable.')
            disabling = values.get('active') is False or values.get('role') == 'photographer'
            if disabling and target['role'] == 'admin':
                count = db.execute("SELECT count(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
                if user_id == user['id'] or (target['active'] and count <= 1):
                    raise HTTPException(400, 'Conservez votre compte administrateur actif.')
            if values:
                assignments = ','.join(f'{key}=?' for key in values)
                db.execute(f'UPDATE users SET {assignments} WHERE id=?', (*values.values(), user_id))
                db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
                if values.get('active') is False:
                    db.execute('UPDATE client_links SET expires=0 WHERE gallery_id IN (SELECT id FROM galleries WHERE owner_id=?)', (user_id,))
            return auth.public_user(db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())
    except ValueError as error:
        raise HTTPException(400, str(error))
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Cet identifiant existe déjà.')


@app.delete('/api/users/{user_id}/sessions')
def revoke_sessions(user_id: int, user=Depends(auth.admin_user)):
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
    return {'ok': True}


class GalleryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class GalleryUpdate(BaseModel):
    cover_photo_id: str | None = Field(default=None, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    archived: bool | None = None


def gallery_access(db, gallery_id, user, permission=None, write=False, owner=False):
    current = db.execute('SELECT * FROM users WHERE id=? AND active=1', (user['id'],)).fetchone()
    if current is None:
        raise HTTPException(401, 'Connexion requise.')
    user = current
    gallery = db.execute('SELECT * FROM galleries WHERE id=?', (gallery_id,)).fetchone()
    if gallery is None:
        raise HTTPException(404, 'Galerie introuvable.')
    if user['role'] != 'admin' and gallery['owner_id'] != user['id']:
        if owner or not db.execute('SELECT 1 FROM gallery_members WHERE gallery_id=? AND user_id=?', (gallery_id, user['id'])).fetchone():
            raise HTTPException(404, 'Galerie introuvable.')
    if permission:
        auth.require_permission(user, permission)
    if write and gallery['archived']:
        raise HTTPException(409, 'Cette galerie est désactivée.')
    return gallery


@app.get('/api/galleries')
def galleries(user=Depends(auth.current_user)):
    with connect() as db:
        rows = db.execute('SELECT g.*, (SELECT count(*) FROM photos WHERE gallery_id=g.id) AS photo_count, COALESCE((SELECT p.id FROM photos p WHERE p.id=g.cover_photo_id AND p.gallery_id=g.id), (SELECT p.id FROM photos p WHERE p.gallery_id=g.id ORDER BY p.rowid DESC LIMIT 1)) AS thumbnail_id FROM galleries g WHERE ? OR g.owner_id=? OR EXISTS (SELECT 1 FROM gallery_members m WHERE m.gallery_id=g.id AND m.user_id=?) ORDER BY g.rowid DESC', (user['role'] == 'admin', user['id'], user['id'])).fetchall()
        return [dict(row) for row in rows]


@app.post('/api/galleries', status_code=201)
def create_gallery(payload: GalleryCreate, user=Depends(auth.current_user)):
    auth.require_permission(user, 'can_create_galleries')
    if not payload.name.strip():
        raise HTTPException(400, 'Donnez un nom à la galerie.')
    gallery_id = uuid.uuid4().hex
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        user_root = storage.user_directory(db, PHOTOS, user['id'])
        user_root.mkdir(parents=True, exist_ok=True)
        folder = storage.allocate_gallery_directory(db, user_root, payload.name.strip(), user['id'])
        db.execute('INSERT INTO galleries(id,name,owner_id,storage_name) VALUES (?,?,?,?)', (gallery_id, payload.name.strip(), user['id'], folder))
    return {'id': gallery_id, 'name': payload.name.strip(), 'owner_id': user['id'], 'archived': 0, 'photo_count': 0, 'storage_name':folder}


@app.patch('/api/galleries/{gallery_id}')
def update_gallery(gallery_id: str, payload: GalleryUpdate, user=Depends(auth.current_user)):
    if payload.name is not None and not payload.name.strip():
        raise HTTPException(400, 'Donnez un nom à la galerie.')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        gallery_access(db, gallery_id, user, 'can_create_galleries', owner=True)
        if 'cover_photo_id' in payload.model_fields_set:
            if payload.cover_photo_id is not None and not db.execute('SELECT 1 FROM photos WHERE id=? AND gallery_id=?', (payload.cover_photo_id, gallery_id)).fetchone():
                raise HTTPException(400, 'Choisissez une photo de cette galerie.')
            db.execute('UPDATE galleries SET cover_photo_id=? WHERE id=?', (payload.cover_photo_id, gallery_id))
        if payload.name is not None:
            db.execute('UPDATE galleries SET name=? WHERE id=?', (payload.name.strip(), gallery_id))
        if payload.archived is not None:
            db.execute('UPDATE galleries SET archived=? WHERE id=?', (payload.archived, gallery_id))
            if payload.archived:
                db.execute('UPDATE client_links SET expires=0 WHERE gallery_id=?', (gallery_id,))
    return {'ok': True}


@app.delete('/api/galleries/{gallery_id}')
def delete_gallery(gallery_id: str, user=Depends(auth.current_user)):
    with lock, connect() as db:
        db.execute('BEGIN IMMEDIATE')
        gallery_access(db, gallery_id, user, 'can_delete', owner=True)
        directory = storage.gallery_directory(db, PHOTOS, gallery_id)
        if directory.is_symlink():
            raise HTTPException(409, 'Le dossier de la galerie est un lien symbolique ; suppression refusée.')
        count = db.execute('SELECT count(*) FROM photos WHERE gallery_id=?', (gallery_id,)).fetchone()[0]
        tombstone = PHOTOS / ('.deleted-' + uuid.uuid4().hex)
        moved = directory.exists()
        if moved:
            directory.rename(tombstone)
        try:
            db.execute('DELETE FROM client_matches WHERE photo_id IN (SELECT id FROM photos WHERE gallery_id=?) OR session_hash IN (SELECT s.token_hash FROM client_sessions s JOIN client_links l ON l.token_hash=s.link_hash WHERE l.gallery_id=?)', (gallery_id, gallery_id))
            db.execute('DELETE FROM client_sessions WHERE link_hash IN (SELECT token_hash FROM client_links WHERE gallery_id=?)', (gallery_id,))
            db.execute('DELETE FROM client_links WHERE gallery_id=?', (gallery_id,))
            db.execute('DELETE FROM photos WHERE gallery_id=?', (gallery_id,))
            db.execute('DELETE FROM gallery_members WHERE gallery_id=?', (gallery_id,))
            db.execute('DELETE FROM galleries WHERE id=?', (gallery_id,))
            db.commit()
        except Exception:
            if moved:
                tombstone.rename(directory)
            raise
    cleanup_pending = False
    if moved:
        try:
            shutil.rmtree(tombstone)
        except OSError:
            logging.exception('Gallery deleted but disk cleanup failed for %s', tombstone.name)
            cleanup_pending = True
    return {'deleted': True, 'photos_deleted': count, 'cleanup_pending': cleanup_pending}


class Member(BaseModel):
    username: str = Field(min_length=3, max_length=64)


@app.get('/api/galleries/{gallery_id}/members')
def gallery_members(gallery_id: str, user=Depends(auth.current_user)):
    with connect() as db:
        gallery_access(db, gallery_id, user, owner=True)
        return [dict(row) for row in db.execute('SELECT u.id,u.username FROM gallery_members m JOIN users u ON u.id=m.user_id WHERE m.gallery_id=?', (gallery_id,))]


@app.post('/api/galleries/{gallery_id}/members')
def add_member(gallery_id: str, payload: Member, user=Depends(auth.current_user)):
    with connect() as db:
        gallery_access(db, gallery_id, user, 'can_share', write=True, owner=True)
        member = db.execute("SELECT id FROM users WHERE username=? AND active=1 AND role='photographer'", (payload.username,)).fetchone()
        if member is None:
            raise HTTPException(404, 'Photographe actif introuvable.')
        db.execute('INSERT OR IGNORE INTO gallery_members VALUES (?,?)', (gallery_id, member['id']))
    return {'ok': True}


@app.delete('/api/galleries/{gallery_id}/members/{member_id}')
def remove_member(gallery_id: str, member_id: int, user=Depends(auth.current_user)):
    with connect() as db:
        gallery_access(db, gallery_id, user, 'can_share', owner=True)
        db.execute('DELETE FROM gallery_members WHERE gallery_id=? AND user_id=?', (gallery_id, member_id))
        # Removing a collaborator also revokes links they might have copied.
        db.execute('UPDATE client_links SET expires=0 WHERE gallery_id=?', (gallery_id,))
    return {'ok': True}


class LinkCreate(BaseModel):
    mode: Literal['gallery', 'search', 'both'] = 'search'
    gallery_id: str
    days: int = Field(default=7, ge=1, le=90)


@app.get('/api/client-links')
def list_links(gallery_id: str, user=Depends(auth.current_user)):
    with connect() as db:
        gallery_access(db, gallery_id, user, 'can_share')
        return [dict(row) for row in db.execute('SELECT token_hash AS id, expires, mode FROM client_links WHERE gallery_id=? ORDER BY rowid DESC', (gallery_id,))]


@app.delete('/api/client-links/{link_id}')
def revoke_link(link_id: str, user=Depends(auth.current_user)):
    with connect() as db:
        row = db.execute('SELECT gallery_id FROM client_links WHERE token_hash=?', (link_id,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Lien introuvable.')
        gallery_access(db, row['gallery_id'], user, 'can_share')
        db.execute('UPDATE client_links SET expires=0 WHERE token_hash=?', (link_id,))
    return {'ok': True}


class InvitationCreate(BaseModel):
    days: int = Field(default=7, ge=1, le=30)
    quota_bytes: int = Field(default=5 * 1024**3, ge=0)


class InvitationToken(BaseModel):
    token: str = Field(min_length=20, max_length=128)


class Registration(Credentials, InvitationToken):
    pass


@app.get('/invite')
def invitation_page():
    return FileResponse(ROOT / 'static' / 'invite.html', headers={'Cache-Control':'no-store', 'Referrer-Policy':'no-referrer'})


@app.post('/api/invitations', status_code=201)
def create_invitation(payload: InvitationCreate, user=Depends(auth.admin_user)):
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('INSERT INTO invitations(token_hash,expires,quota_bytes) VALUES (?,?,?)', (digest(token), int(time.time()) + payload.days * 86400, payload.quota_bytes))
    return {'token':token, 'days':payload.days, 'quota_bytes':payload.quota_bytes}


@app.get('/api/invitations')
def invitations(user=Depends(auth.admin_user)):
    with connect() as db:
        return [dict(row) for row in db.execute('SELECT token_hash AS id,expires,quota_bytes,used FROM invitations ORDER BY rowid DESC')]


@app.delete('/api/invitations/{invitation_id}')
def revoke_invitation(invitation_id: str, user=Depends(auth.admin_user)):
    with connect() as db:
        db.execute('UPDATE invitations SET expires=0 WHERE token_hash=?', (invitation_id,))
    return {'ok':True}


def invitation_valid(db, token_hash):
    row = db.execute('SELECT * FROM invitations WHERE token_hash=? AND used=0 AND expires>?', (token_hash, int(time.time()))).fetchone()
    if row is None:
        raise HTTPException(400, 'Invitation invalide, expirée ou déjà utilisée.')
    return row


@app.post('/api/invitations/check')
def check_invitation(payload: InvitationToken):
    with connect() as db:
        row = invitation_valid(db, digest(payload.token))
        return {'quota_bytes':row['quota_bytes'], 'expires':row['expires']}


@app.post('/api/register', status_code=201)
def register(payload: Registration):
    try:
        auth.validate_credentials(payload.username, payload.password)
    except ValueError as error:
        raise HTTPException(400, str(error))
    with connect() as db:
        invitation_valid(db, digest(payload.token))
    hashed = auth.hash_password(payload.password)
    try:
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            invitation = invitation_valid(db, digest(payload.token))
            cursor = db.execute("INSERT INTO users(username,password_hash,role,quota_bytes) VALUES (?,?,'photographer',?)", (payload.username, hashed, invitation['quota_bytes']))
            auth.initialize_user_directory(db, PHOTOS, cursor.lastrowid, payload.username)
            db.execute('UPDATE invitations SET used=1 WHERE token_hash=?', (digest(payload.token),))
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Cet identifiant existe déjà.')
    return {'ok':True}


def digest(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def client_session(request: Request):
    token = request.cookies.get('photofind_client', '')
    if len(token) > 128:
        raise HTTPException(401, 'Lien client invalide ou expiré.')
    session_hash = digest(token)
    with connect() as db:
        row = db.execute('SELECT s.token_hash, l.gallery_id, l.mode, g.name AS gallery_name FROM client_sessions s JOIN client_links l ON l.token_hash=s.link_hash JOIN galleries g ON g.id=l.gallery_id LEFT JOIN users u ON u.id=g.owner_id WHERE s.token_hash=? AND s.expires>? AND l.expires>? AND g.archived=0 AND (g.owner_id IS NULL OR u.active=1)', (session_hash, int(time.time()), int(time.time()))).fetchone()
    if row is None:
        raise HTTPException(401, 'Lien client invalide ou expiré.')
    expected_gallery = request.query_params.get('gallery_id')
    if expected_gallery is not None and expected_gallery != row['gallery_id']:
        raise HTTPException(401, 'Ce lien ne correspond pas à la galerie de cette session.')
    return dict(row)


class ClientToken(BaseModel):
    gallery_id: str | None = Field(default=None, max_length=64)
    token: str = Field(max_length=128)


@app.get('/client')
@app.get('/client/{gallery_id}')
def client_page(gallery_id: str | None = None):
    return FileResponse(ROOT / 'static' / 'client.html', headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})


@app.post('/api/client-links')
def create_client_link(payload: LinkCreate, user=Depends(auth.current_user)):
    token = secrets.token_urlsafe(32)
    with connect() as db:
        gallery_access(db, payload.gallery_id, user, 'can_share', write=True)
        db.execute('INSERT INTO client_links(token_hash,expires,gallery_id,mode) VALUES (?,?,?,?)', (digest(token), int(time.time()) + payload.days * 86400, payload.gallery_id, payload.mode))
    return {'token': token, 'expires_in_days': payload.days, 'path': '/client/' + payload.gallery_id, 'mode':payload.mode}


@app.get('/api/client/session')
def client_session_status(session=Depends(client_session)):
    return {'ok': True, 'gallery_id': session['gallery_id'], 'mode':session['mode'], 'gallery_name':session['gallery_name']}


@app.post('/api/client/redeem')
def redeem_client_link(payload: ClientToken, request: Request, response: Response):
    link_hash = digest(payload.token)
    now = int(time.time())
    with connect() as db:
        row = db.execute('SELECT l.expires, l.gallery_id, l.mode, g.name AS gallery_name FROM client_links l JOIN galleries g ON g.id=l.gallery_id LEFT JOIN users u ON u.id=g.owner_id WHERE l.token_hash=? AND l.expires>? AND g.archived=0 AND (g.owner_id IS NULL OR u.active=1)', (link_hash, now)).fetchone()
        if row is None or (payload.gallery_id is not None and payload.gallery_id != row['gallery_id']):
            raise HTTPException(401, 'Lien client invalide pour cette galerie ou expiré.')
        session = secrets.token_urlsafe(32)
        db.execute('INSERT INTO client_sessions VALUES (?, ?, ?)', (digest(session), link_hash, min(row['expires'], now + 8 * 3600)))
    response.set_cookie('photofind_client', session, httponly=True, secure=os.environ.get('SECURE_COOKIES', '').lower() == 'true' or request.url.scheme == 'https', samesite='strict', max_age=8 * 3600, path='/')
    response.headers['Cache-Control'] = 'no-store'
    return {'ok': True, 'gallery_id': row['gallery_id'], 'mode':row['mode'], 'gallery_name':row['gallery_name']}


@app.post('/api/client-qr')
def client_qr(payload: ClientToken, request: Request, user=Depends(auth.current_user)):
    with connect() as db:
        link = db.execute('SELECT gallery_id FROM client_links WHERE token_hash=? AND expires>?', (digest(payload.token), int(time.time()))).fetchone()
        if link is None:
            raise HTTPException(404, 'Lien invalide.')
        gallery_access(db, link['gallery_id'], user, 'can_share', write=True)
    origin = request.headers.get('origin', '')
    from urllib.parse import urlsplit
    parsed = urlsplit(origin)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise HTTPException(400, 'Origine invalide.')
    image = qrcode.make(origin + '/client/' + link['gallery_id'] + '#' + payload.token)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return Response(buffer.getvalue(), media_type='image/png', headers={'Cache-Control': 'no-store'})


@app.get('/api/photos')
def list_photos(gallery_id: str, user=Depends(auth.current_user)):
    with connect() as db:
        gallery_access(db, gallery_id, user)
        rows = db.execute('SELECT id, name, faces FROM photos WHERE gallery_id=? ORDER BY rowid DESC', (gallery_id,)).fetchall()
    return [{'id': r['id'], 'name': r['name'], 'faces': len(json.loads(r['faces']))} for r in rows]


def process_photo(contents, filename, gallery_id, user):
    # Network reception can continue while this bounded worker does CPU and disk work.
    with analysis_slots:
        faces = embeddings(contents)
        image = read_image(contents)
        ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok:
            raise ValueError('Impossible de lire cette image.')
        photo_id = uuid.uuid4().hex
        with lock, connect() as db:
            db.execute('BEGIN IMMEDIATE')
            gallery = gallery_access(db, gallery_id, user, 'can_upload', write=True)
            owner = db.execute('SELECT id,quota_bytes FROM users WHERE id=?', (gallery['owner_id'],)).fetchone()
            if owner and owner['quota_bytes'] is not None and auth.storage_usage(db, owner['id']) + encoded.nbytes > owner['quota_bytes']:
                raise HTTPException(413, 'Quota de stockage de la galerie dépassé.')
            directory = storage.gallery_directory(db, PHOTOS, gallery_id)
            directory.mkdir(exist_ok=True)
            path = directory / (photo_id + '.jpg')
            path.write_bytes(encoded.tobytes())
            try:
                db.execute('INSERT INTO photos(id,name,faces,gallery_id,bytes) VALUES (?,?,?,?,?)', (photo_id, Path(filename or 'Photo').name, json.dumps(faces), gallery_id, encoded.nbytes))
                db.commit()
            except Exception:
                path.unlink(missing_ok=True)
                raise
        return {'name': filename, 'faces': len(faces)}


@app.post('/api/photos')
async def upload(gallery_id: str, files: list[UploadFile] = File(...), user=Depends(auth.current_user)):
    with connect() as db:
        gallery_access(db, gallery_id, user, 'can_upload', write=True)
    results = []
    for file in files:
        try:
            contents = await image_bytes(file)
            results.append(await run_in_threadpool(process_photo, contents, file.filename, gallery_id, user))
        except (ValueError, HTTPException) as error:
            results.append({'name': file.filename, 'error': str(error.detail if isinstance(error, HTTPException) else error)})
        except RuntimeError as error:
            raise HTTPException(503, str(error))
    return results


def analyze_selfie(contents):
    with analysis_slots:
        return embeddings(contents)


@app.get('/api/client/photos')
def client_gallery_photos(session=Depends(client_session)):
    if session['mode'] not in ('gallery', 'both'):
        raise HTTPException(403, 'Ce lien permet uniquement une recherche par selfie.')
    with connect() as db:
        return [dict(row) for row in db.execute('SELECT id,name FROM photos WHERE gallery_id=? ORDER BY rowid DESC', (session['gallery_id'],))]


@app.post('/api/search')
async def search(file: UploadFile = File(...), session_hash=Depends(client_session)):
    if session_hash['mode'] not in ('search', 'both'):
        raise HTTPException(403, 'La recherche par selfie n’est pas activée pour ce lien.')
    try:
        faces = await run_in_threadpool(analyze_selfie, await image_bytes(file))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    if len(faces) != 1:
        raise HTTPException(400, 'Le selfie doit contenir exactement un visage. Réessayez avec une photo bien éclairée.')
    query = np.array(faces[0])
    with connect() as db:
        rows = db.execute('SELECT id, name, faces FROM photos WHERE gallery_id=?', (session_hash['gallery_id'],)).fetchall()
    matches = []
    for row in rows:
        vectors = json.loads(row['faces'])
        if vectors:
            score = max(float(np.dot(query, vector)) for vector in vectors)
            if score >= THRESHOLD:
                matches.append({'id': row['id'], 'name': row['name'], 'score': round(score, 3)})
    with connect() as db:
        db.execute('DELETE FROM client_matches WHERE session_hash=?', (session_hash['token_hash'],))
        db.executemany('INSERT INTO client_matches VALUES (?, ?)', [(session_hash['token_hash'], item['id']) for item in matches])
    return sorted(matches, key=lambda x: x['score'], reverse=True)


@app.get('/api/photos/{photo_id}/image')
def photo_image(photo_id: str, user=Depends(auth.current_user)):
    if len(photo_id) != 32 or any(c not in '0123456789abcdef' for c in photo_id):
        raise HTTPException(404)
    with connect() as db:
        row = db.execute('SELECT gallery_id FROM photos WHERE id=?', (photo_id,)).fetchone()
        if row is None:
            raise HTTPException(404)
        gallery_access(db, row['gallery_id'], user)
        path = storage.gallery_directory(db, PHOTOS, row['gallery_id']) / (photo_id + '.jpg')
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type='image/jpeg', filename='photo.jpg', content_disposition_type='inline', headers={'Cache-Control': 'no-store'})


@app.get('/api/client/photos/{photo_id}/image')
def client_photo_image(photo_id: str, session_hash=Depends(client_session)):
    if len(photo_id) != 32 or any(c not in '0123456789abcdef' for c in photo_id):
        raise HTTPException(404)
    with connect() as db:
        photo = db.execute('SELECT gallery_id FROM photos WHERE id=? AND gallery_id=?', (photo_id, session_hash['gallery_id'])).fetchone()
        matched = db.execute('SELECT 1 FROM client_matches WHERE session_hash=? AND photo_id=?', (session_hash['token_hash'], photo_id)).fetchone()
        if photo is None or (session_hash['mode'] == 'search' and matched is None):
            raise HTTPException(404)
        path = storage.gallery_directory(db, PHOTOS, photo['gallery_id']) / (photo_id + '.jpg')
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type='image/jpeg', filename='photo.jpg', content_disposition_type='inline', headers={'Cache-Control': 'no-store'})


@app.delete('/api/photos/{photo_id}')
def delete_photo(photo_id: str, user=Depends(auth.current_user)):
    if len(photo_id) != 32 or any(c not in '0123456789abcdef' for c in photo_id):
        raise HTTPException(404, 'Photo introuvable.')
    with lock, connect() as db:
        row = db.execute('SELECT gallery_id FROM photos WHERE id = ?', (photo_id,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Photo introuvable.')
        gallery_access(db, row['gallery_id'], user, 'can_delete', write=True)
        db.execute('DELETE FROM photos WHERE id = ?', (photo_id,))
        db.execute('DELETE FROM client_matches WHERE photo_id=?', (photo_id,))
        db.commit()
        (storage.gallery_directory(db, PHOTOS, row['gallery_id']) / (photo_id + '.jpg')).unlink(missing_ok=True)
    return {'deleted': True}


@app.delete('/api/photos')
def clear_photos(gallery_id: str, user=Depends(auth.current_user)):
    with lock, connect() as db:
        gallery_access(db, gallery_id, user, 'can_delete', write=True)
        ids = [row['id'] for row in db.execute('SELECT id FROM photos WHERE gallery_id=?', (gallery_id,))]
        db.executemany('DELETE FROM client_matches WHERE photo_id=?', [(photo_id,) for photo_id in ids])
        db.execute('DELETE FROM photos WHERE gallery_id=?', (gallery_id,))
        db.commit()
        directory = storage.gallery_directory(db, PHOTOS, gallery_id)
        for photo_id in ids:
            (directory / (photo_id + '.jpg')).unlink(missing_ok=True)
    return {'deleted': len(ids)}
