# PhotoFind — feuille de route

Les cases sont cochées après implémentation et vérification. Une modification locale
n'est pas considérée comme déployée.

## 1. Imports fiables et progression
- [x] Transférer chaque photo dans sa requête et distinguer transfert / analyse.
- [x] Afficher la progression et les erreurs par photo.
- [x] Permettre l'arrêt après les photos en cours et réessayer uniquement les échecs.
- [x] Exécuter l’analyse dans un thread, hors de la boucle des requêtes (test automatisé).
- [x] Vérifier la persistance d’un import réel OpenCV après redémarrage (test HTTP).
- [ ] Vérifier visuellement l’import, les galeries et l’administration dans le navigateur.
- [x] Examiner l'expérience Erugo avant d'affiner l'interface.

## 2. Galeries et migration
- [x] Créer, renommer et désactiver des galeries.
- [x] Rattacher chaque photo à une galerie et conserver les données existantes.
- [x] Limiter chaque recherche client à la galerie du lien.
- [x] Tester une migration depuis l'ancien schéma et son redémarrage.

## 3. Administration dédiée
- [x] Séparer les pages Administration et espace photographe.
- [x] Lister, créer, modifier et désactiver les comptes depuis l'administration.
- [x] Gérer les permissions (galeries, import, suppression, partage).
- [x] Prévoir la réinitialisation du mot de passe et la révocation des sessions.
- [x] Préserver un administrateur actif et empêcher l'auto-verrouillage.

## 4. Isolation des photographes
- [x] Rattacher chaque galerie à son propriétaire.
- [x] Autoriser explicitement le partage entre photographes.
- [x] Contrôler tous les accès côté serveur, y compris les images et suppressions.
- [x] Tester les accès croisés avec deux photographes et deux clients.

## 5. Liens clients
- [x] Lister les liens par galerie, avec leur expiration.
- [x] Révoquer un lien et invalider les sessions qui en dépendent.
- [x] Permettre de choisir la durée de validité et générer le QR code.

## 6. Sécurité et maintenance
- [x] Limiter les tentatives de connexion.
- [ ] Vérifier les paramètres des cookies derrière le tunnel HTTPS.
- [x] Fournir une sauvegarde cohérente des images et de la base.
- [x] Tester une restauration sur une instance isolée.
- [x] Mettre le README à jour selon le comportement réel.

## 7. Livraison
- [x] Exécuter les tests de migration, permissions, import et recherche.
- [x] Relire le diff et envoyer les commits sur GitHub.
- [ ] Redéployer via Portainer et vérifier le site public.

## Validations et améliorations restantes
- [ ] Construire et vérifier l’image Docker sur le serveur.
- [ ] Prévoir une reprise par morceaux après fermeture du navigateur si les volumes le nécessitent.
- [ ] Éviter les doublons lors d’une réponse perdue après import.

## Constats vérifiés
- Le 9 novembre 2026, la base et le dossier de photos du stockage monté étaient vides.
  La cause de l'import précédent reste inconnue ; aucune récupération n'est établie.
- L'existant réserve la création de comptes à l'administrateur, mais partage la
  bibliothèque entre tous les photographes.

## Journal de travail

### Premier incrément — imports
- Transfert séquentiel par photo, pour limiter la taille des requêtes et conserver
  les photos déjà terminées en cas d’échec d’une autre.
- Progression du transfert, état d’analyse, arrêt entre deux photos et nouvelle
  tentative des échecs / photos non envoyées : implémentés, validation navigateur restante.
- Analyse OpenCV exécutée hors de la boucle des requêtes.
- Correction de « Tout supprimer », qui référençait une section absente de la page.
- Validation : trois tests Python réussis ; contrôle du diff réussi.
- Livraison : incrément local ; pas encore déployé.

### Deuxième incrément — galeries et administration
- Migration additive, accès par propriétaire/collaborateur et recherche client limitée à la galerie.
- Administration dédiée des comptes, permissions, désactivation, mot de passe et sessions.
- Liens de 1 à 90 jours, liste et révocation ; archivage sans effacement des photos.
- Protection des connexions et cookies Secure forcés dans le Compose serveur.
- Maintenance hors ligne : sauvegarde, manifeste, restauration dans un nouveau dossier.
- Quinze tests automatisés passent, dont import réel OpenCV et redémarrage.
- La validation navigateur local a été refusée par le contrôle d’accès de l’outil.
  Elle reste à faire ; les tests QuickJS ne remplacent pas une vérification visuelle.
