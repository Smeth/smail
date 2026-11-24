"""Identifiants de connexion distincts de l’adresse et mot de passe SMTP distinct."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from mailclient.core.accounts import Account, Server
from mailclient.core.imap_client import IMAPClient
from mailclient.core.oauth import OAuth
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database


def account(**values):
    return Account('Hébergé', 'contact@exemple.fr', Server('mail.exemple.fr', 993), Server('smtp.exemple.fr', 465), **values)


class DictVault:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, key):
        if key not in self.values:
            raise RuntimeError('absent')
        return self.values[key]

    def set(self, key, value):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)


def test_logins_saved_apart_from_the_1_0_0_compatible_config(tmp_path):
    db = Database(tmp_path / 'settings.db')
    hosted = account(imap_login='client12345', smtp_login='relais@hebergeur.net')
    db.save(hosted)
    assert db.accounts() == [hosted]
    assert db.accounts()[0].imap_user == 'client12345' and db.accounts()[0].smtp_user == 'relais@hebergeur.net'
    with sqlite3.connect(db.path) as raw:
        config = json.loads(raw.execute('SELECT config FROM accounts').fetchone()[0])
    assert 'imap_login' not in config and 'smtp_login' not in config
    # Lecture stricte, comme Smail 1.0.0 : Account(**config) sans champ inconnu.
    legacy = {key: value for key, value in config.items() if key not in {'imap', 'smtp'}}
    Account(**legacy, imap=Server(**config['imap']), smtp=Server(**config['smtp']))
    hosted.imap_login = hosted.smtp_login = ''
    db.save(hosted)
    assert db.setting(f'logins:{hosted.id}') is None and db.accounts()[0].imap_user == 'contact@exemple.fr'
    hosted.imap_login = 'client12345'
    db.save(hosted)
    db.delete_account(hosted.id)
    assert db.setting(f'logins:{hosted.id}') is None


@pytest.mark.parametrize('login', ['a\r\nb', ' espace', 'x' * 255, 'nul\x00'])
def test_invalid_logins(login):
    with pytest.raises(ValueError):
        account(imap_login=login).validate()


def test_imap_and_smtp_use_their_own_login(monkeypatch):
    imap = MagicMock()
    imap.capability.return_value = ('OK', [b'IMAP4rev1'])
    monkeypatch.setattr('imaplib.IMAP4_SSL', lambda *args, **kwargs: imap)
    tls = SimpleNamespace(connect=lambda account_id, endpoint, factory: factory(None))
    hosted = account(imap_login='client12345', smtp_login='relais@hebergeur.net')
    IMAPClient(hosted, 'mdp-imap', tls).open()
    imap.login.assert_called_once_with('client12345', 'mdp-imap')
    smtp = MagicMock()
    smtp.has_extn.return_value = True
    monkeypatch.setattr('smtplib.SMTP_SSL', lambda *args, **kwargs: smtp)
    from mailclient.core.smtp_client import open_connection
    open_connection(hosted, 'mdp-smtp', tls)
    smtp.login.assert_called_once_with('relais@hebergeur.net', 'mdp-smtp')


def test_pool_never_reuses_a_session_opened_with_another_login():
    hosted = account()
    first = IMAPClient(hosted, 'pw', None)._pool_key()
    hosted.imap_login = 'client12345'
    assert IMAPClient(hosted, 'pw', None)._pool_key() != first


def test_smtp_credential_prefers_distinct_password():
    hosted = account()
    oauth = OAuth(DictVault({hosted.id: 'compte'}))
    assert oauth.credential(hosted, 'smtp') == 'compte' and oauth.credential(hosted) == 'compte'
    oauth.vault.set(hosted.id + ':smtp', 'envoi')
    assert oauth.credential(hosted, 'smtp') == 'envoi' and oauth.credential(hosted) == 'compte'


def test_account_dialog_fields(tmp_path):
    from PySide6.QtWidgets import QApplication
    from mailclient.ui.account_dialog import AccountDialog
    QApplication.instance() or QApplication([])
    db = Database(tmp_path / 'settings.db')
    hosted = account()
    db.save(hosted)
    vault = DictVault({hosted.id: 'compte'})
    dialog = AccountDialog(db, vault, TLSPolicy(db), account=hosted)
    assert dialog.same_smtp_password.isChecked() and not dialog.smtp_password.isEnabled()
    dialog.logins['imap'].setText('client12345')
    dialog.same_smtp_password.setChecked(False)
    assert dialog.smtp_password.isEnabled()
    dialog.smtp_password.setText('envoi')
    dialog.save()
    saved = db.accounts()[0]
    assert saved.imap_login == 'client12345' and saved.smtp_login == '' and vault.values[hosted.id + ':smtp'] == 'envoi'
    reopened = AccountDialog(db, vault, TLSPolicy(db), account=saved)
    assert reopened.logins['imap'].text() == 'client12345' and not reopened.same_smtp_password.isChecked()
    reopened.same_smtp_password.setChecked(True)
    reopened.save()
    assert hosted.id + ':smtp' not in vault.values
    reopened.auth.setCurrentIndex(1)  # OAuth2 : l’identité est l’adresse.
    assert not reopened.logins['imap'].isEnabled() and not reopened.same_smtp_password.isEnabled()
