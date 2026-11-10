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
        if 'storage_name' not in {row['name'] for row in db.execute('PRAGMA table_info(galleries)')}:
            db.execute('ALTER TABLE galleries ADD COLUMN storage_name TEXT')
        db.execute('DROP INDEX IF EXISTS galleries_storage_name')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS galleries_owner_storage ON galleries(owner_id, storage_name)')
        for name, definition in [('accent_color', "TEXT NOT NULL DEFAULT '#789a78'"), ('background_color', "TEXT NOT NULL DEFAULT '#f8f7f1'"), ('logo', 'INTEGER NOT NULL DEFAULT 0'), ('branding_bytes', 'INTEGER NOT NULL DEFAULT 0')]:
            if name not in {row['name'] for row in db.execute('PRAGMA table_info(galleries)')}:
                db.execute(f'ALTER TABLE galleries ADD COLUMN {name} {definition}')
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
        if 'bytes' not in {row['name'] for row in db.execute('PRAGMA table_info(photos)')}:
            db.execute('ALTER TABLE photos ADD COLUMN bytes INTEGER NOT NULL DEFAULT 0')
        for name, definition in [('job_id','TEXT'),('thumbnail_bytes','INTEGER NOT NULL DEFAULT 0'),('thumbnail_status','INTEGER NOT NULL DEFAULT 0'),('content_hash','TEXT'),('encoded_hash','TEXT')]:
            if name not in {row['name'] for row in db.execute('PRAGMA table_info(photos)')}:
                db.execute(f'ALTER TABLE photos ADD COLUMN {name} {definition}')
        db.execute('CREATE INDEX IF NOT EXISTS photos_content ON photos(gallery_id,content_hash)')
        db.execute('CREATE INDEX IF NOT EXISTS photos_encoded ON photos(gallery_id,encoded_hash)')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS photos_job ON photos(job_id)')
        db.execute("CREATE TABLE IF NOT EXISTS photo_jobs (id TEXT PRIMARY KEY, gallery_id TEXT NOT NULL REFERENCES galleries(id), user_id INTEGER NOT NULL REFERENCES users(id), name TEXT NOT NULL, input_path TEXT NOT NULL, input_bytes INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'queued', error TEXT, faces INTEGER, photo_id TEXT, created INTEGER NOT NULL)")
        if 'kind' not in {row['name'] for row in db.execute('PRAGMA table_info(photo_jobs)')}:
            db.execute("ALTER TABLE photo_jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'upload'")
        db.execute('CREATE INDEX IF NOT EXISTS photo_jobs_gallery ON photo_jobs(gallery_id,status)')
        if 'mode' not in {row['name'] for row in db.execute('PRAGMA table_info(client_links)')}:
            db.execute("ALTER TABLE client_links ADD COLUMN mode TEXT NOT NULL DEFAULT 'search'")
        for name, definition in [('name', "TEXT NOT NULL DEFAULT 'Lien client'"), ('nonce', 'TEXT')]:
            if name not in {row['name'] for row in db.execute('PRAGMA table_info(client_links)')}:
                db.execute(f'ALTER TABLE client_links ADD COLUMN {name} {definition}')
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



def allocate_gallery_directory(db, root, name, owner_id):
    """Reserve a readable folder atomically; never reuse an existing directory."""
    import re
    import unicodedata
    from datetime import datetime, timezone
    normalized = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    slug = re.sub(r'[^a-z0-9]+', '-', normalized.lower()).strip('-')[:64].rstrip('-') or 'galerie'
    base = datetime.now(timezone.utc).strftime('%Y-%m-%d') + '-' + slug
    for suffix in range(10000):
        candidate = base + (f'-{suffix}' if suffix else '')
        if db.execute('SELECT 1 FROM galleries WHERE storage_name=? AND owner_id IS ?', (candidate, owner_id)).fetchone():
            continue
        try:
            (root / candidate).mkdir()
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError('Trop de dossiers portant ce nom. Choisissez un autre nom de galerie.')


def gallery_directory(db, root, gallery_id):
    row = db.execute('SELECT storage_name,owner_id FROM galleries WHERE id=?', (gallery_id,)).fetchone()
    if row is None:
        raise ValueError('Galerie introuvable.')
    name = row['storage_name'] or gallery_id
    if not name or name in ('.', '..') or Path(name).name != name:
        raise ValueError('Dossier de galerie invalide.')
    return user_directory(db, root, row['owner_id']) / name


def user_directory(db, root, user_id):
    if user_id is None:
        name = "unassigned"
    else:
        row = db.execute("SELECT storage_name FROM users WHERE id=?", (user_id,)).fetchone()
        name = row["storage_name"] if row and row["storage_name"] else f"user-{user_id}"
    if not name or name in (".", "..") or Path(name).name != name:
        raise ValueError("Dossier utilisateur invalide.")
    return root / name


def organize_photos(path, root):
    """Move legacy flat storage into reserved gallery folders; safe to resume."""
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        import auth
        for user in db.execute('SELECT id,username FROM users WHERE storage_name IS NULL').fetchall():
            auth.initialize_user_directory(db, root, user['id'], user['username'])
        for gallery in db.execute('SELECT id,name,storage_name,owner_id FROM galleries').fetchall():
            user_root = user_directory(db, root, gallery['owner_id'])
            user_root.mkdir(parents=True, exist_ok=True)
            if gallery['storage_name'] is None:
                folder = allocate_gallery_directory(db, user_root, gallery['name'], gallery['owner_id'])
                db.execute('UPDATE galleries SET storage_name=? WHERE id=?', (folder, gallery['id']))
            else:
                gallery_directory(db, root, gallery['id']).mkdir(exist_ok=True)
        # Commit folder mapping before moving files, so a restart uses the same paths.
        db.commit()
        for photo in db.execute('SELECT id,gallery_id,encoded_hash FROM photos'):
            if len(photo['id']) != 32 or any(char not in '0123456789abcdef' for char in photo['id']):
                raise ValueError('Identifiant de photo invalide pendant la migration.')
            filename = photo['id'] + '.jpg'
            destination = gallery_directory(db, root, photo['gallery_id']) / filename
            folder = db.execute('SELECT storage_name FROM galleries WHERE id=?', (photo['gallery_id'],)).fetchone()[0]
            for source in (root / filename, root / folder / filename):
                if source.exists() and source != destination:
                    if destination.exists():
                        raise ValueError('Deux fichiers existent pour une photo. Migration arrêtée sans écrasement.')
                    source.rename(destination)
            if destination.is_file():
                db.execute('UPDATE photos SET bytes=? WHERE id=?', (destination.stat().st_size, photo['id']))
                if photo['encoded_hash'] is None:
                    import hashlib
                    digest = hashlib.sha256()
                    with destination.open('rb') as stream:
                        for chunk in iter(lambda: stream.read(1024*1024),b''):
                            digest.update(chunk)
                    db.execute('UPDATE photos SET encoded_hash=? WHERE id=?',(digest.hexdigest(),photo['id']))
