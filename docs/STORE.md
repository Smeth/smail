# Fiche Microsoft Store de Smail (produit 9NZG6PT58G5J)

Textes à copier dans l’Espace partenaires › smail › Soumission. Langue de la fiche : français (France).

## Paquet

- Fichier : `dist/msix/Smail-X.Y.Z.msix` (construit par `python tools/build_msix.py`, ou artefact « Smail-msix » de GitHub Actions).
- Identité (`packaging/msix/identity.json`) : `Smeth-Dev.smail`, éditeur `CN=66846981-9B72-4B2D-BE19-46D8B67B4CE7`.
- Captures : `python tools/store_screenshots.py` → `dist/store/` (données d’exemple uniquement).

## Tarification et disponibilité

- Prix : **Gratuit**. Disponibilité : tous les marchés (ou France, Belgique, Suisse, Canada, Luxembourg…).
- Visibilité : publique.

## Propriétés

- Catégorie : **Productivité**. Sous-catégorie : aucune.
- Politique de confidentialité : `https://github.com/Smeth/smail/blob/main/PRIVACY.md`
- Site web : `https://github.com/Smeth/smail`
- Coordonnées d’assistance : `https://github.com/Smeth/smail/issues`
- Configuration requise : clavier, souris ; Windows 10 version 1809 ou ultérieure, x64.

## Classification par âge (questionnaire IARC)

Catégorie « Application (hors jeu) » ; réponses :

- Violence, sexualité, langage grossier, drogues, jeux d’argent : **Non**.
- Les utilisateurs peuvent-ils communiquer entre eux ? **Oui** (c’est un client mail : échange de messages avec les contacts de l’utilisateur, sans modération par l’application).
- Partage de la position de l’utilisateur : **Non**. Achats numériques : **Non**. Navigation web non restreinte : **Non** (les liens s’ouvrent dans le navigateur de l’utilisateur).

## Description de la fiche

### Description (texte principal)

Smail est un client mail de bureau pour Windows, simple, rapide et respectueux de votre vie privée. Il fonctionne avec toutes les messageries IMAP/SMTP : votre hébergeur, Gmail, Outlook.com, Yahoo, iCloud…

Vos messages et vos réglages restent sur votre ordinateur : pas de compte Smail, pas de serveur intermédiaire, pas de publicité, aucune collecte de données. Les mots de passe sont rangés dans le Gestionnaire d’identifiants de Windows et la copie locale de vos mails peut être chiffrée.

Écrivez avec un correcteur d’orthographe, une mise en forme simple et votre signature. L’envoi se fait en arrière-plan avec une progression claire, un délai d’annulation et l’envoi programmé. Lisez vos messages par conversation, retrouvez-les avec une recherche avancée et rangez-les avec des règles automatiques.

### Nouveautés de cette version

Reprendre la section de la version dans CHANGELOG.md (par exemple « 1.3.0 »), première phrase et principales lignes.

### Fonctionnalités du produit (une par ligne, 20 au maximum)

- Toutes les messageries IMAP/SMTP, réglages détectés automatiquement à partir de l’adresse
- Vos mails restent sur votre PC ; aucune collecte de données
- Correcteur d’orthographe en français
- Mise en forme, signature par compte et pièces jointes par glisser-déposer
- Envoi en arrière-plan avec annulation et envoi programmé
- Vue par conversation et liste groupée par date
- Recherche avancée : expéditeur, objet, pièces jointes, dates
- Règles de tri, filtre anti-spam et désabonnement en un clic
- Mode hors ligne et réception instantanée
- Thème clair ou sombre, trois styles et trois densités
- Images distantes bloquées par défaut, certificats vérifiés
- Lien « mailto: » : Smail peut être votre messagerie par défaut

### Mots-clés de recherche (7 au maximum)

`mail`, `email`, `courriel`, `IMAP`, `messagerie`, `client mail`, `Outlook`

### Mention de copyright

© 2026 Smeth-Dev — Licence MIT

## Options de soumission › Notes pour la certification

> Smail est une application de bureau (Python / PySide6, Qt WebEngine) empaquetée en MSIX ; la capacité restreinte **runFullTrust** est nécessaire à toute application Win32 empaquetée. L’application n’a pas de compte propre : pour la tester, ajoutez n’importe quel compte de messagerie IMAP/SMTP (par exemple un compte Outlook.com ou Gmail avec mot de passe d’application) via « Ajouter un compte ». Aucune donnée n’est envoyée au développeur. Code source : https://github.com/Smeth/smail

Justification de runFullTrust (si demandée) : « Application de bureau Win32 classique (interface Qt, moteur de rendu des messages Qt WebEngine, accès au Gestionnaire d’identifiants Windows) empaquetée en MSIX pour le Store. »
