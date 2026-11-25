# Historique des versions

## Non publié

Correcteur d’orthographe, Smail comme messagerie par défaut, menus réorganisés et nombreuses retouches d’interface. Les mises à jour vous sont désormais proposées : rien n’est téléchargé sans votre accord (réglable dans Préférences › Général).

- Correcteur d’orthographe en français dans la rédaction : fautes soulignées, suggestions et « Ajouter au dictionnaire » au clic droit (dictionnaire local, aucune connexion).
- Smail comme messagerie par défaut : un lien « mailto: » ouvre un nouveau message prérempli (Préférences › Général › Définir Smail comme messagerie par défaut…). Un second lancement de Smail est transmis à la copie déjà ouverte.
- Message › Afficher l’original : en-têtes complets et verdict SPF / DKIM / DMARC, pour comprendre un classement en spam.
- Pièces jointes reçues : « Tout enregistrer… » dans un dossier (rien n’est écrasé, fichiers dangereux sur accord).
- Menus réorganisés : nouveau menu Dossier ; Comptes › Ajouter / Gérer ; Outils › Actualiser (F5, recharge et synchronise) et Travailler hors ligne ; « Suivre » remplace « Étoiler » partout ; raccourcis Ctrl+U (lu / non lu), Ctrl+Maj+G (suivre), Ctrl+Maj+V (déplacer) ; J, K, E, S dans tous les styles ; le menu clic droit reprend le menu Message.
- Textes accordés (« 1 message », « 5 messages ») ; colonne de gauche « Compte » avec le nom seul ; dossier Brouillons : bouton vers les brouillons enregistrés sur ce PC ; plus de doublon entre notification et barre d’état.
- Filtres de la liste : retour à « Tous » à chaque changement de dossier (un filtre conservé faisait paraître le dossier vide) ; « Non lus » masqué dans Envoyés et Brouillons.
- Liste des messages : un message non lu se distingue d’un coup d’œil (expéditeur et objet en gras, point bleu plus grand) ; les messages lus sont estompés.
- En-tête : bouton thème clair / sombre après les paramètres ; bouton « Commandes » retiré (Ctrl+K ou menu Affichage) ; plus d’espace vide sous l’en-tête. Menu Affichage : « Passer au thème clair / sombre » selon le thème actuel.
- Mises à jour : nouveau mode « Me demander » (par défaut) : la nouvelle version est signalée et rien n’est téléchargé sans votre accord ; modes « Automatiques » et « Désactivées » dans Préférences › Général.
- Correction : le bouton « Filtres » de la recherche plantait quand le champ de recherche était vide (1.2.0).
- Rédaction allégée : pièces jointes en étiquettes compactes (chacune avec son ×, sur plusieurs lignes), total en Mo en tête, en orange au-delà de 25 Mo une fois encodé ; boutons « Joindre », « Image », « Enregistrer » ; titre de la fenêtre égal à l’objet du message.
- Préférences rangées par thème : Général, Comptes, Apparence, Réception, Rédaction, Sécurité, Règles et indésirables, Raccourcis. Page Comptes détaillée (méthode de connexion, serveurs) avec « Ajouter un compte » ; menu Comptes › Gérer les comptes….
- Connexion Gmail et Outlook en un clic (« Se connecter avec Google / Microsoft ») avec l’application OAuth2 de Smail, une fois ses identifiants renseignés (`docs/OAUTH.md`) ; identifiants techniques réservés au mode avancé.

## 1.2.0 — 2026-11-25


Interface plus simple et plus claire. Les copies installées depuis la 1.1.0 se mettent à jour automatiquement.

- Ajout de compte : réglages des serveurs détectés à partir de l’adresse (fichier publié par l’hébergeur, base publique de Thunderbird, noms habituels ; seul le domaine est transmis) ; champ « Votre nom (vu par vos destinataires) ».
- Notifications flottantes en bas de la fenêtre, avec « Annuler » après un déplacement (corbeille, archives, dossier) : les messages reviennent à leur place.
- Dossiers : icônes, dossiers système en tête et nombre de non-lus. Liste des messages groupée par date (« Aujourd’hui », « Hier »…) avec actions au survol (archiver, supprimer, lu/non lu).
- En-tête simplifié : recherche avec formulaire « Filtres », bouton « Commandes », indicateur de connexion ; « Hors ligne » dans le menu Comptes.
- Paquet MSIX pour le Microsoft Store (`tools/build_msix.py`, construit par la CI) ; la version Store laisse ses mises à jour au Store. Politique de confidentialité (`PRIVACY.md`).

## 1.1.1 — 2026-11-24


Première mise à jour installée automatiquement depuis la 1.1.0.

