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
    if not 12 <= len(password) <= 256:
        raise ValueError('Le mot de passe doit contenir entre 12 et 256 caractères.')


def create_user(path: Path, username: str, password: str, role: str, initial=False):
    validate_credentials(username, password)
    hashed = hash_password(password)
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if initial and db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            raise ValueError('Un compte existe déjà.')
        db.execute('INSERT INTO users(username, password_hash, role) VALUES (?, ?, ?)', (username, hashed, role))


def authenticate(path: Path, username: str, password: str):
    with connect(path) as db:
        row = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    if row and verify_password(password, row['password_hash']):
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
        row = db.execute('SELECT users.id, users.username, users.role FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token_hash=? AND sessions.expires>?', (token_hash, int(time.time()))).fetchone()
    if row is None:
        raise HTTPException(401, 'Connexion requise.')
    return row


def admin_user(request: Request):
    user = current_user(request)
    if user['role'] != 'admin':
        raise HTTPException(403, 'Réservé à l’administrateur.')
    return user
