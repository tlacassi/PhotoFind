"""Transactional, additive migrations for the local SQLite library."""
import sqlite3
from pathlib import Path


def connect(path: Path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def initialize(path: Path):
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS photos (id TEXT PRIMARY KEY, name TEXT NOT NULL, faces TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS client_links (token_hash TEXT PRIMARY KEY, expires INTEGER NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS client_sessions (token_hash TEXT PRIMARY KEY, link_hash TEXT NOT NULL, expires INTEGER NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS client_matches (session_hash TEXT NOT NULL, photo_id TEXT NOT NULL, PRIMARY KEY(session_hash, photo_id))')
        db.execute('CREATE TABLE IF NOT EXISTS galleries (id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_id INTEGER REFERENCES users(id), archived INTEGER NOT NULL DEFAULT 0)')
        if 'cover_photo_id' not in {row['name'] for row in db.execute('PRAGMA table_info(galleries)')}:
            db.execute('ALTER TABLE galleries ADD COLUMN cover_photo_id TEXT')
        db.execute('CREATE TABLE IF NOT EXISTS gallery_members (gallery_id TEXT REFERENCES galleries(id), user_id INTEGER REFERENCES users(id), PRIMARY KEY(gallery_id,user_id))')
        for table in ('photos', 'client_links'):
            columns = {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
            if 'gallery_id' not in columns:
                db.execute(f'ALTER TABLE {table} ADD COLUMN gallery_id TEXT REFERENCES galleries(id)')
        if db.execute('SELECT 1 FROM photos WHERE gallery_id IS NULL UNION SELECT 1 FROM client_links WHERE gallery_id IS NULL LIMIT 1').fetchone():
            owner = db.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
            db.execute('INSERT OR IGNORE INTO galleries(id,name,owner_id,archived) VALUES (?, ?, ?, 0)', ('legacy', 'Photos existantes', owner['id'] if owner else None))
            db.execute("UPDATE photos SET gallery_id='legacy' WHERE gallery_id IS NULL")
            db.execute("UPDATE client_links SET gallery_id='legacy' WHERE gallery_id IS NULL")
        db.execute('CREATE INDEX IF NOT EXISTS photos_gallery ON photos(gallery_id)')
        db.execute('CREATE INDEX IF NOT EXISTS links_gallery ON client_links(gallery_id)')


def application_lock(directory: Path, exclusive=False):
    """Hold a process lock to prevent maintenance while the application runs."""
    import fcntl
    handle = (directory / '.application.lock').open('a')
    try:
        fcntl.flock(handle, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('Arrêtez PhotoFind avant cette opération de maintenance.')
    return handle