- Inspiration consultée : [Erugo — envois et progression](https://github.com/ErugoOSS/Erugo).
  PhotoFind reprend le suivi par fichier et la nouvelle tentative dans l’onglet,
  sans intégrer le moteur de transfert reprenable d’Erugo.

### Création et liste des galeries
- [x] Bouton de création ouvrant une fenêtre de saisie du nom.
- [x] Liste grise des galeries, avec nombre de photos et état d’archivage.
- [x] Miniature automatique (dernière photo) ou choix d’une photo avec le bouton étoile.
- [x] Vérifier le refus d’une miniature issue d’une autre galerie et le remplacement
  automatique si la photo choisie est supprimée.
- [x] Sauvegarder les données locales et redémarrer le serveur local sans rechargement
  automatique qui tournait depuis avant l’ajout des galeries.
- La validation visuelle reste en attente ; création et miniature sont testées par API.

### Imports parallèles, stockage et invitations
- [x] Trois requêtes d’import simultanées et deux analyses en parallèle, bornées côté serveur.
- [x] Progression globale et détail par fichier ; arrêt/reprise avec requêtes en cours.
- [x] Vérifier les actions renommer, désactiver/réactiver et miniature automatique (API et DOM simulé).
- [x] Supprimer une galerie et toutes ses photos/liens avec confirmation distincte.
- [x] Plusieurs liens simultanés, dates indépendantes et URL explicite de galerie.
- [x] Modes galerie, selfie ou mixte, contrôlés côté serveur.
- [x] Dossier par utilisateur, galeries datées et suffixes uniques, migration sans écrasement.
- [x] Invitations administrateur à usage unique avec durée et quota, inscription autonome.
- [x] Quotas modifiables, consommation visible côté admin et photographe, contrôle atomique à l’import.
- [x] Migration et conservation des images existantes vérifiées sur une bibliothèque isolée.
- Validation : 21 tests passent, dont concurrence, quotas, invitations, stockage, modes et suppression.
- Validation visuelle navigateur toujours en attente (accès précédemment refusé par l’outil).

- Migration locale appliquée après sauvegarde : 95 images préexistantes conservées,
  contrôlées par SHA-256 ; serveur local redémarré avec le nouveau code.

### Navigation, présentation et traitement durable
- [x] Résultats du selfie en haut, message avec le nombre de photos et défilement.
- [x] Retirer les noms de fichiers et le badge « Espace client » de la vue client.
- [x] Visionneuse client et photographe, précédent/suivant, clavier et téléchargement.
- [x] Accueil photographe distinct et page dédiée par galerie.
- [x] Liens nommés avec copie, QR code réouvrable et suppression effective de la liste.
- [x] Glisser-déposer avec voile, panneau de progression et compteur sur les galeries.
- [x] File de traitement persistante, reprise et déduplication au redémarrage.
- [x] Miniatures en arrière-plan avec repli sur le JPEG principal et mise à jour de la grille.
- [x] Retirer le bouton de miniature automatique, conserver le choix par étoile.
- [x] Personnalisation par galerie : couleurs et logo, avec PhotoFind par défaut.
- [x] Sauvegarder/restaurer la clé nécessaire pour recopier les nouveaux liens.
- [x] Annuler les traitements en attente lors de l’effacement des photos ou de la galerie.
- Validation automatisée : API, reprise de traitements, permissions, QR, fichiers,
  navigation de visionneuse et structure HTML. Vérification visuelle navigateur restante.

- Livraison locale : sauvegarde effectuée, serveur redémarré ; 95 photos préexistantes
  vérifiées par SHA-256 et 95 miniatures générées sans modification des JPEG principaux.
- 27 tests automatisés passent. Le déploiement public Portainer et la validation
  visuelle dans un navigateur restent des étapes distinctes.

### Aperçu des couleurs, stabilité des images et doublons
- [x] Appliquer les couleurs en direct sur la page photographe, sans requête d’écriture.
- [x] Enregistrer explicitement le thème et conserver l’aperçu pendant le suivi d’import.
- [x] Conserver les éléments de galerie et de photo pendant les mises à jour de progression.
- [x] Utiliser directement les miniatures prêtes, sans provoquer un second rechargement.
- [x] Refuser les doublons dans une même galerie, même renommés ou importés simultanément.
- [x] Indexer les images existantes sans supprimer les copies déjà présentes et sans
  régénérer les miniatures existantes.
- [x] Afficher l’erreur de doublon dans le traitement en arrière-plan.
- Validation : 34 tests passent, dont aperçu sans sauvegarde, stabilité des miniatures,
  contenu identique avec métadonnées différentes, concurrence et remontée de l’erreur.

### Selfies et gros plans
- [x] Distinguer aucun visage, plusieurs visages et aucune correspondance.
- [x] Détection multi-échelle bornée, avec coordonnées natives pour l’alignement SFace.
- [x] Conserver les détections natives et supprimer les doublons entre échelles.
- [x] Garder le seuil de comparaison existant.
- Validation : 38 tests passent. Sur un gros plan d’une image publique de test OpenCV,
  l’ancien passage natif détectait 0 visage ; la correction en détecte 1 et retrouve
  la référence (cosinus 0,943 au seuil 0,363). Ce n’est pas une mesure de précision
  sur les photos de l’utilisateur ; son selfie reste à retester.
- [x] Proposer une réanalyse des visages des galeries existantes.

### Réanalyse des galeries existantes
- [x] Traitement persistant distinct pour réindexer les visages sans réimporter les images.
- [x] Bouton propriétaire/administrateur ; refus des galeries non autorisées et désactivées.
- [x] Ne pas effacer le fichier source dans le nettoyage des traitements de réanalyse.
- [x] Conserver les anciennes empreintes si le nombre de visages n’augmente pas.
- [x] Éviter de lancer deux réanalyses simultanées pour la même photo.
- Validation : 39 tests passent, dont conservation des fichiers et des empreintes
  lors d’une réanalyse moins favorable.
- Comparaison locale sans modification des images : 13 photos auparavant sans visage
  deviennent indexables, 15 visages supplémentaires sur 95 photos. Ce gain ne mesure
  pas le nombre de correspondances exactes pour le selfie de l’utilisateur.

- Réanalyse locale terminée : 73 photos avec visage indexé (60 auparavant), 84
  visages (69 auparavant), 0 traitement en erreur. Aucune image n’a été modifiée.
- [x] Vérifier qu’un redémarrage de la file ne relance pas les analyses terminées.
- Le bouton manuel permet une nouvelle réanalyse ; les tâches interrompues restent
  les seules à reprendre automatiquement après un redémarrage.
