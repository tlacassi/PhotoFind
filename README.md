# PhotoFind

Prototype auto-hébergé : un photographe importe des photos dans une galerie ;
un client ouvre un lien privé et utilise un selfie pour retrouver ses photos.
L'analyse se fait sur votre serveur avec OpenCV YuNet/SFace. Les données ne sont
pas envoyées à un service de reconnaissance externe.

## Fonctionnement

- **Galeries** : bouton de création ouvrant la saisie du nom, liste de galeries
  avec miniature, renommage, désactivation et suppression définitive. La miniature utilise la
  dernière photo importée par défaut ; le bouton étoile permet de la choisir. Une galerie appartient à un
  compte ; son propriétaire peut autoriser explicitement d'autres photographes.
  L'administrateur voit toutes les galeries.
- **Import** : sélection ou glisser-déposer dans une galerie, voile de dépôt et panneau
  de progression en bas à droite. Trois envois simultanés transmettent les fichiers
  vers une file persistante sur le serveur. Après leur envoi, l’analyse et l’écriture
  continuent même si l’onglet est fermé. Les requêtes et fichiers qui n’ont pas fini
  d’être envoyés nécessitent de garder l’onglet ouvert. Deux analyses au maximum
  (`ANALYSIS_WORKERS`, défaut 2), un thread OpenCV par analyse (`OPENCV_THREADS`, défaut 1).
  La file SQLite reprend les traitements interrompus au redémarrage ; un identifiant
  de traitement évite de dupliquer une photo déjà enregistrée lors de cette reprise.
  Les galeries indiquent le nombre de photos restantes.
  Les doublons sont refusés dans une même galerie en comparant les pixels normalisés
  et le JPEG conservé, sans utiliser le nom du fichier. Le contrôle est répété dans
  la transaction d’écriture pour couvrir les imports simultanés. Une erreur par
  fichier est affichée dans le panneau ; les anciennes photos ne sont pas supprimées.
  Il ne s’agit pas d’une recherche approximative de photos ressemblantes.
- **Miniatures et visionneuse** : un worker génère les aperçus de 480 pixels maximum
  dans `.thumbnails/` au sein de la galerie. En attendant, la grille utilise le JPEG
  principal ; elle passe ensuite à l’aperçu. Les aperçus existants ne sont pas
  recalculés lors d’un affichage. Le suivi de progression réutilise les éléments
  d’image existants et seules les miniatures encore absentes sont vérifiées. La visionneuse client et photographe
  affiche le JPEG principal, avec précédent/suivant et navigation clavier. Le nom de
  fichier n’est pas affiché côté client. Les résultats du selfie sont placés en haut
  et annoncent directement leur nombre.
- **Navigation et personnalisation** : l’accueil photographe liste les galeries ;
  chacune s’ouvre sur `/galeries/<id>/<nom>`. Le nom de l’URL peut changer sans casser
  l’identifiant. Une galerie peut définir sa couleur principale, son fond et son logo
  PNG/JPEG/WebP (2 Mo maximum, réencodé en PNG). Les couleurs choisies s’appliquent
  immédiatement à la page du photographe comme aperçu. Le bouton Enregistrer
  sauvegarde ces couleurs pour la galerie et ses liens clients. Par défaut,
  PhotoFind est conservé.
- **Clients sans compte** : lien privé et QR code associés à une galerie, validité
  de 1 à 90 jours, plusieurs liens simultanés avec des expirations indépendantes.
  Modes : galerie seule, selfie seul ou les deux. Le serveur contrôle les modes.
  L’adresse contient la galerie (`/client/<id>#<token>`), et le token du lien est retiré de la barre d'adresse après échange
  contre un cookie HttpOnly. Une session dure au maximum 8 heures. En mode selfie seul, les images
  téléchargeables sont limitées aux résultats de la recherche de cette session.
  En mode galerie ou mixte, toutes les images de cette galerie sont consultables.
- **Liens** : nom du client, date d’expiration, boutons Copier, QR code et Supprimer.
  Supprimer retire définitivement le lien de la liste et invalide ses sessions.
  Les nouveaux liens peuvent être reconstruits grâce à `link-signing.key`, conservée
  avec les données et incluse dans la sauvegarde. Les anciens liens stockés uniquement
  sous forme d’empreinte restent valables, mais doivent être recréés pour être recopiés.
  La désactivation révoque les liens ; réactiver la galerie ne les réactive pas.
  La suppression efface sa galerie, ses photos et ses liens après confirmation,
  y compris lorsque la galerie est désactivée.
- **Administration `/admin`** : création, liste, modification, désactivation et
  réinitialisation du mot de passe des comptes ; déconnexion de leurs sessions.
  Permissions : gestion de ses galeries, import, suppression de photos, partage.
  Les administrateurs ont tous les droits. Votre propre compte administrateur ne
  peut être désactivé ou rétrogradé depuis cette interface.
