# Politique de confidentialité de Smail

Dernière mise à jour : 25 novembre 2026. — *English version: [below](#english).*

Smail est un client mail de bureau pour Windows. **Il ne collecte aucune donnée sur vous** : pas de compte Smail, pas de serveur Smail, pas de statistiques d’utilisation, pas de publicité, aucune revente ni aucun partage de données. Vos messages et vos réglages restent sur votre ordinateur.

## Les données que Smail traite, et où elles restent

| Donnée | Où elle est conservée |
| --- | --- |
| Paramètres de vos comptes (adresse, serveurs, identifiants de connexion) | Sur votre PC, dans le dossier de Smail (`%LOCALAPPDATA%\SmailDesktop\Smail`) |
| Mots de passe et jetons de connexion | Dans le Gestionnaire d’identifiants de Windows, sur votre PC |
| Copie locale de vos messages, pièces jointes, brouillons et contacts (pour le mode hors ligne et la recherche) | Sur votre PC, dans le même dossier. Vous pouvez la chiffrer : Préférences › Sécurité |
| Journal technique (`smail.log`) | Sur votre PC. Il contient des dates et des types d’erreur, **jamais le contenu de vos messages** |

Rien de tout cela n’est envoyé au développeur de Smail ni à un tiers.

## Les connexions réseau de Smail

Smail se connecte uniquement aux services nécessaires à ce que vous lui demandez :

- **Vos serveurs de messagerie** (IMAP pour recevoir, SMTP pour envoyer), ceux que vous avez configurés, avec un chiffrement TLS vérifié.
- **Détection des réglages**, à l’ajout d’un compte : pour trouver vos serveurs, Smail consulte le fichier de réglages publié par le domaine de votre adresse (par exemple `autoconfig.votredomaine.fr`), puis la base publique de réglages de Thunderbird (`autoconfig.thunderbird.net`). **Seul le nom de domaine est transmis**, jamais votre adresse complète ni votre mot de passe. Rien n’est consulté pour les grands fournisseurs déjà connus de Smail (Gmail, Outlook, Yahoo, iCloud).
- **Google ou Microsoft**, seulement si vous choisissez de vous connecter à un compte Gmail ou Outlook par leur page d’autorisation (OAuth2). Smail n’a alors jamais accès à votre mot de passe.
- **GitHub** (version téléchargée depuis le site de Smail uniquement) : une requête anonyme toutes les 6 heures pour savoir si une nouvelle version existe, puis le téléchargement de la mise à jour si vous l’acceptez. Aucune information personnelle n’est transmise. La version du Microsoft Store ne fait pas cette requête : le Store gère ses mises à jour.
- **Les sites des expéditeurs**, uniquement après votre action :
  - les **images distantes** d’un message sont bloquées par défaut ; si vous choisissez de les afficher, l’expéditeur peut savoir que vous avez ouvert son message ;
  - le **désabonnement** d’une liste de diffusion envoie, après votre confirmation, la demande prévue par l’expéditeur (adresse web ou e-mail) ;
  - un **lien** que vous ouvrez s’affiche dans votre navigateur.

## Vos droits et la suppression de vos données

Toutes vos données sont sur votre ordinateur : vous en gardez le contrôle complet.

- **Supprimer un compte** (menu Comptes › Supprimer le compte) efface de ce PC sa configuration, sa copie locale des messages, ses brouillons, ses certificats approuvés et ses mots de passe du Gestionnaire d’identifiants. Vos messages restent sur le serveur de votre fournisseur de messagerie.
- **Désinstaller Smail** retire le programme. Pour tout effacer, supprimez d’abord vos comptes dans Smail, ou supprimez ensuite le dossier `%LOCALAPPDATA%\SmailDesktop\Smail`.

Les données détenues par votre fournisseur de messagerie (Gmail, Outlook, votre hébergeur…) relèvent de sa propre politique de confidentialité.

## Enfants

Smail ne collecte aucune donnée, y compris sur les enfants.

## Modifications et contact

Toute modification de cette politique sera publiée sur cette page, avec sa date. Pour toute question : <https://github.com/Smeth/smail/issues>

---

<a id="english"></a>

# Smail privacy policy

Last updated: November 25, 2026.

Smail is a desktop email client for Windows. **It collects no data about you**: no Smail account, no Smail server, no usage statistics, no advertising, and no data is sold or shared. Your messages and settings stay on your computer.

## The data Smail handles, and where it stays

| Data | Where it is stored |
| --- | --- |
| Your account settings (address, servers, sign-in details) | On your PC, in Smail’s folder (`%LOCALAPPDATA%\SmailDesktop\Smail`) |
| Passwords and sign-in tokens | In Windows Credential Manager, on your PC |
| Local copy of your messages, attachments, drafts and contacts (for offline mode and search) | On your PC, in the same folder. You can encrypt it: Settings › Security |
| Technical log (`smail.log`) | On your PC. It contains dates and error types, **never the content of your messages** |

None of this is sent to Smail’s developer or to any third party.

## Smail’s network connections

Smail only connects to the services needed for what you ask it to do:

- **Your mail servers** (IMAP to receive, SMTP to send), the ones you configured, over verified TLS encryption.
- **Settings detection**, when you add an account: to find your servers, Smail looks up the settings file published by your email domain (for example `autoconfig.yourdomain.com`), then Thunderbird’s public settings database (`autoconfig.thunderbird.net`). **Only the domain name is sent**, never your full address or your password. Nothing is looked up for the major providers Smail already knows (Gmail, Outlook, Yahoo, iCloud).
- **Google or Microsoft**, only if you choose to sign in to a Gmail or Outlook account through their authorization page (OAuth2). Smail never has access to your password.
- **GitHub** (version downloaded from Smail’s website only): an anonymous request every 6 hours to check whether a new version exists, then the download of the update if you accept it. No personal information is sent. The Microsoft Store version does not make this request: the Store handles its updates.
- **Senders’ websites**, only after you act:
  - **remote images** in a message are blocked by default; if you choose to show them, the sender may learn that you opened the message;
  - **unsubscribing** from a mailing list sends, after your confirmation, the request provided by the sender (web address or email);
  - a **link** you open is shown in your web browser.

## Your rights and deleting your data

All your data is on your computer: you keep full control of it.

- **Removing an account** (Accounts › Delete account) deletes from this PC its configuration, its local copy of messages, its drafts, its trusted certificates and its passwords in Credential Manager. Your messages remain on your email provider’s server.
- **Uninstalling Smail** removes the program. To erase everything, remove your accounts in Smail first, or delete the `%LOCALAPPDATA%\SmailDesktop\Smail` folder afterwards.

Data held by your email provider (Gmail, Outlook, your hosting provider…) is covered by that provider’s own privacy policy.

## Children

Smail collects no data, including about children.

## Changes and contact

Any change to this policy will be published on this page, with its date. For any question: <https://github.com/Smeth/smail/issues>
