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

## Comptes et chiffrement réseau

**Ajouter un compte** permet de saisir le nom, l’adresse et les paramètres distincts IMAP/SMTP. En quittant le champ adresse, les domaines Gmail, Outlook/Hotmail et Yahoo préremplissent les champs serveur encore vides. Pour LWS, cPanel ou un serveur interne, reprenez les valeurs fournies par votre hébergeur ou administrateur. Le bouton **Compte** modifie un compte existant, sa signature et son authentification.

| Connexion | Port IMAP usuel | Port SMTP usuel | Comportement |
| --- | --- | --- | --- |
| SSL/TLS | 993 | 465 | TLS immédiat, choix initial |
| STARTTLS | 143 | 587 | Mise à niveau chiffrée obligatoire avant authentification |
| Aucun | 143 | 25 | Connexion en clair après confirmation explicite |

Le changement du type remplit le port usuel ; le port reste modifiable. **Aucun** affiche un avertissement rouge et impose de cocher la confirmation du risque avant le test ou l’enregistrement. Un cadenas ouvert et un avertissement restent visibles près du compte. Ce mode expose les identifiants et les mails aux tiers présents sur le réseau ; certains serveurs refusent cette authentification. OAuth2 exige une connexion chiffrée sur les deux serveurs.

**Tester la connexion IMAP et SMTP** s’authentifie aux deux serveurs sans envoyer de message. L’identifiant de connexion est l’adresse e-mail pour les deux protocoles. Les noms affichés et les objets peuvent être accentués ; les adresses de boîte doivent être ASCII. Les identifiants de connexion différents de l’adresse et les identifiants IMAP/SMTP distincts ne sont pas pris en charge.

La vérification TLS système et le contrôle du nom de serveur sont actifs par défaut (`ssl.create_default_context`). Si la vérification échoue, une sonde sans authentification récupère le certificat. La boîte de sécurité affiche le serveur, l’émetteur, les dates, l’empreinte SHA-256 et la raison de l’échec. **Annuler** est le choix par défaut. **Continuer quand même** autorise seulement cette empreinte pour ce compte et ce serveur pendant la session. La case de confiance permanente conserve cette empreinte dans SQLite. Tout changement d’empreinte réaffiche l’alerte, même si le nouveau certificat est par ailleurs valide. Comparez l’empreinte avec votre administrateur via un canal indépendant avant de faire confiance.

Un serveur sans STARTTLS est refusé sans envoi d’identifiants : aucun repli automatique en clair. Une alerte de certificat rencontrée en synchronisation suspend cette opération ; choisissez le compte puis **Actualiser** pour examiner l’alerte. Relancez ensuite **Synchroniser** ; la surveillance IDLE peut être redémarrée en désactivant puis réactivant son option dans Préférences. Pour supprimer une ancienne exception persistante, fermez Smail puis retirez l’entrée concernée de la table `pins` de `settings.db`.

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
- **Lu / non lu**, **Étoiler**, **Déplacer**, **Archiver** et **Supprimer** agissent sur le message sélectionné, y compris depuis la boîte unifiée. Supprimer déplace vers la corbeille après confirmation, sans suppression définitive. Si aucun dossier spécial n’est reconnu, choisissez un dossier existant ; créez au besoin ce dossier depuis votre webmail puis actualisez.
- Les actions vérifient UIDVALIDITY pour éviter de modifier un autre message après recréation d’un dossier. Déplacer utilise UID MOVE si disponible, sinon COPY puis suppression ciblée de la source. Sans UIDPLUS, la source reste marquée `Deleted` en attendant la purge du serveur ; Smail n’exécute jamais une purge globale susceptible de supprimer les mails d’une autre session.
- Saisissez une recherche puis appuyez sur **Entrée**. En ligne, IMAP TEXT cherche dans tout le dossier avec une valeur UTF-8 littérale. Hors ligne, et dans la réception unifiée, la recherche porte sur les métadonnées et contenus déjà présents dans le cache. La bannière indique cette portée. Si le serveur refuse la recherche, le cache disponible est utilisé et indiqué.

Le HTML est nettoyé sur liste blanche avec Bleach. Scripts, iframes, formulaires, événements JavaScript et styles du mail sont exclus. JavaScript, navigation externe, accès aux fichiers locaux et téléchargements WebEngine sont bloqués ; une CSP et un intercepteur réseau renforcent ces règles. Le profil WebEngine est privé, en mémoire. Les documents sont servis à WebEngine via un protocole interne en mémoire, sans fichier temporaire et sans la limite d’URL data de `setHtml`.

