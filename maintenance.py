"""Offline backup and restore. Stop every PhotoFind process before running."""
import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import storage


def checksum(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate(directory):
    database = directory / 'photos.db'
    with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Base de données invalide.')
        for (photo_id,) in db.execute('SELECT id FROM photos'):
            if len(photo_id) != 32 or any(char not in '0123456789abcdef' for char in photo_id):
                raise ValueError('Identifiant photo invalide.')
            if not (directory / 'photos' / (photo_id + '.jpg')).is_file():
                raise ValueError('Une photo enregistrée manque dans la sauvegarde.')


def backup(source, destination):
    source = source.resolve(); destination = destination.resolve()
    if source == destination or source in destination.parents:
        raise ValueError('Choisissez une destination extérieure au dossier de données.')
    if destination.exists():
        raise ValueError('La destination doit être un nouveau dossier.')
    with storage.application_lock(source, exclusive=True):
        validate(source)
        destination.mkdir(mode=0o700, parents=True)
        with sqlite3.connect(f'file:{source / "photos.db"}?mode=ro', uri=True) as src, sqlite3.connect(destination / 'photos.db') as dst:
            src.backup(dst)
        shutil.copytree(source / 'photos', destination / 'photos')
        validate(destination)
        manifest = {str(file.relative_to(destination)): checksum(file) for file in destination.rglob('*') if file.is_file()}
        (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2))


def restore(source, destination):
    source = source.resolve(); destination = destination.resolve()
    if destination.exists():
        raise ValueError('Restaurez dans un nouveau dossier, jamais sur les données en place.')
    manifest = json.loads((source / 'manifest.json').read_text())
    if 'photos.db' not in manifest:
        raise ValueError('Manifeste incomplet.')
    for name, expected in manifest.items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Chemin invalide dans le manifeste.')
        file = source / relative
        if not file.is_file() or file.is_symlink() or checksum(file) != expected:
            raise ValueError('Sauvegarde incomplète ou altérée.')
    validate(source)
    destination.mkdir(mode=0o700, parents=True)
    for name in manifest:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    (destination / 'photos').mkdir(exist_ok=True)
    validate(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['backup', 'restore'])
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        (backup if args.operation == 'backup' else restore)(args.source, args.destination)
    except (ValueError, RuntimeError, OSError, sqlite3.DatabaseError) as error:
        parser.exit(1, f'{error}\n')
    print('Opération terminée et intégrité vérifiée.')
