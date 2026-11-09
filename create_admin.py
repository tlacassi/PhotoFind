"""Create the initial admin from an interactive terminal; never pass passwords as arguments."""
import getpass
import os
from pathlib import Path

import auth

root = Path(__file__).resolve().parent
data = Path(os.environ.get('DATA_DIR', root / 'data'))
data.mkdir(parents=True, exist_ok=True)
db = data / 'photos.db'
auth.initialize(db)
username = input('Identifiant administrateur : ').strip()
password = getpass.getpass('Mot de passe (12 caractères minimum) : ')
if password != getpass.getpass('Confirmez le mot de passe : '):
    raise SystemExit('Les mots de passe ne correspondent pas.')
try:
    auth.create_user(db, username, password, 'admin', initial=True)
except ValueError as error:
    raise SystemExit(str(error))
print('Compte administrateur créé.')
