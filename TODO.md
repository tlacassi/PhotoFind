# PhotoFind — feuille de route

Les cases sont cochées après implémentation et vérification. Une modification locale
n'est pas considérée comme déployée.

## 1. Imports fiables et progression
- [x] Transférer les photos une par une et distinguer transfert / analyse.
- [x] Afficher la progression et les erreurs par photo.
- [x] Permettre l'arrêt après la photo en cours et réessayer uniquement les échecs.
- [x] Exécuter l’analyse dans un thread, hors de la boucle des requêtes (test automatisé).
- [x] Vérifier la persistance d’un import réel OpenCV après redémarrage (test HTTP).
- [ ] Vérifier visuellement l’import, les galeries et l’administration dans le navigateur.
- [x] Examiner l'expérience Erugo avant d'affiner l'interface.

## 2. Galeries et migration
- [x] Créer, renommer et archiver des galeries.
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
