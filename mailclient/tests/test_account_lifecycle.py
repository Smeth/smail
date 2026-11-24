"""Suppression de compte, migration du schéma et exceptions de certificat."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
import json
import sqlite3
import time
from types import SimpleNamespace
import pytest
from mailclient.core.accounts import Account, Server
from mailclient.core.service import MailService, cache_key
from mailclient.core.tls_policy import TLSPolicy, CertificateAlert
from mailclient.storage.database import Database, SCHEMA_VERSION


class DictVault:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.deleted = []

    def get(self, key):
        if key not in self.values:
            raise RuntimeError('absent')
        return self.values[key]

    def set(self, key, value):
        self.values[key] = value

    def delete(self, key):
        self.deleted.append(key)
        self.values.pop(key, None)


def make_account(name='Perso', email='a@example.com'):
    return Account(name, email, Server('imap.example.com', 993), Server('smtp.example.com', 465))


def body_key(account, folder, uid, validity='7'):
    return MailService.body_key(dict(account=account.id, folder=folder, uidvalidity=validity, uid=uid))


def fill_cache(db, account):
    row = dict(uid='5', uidvalidity='7', account=account.id, folder='INBOX', sender='x', subject='s', date='')
    db.cache_put('folders', account.id, [['INBOX', 'Réception']], account.id)
    db.cache_put('mailbox', cache_key(account.id, 'INBOX'), dict(account=account.id, folder='INBOX', pages={'0': [row]}, total=1, uidvalidity='7'))
    db.cache_put('body', body_key(account, 'INBOX', '5'), 'cmF3', account.id)
    db.cache_put('draft', 'd-' + account.id, dict(id='d', account=account.id, body='brouillon'))
    db.cache_put('sent-copy', 's-' + account.id, dict(id='s', account=account.id, raw=''))
    db.cache_put('notified', account.id, dict(validity='7', uid=5), account.id)
    db.trust(account.id, 'imap:imap.example.com:993:SSL/TLS', 'ab' * 32)


def cache_count(db, account_id):
    with sqlite3.connect(db.path) as raw:
        return raw.execute('SELECT COUNT(*) FROM cache c JOIN cache_owner o ON o.kind=c.kind AND o.key=c.key WHERE o.account=?', (account_id,)).fetchone()[0]


def test_delete_account_removes_only_that_account(tmp_path):
    db = Database(tmp_path / 'settings.db')
    gone, kept = make_account(), make_account('Travail', 'b@example.com')
    for account in (gone, kept):
        db.save(account)
        fill_cache(db, account)
    assert cache_count(db, gone.id) == 6
    db.delete_account(gone.id)
    assert [a.id for a in db.accounts()] == [kept.id]
    assert cache_count(db, gone.id) == 0
    assert cache_count(db, kept.id) == 6
    assert [pin[0] for pin in db.pins()] == [kept.id]
    assert db.cache_list('draft') == [dict(id='d', account=kept.id, body='brouillon')]
    # Une synchronisation encore en vol ne peut pas recréer le cache du compte supprimé.
    db.cache_put('body', body_key(gone, 'INBOX', '9'), 'eA==', gone.id)
    db.cache_put('mailbox', cache_key(gone.id, 'INBOX'), dict(account=gone.id, pages={}))
    assert cache_count(db, gone.id) == 0


def test_service_delete_account_clears_vault_and_session_trust(tmp_path):
    db = Database(tmp_path / 'settings.db')
    account = make_account()
    db.save(account)
    vault = DictVault({account.id: 'pw', account.id + ':oauth': '{}', 'other': 'x'})
    tls = TLSPolicy(db)
    alert = CertificateAlert(account.id, 'imap:h', 'f' * 64, 'issuer', 'dates', 'raison')
    tls.approve(alert, permanent=True)
    MailService(db, vault, tls).delete_account(account)
    assert set(vault.deleted) == {account.id, account.id + ':smtp', account.id + ':oauth', account.id + ':oauth-client-secret'}
    assert vault.values == {'other': 'x'}
    assert tls.session == {} and db.pins() == []
    assert db.accounts() == []


def test_service_reports_vault_failure_after_local_deletion(tmp_path):
    db = Database(tmp_path / 'settings.db')
    account = make_account()
    db.save(account)
    class BrokenVault(DictVault):
        def delete(self, key):
            raise OSError('coffre indisponible')
    with pytest.raises(RuntimeError, match='secrets'):
        MailService(db, BrokenVault(), TLSPolicy(db)).delete_account(account)
    assert db.accounts() == []


def test_secrets_delete_removes_chunks(monkeypatch):
    from mailclient.storage.secrets import Secrets
    values = {}
    backend = SimpleNamespace(get_password=lambda service, key: values.get(key),
                              set_password=lambda service, key, value: values.__setitem__(key, value),
                              delete_password=lambda service, key: values.pop(key))
    vault = Secrets()
    monkeypatch.setattr(vault, '_backend', lambda: backend)
    vault.set('acc:oauth', 'y' * 2200)
    vault.set('acc', 'court')
    vault.set('autre', 'z')
    assert len(values) > 3
    vault.delete('acc:oauth')
    vault.delete('acc')
    vault.delete('absent')  # Pas d’erreur pour un secret déjà retiré.
    assert values == {'autre': 'z'}


def test_migration_from_unversioned_database_backfills_accounts(tmp_path):
    path = tmp_path / 'old.db'
    account = make_account()
    raw = sqlite3.connect(path)
    raw.executescript('CREATE TABLE accounts (id TEXT PRIMARY KEY, config TEXT NOT NULL); CREATE TABLE pins (account TEXT, endpoint TEXT, fingerprint TEXT, PRIMARY KEY(account,endpoint));'
                      'CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL); CREATE TABLE cache (kind TEXT, key TEXT, data BLOB NOT NULL, PRIMARY KEY(kind,key));')
    raw.execute('INSERT INTO accounts VALUES (?,?)', (account.id, json.dumps(account.to_dict())))
    def put(kind, key, value):
        raw.execute('INSERT INTO cache VALUES (?,?,?)', (kind, Database._cache_key(key), b'P' + json.dumps(value, ensure_ascii=False).encode()))
    row = dict(uid='5', uidvalidity='7', account=account.id, folder='INBOX')
    put('folders', account.id, [['INBOX', 'Réception']])
    put('notified', account.id, dict(validity='7', uid=5))
    put('mailbox', cache_key(account.id, 'INBOX'), dict(account=account.id, folder='INBOX', pages={'0': [row]}))
    put('body', body_key(account, 'INBOX', '5'), 'cmF3')
    put('draft', 'd1', dict(id='d1', account=account.id))
    put('sent-copy', 's1', dict(id='s1', account=account.id, raw=''))
    raw.commit()
    raw.close()
    db = Database(path)
    with sqlite3.connect(path) as check:
        assert check.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
        assert check.execute('SELECT COUNT(*) FROM cache c WHERE NOT EXISTS (SELECT 1 FROM cache_owner o WHERE o.kind=c.kind AND o.key=c.key)').fetchone()[0] == 0
        assert [row[1] for row in check.execute('PRAGMA table_info(cache)')] == ['kind', 'key', 'data']
    assert cache_count(db, account.id) == 6
    Database(path)  # Une seconde ouverture ne rejoue pas la migration.


def test_smail_1_0_0_can_still_write_after_migration_and_its_entries_are_claimed(tmp_path):
    path = tmp_path / 'settings.db'
    db = Database(path)
    account = make_account()
    db.save(account)
    # Écriture telle que la réalise Smail 1.0.0 : trois valeurs, aucune table cache_owner.
    with sqlite3.connect(path) as legacy:
        legacy.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)',
                       ('draft', Database._cache_key('ancien'), b'P' + json.dumps(dict(id='ancien', account=account.id)).encode()))
    Database(path).delete_account(account.id)
    with sqlite3.connect(path) as check:
        assert check.execute('SELECT COUNT(*) FROM cache').fetchone()[0] == 0


def test_preview_schema_with_account_column_is_converted(tmp_path):
    path = tmp_path / 'preview.db'
    account = make_account()
    raw = sqlite3.connect(path)
    raw.executescript('CREATE TABLE accounts (id TEXT PRIMARY KEY, config TEXT NOT NULL); CREATE TABLE pins (account TEXT, endpoint TEXT, fingerprint TEXT, PRIMARY KEY(account,endpoint));'
                      'CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL); CREATE TABLE cache (kind TEXT, key TEXT, data BLOB NOT NULL, PRIMARY KEY(kind,key));'
                      'ALTER TABLE cache ADD COLUMN account TEXT; CREATE INDEX cache_account ON cache(account); PRAGMA user_version = 1;')
    raw.execute('INSERT INTO accounts VALUES (?,?)', (account.id, json.dumps(account.to_dict())))
    raw.execute('INSERT INTO cache VALUES (?,?,?,?)', ('body', 'x', b'P"eA=="', account.id))
    raw.commit()
    raw.close()
    db = Database(path)
    with sqlite3.connect(path) as check:
        assert check.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
        assert [row[1] for row in check.execute('PRAGMA table_info(cache)')] == ['kind', 'key', 'data']
    assert cache_count(db, account.id) == 1


def test_newer_schema_is_refused(tmp_path):
    path = tmp_path / 'future.db'
    Database(path)
    with sqlite3.connect(path) as raw:
        raw.execute(f'PRAGMA user_version = {SCHEMA_VERSION + 1}')
    with pytest.raises(RuntimeError, match='plus récente'):
        Database(path)


def test_main_window_delete_account_flow(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from mailclient.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    db = Database(tmp_path / 'settings.db')
    gone, kept = make_account(), make_account('Travail', 'b@example.com')
    for account in (gone, kept):
        db.save(account)
        fill_cache(db, account)
    vault = DictVault({gone.id: 'pw'})
    window = MainWindow(db, vault, TLSPolicy(db), auto_load=False)
    window.reload_accounts = lambda: setattr(window, 'accounts', db.accounts())
    window.accounts = db.accounts()
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: QMessageBox.Cancel)
    assert not window.delete_account(gone)
    assert len(db.accounts()) == 2
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: QMessageBox.Yes)
    assert window.delete_account(gone)
    deadline = time.monotonic() + 5
    while window.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert not window.busy
    assert [a.id for a in window.accounts] == [kept.id]
    assert gone.id in vault.deleted
    assert 'supprimé' in window.statusBar().currentMessage()
    window.reader.shutdown()
    window.close()
    from shiboken6 import delete
    delete(window)


def test_settings_lists_and_removes_pinned_certificates(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from mailclient.ui.settings_dialog import SettingsDialog
    QApplication.instance() or QApplication([])
    db = Database(tmp_path / 'settings.db')
    account = make_account()
    db.save(account)
    db.trust(account.id, 'imap:imap.example.com:993:SSL/TLS', 'ab' * 32)
    db.trust('ancien', 'smtp:smtp.example.com:465:SSL/TLS', 'cd' * 32)
    dialog = SettingsDialog(db)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    dialog.remove_pin(account.id, 'imap:imap.example.com:993:SSL/TLS', dialog)
    assert db.pins() == [('ancien', 'smtp:smtp.example.com:465:SSL/TLS', 'cd' * 32)]
    dialog.reject()
    from shiboken6 import delete
    delete(dialog)
