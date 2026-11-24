# Politique de confidentialité de Smail

*Dernière mise à jour : 24 novembre 2026*

Smail est un client mail de bureau pour Windows. **Il ne collecte aucune donnée sur vous** : pas de compte Smail, pas de serveur Smail, pas de statistiques d’utilisation, pas de publicité, aucune revente ni aucun partage de données. Vos messages et vos réglages restent sur votre ordinateur.

## Les données que Smail traite, et où elles restent

| Donnée | Où elle est conservée |
|---|---|
| Paramètres de vos comptes (adresse, serveurs, identifiants de connexion) | Sur votre PC, dans le dossier de Smail (`%LOCALAPPDATA%\SmailDesktop\Smail`) |
| Mots de passe et jetons de connexion | Dans le Gestionnaire d’identifiants de Windows, sur votre PC |
| Copie locale de vos messages, pièces jointes, brouillons et contacts (pour le mode hors ligne et la recherche) | Sur votre PC, dans le même dossier. Vous pouvez la chiffrer : Préférences › Sécurité |
| Journal technique (`smail.log`) | Sur votre PC. Il contient des dates et des types d’erreur, **jamais le contenu de vos messages** |

Rien de tout cela n’est envoyé au développeur de Smail ni à un tiers.

## Les connexions réseau de Smail

Smail se connecte uniquement aux services nécessaires à ce que vous lui demandez :

- **Vos serveurs de messagerie** (IMAP pour recevoir, SMTP pour envoyer), ceux que vous avez configurés, avec un chiffrement TLS vérifié.
- **Google ou Microsoft**, seulement si vous choisissez de vous connecter à un compte Gmail ou Outlook par leur page d’autorisation (OAuth2). Smail n’a alors jamais accès à votre mot de passe.
- **GitHub** (version téléchargée depuis le site de Smail uniquement) : une requête anonyme toutes les 6 heures pour savoir si une nouvelle version existe, puis le téléchargement de la mise à jour. Aucune information personnelle n’est transmise. La version du Microsoft Store ne fait pas cette requête : le Store gère ses mises à jour.
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

Toute modification de cette politique sera publiée sur cette page, avec sa date. Pour toute question : https://github.com/Smeth/smail/issues

---

## Privacy policy (summary in English)

Smail is a Windows desktop email client. **It collects no data about you**: no Smail account, no Smail server, no analytics, no advertising, no data sale or sharing. Account settings, a local copy of your messages, drafts and contacts are stored only on your computer (optionally encrypted); passwords and tokens are stored in Windows Credential Manager; the local log never contains message content.

Smail only connects to: your own mail servers (IMAP/SMTP over verified TLS); Google or Microsoft sign-in pages, only if you choose OAuth2; GitHub, anonymously, to check for updates (not in the Microsoft Store version); and, only after your action, remote images (blocked by default), mailing-list unsubscribe requests (after confirmation) and links you open.

Deleting an account in Smail removes all its local data and stored credentials from your PC. Questions: https://github.com/Smeth/smail/issues
