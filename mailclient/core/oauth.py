"""OAuth2 bureau : navigateur système, loopback, state et PKCE S256.

Les identifiants client sont ceux de l'application Smail (mailclient/core/oauth_apps.py, connexion en un
clic) ou ceux d'une application enregistrée par l'utilisateur (réglages avancés).
Les jetons et le secret client Google restent exclusivement dans keyring.
"""
from mailclient.i18n import tr
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PROVIDERS = {
    'google': ('https://accounts.google.com/o/oauth2/v2/auth', 'https://oauth2.googleapis.com/token',
               'https://mail.google.com/'),
    'microsoft': ('https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
                  'https://login.microsoftonline.com/common/oauth2/v2.0/token',
                  'offline_access https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send'),
}

def xoauth2(address: str, token: str) -> bytes:
    if any(c in address + token for c in '\r\n\x00\x01'):
        raise ValueError(tr('Identifiants OAuth2 invalides.'))
    return f'user={address}\x01auth=Bearer {token}\x01\x01'.encode('utf-8')

class OAuth:
    def __init__(self, vault):
        self.vault = vault
        self.lock = threading.RLock()

    @staticmethod
    def provider(account):
        authorize, token, scope = PROVIDERS[account.auth_method]
        if account.auth_method == 'microsoft':
            authorize = authorize.replace('/common/', '/' + account.oauth_tenant + '/')
            token = token.replace('/common/', '/' + account.oauth_tenant + '/')
        return authorize, token, scope

    def _request(self, account, values):
        values['client_id'] = account.oauth_client_id
        if account.auth_method == 'google':
            try:
                secret = self.vault.get(account.id + ':oauth-client-secret')
            except RuntimeError:
                secret = ''
            if not secret:  # Application Google de Smail (connexion en un clic).
                from mailclient.core.oauth_apps import google_secret
                secret = google_secret(account.oauth_client_id)
            if secret:
                values['client_secret'] = secret
        try:
            request = Request(self.provider(account)[1], data=urlencode(values).encode('ascii'),
                              headers={'Content-Type': 'application/x-www-form-urlencoded'})
            with urlopen(request, timeout=20) as response:
                result = json.load(response)
        except (HTTPError, URLError, ValueError):
            raise RuntimeError(tr('OAuth2 : autorisation refusée ou expirée. Vérifiez la configuration et reconnectez ce compte.')) from None
        if not result.get('access_token'):
            raise RuntimeError(tr('OAuth2 : aucun jeton reçu.'))
        result['expires_at'] = time.time() + int(result.get('expires_in', 3600))
        result['client_id'] = account.oauth_client_id
        result['provider'] = account.auth_method
        result['email'] = account.email
        result['tenant'] = account.oauth_tenant
        return result

    def authorize(self, account, cancelled=None):
        cancelled = cancelled or threading.Event()
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')
        callback = {}
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(2)

            def do_GET(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                if parsed.path != '/callback' or not hmac.compare_digest(query.get('state', [''])[0], state):
                    self.send_error(400)
                    return
                callback.update(code=query.get('code', [''])[0], error=query.get('error', [''])[0])
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(tr('Vous pouvez fermer cet onglet et revenir dans Smail.').encode('utf-8'))
            def log_message(self, *args):
                pass
        with HTTPServer(('127.0.0.1', 0), Handler) as server:
            server.timeout = 0.5
            host = 'localhost' if account.auth_method == 'microsoft' else '127.0.0.1'
            redirect = f'http://{host}:{server.server_port}/callback'
            values = dict(client_id=account.oauth_client_id, response_type='code', redirect_uri=redirect,
                          scope=self.provider(account)[2], state=state,
                          code_challenge=challenge, code_challenge_method='S256', login_hint=account.email)
            if account.auth_method == 'google':
                values.update(access_type='offline', prompt='consent')
            if not webbrowser.open(self.provider(account)[0] + '?' + urlencode(values)):
                raise RuntimeError(tr('Impossible d’ouvrir le navigateur système pour OAuth2.'))
            deadline = time.monotonic() + 180
            while not callback and not cancelled.is_set() and time.monotonic() < deadline:
                server.handle_request()
        if not callback.get('code') or cancelled.is_set():
            raise RuntimeError(tr('Autorisation OAuth2 annulée ou délai dépassé.'))
        result = self._request(account, dict(grant_type='authorization_code', code=callback['code'],
                                            code_verifier=verifier, redirect_uri=redirect))
        with self.lock:
            self.vault.set(account.id + ':oauth', json.dumps(result))

    def credential(self, account, protocol='imap') -> str:
        """Mot de passe ou jeton d’accès ; pour SMTP, le mot de passe SMTP distinct s’il a été défini."""
        if account.auth_method == 'password':
            if protocol == 'smtp':
                try:
                    return self.vault.get(account.id + ':smtp')
                except RuntimeError:
                    pass  # Pas de mot de passe SMTP distinct : celui du compte.
            return self.vault.get(account.id)
        with self.lock:
            try:
                tokens = json.loads(self.vault.get(account.id + ':oauth'))
            except (RuntimeError, ValueError):
                raise RuntimeError(tr('Connectez ce compte avec le bouton OAuth2 dans les paramètres du compte.')) from None
            if (tokens.get('client_id'), tokens.get('provider'), tokens.get('email'), tokens.get('tenant', 'common')) != (account.oauth_client_id, account.auth_method, account.email, account.oauth_tenant):
                raise RuntimeError(tr('La configuration OAuth2 a changé : reconnectez ce compte.'))
            if tokens.get('expires_at', 0) <= time.time() + 90:
                if not tokens.get('refresh_token'):
                    raise RuntimeError(tr('Autorisation OAuth2 expirée : reconnectez ce compte.'))
                fresh = self._request(account, dict(grant_type='refresh_token', refresh_token=tokens['refresh_token']))
                tokens.update(fresh)
                self.vault.set(account.id + ':oauth', json.dumps(tokens))
            return tokens['access_token']

    def is_authorized(self, account) -> bool:
        """Vérification locale, sans renouvellement ni requête réseau."""
        try:
            tokens = json.loads(self.vault.get(account.id + ':oauth'))
            return (tokens.get('client_id'), tokens.get('provider'), tokens.get('email'), tokens.get('tenant', 'common')) == (account.oauth_client_id, account.auth_method, account.email, account.oauth_tenant) and bool(tokens.get('access_token'))
        except (ValueError, RuntimeError):
            return False
