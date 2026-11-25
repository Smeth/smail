# Smail — V1

**Version 1.0.0 — première version publique.** Client mail de bureau pour Windows, en français, développé en Python avec PySide6.

La V1 propose trois styles d’interface, les thèmes clair et sombre, une boîte de réception unifiée, une rédaction avec miniatures des pièces jointes et un volet de lecture organisé en cartes. Les réglages d’apparence sont accessibles dans le menu **Affichage**. Les détails de cette version figurent dans [CHANGELOG.md](CHANGELOG.md).

Client de bureau en français, Python 3.11+ et PySide6, avec les quatre phases du cahier des charges implémentées. IMAP gère la réception et les actions ; SMTP gère l’envoi. Aucun identifiant de compte ni identifiant d’application OAuth n’est livré avec le projet.

## Installer et lancer

Dans PowerShell :

```powershell
git clone https://github.com/Smeth/smail.git
cd smail
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m mailclient.main
```

Pour mettre à jour une installation existante, fermez Smail, réexécutez la commande d’installation des dépendances, puis la commande de lancement. Les comptes existants restent compatibles et les nouvelles tables SQLite sont créées automatiquement. Il n’est pas nécessaire d’activer l’environnement virtuel ni de modifier la politique d’exécution PowerShell.

L’exécutable construit est `dist\Smail\Smail.exe`. Conservez et distribuez **tout** le dossier `dist\Smail` : le fichier exe seul ne suffit pas, notamment pour WebEngine.

Pour distribuer Smail, préférez l’installateur `Smail-<version>-installation.exe`, produit par l’intégration continue (ou localement avec Inno Setup 6 : `ISCC.exe /DAppVersion=1.0.0 installer\Smail.iss` après PyInstaller). Il installe Smail pour l’utilisateur courant, sans droits administrateur, dans `%LOCALAPPDATA%\Programs\Smail`, avec un raccourci dans le menu Démarrer. La désinstallation conserve les comptes, le cache et les secrets : supprimez d’abord vos comptes dans Smail pour tout effacer. L’installateur n’est pas signé : Windows SmartScreen peut afficher un avertissement tant qu’un certificat de signature de code n’est pas utilisé.

## Comptes et chiffrement réseau

**Ajouter un compte** permet de saisir le nom, l’adresse et les paramètres distincts IMAP/SMTP. En quittant le champ adresse, les domaines Gmail, Outlook/Hotmail et Yahoo préremplissent les champs serveur encore vides. Pour LWS, cPanel ou un serveur interne, reprenez les valeurs fournies par votre hébergeur ou administrateur. Le bouton **Compte** modifie un compte existant, sa signature et son authentification.

**Comptes › Supprimer le compte…** (ou l’icône corbeille dans Préférences › Comptes) retire le compte de ce PC après confirmation : paramètres, cache hors ligne, brouillons locaux, copies locales des envois, certificats approuvés, ainsi que mot de passe et jetons OAuth2 du Gestionnaire d’identifiants Windows. Les messages restent sur le serveur. Fermez d’abord les fenêtres de rédaction ouvertes.

| Connexion | Port IMAP usuel | Port SMTP usuel | Comportement |
| --- | --- | --- | --- |
| SSL/TLS | 993 | 465 | TLS immédiat, choix initial |
| STARTTLS | 143 | 587 | Mise à niveau chiffrée obligatoire avant authentification |
| Aucun | 143 | 25 | Connexion en clair après confirmation explicite |

Le changement du type remplit le port usuel ; le port reste modifiable. **Aucun** affiche un avertissement rouge et impose de cocher la confirmation du risque avant le test ou l’enregistrement. Un cadenas ouvert et un avertissement restent visibles près du compte. Ce mode expose les identifiants et les mails aux tiers présents sur le réseau ; certains serveurs refusent cette authentification. OAuth2 exige une connexion chiffrée sur les deux serveurs.

**Tester la connexion IMAP et SMTP** s’authentifie aux deux serveurs sans envoyer de message. L’identifiant de connexion est par défaut l’adresse e-mail. Si votre hébergeur fournit un identifiant différent (par exemple « client12345 ») ou un serveur d’envoi avec ses propres identifiants, renseignez le champ **Identifiant** du bloc IMAP ou SMTP et, au besoin, décochez **Mot de passe SMTP identique à celui du compte** pour saisir un mot de passe SMTP distinct (conservé dans le Gestionnaire d’identifiants Windows). Ces identifiants sont enregistrés à part de la configuration du compte, qui reste lisible par Smail 1.0.0. En OAuth2, l’identité est toujours l’adresse e-mail. Les noms affichés et les objets peuvent être accentués ; les adresses de boîte doivent être ASCII.

