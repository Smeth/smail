# Historique des versions

## Non publié

- Suppression d’un compte (menu Comptes ou Préférences) : configuration, cache, brouillons, copies d’envoi, certificats approuvés et secrets du coffre Windows sont effacés de ce PC.
- Liste et retrait des certificats approuvés dans Préférences › Sécurité.
- Sélection multiple des messages ; actions groupées en une commande IMAP par dossier.
- Tout marquer comme lu, suppression définitive depuis la corbeille, vidage de la corbeille et du spam.
- Création, renommage et suppression de dossiers (noms accentués encodés en UTF-7 modifié).
- Performances : réutilisation des sessions IMAP et téléchargement des listes et de la synchronisation par lots.
- Schéma SQLite versionné avec migrations automatiques ; compatibilité conservée avec Smail 1.0.0.
- Icône de l’application, informations de version de l’exécutable, gestionnaire d’erreurs inattendues.
- Dépendances de développement séparées (`requirements-dev.txt`) et intégration continue GitHub Actions.

## V1 — 1.0.0

Première version publique de Smail, client mail de bureau Windows en français.

- Gestion de plusieurs comptes IMAP/SMTP et boîte de réception unifiée.
- Connexions SSL/TLS et STARTTLS, authentification par mot de passe ou OAuth2 configurable.
- Lecture HTML assainie, images intégrées, autorisation explicite des images distantes et alertes sur les pièces jointes dangereuses.
- Nouveau volet de lecture : sujet séparé, avatar, expéditeur, destinataires, date et actions de réponse dans l’en-tête.
- Rédaction compacte, Cc/Cci, signature, ajout de fichiers, glisser-déposer, collage d’images et miniatures.
- Brouillons locaux automatiques, copies serveur et export des messages envoyés au format EML.
- Recherche, dossiers, déplacement, archivage et gestion des états lus/non lus et étoiles.
- Synchronisation en arrière-plan, cache hors ligne et chiffrement optionnel du contenu du cache.
- Trois styles d’interface, thèmes clair/sombre, densité réglable et palette de commandes.
- Scripts de compilation Windows avec PyInstaller ; maquettes autonomes conservées dans `mockups/`.

Validation avant publication : **104 tests locaux réussis** et démarrage de l’exécutable Windows vérifié. Les tests locaux ne remplacent pas les essais avec chaque fournisseur de messagerie.

Les fichiers de configuration personnels, caches, journaux, secrets et dossiers de compilation ne font pas partie des sources publiées. L’utilisation d’OAuth2 nécessite les identifiants d’une application enregistrée auprès du fournisseur.
