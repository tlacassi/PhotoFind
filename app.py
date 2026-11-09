import io
import json
import os
import sqlite3
import threading
import uuid
import secrets
import hashlib
import time

import auth
from pathlib import Path

import cv2
import numpy as np
import qrcode
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
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
THRESHOLD = float(os.environ.get('MATCH_THRESHOLD', '0.363'))
MAX_BYTES = 20 * 1024 * 1024
lock = threading.Lock()
app = FastAPI(title='PhotoFind')
app.state.db_path = DB
auth.initialize(DB)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db


with connect() as db:
    db.execute('CREATE TABLE IF NOT EXISTS photos (id TEXT PRIMARY KEY, name TEXT NOT NULL, faces TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS client_links (token_hash TEXT PRIMARY KEY, expires INTEGER NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS client_sessions (token_hash TEXT PRIMARY KEY, link_hash TEXT NOT NULL, expires INTEGER NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS client_matches (session_hash TEXT NOT NULL, photo_id TEXT NOT NULL, PRIMARY KEY(session_hash, photo_id))')


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
    user = auth.authenticate(DB, credentials.username, credentials.password)
    if not user:
        raise HTTPException(401, 'Identifiant ou mot de passe incorrect.')
    token = auth.new_session(DB, user['id'])
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite='strict', secure=request.url.scheme == 'https', max_age=auth.SESSION_SECONDS, path='/')
    return {'username': user['username'], 'role': user['role']}


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
    return {'username': user['username'], 'role': user['role']}


@app.post('/api/users', status_code=201)
def create_photographer(credentials: Credentials, user=Depends(auth.admin_user)):
    try:
        auth.create_user(DB, credentials.username, credentials.password, 'photographer')
    except ValueError as error:
        raise HTTPException(400, str(error))
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Cet identifiant existe déjà.')
    return {'username': credentials.username, 'role': 'photographer'}



def digest(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def client_session(request: Request):
    token = request.cookies.get('photofind_client', '')
    if len(token) > 128:
        raise HTTPException(401, 'Lien client invalide ou expiré.')
    session_hash = digest(token)
    with connect() as db:
        row = db.execute('SELECT s.token_hash FROM client_sessions s JOIN client_links l ON l.token_hash=s.link_hash WHERE s.token_hash=? AND s.expires>? AND l.expires>?', (session_hash, int(time.time()), int(time.time()))).fetchone()
    if row is None:
        raise HTTPException(401, 'Lien client invalide ou expiré.')
    return session_hash


class ClientToken(BaseModel):
    token: str = Field(max_length=128)


@app.get('/client')
def client_page():
    return FileResponse(ROOT / 'static' / 'client.html', headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})


@app.post('/api/client-links')
def create_client_link(user=Depends(auth.current_user)):
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('INSERT INTO client_links VALUES (?, ?)', (digest(token), int(time.time()) + 7 * 86400))
    return {'token': token, 'expires_in_days': 7}


@app.post('/api/client/redeem')
def redeem_client_link(payload: ClientToken, request: Request, response: Response):
    link_hash = digest(payload.token)
    now = int(time.time())
    with connect() as db:
        row = db.execute('SELECT expires FROM client_links WHERE token_hash=? AND expires>?', (link_hash, now)).fetchone()
        if row is None:
            raise HTTPException(401, 'Lien client invalide ou expiré.')
        session = secrets.token_urlsafe(32)
        db.execute('INSERT INTO client_sessions VALUES (?, ?, ?)', (digest(session), link_hash, min(row['expires'], now + 8 * 3600)))
    response.set_cookie('photofind_client', session, httponly=True, secure=request.url.scheme == 'https', samesite='strict', max_age=8 * 3600, path='/')
    response.headers['Cache-Control'] = 'no-store'
    return {'ok': True}


@app.post('/api/client-qr')
def client_qr(payload: ClientToken, request: Request, user=Depends(auth.current_user)):
    with connect() as db:
        if db.execute('SELECT 1 FROM client_links WHERE token_hash=? AND expires>?', (digest(payload.token), int(time.time()))).fetchone() is None:
            raise HTTPException(404, 'Lien invalide.')
    origin = request.headers.get('origin', '')
    from urllib.parse import urlsplit
    parsed = urlsplit(origin)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise HTTPException(400, 'Origine invalide.')
    image = qrcode.make(origin + '/client#' + payload.token)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return Response(buffer.getvalue(), media_type='image/png', headers={'Cache-Control': 'no-store'})


