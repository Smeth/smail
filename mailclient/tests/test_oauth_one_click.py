"""Connexion Gmail / Outlook en un clic avec l’application OAuth2 de Smail."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import io
import json
from urllib.parse import parse_qs
import pytest
from mailclient.core import oauth_apps
from mailclient.core.accounts import Account, Server
from mailclient.core.oauth import OAuth


@pytest.fixture
def smail_apps(monkeypatch):
    monkeypatch.setattr(oauth_apps, 'GOOGLE_CLIENT_ID', 'smail-google.apps.googleusercontent.com')
    monkeypatch.setattr(oauth_apps, 'GOOGLE_CLIENT_SECRET', 'secret-public-de-bureau')
    monkeypatch.setattr(oauth_apps, 'MICROSOFT_CLIENT_ID', '00000000-1111-2222-3333-444444444444')


class Vault:
    def __init__(self):
        self.values = {}

    def get(self, key):
        if key not in self.values:
            raise RuntimeError('absent')
        return self.values[key]

    def set(self, key, value):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)


def test_without_smail_apps_buttons_are_hidden(tmp_path):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from mailclient.core.tls_policy import TLSPolicy
    from mailclient.storage.database import Database
    from mailclient.ui.account_dialog import AccountDialog
    assert not oauth_apps.available('google') or oauth_apps.GOOGLE_CLIENT_ID  # Valeurs du dépôt.
    db = Database(tmp_path / 'settings.db')
    dialog = AccountDialog(db, Vault(), TLSPolicy(db))
    assert dialog.quick.isHidden() == (not oauth_apps.available('google') and not oauth_apps.available('microsoft'))


def test_google_secret_only_for_smail_client(smail_apps, monkeypatch):
    sent = []
    class Response(io.BytesIO):
        def __exit__(self, *args):
            return False
    def urlopen(request, timeout):
        sent.append(parse_qs(request.data.decode()))
        return Response(json.dumps(dict(access_token='a', refresh_token='r', expires_in=3600)).encode())
    monkeypatch.setattr('mailclient.core.oauth.urlopen', urlopen)
    account = Account('Moi', 'moi@gmail.com', Server('imap.gmail.com', 993), Server('smtp.gmail.com', 587, 'STARTTLS'),
                      auth_method='google', oauth_client_id=oauth_apps.GOOGLE_CLIENT_ID)
    OAuth(Vault())._request(account, dict(grant_type='refresh_token', refresh_token='r'))
    assert sent[-1]['client_secret'] == ['secret-public-de-bureau'] and sent[-1]['client_id'] == [oauth_apps.GOOGLE_CLIENT_ID]
    account.oauth_client_id = 'mon-application-a-moi'
    OAuth(Vault())._request(account, dict(grant_type='refresh_token', refresh_token='r'))
    assert 'client_secret' not in sent[-1]  # Jamais le secret de Smail pour une autre application.


def test_one_click_fills_everything_and_opens_the_browser(smail_apps, tmp_path, monkeypatch):
    from mailclient.tests.test_ui import APP, process_until  # noqa: F401
    from mailclient.core.tls_policy import TLSPolicy
    from mailclient.storage.database import Database
    from mailclient.ui.account_dialog import AccountDialog
    db = Database(tmp_path / 'settings.db')
    vault = Vault()
    dialog = AccountDialog(db, vault, TLSPolicy(db))
    assert not dialog.quick.isHidden() and not dialog.quick_buttons['microsoft'].isHidden()
    authorized = []
    monkeypatch.setattr(dialog.oauth, 'authorize', lambda account, cancelled: authorized.append(account))
    dialog.one_click('google')
    assert 'adresse' in dialog.status.text() and not authorized
    dialog.name.setText('Marie Dupont')
    dialog.address.setText('marie@entreprise.fr')  # Google Workspace sur un domaine personnel.
    dialog.one_click('google')
    assert process_until(lambda: authorized and not dialog.busy)
    account = authorized[0]
    assert (account.auth_method, account.oauth_client_id) == ('google', oauth_apps.GOOGLE_CLIENT_ID)
    assert (account.imap.host, account.smtp.host) == ('imap.gmail.com', 'smtp.gmail.com')
    assert dialog.oauth_group.isHidden()  # Aucun identifiant technique affiché.
    assert dialog.status.text() == 'Connexion autorisée. Cliquez sur « Enregistrer » pour terminer.'
    dialog.auth.setCurrentIndex(2)  # Passage à Microsoft : l’identifiant suit.
    assert dialog.client_id.text() == oauth_apps.MICROSOFT_CLIENT_ID
    dialog.own_app.setChecked(True)  # Avancé : sa propre application.
    assert not dialog.oauth_group.isHidden()


def test_detection_suggests_the_right_button(smail_apps, tmp_path):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from mailclient.core import autoconfig
    from mailclient.core.tls_policy import TLSPolicy
    from mailclient.storage.database import Database
    from mailclient.ui.account_dialog import AccountDialog
    db = Database(tmp_path / 'settings.db')
    dialog = AccountDialog(db, Vault(), TLSPolicy(db))
    dialog.address.setText('quelquun@hotmail.fr')
    dialog.preset()
    assert '« Se connecter avec Microsoft »' in dialog.detect_status.text()
    assert autoconfig.known('a@hotmail.fr').imap.host == 'outlook.office365.com'
