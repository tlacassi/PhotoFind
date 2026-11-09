"""Local account and session storage for the PhotoFind prototype."""
import hashlib
import hmac
import secrets
import sqlite3
import time
from pathlib import Path

from fastapi import HTTPException, Request

SESSION_SECONDS = 8 * 60 * 60
COOKIE = 'photofind_session'


def connect(path: Path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def initialize(path: Path):
    with connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL COLLATE NOCASE, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN (\'admin\', \'photographer\')))')
        columns = {row['name'] for row in db.execute('PRAGMA table_info(users)')}
        for name in ('active', 'can_create_galleries', 'can_upload', 'can_delete', 'can_share'):
            if name not in columns:
                db.execute(f'ALTER TABLE users ADD COLUMN {name} INTEGER NOT NULL DEFAULT 1')
        for name, definition in [('storage_name', 'TEXT'), ('quota_bytes', 'INTEGER')]:
            if name not in columns:
                db.execute(f'ALTER TABLE users ADD COLUMN {name} {definition}')
        db.execute('CREATE TABLE IF NOT EXISTS invitations (token_hash TEXT PRIMARY KEY, expires INTEGER NOT NULL, quota_bytes INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0)')
        db.execute('CREATE TABLE IF NOT EXISTS login_attempts (username TEXT PRIMARY KEY COLLATE NOCASE, failures INTEGER NOT NULL, until INTEGER NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires INTEGER NOT NULL)')


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=16384, r=8, p=1)
    return f'{salt.hex()}${digest.hex()}'


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split('$', 1)
    candidate = hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return hmac.compare_digest(candidate.hex(), digest)


def validate_credentials(username: str, password: str):
    if not 3 <= len(username) <= 64 or not all(c.isascii() and (c.isalnum() or c in '._-') for c in username):
        raise ValueError('Identifiant invalide : 3 à 64 lettres, chiffres, points, tirets ou underscores.')
    if not 8 <= len(password) <= 256:
        raise ValueError('Le mot de passe doit contenir entre 8 et 256 caractères.')


def create_user(path: Path, username: str, password: str, role: str, initial=False, quota_bytes=None):
    validate_credentials(username, password)
    hashed = hash_password(password)
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if initial and db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            raise ValueError('Un compte existe déjà.')
        cursor = db.execute('INSERT INTO users(username, password_hash, role, quota_bytes) VALUES (?, ?, ?, ?)', (username, hashed, role, quota_bytes))
        initialize_user_directory(db, path.parent / 'photos', cursor.lastrowid, username)
        return cursor.lastrowid


def authenticate(path: Path, username: str, password: str):
    with connect(path) as db:
        row = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    if row and row['active'] and verify_password(password, row['password_hash']):
        return row
    return None


def new_session(path: Path, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with connect(path) as db:
        db.execute('DELETE FROM sessions WHERE expires <= ?', (int(time.time()),))
        db.execute('INSERT INTO sessions VALUES (?, ?, ?)', (token_hash, user_id, int(time.time()) + SESSION_SECONDS))
    return token


def current_user(request: Request):
    token = request.cookies.get(COOKIE, '')
    if len(token) > 128:
        raise HTTPException(401, 'Connexion requise.')
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with connect(request.app.state.db_path) as db:
        row = db.execute('SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token_hash=? AND sessions.expires>? AND users.active=1', (token_hash, int(time.time()))).fetchone()
    if row is None:
        raise HTTPException(401, 'Connexion requise.')
    return row


def admin_user(request: Request):
    user = current_user(request)
    if user['role'] != 'admin':
        raise HTTPException(403, 'Réservé à l’administrateur.')
    return user


def public_user(user):
    return {key: user[key] for key in ('id', 'username', 'role', 'active', 'can_create_galleries', 'can_upload', 'can_delete', 'can_share', 'quota_bytes')}


def require_permission(user, permission):
    if user['role'] != 'admin' and not user[permission]:
        raise HTTPException(403, 'Permission insuffisante.')


def login_allowed(path, username):
    now = int(time.time())
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM login_attempts WHERE until<=?', (now,))
        row = db.execute('SELECT failures FROM login_attempts WHERE username=?', (username,)).fetchone()
        if row and row['failures'] >= 10:
            raise HTTPException(429, 'Trop de tentatives. Réessayez dans 15 minutes.')
        db.execute('INSERT INTO login_attempts VALUES (?,1,?) ON CONFLICT(username) DO UPDATE SET failures=failures+1', (username, now + 900))


def clear_attempts(path, username):
    with connect(path) as db:
        db.execute('DELETE FROM login_attempts WHERE username=?', (username,))



def initialize_user_directory(db, root, user_id, username):
    import re
    slug = re.sub(r'[^a-z0-9]+', '-', username.lower()).strip('-')[:40] or 'photographe'
    name = f'user-{user_id}-{slug}'
    (root / name).mkdir(parents=True, exist_ok=True)
    db.execute('UPDATE users SET storage_name=? WHERE id=?', (name, user_id))


def storage_usage(db, user_id):
    return db.execute('SELECT COALESCE(SUM(p.bytes),0) FROM photos p JOIN galleries g ON g.id=p.gallery_id WHERE g.owner_id=?', (user_id,)).fetchone()[0]