La vérification TLS système et le contrôle du nom de serveur sont actifs par défaut (`ssl.create_default_context`). Si la vérification échoue, une sonde sans authentification récupère le certificat. La boîte de sécurité affiche le serveur, l’émetteur, les dates, l’empreinte SHA-256 et la raison de l’échec. **Annuler** est le choix par défaut. **Continuer quand même** autorise seulement cette empreinte pour ce compte et ce serveur pendant la session. La case de confiance permanente conserve cette empreinte dans SQLite. Tout changement d’empreinte réaffiche l’alerte, même si le nouveau certificat est par ailleurs valide. Comparez l’empreinte avec votre administrateur via un canal indépendant avant de faire confiance.

Un serveur sans STARTTLS est refusé sans envoi d’identifiants : aucun repli automatique en clair. Une alerte de certificat rencontrée en synchronisation suspend cette opération ; choisissez le compte puis **Actualiser** pour examiner l’alerte. Relancez ensuite **Synchroniser** ; la surveillance IDLE peut être redémarrée en désactivant puis réactivant son option dans Préférences. Pour retirer une exception permanente, ouvrez **Préférences › Sécurité › Certificats approuvés** puis cliquez sur **Retirer** : l’alerte réapparaîtra à la prochaine connexion à ce serveur.

## Gmail : mot de passe d’application

