# PhotoFind — feuille de route

Les cases sont cochées après implémentation et vérification. Une modification locale
n'est pas considérée comme déployée.

## 1. Imports fiables et progression
- [ ] Transférer les photos une par une et distinguer transfert / analyse.
- [ ] Afficher la progression et les erreurs par photo.
- [ ] Permettre l'arrêt après la photo en cours et réessayer uniquement les échecs.
- [x] Exécuter l’analyse dans un thread, hors de la boucle des requêtes (test automatisé).
- [ ] Vérifier l'import dans le navigateur et la persistance après redémarrage.
- [ ] Examiner l'expérience Erugo avant d'affiner l'interface.

## 2. Galeries et migration
- [ ] Créer, renommer et archiver des galeries.
- [ ] Rattacher chaque photo à une galerie et conserver les données existantes.
- [ ] Limiter chaque recherche client à la galerie du lien.
- [ ] Tester une migration depuis l'ancien schéma et son redémarrage.

## 3. Administration dédiée
- [ ] Séparer les pages Administration et espace photographe.
- [ ] Lister, créer, modifier et désactiver les comptes depuis l'administration.
- [ ] Gérer les permissions (galeries, import, suppression, partage).
- [ ] Prévoir la réinitialisation du mot de passe et la révocation des sessions.
- [ ] Préserver un administrateur actif et empêcher l'auto-verrouillage.

## 4. Isolation des photographes
- [ ] Rattacher chaque galerie à son propriétaire.
- [ ] Autoriser explicitement le partage entre photographes.
- [ ] Contrôler tous les accès côté serveur, y compris les images et suppressions.
- [ ] Tester les accès croisés avec deux photographes et deux clients.

## 5. Liens clients
- [ ] Lister les liens par galerie, avec leur expiration.
- [ ] Révoquer un lien et invalider les sessions qui en dépendent.
- [ ] Permettre de choisir la durée de validité et générer le QR code.

## 6. Sécurité et maintenance
- [ ] Limiter les tentatives de connexion.
- [ ] Vérifier les paramètres des cookies derrière le tunnel HTTPS.
- [ ] Fournir une sauvegarde cohérente des images et de la base.
- [ ] Tester une restauration sur une instance isolée.
- [ ] Mettre le README à jour selon le comportement réel.

## 7. Livraison
- [ ] Exécuter les tests de migration, permissions, import et recherche.
- [ ] Relire le diff, envoyer les commits sur GitHub.
- [ ] Redéployer via Portainer et vérifier le site public.

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