@app.get('/api/photos')
def list_photos(user=Depends(auth.current_user)):
    with connect() as db:
        rows = db.execute('SELECT id, name, faces FROM photos ORDER BY rowid DESC').fetchall()
    return [{'id': r['id'], 'name': r['name'], 'faces': len(json.loads(r['faces']))} for r in rows]


@app.post('/api/photos')
async def upload(files: list[UploadFile] = File(...), user=Depends(auth.current_user)):
    results = []
    for file in files:
        try:
            contents = await image_bytes(file)
            faces = await run_in_threadpool(embeddings, contents)
            photo_id = uuid.uuid4().hex
            # Re-encode decoded image to ensure only valid image data is served.
            image = read_image(contents)
            ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not ok:
                raise ValueError('Impossible de lire cette image.')
            (PHOTOS / (photo_id + '.jpg')).write_bytes(encoded.tobytes())
            with connect() as db:
                db.execute('INSERT INTO photos VALUES (?, ?, ?)', (photo_id, Path(file.filename or 'Photo').name, json.dumps(faces)))
            results.append({'name': file.filename, 'faces': len(faces)})
        except (ValueError, HTTPException) as e:
            results.append({'name': file.filename, 'error': str(e.detail if isinstance(e, HTTPException) else e)})
        except RuntimeError as e:
            raise HTTPException(503, str(e))
    return results


@app.post('/api/search')
async def search(file: UploadFile = File(...), session_hash=Depends(client_session)):
    try:
        faces = await run_in_threadpool(embeddings, await image_bytes(file))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    if len(faces) != 1:
        raise HTTPException(400, 'Le selfie doit contenir exactement un visage. Réessayez avec une photo bien éclairée.')
    query = np.array(faces[0])
    with connect() as db:
        rows = db.execute('SELECT id, name, faces FROM photos').fetchall()
    matches = []
    for row in rows:
        vectors = json.loads(row['faces'])
        if vectors:
            score = max(float(np.dot(query, vector)) for vector in vectors)
            if score >= THRESHOLD:
                matches.append({'id': row['id'], 'name': row['name'], 'score': round(score, 3)})
    with connect() as db:
        db.execute('DELETE FROM client_matches WHERE session_hash=?', (session_hash,))
        db.executemany('INSERT INTO client_matches VALUES (?, ?)', [(session_hash, item['id']) for item in matches])
    return sorted(matches, key=lambda x: x['score'], reverse=True)


@app.get('/api/photos/{photo_id}/image')
def photo_image(photo_id: str, user=Depends(auth.current_user)):
    if len(photo_id) != 32 or any(c not in '0123456789abcdef' for c in photo_id):
        raise HTTPException(404)
    path = PHOTOS / (photo_id + '.jpg')
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type='image/jpeg', filename='photo.jpg', content_disposition_type='inline')


@app.get('/api/client/photos/{photo_id}/image')
def client_photo_image(photo_id: str, session_hash=Depends(client_session)):
    with connect() as db:
        allowed = db.execute('SELECT 1 FROM client_matches WHERE session_hash=? AND photo_id=?', (session_hash, photo_id)).fetchone()
    if allowed is None or len(photo_id) != 32 or any(c not in '0123456789abcdef' for c in photo_id):
        raise HTTPException(404)
    path = PHOTOS / (photo_id + '.jpg')
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type='image/jpeg', filename='photo.jpg', content_disposition_type='inline', headers={'Cache-Control': 'no-store'})


@app.delete('/api/photos/{photo_id}')
def delete_photo(photo_id: str, user=Depends(auth.current_user)):
    if len(photo_id) != 32 or any(c not in '0123456789abcdef' for c in photo_id):
        raise HTTPException(404, 'Photo introuvable.')
    with lock, connect() as db:
        row = db.execute('SELECT id FROM photos WHERE id = ?', (photo_id,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Photo introuvable.')
        (PHOTOS / (photo_id + '.jpg')).unlink(missing_ok=True)
        db.execute('DELETE FROM photos WHERE id = ?', (photo_id,))
    return {'deleted': True}


@app.delete('/api/photos')
def clear_photos(user=Depends(auth.current_user)):
    with lock, connect() as db:
        ids = [row['id'] for row in db.execute('SELECT id FROM photos')]
        db.execute('DELETE FROM photos')
        for photo_id in ids:
            (PHOTOS / (photo_id + '.jpg')).unlink(missing_ok=True)
    return {'deleted': len(ids)}