Les images distantes sont bloquées jusqu’au clic **Afficher les images**. Ce clic autorise les seules images HTTP/HTTPS du message courant ; il peut signaler votre lecture à l’expéditeur. Le message suivant rétablit le blocage. Les images intégrées PNG/JPEG/GIF/WebP via Content-ID ne nécessitent pas de réseau. Les liens sont inactifs et la mise en page peut être simplifiée par le nettoyage.

Les pièces jointes ne sont jamais ouvertes automatiquement. Sélectionnez-en une puis **Enregistrer la pièce jointe…**. Les noms sont assainis pour Windows ; les exécutables, scripts et certains formats actifs affichent un avertissement supplémentaire avec annulation par défaut. Les fichiers que vous enregistrez explicitement ne sont pas protégés par le chiffrement du cache.

## Rédiger et envoyer

**Rédiger**, **Répondre**, **Répondre à tous** et **Transférer** ouvrent une fenêtre avec choix du compte, À/Cc/Cci, objet, corps et pièces jointes. Répondre respecte Reply-To ; répondre à tous retire votre adresse et les doublons. Les en-têtes de fil de discussion sont conservés. Le transfert inclut les pièces jointes. La signature du compte est ajoutée à la rédaction ; après changement de compte dans une rédaction ouverte, vérifiez manuellement la signature.

Les en-têtes et adresses sont validés ; les contrôles CR/LF sont interdits. Les destinataires Cci figurent dans l’enveloppe SMTP, jamais dans le message transmis ni sa copie enregistrée. SMTP n’est jamais relancé automatiquement après une erreur : une coupure après DATA peut laisser la livraison incertaine. Vérifiez la réception avant un nouvel essai. En cas d’acceptation partielle, seuls les destinataires refusés restent dans le brouillon ; les destinataires acceptés ne sont pas remis automatiquement dans un nouvel envoi.

Les brouillons locaux sont sauvegardés en arrière-plan après 1,5 seconde d’inactivité et périodiquement pendant la rédaction. Fermer la fenêtre ou appuyer sur Échap attend la sauvegarde. **Brouillons locaux** permet de les reprendre après redémarrage ; **Supprimer le brouillon** le retire après confirmation. **Copier aux brouillons du serveur** crée une copie explicite sur le serveur, y compris pour un brouillon sans destinataire ; chaque clic crée une nouvelle copie. La sauvegarde automatique locale reste disponible sans réseau.

Après acceptation SMTP, une copie locale est conservée dans **Envoyés locaux**. Pour les serveurs autres que Gmail, Smail tente aussi de conserver une copie dans le dossier Envoyés. L’envoi SMTP et cette copie sont deux tâches distinctes : une erreur de copie ou une alerte de certificat ne renvoie jamais le message. **Exporter .eml** sauvegarde la copie locale ouverte. Si le serveur conserve déjà lui-même une copie, une seconde copie serveur peut apparaître (le cas Gmail est traité automatiquement).

Raccourcis : Ctrl+N rédiger, Ctrl+R répondre, Ctrl+Maj+R répondre à tous, Ctrl+L transférer, Suppr déplacer vers la corbeille, F5 synchroniser.

## Hors ligne, synchronisation et confort

**Préférences** règle le thème clair/sombre, l’intervalle de synchronisation (5 minutes initialement), le nombre de messages à télécharger automatiquement par dossier (100 initialement), IDLE, les notifications et la réduction en zone de notification.

La synchronisation travaille dans un QThread. Elle parcourt les dossiers sélectionnables, récupère les derniers messages complets avec leurs pièces jointes, actualise les drapeaux et réutilise les contenus déjà téléchargés. Les contenus précédemment synchronisés sortant de cette fenêtre sont retirés lors du cycle suivant ; les messages consultés manuellement peuvent également être en cache. Les messages plus anciens restent consultables en ligne, par pages de 50. Une page jamais téléchargée ne sera pas disponible hors ligne.

IMAP IDLE utilise une session dédiée par compte, compatible Python 3.11+, pour détecter les changements de réception. Les connexions IDLE sont renouvelées et se reconnectent avec un délai progressif après coupure. Si IDLE n’est pas proposé, la synchronisation périodique prend le relais. Les autres dossiers sont vérifiés au cycle périodique. Les notifications Windows utilisent QSystemTrayIcon et annoncent seulement le nombre de nouveaux mails ; la première synchronisation ne signale pas les anciens messages.