- Nouveau : Outils › À propos de Smail affiche la version, le mode de mise à jour de cette copie et le dossier des données locales.

## 1.1.0 — 2026-11-24

Smail 1.1.0 est une mise à jour majeure. **Depuis la 1.0.0, installez-la une fois manuellement** (l’installateur conserve vos comptes, votre cache et vos réglages) : les versions suivantes s’installeront ensuite toutes seules.

### Rédaction et envoi

- Rédaction mise en forme : gras, italique, souligné, listes et liens, avec une version texte équivalente pour les destinataires qui n’affichent pas le HTML ; signature mise en forme par compte.
- Envoi en arrière-plan : la fenêtre de rédaction se ferme dès « Envoyer ». En bas de la fenêtre principale, « Annuler » reste possible pendant le délai d’annulation (réglable de 0 à 30 s), puis la progression s’affiche : connexion, Mo envoyés, vérification par le serveur, copie dans Envoyés.
- Envoi programmé (« Envoyer plus tard ») et boîte d’envoi locale (Fichier › Envois programmés), où sont aussi conservés les envois en échec. Un message n’est jamais renvoyé automatiquement.
- Alerte avant d’envoyer un message de plus de 25 Mo : beaucoup de messageries (Outlook, Microsoft 365, entreprises) refusent les messages de plus de 20 à 35 Mo ; Gmail accepte jusqu’à 50 Mo.
- Carnet d’adresses et autocomplétion des destinataires.
- Invitations de calendrier : résumé en heure locale, réponse Accepter / Provisoire / Refuser, ajout au calendrier Windows.

### Lecture et organisation

- Vue par conversation : messages regroupés, lecture empilée avec extraits, vos réponses incluses, actions sur toute la conversation (Alt+Bas / Alt+Haut pour naviguer).
- Liste des messages sans pages : les messages plus anciens se chargent en arrivant en bas de la liste.
- Sélection multiple, glisser-déposer vers un dossier, tout marquer comme lu, vider la corbeille et le spam.
- Création, renommage et suppression de dossiers ; noms lisibles sur les serveurs qui ajoutent « INBOX. » devant chaque dossier.
- Aperçu des pièces jointes (images, PDF, textes), message dans une fenêtre séparée, impression.
- Report de messages : un message quitte la réception et y revient à l’heure choisie.
- Aperçus des messages dans la liste, sans citations ni signature.

### Tri, spam et désabonnement

- Règles de tri, expéditeurs bloqués et approuvés, spam signalé par le serveur, actions « Signaler comme spam » et « Ce n’est pas un spam ».
- Désabonnement des listes de diffusion en un clic, toujours après confirmation.

### Recherche

- Recherche avancée : `de:`, `à:`, `objet:`, `a:pj`, `est:nonlu`, `après:`, `avant:`, expressions entre guillemets ; recherche dans tous les dossiers.
- Recherche hors ligne plus rapide (index local) lorsque le cache n’est pas chiffré.

### Comptes, sécurité et mises à jour

- Mises à jour automatiques : vérification toutes les 6 heures, téléchargement en arrière-plan, installation à la fermeture de Smail (ou « Redémarrer maintenant »). Chaque mise à jour est signée et vérifiée avant installation.
- Identifiants de connexion IMAP et SMTP distincts de l’adresse, mot de passe d’envoi distinct (hébergeurs qui l’exigent).
- Suppression complète d’un compte de ce PC : configuration, cache, brouillons, certificats approuvés et mots de passe du coffre Windows.
- Liste et retrait des certificats approuvés (Préférences › Sécurité).
- Installateur Windows sans droits administrateur ; nouvelle icône.

### Corrections

- Envoi des messages volumineux : le délai d’attente de 20 s coupait l’envoi et la copie dans Envoyés. Le serveur dispose maintenant de 5 minutes ; une connexion coupée pendant l’envoi est signalée « peut-être envoyé » ; les copies dans Envoyés manquées sont rattrapées automatiquement, sans doublon.
- Réponses : les noms accentués s’affichent en clair dans les champs À et Cc.
- Autocomplétion : l’adresse choisie n’est plus insérée deux fois ; virgule finale acceptée.
- Boutons : plus de cadre de focus après un clic.
- Plus de dossiers affichés en double après traduction de leur nom.

### Technique

- Synchronisation incrémentale (CONDSTORE), sessions IMAP réutilisées, téléchargements par lots.
- Base locale versionnée avec migrations automatiques ; données compatibles avec Smail 1.0.0.
- Licence MIT ; intégration continue et publication automatisées (GitHub Actions) ; journal des erreurs inattendues sans contenu de message.

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