- **Invitations** : l’administrateur génère un lien à usage unique, valable 1 à 30
  jours, et choisit le quota du futur photographe. Le destinataire définit son
  identifiant et son mot de passe ; il obtient son compte personnel sans accès
  automatique aux galeries existantes. Les invitations sont listables et révocables.
- **Quotas** : quota des photos modifiable par l’administrateur, consommation visible
  des deux côtés. Valeur vide = illimité dans la gestion des comptes, 0 = aucun
  nouvel import. L’usage correspond aux JPEG, miniatures et logos stockés. Les fichiers en attente
  réservent aussi leurs octets jusqu’à la fin du traitement. Si le quota ne laisse
  pas de place pour une miniature, le JPEG principal reste affiché.
  Les imports concurrents réservent leur place dans une transaction SQLite pour
  éviter de dépasser le quota. Un import dans une galerie partagée compte pour
  son propriétaire. Les comptes existants restent illimités jusqu’à modification ;
  la création et les invitations proposent 5 Gio par défaut.
- **Accès partagés** : les collaborateurs utilisent leurs permissions de compte
  dans une galerie autorisée, mais seul le propriétaire ou l'administrateur peut
  renommer/désactiver/supprimer la galerie et gérer ses collaborateurs. Retirer un collaborateur
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

Un seul processus PhotoFind doit utiliser un dossier de données donné ; un verrou
exclusif évite de démarrer deux instances qui récupéreraient la même file de travail.

Les fichiers sont rangés dans `photos/user-<id>-<identifiant>/<date>-<nom-galerie>/`.
La date utilise UTC. Un nom déjà pris reçoit `-1`, `-2`, etc., sans réutiliser de
dossier existant, y compris hors base. Les identifiants de galerie et les liens
sont indépendants de ces noms. Renommer un compte ou une galerie ne renomme pas
son dossier : les chemins restent stables. SQLite reste une base commune, avec
les associations et les empreintes, et non un fichier de base par utilisateur.


Le service écoute sur `127.0.0.1:18080` du serveur. La route du tunnel Cloudflare
existant cible `http://127.0.0.1:18080` depuis le même hôte. Le Compose serveur
force les cookies `Secure` ; utilisez l'adresse HTTPS publique pour vous connecter.
Le Compose local garde ces cookies utilisables en HTTP sur localhost.

Dans Portainer, stack `photofind` : dépôt `tlacassi/PhotoFind`, branche `main`,
fichier `compose.yaml`, puis **Pull and redeploy**. L'image est reconstruite depuis
le code ; aucun registre d'images n'est nécessaire. Sauvegardez avant mise à jour.

### Migration des anciennes bibliothèques

Au démarrage, une migration additive ajoute les galeries, permissions, modes de liens et quotas.
Les anciennes photos et anciens liens sont rattachés à « Photos existantes »,
possédée par le premier administrateur. S'il n'existe pas encore d'administrateur,
cette galerie n'est visible que des administrateurs futurs. Aucune empreinte existante n’est supprimée ou recalculée. Les images existantes
sont déplacées dans les dossiers utilisateur/galerie sans réencodage et sans écrasement. Les autres photographes n'ont
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
les images, miniatures, logos, fichiers en attente, la clé de liens et un manifeste SHA-256, contrôle l'intégrité SQLite et vérifie les
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
permissions, comptes, désactivation, suppression, invitations, quotas concurrents, révocation, limitation des connexions, cookies,
import parallèle, migration physique, progression/arrêt/reprise avec faux transport JavaScript, sauvegarde et
restauration. Le test réel d'import et redémarrage nécessite les modèles téléchargés.
Les tests de recherche utilisent des embeddings déterministes ; ils vérifient
l'isolation, pas la précision biométrique. Les tests JavaScript utilisent QuickJS
et un DOM simulé : une validation visuelle dans un navigateur reste nécessaire.

## Limites

- JPEG/PNG/WebP, 20 Mo par fichier. Les images téléchargées sont réencodées en JPEG,
  limitées à 2400 pixels sur le plus grand côté ; les originaux ne sont pas conservés.
- La reprise des fichiers pas encore transférés concerne le lot dans l’onglet ouvert.
  Pas de reprise par morceaux après fermeture du navigateur. Les fichiers déjà reçus
  par le serveur restent dans la file persistante et sont traités sans le navigateur. Une réponse réseau perdue après import
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
- Pas de paiement, de galerie publique sans lien privé, de ZIP ou de sauvegarde
  programmée. Si un problème disque empêche l’effacement après suppression d’une
  galerie, l’interface et les journaux signalent le dossier `.deleted-*` à nettoyer ;
  ce reliquat n’est plus accessible par les liens et n’est plus compté dans le quota.

Voir [TODO.md](TODO.md) pour l'avancement et les validations restantes.
Les modèles et leurs licences sont référencés dans [OpenCV Zoo](https://github.com/opencv/opencv_zoo).