Activez la validation en deux étapes du compte Google, puis créez un mot de passe d’application dédié à Smail. Saisissez ce mot de passe dans Smail, plutôt que votre mot de passe principal. L’option peut être absente selon la politique de l’organisation ou la configuration de sécurité du compte. Consultez les [instructions Google](https://support.google.com/accounts/answer/185833?hl=fr).

Gmail peut aussi utiliser OAuth2 avec la configuration ci-dessous. Le serveur Gmail conserve automatiquement la copie des messages envoyés ; Smail évite un APPEND supplémentaire pour ne pas créer de doublon.

## OAuth2 Google et Microsoft

Le flux est implémenté : navigateur système, code d’autorisation, PKCE S256, vérification `state`, retour HTTP limité à la boucle locale, renouvellement des jetons et authentification IMAP/SMTP XOAUTH2. Aucun navigateur de lecture des mails n’est utilisé pour la connexion. Jetons, jetons de renouvellement et secret client Google sont stockés exclusivement dans le Gestionnaire d’identifiants Windows, via keyring. Les longs jetons sont découpés en plusieurs entrées du coffre pour respecter la limite Windows ; aucun fragment n’est écrit en fichier.

Il faut disposer d’une **application enregistrée chez le fournisseur**. Le projet ne peut pas créer cet enregistrement dans votre compte et ne contient aucun identifiant client partagé.

### Google

1. Dans Google Cloud, configurez l’écran de consentement OAuth et un client OAuth de type **Application de bureau**. Ajoutez votre compte aux utilisateurs de test si l’application est en mode test. Le scope d’accès aux mails est `https://mail.google.com/` ; la distribution publique peut exiger la vérification Google de ce scope restreint.
2. Dans **Compte**, sélectionnez **OAuth2 Google**, renseignez l’identifiant client et le secret client fourni pour ce client bureau, si requis.
3. Cliquez sur **Connecter avec OAuth2 dans le navigateur** et autorisez le compte correspondant à l’adresse saisie dans Smail. Le retour utilise `http://127.0.0.1:<port-libre>/callback`.
4. Testez les serveurs puis enregistrez le compte. Le renouvellement est automatique tant que le fournisseur autorise le jeton de renouvellement.

Voir la [documentation Google pour les applications de bureau](https://developers.google.com/identity/protocols/oauth2/native-app).

### Microsoft / Outlook / Microsoft 365

1. Enregistrez une application native publique dans Microsoft Entra. Choisissez les types de comptes attendus (inclure les comptes personnels pour Outlook.com).
2. Ajoutez un retour de type **Mobile et applications de bureau** : `http://localhost/callback`. Smail écoute uniquement sur `127.0.0.1`, avec un port libre ; Microsoft ignore le port lors de la comparaison du retour localhost.
3. Ajoutez les permissions **déléguées** Exchange Online `IMAP.AccessAsUser.All` et `SMTP.Send`, ainsi que le consentement nécessaire à `offline_access`. Votre organisation peut imposer un consentement administrateur ou restreindre IMAP/SMTP AUTH. Il ne s’agit pas des permissions Microsoft Graph `Mail.*`.
4. Dans Smail, sélectionnez **OAuth2 Microsoft**, saisissez l’identifiant client. Le tenant est `common` par défaut ; pour une application mono-tenant, renseignez l’UUID ou le domaine du tenant. Aucun secret client confidentiel n’est demandé pour ce client public.
5. Connectez-vous dans le navigateur, testez IMAP/SMTP puis enregistrez.

Références : [OAuth pour IMAP/SMTP Microsoft](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth) et [retours localhost](https://learn.microsoft.com/en-us/entra/identity-platform/reply-url). La disponibilité dépend aussi des autorisations du compte et du tenant. Une modification d’identifiant client, de tenant ou d’adresse impose de refaire l’autorisation.

## Lire, rechercher et gérer les messages

L’interface propose les dossiers, la liste paginée par 50 et le panneau de lecture. Les UID décroissants donnent l’ordre de réception ; l’ordre unifié utilise les dates déclarées des messages. Les non lus sont en gras, les étoiles et pièces jointes ont un indicateur.

- Sélectionnez un message pour le lire en texte brut ou HTML sécurisé. Les encodages MIME, UTF-8, ISO-8859-1, quoted-printable et base64 sont décodés. La lecture seule utilise `BODY.PEEK` et ne change pas le drapeau lu/non lu.
- **Vue par conversation** (Affichage › Regrouper par conversation, Ctrl+Maj+T, activée par défaut) : les messages d’une même discussion sont réunis sur une ligne, d’après Message-ID, In-Reply-To et References (sans jamais mélanger deux comptes ; repli sur le sujet pour les réponses « Re: » dépourvues de références). La ligne affiche les participants, le nombre de messages de la page, et reste en gras s’il reste un non-lu. À l’ouverture, le lecteur affiche le premier message non lu, sinon le plus récent, dans une lecture empilée : les messages antérieurs sont repliés au-dessus (expéditeur, date et extrait), les suivants en dessous, y compris vos réponses retrouvées dans Envoyés et les autres dossiers en cache. Cliquez sur un message replié ou utilisez Alt+Bas / Alt+Haut pour le déplier. Les extraits ignorent les citations et signatures ; ils sont calculés à la synchronisation et conservés dans le cache. Archiver, Supprimer, Déplacer, Lu / non lu et Étoiler s’appliquent à toute la conversation de la liste ; Répondre vise le message affiché. Le regroupement porte sur la page chargée (50 messages).
- Ctrl+clic, Maj+clic ou Ctrl+A sélectionnent plusieurs messages. **Lu / non lu**, **Étoiler**, **Déplacer**, **Archiver** et **Supprimer** agissent sur toute la sélection, y compris depuis la boîte unifiée (Déplacer exige des messages d’un seul compte) ; une seule commande IMAP est envoyée par dossier. Répondre et Transférer exigent un seul message. Supprimer déplace vers la corbeille après confirmation ; depuis la corbeille, Supprimer devient une **suppression définitive**, confirmée séparément.
- **Tout marquer comme lu** (Ctrl+Maj+U, menu Message ou clic droit sur un dossier) agit sur tout le dossier courant côté serveur, ou sur la réception de chaque compte dans la boîte unifiée.
- **Comptes › Dossier** (ou clic droit sur la liste des dossiers) crée, renomme ou supprime un dossier. Les dossiers système (réception, envoyés, brouillons, corbeille, spam) sont protégés. Pour un sous-dossier, utilisez le séparateur de votre serveur (souvent `/` ou `.`). **Vider le dossier…** supprime définitivement tout le contenu de la corbeille ou du spam.
- Les actions vérifient UIDVALIDITY pour éviter de modifier un autre message après recréation d’un dossier. Déplacer utilise UID MOVE si disponible, sinon COPY puis suppression ciblée de la source. Sans UIDPLUS, la source reste marquée `Deleted` (masquée) en attendant la purge du serveur ; Smail n’exécute une purge globale (EXPUNGE) que lorsque vous videz entièrement la corbeille ou le spam.
- **Recherche avancée** : combinez des opérateurs (en français ou en anglais) — `de:` / `from:`, `à:` / `to:`, `objet:` / `subject:`, `a:pj` (pièce jointe), `est:nonlu`, `est:lu`, `est:étoilé`, `après:` / `avant:` avec une date `2026-11-01` ou `01/11/2026` (`avant:` exclut le jour indiqué) — et des mots ou `"expressions exactes"` cherchés dans tout le message ; tous les critères doivent être réunis. En ligne, la recherche est traduite en commandes IMAP SEARCH ; chaque texte accentué part dans sa propre commande (littéral UTF-8, jamais interpolé) et les résultats sont croisés. `a:pj` est vérifié sur la structure des messages (5 000 au plus). Hors ligne et dans la réception unifiée, les mêmes critères s’appliquent au cache. La liste **Ce dossier / Tous les dossiers** étend la recherche à tous les dossiers du compte (les 100 résultats les plus récents, avec leur dossier d’origine).
- Saisissez une recherche puis appuyez sur **Entrée**. En ligne, IMAP TEXT cherche dans tout le dossier avec une valeur UTF-8 littérale. Hors ligne, et dans la réception unifiée, la recherche porte sur les métadonnées et contenus déjà présents dans le cache. La bannière indique cette portée. Si le chiffrement du cache est désactivé, un index plein texte SQLite (FTS5) accélère cette recherche à partir de trois caractères ; il contient le texte des messages, comme le cache non chiffré lui-même. Activer le chiffrement supprime cet index et la recherche hors ligne parcourt alors le cache déchiffré. Si le serveur refuse la recherche, le cache disponible est utilisé et indiqué.

Le HTML est nettoyé sur liste blanche avec Bleach. Scripts, iframes, formulaires, événements JavaScript et styles du mail sont exclus. JavaScript, navigation externe, accès aux fichiers locaux et téléchargements WebEngine sont bloqués ; une CSP et un intercepteur réseau renforcent ces règles. Le profil WebEngine est privé, en mémoire. Les documents sont servis à WebEngine via un protocole interne en mémoire, sans fichier temporaire et sans la limite d’URL data de `setHtml`.

Les images distantes sont bloquées jusqu’au clic **Afficher les images**. Ce clic autorise les seules images HTTP/HTTPS du message courant ; il peut signaler votre lecture à l’expéditeur. Le message suivant rétablit le blocage. Les images intégrées PNG/JPEG/GIF/WebP via Content-ID ne nécessitent pas de réseau. Les liens sont inactifs et la mise en page peut être simplifiée par le nettoyage.

**Aperçu** (bouton ou double-clic sur une pièce jointe) : images et PDF s’affichent dans Smail, sans programme externe ni fichier temporaire ; les fichiers texte (y compris HTML, XML, CSV, calendrier) sont montrés en source brute, jamais interprétés, dans la limite de 2 Mo. Les fichiers exécutables ou actifs ne sont jamais prévisualisés.

**Invitations de calendrier** : un message contenant une invitation (`text/calendar` ou `.ics`) affiche son titre, sa date en heure locale, le lieu et l’organisateur. **Accepter**, **Provisoire** ou **Refuser** envoie à l’organisateur, après confirmation, une réponse standard iTIP (`METHOD:REPLY`) lue par Outlook, Google Agenda ou Thunderbird ; une copie va dans Envoyés. **Ajouter au calendrier** ouvre l’invitation dans l’application de calendrier de Windows (via un fichier temporaire `.ics`, non chiffré). Une annulation (`METHOD:CANCEL`) est signalée sans bouton de réponse. Smail ne gère pas d’agenda. Les fuseaux sont convertis grâce au paquet `tzdata` et aux noms de fuseaux Windows d’Outlook les plus courants ; un fuseau inconnu est affiché tel quel, avec son nom.

**Ouvrir dans une fenêtre** (double-clic sur un message, ou Ctrl+O) affiche le message dans sa propre fenêtre, avec le même lecteur isolé ; Répondre, Répondre à tous et Transférer y restent disponibles, le rangement se fait depuis la liste. **Imprimer…** (Ctrl+P) imprime l’en-tête et le corps nettoyé, sans image distante ; choisissez l’imprimante « Microsoft Print to PDF » pour obtenir un PDF. Les messages sélectionnés peuvent être **glissés sur un dossier** de la barre latérale pour les y déplacer (pas dans la réception unifiée ni hors ligne).

Les pièces jointes ne sont jamais ouvertes automatiquement. Sélectionnez-en une puis **Enregistrer la pièce jointe…**. Les noms sont assainis pour Windows ; les exécutables, scripts et certains formats actifs affichent un avertissement supplémentaire avec annulation par défaut. Les fichiers que vous enregistrez explicitement ne sont pas protégés par le chiffrement du cache.

## Rédiger et envoyer

**Rédiger**, **Répondre**, **Répondre à tous** et **Transférer** ouvrent une fenêtre avec choix du compte, À/Cc/Cci, objet, corps et pièces jointes. Répondre respecte Reply-To ; répondre à tous retire votre adresse et les doublons. Les en-têtes de fil de discussion sont conservés. Le transfert inclut les pièces jointes. La signature du compte est ajoutée à la rédaction ; après changement de compte dans une rédaction ouverte, vérifiez manuellement la signature.

**Mise en forme** : la barre au-dessus du corps applique gras (Ctrl+B), italique (Ctrl+I), souligné (Ctrl+U), listes à puces ou numérotées, liens (Ctrl+Maj+K ; https, http ou adresse e-mail uniquement) et l’effacement de la mise en forme. Un message mis en forme part en HTML accompagné d’un texte brut équivalent (listes et adresses des liens conservées) ; sans mise en forme, il reste en texte simple. Le HTML envoyé est reconstruit par Smail avec un jeu fermé de balises : un contenu collé depuis une page web ou un traitement de texte est réduit à ce jeu (styles, scripts et images distantes écartés). Les brouillons conservent la mise en forme.

**Signature mise en forme** : dans **Compte**, la signature accepte la même mise en forme (sans image). Elle est insérée au-dessus de la citation dans les réponses. Sa version mise en forme est conservée dans le cache du compte (chiffrée avec lui) ; la configuration du compte garde une version texte, utilisée pour les clients sans HTML.

**Envoi en arrière-plan et annulation** : après **Envoyer**, la fenêtre de rédaction se ferme aussitôt et le message part en arrière-plan. En bas de la fenêtre principale, « Envoi de « Objet » dans 8 s » propose **Annuler** pendant le délai d’annulation (10 s par défaut, réglable de 0 à 30 s dans Préférences › Rédaction) : le message est alors rouvert en brouillon. Puis la progression réelle s’affiche : connexion, envoi des données (Mo envoyés), vérification par le serveur (souvent son antivirus), copie dans Envoyés. Les messages partent un par un ; hors ligne, ils attendent la reconnexion. Quitter Smail pendant le délai envoie le message avant la fermeture. Un échec ou un envoi incertain est notifié et conservé dans **Fichier › Envois programmés** (jamais renvoyé automatiquement) ; « Modifier… » le rouvre. Les adresses sont vérifiées avant le délai.

**Envoyer plus tard** (bouton horloge) : choix rapides (dans 1 heure, demain 8 h, lundi 8 h) ou date libre. Le message attend dans une boîte d’envoi locale, chiffrée avec le cache ; **Fichier › Envois programmés…** permet de le modifier (il redevient un brouillon) ou de le supprimer. Smail doit être ouvert à l’heure prévue ; sinon, l’envoi a lieu au démarrage suivant. Comme pour un envoi immédiat, un échec n’est jamais renvoyé automatiquement : il reste visible avec sa cause. Un envoi interrompu (Smail fermé brutalement pendant la connexion SMTP) passe à l’état « incertain » : vérifiez vos Envoyés avant de le rouvrir.

Les champs À, Cc et Cci proposent les adresses connues dès la saisie : expéditeurs vus lors de la synchronisation (hors spam) et destinataires de vos envois, ces derniers en premier. Le carnet d’adresses est conservé par compte dans le cache : il est chiffré avec lui et effacé avec le compte.

Les en-têtes et adresses sont validés ; les contrôles CR/LF sont interdits. Les destinataires Cci figurent dans l’enveloppe SMTP, jamais dans le message transmis ni sa copie enregistrée. SMTP n’est jamais relancé automatiquement après une erreur : une coupure après DATA peut laisser la livraison incertaine. Vérifiez la réception avant un nouvel essai. En cas d’acceptation partielle, seuls les destinataires refusés restent dans le brouillon ; les destinataires acceptés ne sont pas remis automatiquement dans un nouvel envoi.

Les brouillons locaux sont sauvegardés en arrière-plan après 1,5 seconde d’inactivité et périodiquement pendant la rédaction. Fermer la fenêtre ou appuyer sur Échap attend la sauvegarde. **Brouillons locaux** permet de les reprendre après redémarrage ; **Supprimer le brouillon** le retire après confirmation. **Copier aux brouillons du serveur** crée une copie explicite sur le serveur, y compris pour un brouillon sans destinataire ; chaque clic crée une nouvelle copie. La sauvegarde automatique locale reste disponible sans réseau.

Après acceptation SMTP, une copie locale est conservée dans **Envoyés locaux**. Pour les serveurs autres que Gmail, Smail tente aussi de conserver une copie dans le dossier Envoyés. L’envoi SMTP et cette copie sont deux tâches distinctes : une erreur de copie ou une alerte de certificat ne renvoie jamais le message. **Exporter .eml** sauvegarde la copie locale ouverte. Si le serveur conserve déjà lui-même une copie, une seconde copie serveur peut apparaître (le cas Gmail est traité automatiquement).

Raccourcis : Ctrl+N rédiger, Ctrl+R répondre, Ctrl+Maj+R répondre à tous, Ctrl+L transférer, Suppr déplacer vers la corbeille, Ctrl+Maj+U tout marquer comme lu, F5 synchroniser.

## Règles, courrier indésirable et désabonnement

**Préférences › Règles et indésirables** regroupe les règles de tri, les expéditeurs bloqués et approuvés. Une règle a une condition (De, À ou Cc, Objet, ou n’importe lequel ; contient, est exactement, se termine par) et une action (déplacer vers un dossier, marquer comme lu, étoiler, corbeille, indésirables), pour un compte ou tous. **Message › Créer une règle à partir du message…** la pré-remplit avec l’expéditeur.

Les filtres s’appliquent lors de la synchronisation, côté client, aux **nouveaux** messages de la réception ; ceux déjà présents ne sont jamais déplacés sans votre demande (**Appliquer maintenant**). Ordre : un expéditeur approuvé n’est jamais traité comme indésirable ; un expéditeur bloqué (adresse ou domaine `@exemple.fr`) va aux indésirables ; un message marqué spam par le filtre du serveur (`X-Spam-Flag`, `X-Spam-Status`…) aussi, sauf si l’option est décochée ; sinon la première règle qui correspond s’applique. Les messages filtrés vers les indésirables ne déclenchent pas de notification. **Message › Courrier indésirable** propose **Signaler comme spam** (Ctrl+Maj+J), **Bloquer l’expéditeur** et **Ce n’est pas un spam** (retour en réception, expéditeur approuvé). Règles et listes sont conservées dans le cache (chiffrées avec lui).

**Reporter** (Message › Reporter…, Ctrl+Maj+Z) retire un message de la réception jusqu’à une date choisie (dans 3 heures, ce soir, demain, samedi, lundi ou date libre) : il est déplacé dans un dossier « Reportés », créé au besoin sur le serveur, puis remis dans son dossier d’origine, non lu, à l’échéance. Le message est retrouvé par son Message-ID, son identifiant IMAP changeant à chaque déplacement. Smail doit être ouvert à l’échéance (sinon le retour a lieu au démarrage suivant) ; un message sorti manuellement de « Reportés » n’est plus suivi.

Pour une lettre d’information, le lecteur affiche **Se désabonner** (en-têtes `List-Unsubscribe`). Après confirmation, Smail utilise, dans cet ordre : le désabonnement en un clic (RFC 8058 : requête HTTPS sans navigateur, sans cookie ni redirection, refusée vers une adresse locale ou privée), un e-mail de désabonnement envoyé depuis votre compte, ou l’ouverture de la page dans votre navigateur.

## Hors ligne, synchronisation et confort

**Préférences** règle le thème clair/sombre, l’intervalle de synchronisation (5 minutes initialement), le nombre de messages à télécharger automatiquement par dossier (100 initialement), IDLE, les notifications et la réduction en zone de notification.

La synchronisation travaille dans un QThread. Elle parcourt les dossiers sélectionnables, récupère les derniers messages complets avec leurs pièces jointes, actualise les drapeaux et réutilise les contenus déjà téléchargés. Les contenus précédemment synchronisés sortant de cette fenêtre sont retirés lors du cycle suivant ; les messages consultés manuellement peuvent également être en cache. Les messages plus anciens restent consultables en ligne, par pages de 50. Une page jamais téléchargée ne sera pas disponible hors ligne.

La synchronisation est incrémentale : seuls les messages absents du cache sont téléchargés, et les contenus déjà présents ne sont pas réécrits. Si le serveur propose CONDSTORE (RFC 7162, par exemple Gmail, Dovecot, Outlook), un dossier dont l’état n’a pas changé depuis la dernière synchronisation (STATUS identique, y compris HIGHESTMODSEQ) n’est même pas ouvert. Sans CONDSTORE, chaque dossier est vérifié à chaque cycle.

IMAP IDLE utilise une session dédiée par compte, compatible Python 3.11+, pour détecter les changements de réception. Les connexions IDLE sont renouvelées et se reconnectent avec un délai progressif après coupure. Si IDLE n’est pas proposé, la synchronisation périodique prend le relais. Les autres dossiers sont vérifiés au cycle périodique. Les notifications Windows utilisent QSystemTrayIcon et annoncent seulement le nombre de nouveaux mails ; la première synchronisation ne signale pas les anciens messages.

La sélection **Tous les comptes — Réception unifiée** rassemble les réceptions déjà synchronisées et conserve le compte d’origine pour les actions et réponses. **Synchroniser** met à jour tous les comptes. La case **Hors ligne** arrête les nouvelles synchronisations et sessions IDLE, consulte le cache et bloque les nouveaux envois/actions réseau dans les rédactions. Une opération réseau déjà engagée peut finir avant l’arrêt.

Si la zone de notification est disponible, fermer la fenêtre principale la masque par défaut. Double-cliquez sur l’icône pour la rouvrir. Son menu propose **Ouvrir**, **Synchroniser** et **Quitter**. Quitter attend la fin des opérations et la sauvegarde des brouillons ; les connexions ont des délais d’attente bornés.

## Cache, coffre Windows et journal

Les fichiers de configuration sont placés dans `QStandardPaths.AppLocalDataLocation`, habituellement `%LOCALAPPDATA%\SmailDesktop\Smail` : `settings.db` et `smail.log`. Les mots de passe ne figurent jamais dans SQLite. Keyring doit utiliser le Gestionnaire d’identifiants Windows ; aucun repli en fichier ou coffre en clair n’est autorisé.

L’option **Chiffrer les messages, pièces jointes et brouillons du cache** applique un chiffrement authentifié Fernet aux enregistrements de contenu, avec une clé conservée uniquement dans le coffre Windows. La migration est transactionnelle et un VACUUM retire les anciennes pages libres de la base courante. Il s’agit du chiffrement des contenus au niveau application, **pas d’un fichier SQLite intégralement chiffré avec SQLCipher** : schéma, paramètres publics de comptes et exceptions de certificat restent lisibles. Les clés de recherche du cache sont hachées. L’option est désactivée initialement ; sans elle, le cache contient les contenus en clair sur ce PC.

Ne supprimez pas la clé `cache-encryption-key` du service keyring `SmailDesktop` : sans elle, un cache chiffré ne peut pas être déchiffré. Sauvegarder uniquement `settings.db` ne sauvegarde pas la clé. La migration ne chiffre pas les anciennes sauvegardes, les exports, les fichiers joints enregistrés ni les éventuelles copies réalisées auparavant par le système.

Le schéma SQLite est versionné (`PRAGMA user_version`) et migré automatiquement au démarrage ; une base créée par une version plus récente de Smail est refusée plutôt que modifiée. La table `cache` conserve sa structure d’origine : une base migrée reste utilisable par Smail 1.0.0.

Les sessions IMAP authentifiées sont réutilisées pendant 4 minutes au plus (vérification NOOP avant réemploi, fermeture après toute erreur) et les listes de messages sont téléchargées en une commande par page ; IDLE garde sa session dédiée.

Le journal tourne sur trois sauvegardes de 500 Ko. Il contient démarrage/arrêt, noms de types d’erreurs techniques et, pour une erreur inattendue, les fichiers et lignes de code concernés ; aucun mot de passe, jeton, contenu de mail ou exception serveur brute n’y est écrit. Ne pas activer les traces détaillées des bibliothèques IMAP/SMTP.

## Structure du code

- `core/accounts.py` : configuration publique et validation.
- `core/imap_client.py`, `smtp_client.py` : protocoles, actions UID, MIME sortant et IDLE.
- `core/oauth.py`, `tls_policy.py` : OAuth2/PKCE, secrets et politique de certificats.
- `core/parser.py`, `html_security.py` : MIME et nettoyage HTML.
- `core/service.py`, `sync.py` : cache, boîte unifiée, orchestration et threads Qt.
- `storage/database.py`, `secrets.py` : SQLite, chiffrement des contenus et coffre Windows.
- `ui/` : fenêtre principale, lecteur, rédaction, comptes, préférences et certificats.
- `utils/` : dossier utilisateur et journal rotatif.
- `tests/` : tests unitaires et intégrations locales indépendants de vos comptes.

Les appels réseau, la synchronisation et les sauvegardes de brouillons passent par QThreadPool/QThread et des signaux Qt. Les actions sur les serveurs et les envois exigent vos clics dans l’application ; le diagnostic et les tests n’utilisent aucun compte réel.

## Tests, diagnostic et build Windows

Les outils de test et de compilation sont dans `requirements-dev.txt` (qui inclut aussi les dépendances d’exécution) :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest mailclient/tests -q
.\.venv\Scripts\python.exe -m mailclient.main --smoke-test
.\.venv\Scripts\python.exe -m PyInstaller --clean Smail.spec
```

La version de l’application est définie une seule fois dans `mailclient/__init__.py` ; `Smail.spec` en dérive les informations de version de l’exécutable. L’icône `mailclient/ui/assets/smail.ico` est générée par `python tools/make_icon.py`. Le workflow `.github/workflows/ci.yml` exécute les tests sous Windows (Python 3.11 et 3.13), construit l’exécutable, lance son diagnostic et publie le dossier `dist\Smail` comme artefact.

Le diagnostic ouvre brièvement une fenêtre avec un message fictif, vérifie WebEngine et le backend du coffre puis se ferme avec le code 0 attendu. Il ne charge pas les comptes, ne lit pas leurs identifiants et ne se connecte pas aux serveurs. Il peut créer ou migrer les tables de configuration et écrire les événements de démarrage/arrêt habituels. Pour tester l’exécutable dans PowerShell en attendant son code de sortie :

```powershell
$p = Start-Process .\dist\Smail\Smail.exe -ArgumentList '--smoke-test' -PassThru -Wait
$p.ExitCode
```

Les tests couvrent MIME, encodages, TLS et empreintes, STARTTLS sans repli, SQLite, migrations de schéma et de chiffrement, suppression de compte, actions groupées et gestion des dossiers, réserve de sessions IMAP, coffre Windows et longs jetons, en-têtes/Cci, réponses, brouillons, envois partiels, absence de double envoi, déplacement sans purge globale, recherche littérale, cache hors ligne et boîte unifiée. Des serveurs exclusivement locaux vérifient une vraie session SMTP, le dialogue IDLE, le rappel OAuth PKCE/state et les requêtes d’images WebEngine. Le rendu des tests sans écran utilise le mode logiciel pour éviter les problèmes GPU de la plateforme offscreen.

L’autorisation OAuth réelle doit être validée avec votre propre identifiant d’application, le consentement du fournisseur et votre compte. L’envoi et les actions réels doivent être vérifiés avec un compte de test et un destinataire contrôlé. Une suite locale ne remplace pas ces validations de bout en bout chez votre hébergeur.

Références de sécurité : [nettoyage Bleach](https://bleach.readthedocs.io/en/latest/clean.html), [interception WebEngine](https://doc.qt.io/qt-6.8/qwebengineurlrequestinterceptor.html) et [schéma interne WebEngine](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEngineUrlSchemeHandler.html).

## Mises à jour automatiques et publication d’une version

Smail installé par l’installateur vérifie toutes les 6 heures (et 45 secondes après le démarrage) la dernière publication GitHub du dépôt, par une requête anonyme. Une version plus récente est téléchargée en arrière-plan puis installée en silence **à la fermeture de Smail** ; le bandeau « Smail X est prêt » propose aussi « Redémarrer maintenant ». Les comptes, le cache et les réglages sont conservés. Désactivable dans Préférences › Général ; vérification manuelle par Outils › Rechercher des mises à jour.

Sécurité : chaque publication contient `smail-update.json` (version, nom, taille et SHA-256 de l’installateur) signé en Ed25519 par la CI. Smail n’installe rien si la signature ne correspond pas à la clé publique embarquée (`mailclient/core/updater.py`) ou si l’empreinte du fichier téléchargé diffère. Seuls les hôtes HTTPS de GitHub sont acceptés. Après deux échecs d’installation d’une même version, Smail cesse de réessayer et propose la page de téléchargement. Une copie lancée depuis les sources ou un dossier copié signale seulement la nouvelle version.

**Publier une version :**

1. Décrivez les changements dans la section `## Non publié` de `CHANGELOG.md` et faites un commit.
2. `python tools/release.py 1.2.0 --push` : numéro de version, CHANGELOG daté, commit, tag `v1.2.0` et envoi.
3. Le workflow `.github/workflows/release.yml` teste, construit, signe et publie l’installateur. Les Smail installés se mettent à jour d’eux-mêmes.

**Clé de signature (une seule fois) :** la clé privée est le secret `UPDATE_SIGNING_KEY` du dépôt (contenu PEM complet), à ajouter par `gh secret set UPDATE_SIGNING_KEY < chemin\update-signing-key.pem` ou dans Settings › Secrets and variables › Actions. Gardez une sauvegarde hors ligne de ce fichier : sans lui, aucune mise à jour ne peut plus être signée pour les copies installées. Ne le placez jamais dans le dépôt.

## Microsoft Store (paquet MSIX)

`python tools/build_msix.py` transforme le dossier `dist\Smail` de PyInstaller en paquet `dist\msix\Smail-X.Y.Z.msix`, construit aussi par la CI à chaque version (artefact « Smail-msix-vX.Y.Z », à téléverser dans Partner Center). Le paquet n’est pas signé : le Microsoft Store le signe lors de la publication, ce qui supprime l’avertissement SmartScreen. L’identité du paquet (`packaging/msix/identity.json`) doit reprendre les valeurs de Partner Center › Gestion des produits › Identité du produit. Dans la version Store, Smail détecte son paquet et laisse les mises à jour au Store. Les données d’une copie Store sont rangées par Windows dans le dossier du paquet, séparément de la version installée par l’installateur.

Test local sans Store : activez le mode développeur de Windows, puis `python tools/build_msix.py --layout-only` et `Add-AppxPackage -Register dist\msix\layout\AppxManifest.xml` (retrait : `Get-AppxPackage *Smail* | Remove-AppxPackage`).

Politique de confidentialité (exigée par le Store) : [PRIVACY.md](PRIVACY.md).

## Licence

Smail est distribué sous licence MIT : voir [LICENSE](LICENSE). Les icônes Lucide restent sous leur propre licence (`mailclient/ui/assets/LICENSE-LUCIDE.txt`).
