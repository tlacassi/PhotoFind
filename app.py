import io
import json
import os
import sqlite3
import threading
import uuid
from pathlib import Path

import cv2
import numpy as np
import qrcode
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

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
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db


with connect() as db:
    db.execute('CREATE TABLE IF NOT EXISTS photos (id TEXT PRIMARY KEY, name TEXT NOT NULL, faces TEXT NOT NULL)')


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


@app.get('/')
def index():
    return FileResponse(ROOT / 'static' / 'index.html')


@app.get('/client', name='client_page')
def client_page():
    return FileResponse(ROOT / 'static' / 'client.html')


@app.get('/api/client-qr')
def client_qr(request: Request):
    image = qrcode.make(str(request.url_for('client_page')))
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return Response(buffer.getvalue(), media_type='image/png', headers={'Cache-Control': 'no-store'})


@app.get('/api/photos')
def list_photos():
    with connect() as db:
        rows = db.execute('SELECT id, name, faces FROM photos ORDER BY rowid DESC').fetchall()
    return [{'id': r['id'], 'name': r['name'], 'faces': len(json.loads(r['faces']))} for r in rows]


@app.post('/api/photos')
async def upload(files: list[UploadFile] = File(...)):
    results = []
    for file in files:
        try:
            contents = await image_bytes(file)
            faces = embeddings(contents)
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
async def search(file: UploadFile = File(...)):
    try:
        faces = embeddings(await image_bytes(file))
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
    return sorted(matches, key=lambda x: x['score'], reverse=True)


@app.get('/api/photos/{photo_id}/image')
def photo_image(photo_id: str):
    if len(photo_id) != 32 or any(c not in '0123456789abcdef' for c in photo_id):
        raise HTTPException(404)
    path = PHOTOS / (photo_id + '.jpg')
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type='image/jpeg', filename='photo.jpg', content_disposition_type='inline')


@app.delete('/api/photos')
def clear_photos():
    with lock, connect() as db:
        ids = [row['id'] for row in db.execute('SELECT id FROM photos')]
        db.execute('DELETE FROM photos')
        for photo_id in ids:
            (PHOTOS / (photo_id + '.jpg')).unlink(missing_ok=True)
    return {'deleted': len(ids)}
