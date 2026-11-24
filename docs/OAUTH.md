# Créer les applications OAuth2 de Smail (Google et Microsoft)

Ces deux applications permettent la connexion « en un clic » : l’utilisateur clique sur **Se connecter avec Google** (ou Microsoft), se connecte dans son navigateur, et Smail reçoit une autorisation, sans jamais voir le mot de passe.

À faire **une seule fois**, par le responsable de Smail. Les valeurs obtenues vont dans `mailclient/core/oauth_apps.py`.

> Les consoles de Google et Microsoft changent souvent d’apparence : les noms de menus ci-dessous peuvent varier légèrement.

## Google (Gmail et Google Workspace)

1. Ouvrez <https://console.cloud.google.com> avec votre compte Google et créez un projet nommé **Smail**.
2. **API et services › Bibliothèque** : activez **Gmail API**.
3. **Google Auth Platform** (anciennement « Écran de consentement OAuth ») :
   - **Branding** : nom de l’application `Smail`, adresse e-mail d’assistance, page d’accueil `https://github.com/Smeth/smail`, politique de confidentialité `https://github.com/Smeth/smail/blob/main/PRIVACY.md` ;
   - **Audience** : **Externe** ;
   - **Accès aux données** : ajoutez le champ d’application `https://mail.google.com/`.
4. **Clients › Créer un client** : type **Application de bureau**, nom `Smail`. Notez l’**ID client** et le **code secret du client**.
5. **Audience › Utilisateurs test** : ajoutez les adresses Gmail qui utiliseront Smail (100 au maximum).

### Limite importante côté Google

L’accès complet à Gmail (`https://mail.google.com/`) est un champ d’application **restreint** :

- **En mode « Test »** (gratuit, immédiat) : seuls les utilisateurs test ajoutés à l’étape 5 peuvent se connecter, et Google **expire leur autorisation au bout de 7 jours** : il faut alors se reconnecter dans Smail (Comptes › Paramètres du compte › Se connecter avec Google). Suffisant pour vous et quelques amis.
- **En production** (ouvert à tous) : Google exige une **vérification de l’application** et, pour ce type d’accès, un **audit de sécurité annuel par un organisme tiers**, payant. À n’envisager que pour une diffusion large.

Alternative sans ces contraintes pour les utilisateurs Gmail : le **mot de passe d’application** Google (compte avec validation en deux étapes › Mots de passe des applications), utilisable dans Smail avec « Mot de passe ».

## Microsoft (Outlook.com, Hotmail, Microsoft 365)

1. Ouvrez <https://entra.microsoft.com> (ou <https://portal.azure.com>) avec votre compte Microsoft. Si le portail refuse un compte personnel, créez un compte Azure gratuit.
2. **Inscriptions d’applications › Nouvelle inscription** :
   - nom : `Smail` ;
   - types de comptes : **Comptes dans un annuaire d’organisation et comptes Microsoft personnels** ;
   - URI de redirection : plateforme **Client public/natif (mobile et bureau)**, valeur `http://localhost`.
3. **Authentification** : **Autoriser les flux de clients publics** sur **Oui**.
4. **Autorisations de l’API** (facultatif, Smail les demande à la connexion) : Microsoft Graph, autorisations déléguées `offline_access`, `IMAP.AccessAsUser.All` et `SMTP.Send`.
5. Notez l’**ID d’application (client)**. Aucun secret n’est nécessaire.

Sans « vérification de l’éditeur » (programme partenaire Microsoft, gratuit mais administratif), la page de connexion indique « non vérifié » : la connexion fonctionne quand même. Dans certaines entreprises, l’administrateur Microsoft 365 doit approuver Smail ou avoir activé SMTP AUTH.

## Intégrer les valeurs

Envoyez les trois valeurs au développeur, ou remplissez `mailclient/core/oauth_apps.py` :

```python
GOOGLE_CLIENT_ID = '….apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET = 'GOCSPX-…'
MICROSOFT_CLIENT_ID = '00000000-0000-0000-0000-000000000000'
```

Pour une application de bureau, ces valeurs ne sont **pas secrètes** (Google et Microsoft le documentent : elles sont lisibles dans tout programme installé) ; la sécurité repose sur la connexion de l’utilisateur dans son navigateur et sur PKCE. Elles peuvent donc figurer dans le dépôt public. Gardez en revanche votre compte Google Cloud / Microsoft protégé par la validation en deux étapes.