La sélection **Tous les comptes — Réception unifiée** rassemble les réceptions déjà synchronisées et conserve le compte d’origine pour les actions et réponses. **Synchroniser** met à jour tous les comptes. La case **Hors ligne** arrête les nouvelles synchronisations et sessions IDLE, consulte le cache et bloque les nouveaux envois/actions réseau dans les rédactions. Une opération réseau déjà engagée peut finir avant l’arrêt.

Si la zone de notification est disponible, fermer la fenêtre principale la masque par défaut. Double-cliquez sur l’icône pour la rouvrir. Son menu propose **Ouvrir**, **Synchroniser** et **Quitter**. Quitter attend la fin des opérations et la sauvegarde des brouillons ; les connexions ont des délais d’attente bornés.

## Cache, coffre Windows et journal

Les fichiers de configuration sont placés dans `QStandardPaths.AppLocalDataLocation`, habituellement `%LOCALAPPDATA%\SmailDesktop\Smail` : `settings.db` et `smail.log`. Les mots de passe ne figurent jamais dans SQLite. Keyring doit utiliser le Gestionnaire d’identifiants Windows ; aucun repli en fichier ou coffre en clair n’est autorisé.

L’option **Chiffrer les messages, pièces jointes et brouillons du cache** applique un chiffrement authentifié Fernet aux enregistrements de contenu, avec une clé conservée uniquement dans le coffre Windows. La migration est transactionnelle et un VACUUM retire les anciennes pages libres de la base courante. Il s’agit du chiffrement des contenus au niveau application, **pas d’un fichier SQLite intégralement chiffré avec SQLCipher** : schéma, paramètres publics de comptes et exceptions de certificat restent lisibles. Les clés de recherche du cache sont hachées. L’option est désactivée initialement ; sans elle, le cache contient les contenus en clair sur ce PC.

Ne supprimez pas la clé `cache-encryption-key` du service keyring `SmailDesktop` : sans elle, un cache chiffré ne peut pas être déchiffré. Sauvegarder uniquement `settings.db` ne sauvegarde pas la clé. La migration ne chiffre pas les anciennes sauvegardes, les exports, les fichiers joints enregistrés ni les éventuelles copies réalisées auparavant par le système.

Le journal tourne sur trois sauvegardes de 500 Ko. Il contient démarrage/arrêt et noms de types d’erreurs techniques ; aucun mot de passe, jeton, contenu de mail ou exception serveur brute n’y est écrit. Ne pas activer les traces détaillées des bibliothèques IMAP/SMTP.

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

```powershell
.\.venv\Scripts\python.exe -m pytest mailclient/tests -q
.\.venv\Scripts\python.exe -m mailclient.main --smoke-test
.\.venv\Scripts\python.exe -m PyInstaller --clean Smail.spec
```

Le diagnostic ouvre brièvement une fenêtre avec un message fictif, vérifie WebEngine et le backend du coffre puis se ferme avec le code 0 attendu. Il ne charge pas les comptes, ne lit pas leurs identifiants et ne se connecte pas aux serveurs. Il peut créer les tables de configuration et écrire les événements de démarrage/arrêt habituels. Pour tester l’exécutable dans PowerShell en attendant son code de sortie :

```powershell
$p = Start-Process .\dist\Smail\Smail.exe -ArgumentList '--smoke-test' -PassThru -Wait
$p.ExitCode
```

Les tests couvrent MIME, encodages, TLS et empreintes, STARTTLS sans repli, SQLite et migration de chiffrement, coffre Windows et longs jetons, en-têtes/Cci, réponses, brouillons, envois partiels, absence de double envoi, déplacement sans purge globale, recherche littérale, cache hors ligne et boîte unifiée. Des serveurs exclusivement locaux vérifient une vraie session SMTP, le dialogue IDLE, le rappel OAuth PKCE/state et les requêtes d’images WebEngine. Le rendu des tests sans écran utilise le mode logiciel pour éviter les problèmes GPU de la plateforme offscreen.

L’autorisation OAuth réelle doit être validée avec votre propre identifiant d’application, le consentement du fournisseur et votre compte. L’envoi et les actions réels doivent être vérifiés avec un compte de test et un destinataire contrôlé. Une suite locale ne remplace pas ces validations de bout en bout chez votre hébergeur.

Références de sécurité : [nettoyage Bleach](https://bleach.readthedocs.io/en/latest/clean.html), [interception WebEngine](https://doc.qt.io/qt-6.8/qwebengineurlrequestinterceptor.html) et [schéma interne WebEngine](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEngineUrlSchemeHandler.html).
