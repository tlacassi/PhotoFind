# PhotoFind

Prototype auto-hébergé : un photographe importe des photos dans une galerie ;
un client ouvre un lien privé et utilise un selfie pour retrouver ses photos.
L'analyse se fait sur votre serveur avec OpenCV YuNet/SFace. Les données ne sont
pas envoyées à un service de reconnaissance externe.

## Fonctionnement

- **Galeries** : bouton de création ouvrant la saisie du nom, liste de galeries
  avec miniature, renommage et archivage. La miniature utilise la dernière photo
  importée par défaut ; le bouton étoile d’une photo permet de la choisir. Une galerie appartient à un
  compte ; son propriétaire peut autoriser explicitement d'autres photographes.
  L'administrateur voit toutes les galeries.
- **Import** : photos envoyées une par une, progression du transfert puis état
  d'analyse, résultat par photo, arrêt après la photo en cours et nouvelle tentative
  des photos en erreur ou non envoyées. L'analyse est exécutée dans un thread.
- **Clients sans compte** : lien privé et QR code associés à une galerie, validité
  de 1 à 90 jours. Le token du lien est retiré de la barre d'adresse après échange
  contre un cookie HttpOnly. Une session dure au maximum 8 heures. Les images
  téléchargeables sont limitées aux résultats de la recherche de cette session.
- **Liens** : liste des dates d'expiration et révocation immédiate des accès liés.
  L'archivage révoque les liens, et les restaurer ne réactive pas les anciens liens.
- **Administration `/admin`** : création, liste, modification, désactivation et
  réinitialisation du mot de passe des comptes ; déconnexion de leurs sessions.
  Permissions : gestion de ses galeries, import, suppression de photos, partage.
  Les administrateurs ont tous les droits. Votre propre compte administrateur ne
  peut être désactivé ou rétrogradé depuis cette interface.
- **Accès partagés** : les collaborateurs utilisent leurs permissions de compte
  dans une galerie autorisée, mais seul le propriétaire ou l'administrateur peut
  renommer/archiver la galerie et gérer ses collaborateurs. Retirer un collaborateur
  révoque tous les liens de la galerie, car il pourrait les avoir conservés.

Les changements de compte révoquent ses sessions. Désactiver un propriétaire
révoque également les liens de ses galeries.

## Essai sur Mac

Avec Python 3.11 ou 3.12 :

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python download_models.py
python create_admin.py
uvicorn app:app --host 127.0.0.1 --port 8000
```

Ouvrez <http://127.0.0.1:8000>. Le script de création du premier administrateur
vous demande votre identifiant et votre mot de passe, sans argument ou affichage
du mot de passe. Il refuse de créer un nouveau compte initial si un compte existe.
Les suivants se créent depuis l'administration. Minimum : 8 caractères.

Avec Docker Desktop :

```sh
docker compose -f compose.local.yaml build
docker compose -f compose.local.yaml run --rm photofind python create_admin.py
docker compose -f compose.local.yaml up -d
```

Le volume `photofind-data` conserve les données entre les redémarrages.
Ne lancez pas `down -v` si vous voulez conserver cette bibliothèque.

## Serveur et Portainer

La stack serveur utilise `compose.yaml`, construit l'image depuis le dépôt et
monte **`/mnt/data/PhotoFind` vers `/data`**. Ce dossier doit déjà exister et être
accessible en lecture/écriture à l'UID 10001 du conteneur. La base `photos.db`, les
photos réencodées et les empreintes y résident, hors du dépôt et de l'image.
La bibliothèque locale du Mac est distincte de celle du serveur.

Le service écoute sur `127.0.0.1:18080` du serveur. La route du tunnel Cloudflare
existant cible `http://127.0.0.1:18080` depuis le même hôte. Le Compose serveur
force les cookies `Secure` ; utilisez l'adresse HTTPS publique pour vous connecter.
Le Compose local garde ces cookies utilisables en HTTP sur localhost.

Dans Portainer, stack `photofind` : dépôt `tlacassi/PhotoFind`, branche `main`,
fichier `compose.yaml`, puis **Pull and redeploy**. L'image est reconstruite depuis
le code ; aucun registre d'images n'est nécessaire. Sauvegardez avant mise à jour.

### Migration des anciennes bibliothèques

Au démarrage, une migration additive ajoute les galeries et les permissions.
Les anciennes photos et anciens liens sont rattachés à « Photos existantes »,
possédée par le premier administrateur. S'il n'existe pas encore d'administrateur,
cette galerie n'est visible que des administrateurs futurs. Aucune image ni
empreinte existante n'est supprimée ou recalculée. Les autres photographes n'ont
plus accès automatiquement à cette bibliothèque : accordez-leur un accès explicite.
La migration peut être relancée au redémarrage sans dupliquer les données.

## Sauvegarder et restaurer

Arrêtez tous les processus PhotoFind pendant une sauvegarde pour figer les photos
et SQLite ensemble. Le verrou de maintenance refuse la sauvegarde si une instance
de cette version utilise le dossier. Il ne protège pas contre des outils externes
qui modifieraient directement les fichiers.

Exemple avec Python installé sur l'hôte :

```sh
python maintenance.py backup /mnt/data/PhotoFind /mnt/data/PhotoFind-backups/snapshot-001
python maintenance.py restore /mnt/data/PhotoFind-backups/snapshot-001 /mnt/data/PhotoFind-restored
```

Les destinations doivent être de nouveaux dossiers. Le script conserve la base,
les images et un manifeste SHA-256, contrôle l'intégrité SQLite et vérifie les
images référencées. La restauration refuse une sauvegarde altérée et n'écrase pas
les données existantes. Pour utiliser la copie restaurée, changez le bind mount,
vérifiez les permissions de l'UID 10001, puis redémarrez la stack. Gardez l'ancien
dossier jusqu'à la validation. Les sauvegardes contiennent aussi les données de
reconnaissance et les comptes : protégez-les comme les données d'origine.

Le script est également dans l'image : stack arrêtée, un conteneur ponctuel avec
les dossiers de données et de sauvegardes montés permet les mêmes commandes.
Il ne lance pas le serveur. Aucune sauvegarde automatique n'est programmée.

## Tests

```sh
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Tests : migration répétée, deux photographes et deux clients isolés, collaboration,
permissions, comptes, archivage, révocation, limitation des connexions, cookies,
import, progression/arrêt/reprise avec faux transport JavaScript, sauvegarde et
restauration. Le test réel d'import et redémarrage nécessite les modèles téléchargés.
Les tests de recherche utilisent des embeddings déterministes ; ils vérifient
l'isolation, pas la précision biométrique. Les tests JavaScript utilisent QuickJS
et un DOM simulé : une validation visuelle dans un navigateur reste nécessaire.

## Limites

- JPEG/PNG/WebP, 20 Mo par fichier. Les images téléchargées sont réencodées en JPEG,
  limitées à 2400 pixels sur le plus grand côté ; les originaux ne sont pas conservés.
- La reprise concerne les fichiers du lot dans l'onglet ouvert. Pas de reprise par
  morceaux après fermeture du navigateur. Une réponse réseau perdue après import
  peut entraîner un doublon si le fichier est renvoyé. Le transfert et l'analyse
  sont des phases séparées ; 100 % du transfert ne signifie pas analyse terminée.
- La reconnaissance peut manquer une personne ou proposer une mauvaise photo.
  Le selfie n'est pas conservé, les photos/empreintes le sont jusqu'à suppression.
  Une personne possédant le lien peut rechercher dans sa galerie : ce lien ne
  prouve pas l'identité de la personne qui envoie le selfie.
- Dix tentatives de connexion par identifiant sur une fenêtre de quinze minutes.
  Cette protection n'est pas un dispositif complet contre les attaques distribuées.
  Pas de MFA ni de récupération par email ; réinitialisation via un administrateur.
- Les partages entre photographes sont des accès à la galerie avec leurs permissions
  globales, pas des rôles différents pour chaque galerie.
- Pas de paiement, de galerie publique, de ZIP, de suppression de galerie complète,
  de quota de stockage ou de sauvegarde programmée pour le moment.

Voir [TODO.md](TODO.md) pour l'avancement et les validations restantes.
Les modèles et leurs licences sont référencés dans [OpenCV Zoo](https://github.com/opencv/opencv_zoo).
