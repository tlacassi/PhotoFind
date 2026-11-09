# PhotoFind — prototype local

Importez des photos, puis utilisez un selfie pour retrouver celles qui contiennent le même visage. Les images et les empreintes sont traitées et stockées localement. Aucun compte ou service externe n'est nécessaire après le téléchargement initial des modèles.

## Démarrage sur Mac avec Docker

1. Installez et lancez [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2. Dans le Terminal, ouvrez ce dossier, puis lancez :

   ```sh
   docker compose up --build
   ```

3. Ouvrez <http://localhost:8000> sur le Mac. Le premier démarrage télécharge les dépendances et les modèles (environ 40 Mo), et peut prendre quelques minutes.
4. Dans l’espace photographe, importez des photos JPEG, PNG ou WebP puis cliquez sur « Générer le lien client ». Ouvrez « Tester la vue client » pour choisir un selfie et télécharger les photos correspondantes.

Arrêtez avec `Ctrl+C`. Pour relancer : `docker compose up`. Les images et les données restent dans le volume Docker `photofind-data` ; le bouton « Tout supprimer » efface les photos et leurs empreintes. Docker peut préfixer le nom du volume avec le nom du dossier.

## Sans Docker

Avec Python 3.11 ou 3.12 :

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python download_models.py
uvicorn app:app --host 127.0.0.1 --port 8000
```

## Limites du prototype

- Le lien client et son QR code utilisent l’adresse du navigateur. Avec localhost, ils fonctionnent uniquement sur le Mac : le QR code ne permet pas d’y accéder depuis un téléphone. Ce prototype ne dispose pas d’authentification ni d’isolation des accès : la vue client n’empêche pas d’accéder aux fonctions photographe ou aux autres photos par l’API. Ne l’exposez pas sur Internet, y compris via un tunnel Cloudflare, avant d’avoir sécurisé les accès et les données. Le port Docker reste lié à localhost.
- Les photos importées sont réencodées en JPEG et limitées à 2 400 pixels sur leur plus grand côté ; le téléchargement fournit cette version, pas l'original. Les fichiers HEIC de certains iPhone doivent d'abord être convertis en JPEG.
- La reconnaissance peut manquer une personne ou proposer une mauvaise photo. Les photos sans visage détecté restent dans la bibliothèque mais ne peuvent pas correspondre à une recherche. Essayez des images nettes et bien éclairées.
- Les empreintes faciales et les photos restent enregistrées jusqu'à leur suppression. Le selfie n'est pas enregistré. Utilisez uniquement des photos et selfies pour lesquels les personnes concernées ont donné leur accord ; avant toute mise en production, examinez les obligations applicables aux données biométriques.
- Les modèles YuNet et SFace sont distribués par [OpenCV Zoo](https://github.com/opencv/opencv_zoo). Vérifiez les licences et conditions des modèles avant une exploitation commerciale.

## Déploiement privé via Portainer

La configuration fournie est destinée à un essai privé, pas à une mise en ligne client. Le conteneur écoute sur le port 8000 du serveur, lié exclusivement à l'interface locale du serveur (`127.0.0.1`). Il n'est donc pas accessible directement depuis un autre appareil. Un tunnel SSH vers ce port permet à l'administrateur de le tester ; ne branchez pas encore de tunnel Cloudflare public.

Dans Portainer, créez une stack depuis ce dépôt Git privé, sélectionnez la branche `main` et le chemin `compose.yaml`. Activez l'authentification Git et configurez vos propres identifiants en lecture seule dans Portainer. La stack construit l'image depuis le Dockerfile : le serveur doit pouvoir télécharger les dépendances et les modèles. Selon la configuration et la version de Portainer, la construction depuis Git peut ne pas fonctionner avec un environnement Docker distant ; vérifiez les journaux de déploiement.

Le volume Docker `photofind-data` stocke la base SQLite, les photos et les empreintes. Il est distinct des données du Mac : le déploiement ne transfère pas automatiquement la bibliothèque locale. Sauvegardez le volume entier, application arrêtée pour conserver la cohérence de SQLite et des photos, et vérifiez régulièrement une restauration. Ne supprimez pas le volume lors d'une mise à jour ou suppression de stack. La bibliothèque n'est pas incluse dans le dépôt Git ni dans l'image Docker.

Le conteneur fonctionne sans privilèges root et dispose d'un contrôle de santé. Les modèles sont téléchargés à la construction et leur empreinte SHA-256 est vérifiée. L'application ne propose toujours pas d'authentification ou de séparation des droits, de liens privés, de limitation des requêtes, ni de protection suffisante des photos et données biométriques. Ces points restent à concevoir et tester avant toute exposition Internet, même derrière Cloudflare.
