"""Applications OAuth2 de Smail chez Google et Microsoft (connexion « en un clic »).

Ces identifiants désignent l’application Smail, pas un utilisateur : ils ne donnent accès à aucune boîte.
Pour une application de bureau, Google et Microsoft les considèrent publics (le « secret » client Google
d’une application de bureau n’est pas confidentiel ; la sécurité repose sur PKCE et le consentement de
l’utilisateur). Voir docs/OAUTH.md pour les créer.

Valeurs vides : les boutons « Se connecter avec… » sont masqués et seule la saisie manuelle reste possible.
"""
GOOGLE_CLIENT_ID = ''
GOOGLE_CLIENT_SECRET = ''
MICROSOFT_CLIENT_ID = ''

# Serveurs IMAP qui désignent un fournisseur, y compris pour un domaine personnel (Google Workspace, Microsoft 365).
PROVIDER_HOSTS = {'imap.gmail.com': 'google', 'outlook.office365.com': 'microsoft'}


def client_id(provider: str) -> str:
    return {'google': GOOGLE_CLIENT_ID, 'microsoft': MICROSOFT_CLIENT_ID}.get(provider, '').strip()


def available(provider: str) -> bool:
    return bool(client_id(provider))


def google_secret(used_client_id: str) -> str:
    """Secret de l’application Google de Smail, seulement pour son propre identifiant."""
    return GOOGLE_CLIENT_SECRET if GOOGLE_CLIENT_ID and used_client_id == GOOGLE_CLIENT_ID else ''


def provider_for(imap_host: str) -> str | None:
    return PROVIDER_HOSTS.get((imap_host or '').strip().lower())
