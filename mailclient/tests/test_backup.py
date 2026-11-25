"""Sauvegarde et restauration : tout ce qui n’existe que sur ce PC, chiffré, jamais un mot de passe."""
import json
import os
import zlib

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from mailclient.core import backup  # noqa: E402
from mailclient.core.accounts import Account, Server  # noqa: E402
from mailclient.storage.database import Database  # noqa: E402
from mailclient.tests.test_complete import Vault  # noqa: E402

PASSWORD = 'correct horse battery'


def filled(tmp_path, name='old.db'):
    vault = Vault()
    db = Database(tmp_path / name, vault)
    account = Account('Camille', 'camille@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465),
                      signature='Camille', imap_login='camille.login')
    db.save(account)
    vault.set(account.id, 'mot-de-passe-du-compte')
    db.set_setting('theme', 1)
    db.set_setting('language', 'en')
    db.set_setting('update_pending', dict(version='0.0.1', path='C:/temp/Smail-setup.exe'))  # Propre à ce PC.
    db.cache_put('draft', 'd1', dict(id='d1', account=account.id, subject='Brouillon local'), account.id)
    db.cache_put('sent-copy', 's1', dict(id='s1', account=account.id, raw='Zm9v'), account.id)
    db.cache_put('filters', 'global', dict(rules=[dict(name='Factures')], blocked=['spam@x.fr'], safe=[], spam_headers=True))
    db.cache_put('signature', account.id, dict(account=account.id, qt_html='<b>Camille</b>'), account.id)
    db.cache_put('body', 'gros-message', dict(raw='x' * 1000), account.id)  # Cache retéléchargeable : pas sauvegardé.
    db.trust(account.id, 'imap:imap.example.com:993', 'ab' * 32)
    return db, account


def test_round_trip_restores_everything_kept_on_this_pc(tmp_path):
    old, account = filled(tmp_path)
    data = backup.export(old, PASSWORD)
    assert data.startswith(backup.MAGIC) and b'Camille' not in data and b'Factures' not in data  # Chiffré.
    payload = backup.read(data, PASSWORD)
    assert backup.summary(payload)['accounts'] == ['Camille <camille@example.com>'] and backup.summary(payload)['drafts'] == 1
    new = Database(tmp_path / 'new.db', Vault())
    restored = backup.restore(new, payload)
    assert [a.email for a in restored] == ['camille@example.com']
    same = new.accounts()[0]
    assert (same.id, same.signature, same.imap_login, same.imap.host) == (account.id, 'Camille', 'camille.login', 'imap.example.com')
    assert new.setting('theme') == 1 and new.setting('language') == 'en' and new.setting('update_pending') is None
    assert new.cache_get('draft', 'd1')['subject'] == 'Brouillon local' and new.cache_get('sent-copy', 's1')['raw'] == 'Zm9v'
    assert new.cache_get('filters', 'global')['blocked'] == ['spam@x.fr']
    assert new.cache_get('signature', account.id)['qt_html'] == '<b>Camille</b>'
    assert new.cache_get('body', 'gros-message') is None
    assert new.pin(account.id, 'imap:imap.example.com:993') == 'ab' * 32


def test_backup_never_contains_a_password_or_token(tmp_path):
    old, _ = filled(tmp_path)
    old.secrets.set('cache-encryption-key', 'clé-du-cache')
    salt = backup.export(old, PASSWORD)
    from cryptography.fernet import Fernet
    clear = zlib.decompress(Fernet(backup._key(PASSWORD, salt[8:24])).decrypt(salt[24:])).decode('utf-8')
    assert 'mot-de-passe-du-compte' not in clear and 'clé-du-cache' not in clear
    assert 'password' not in json.loads(clear)['accounts'][0]


def test_wrong_password_tampering_and_weak_passwords_are_refused(tmp_path):
    old, _ = filled(tmp_path)
    data = backup.export(old, PASSWORD)
    with pytest.raises(backup.BackupError, match='Mot de passe incorrect'):
        backup.read(data, 'pas le bon mot de passe')
    with pytest.raises(backup.BackupError):
        backup.read(data[:-5] + b'XXXXX', PASSWORD)  # Fichier modifié.
    with pytest.raises(backup.BackupError, match='pas une sauvegarde'):
        backup.read(b'PK\x03\x04 un zip quelconque', PASSWORD)
    with pytest.raises(backup.BackupError, match='au moins'):
        backup.export(old, 'court')


def test_restore_into_an_encrypted_cache(tmp_path):
    old, _ = filled(tmp_path)
    payload = backup.read(backup.export(old, PASSWORD), PASSWORD)
    new = Database(tmp_path / 'chiffre.db', Vault())
    new.encrypt_cache(True)
    backup.restore(new, payload)
    assert new.cache_get('draft', 'd1')['subject'] == 'Brouillon local'
    with new.connect() as db:
        stored = [bytes(row[0]) for row in db.execute("SELECT data FROM cache WHERE kind='draft'")]
    assert stored and all(item.startswith(b'E') for item in stored)  # Rechiffré avec la clé de ce PC.
    assert new.setting('cache_encrypted') is True  # Réglage local conservé.


def test_monthly_reminder(tmp_path):
    from datetime import datetime, timedelta, timezone
    db, _ = filled(tmp_path)
    assert backup.reminder_due(db)
    db.set_setting('backup_reminded', datetime.now(timezone.utc).isoformat())
    assert not backup.reminder_due(db)
    db.set_setting('backup_reminded', (datetime.now(timezone.utc) - timedelta(days=40)).isoformat())
    assert backup.reminder_due(db)
    db.set_setting('backup_reminder', False)
    assert not backup.reminder_due(db)
    assert not backup.reminder_due(Database(tmp_path / 'vide.db'))  # Aucun compte : rien à sauvegarder.


def test_backup_and_restore_from_the_file_menu(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from mailclient.core.tls_policy import TLSPolicy
    from mailclient.tests.test_ui import APP, process_until
    from mailclient.ui.main_window import MainWindow
    old, account = filled(tmp_path)
    target = tmp_path / 'sauvegarde.smailbackup'
    window = MainWindow(old, old.secrets, TLSPolicy(old), auto_load=False)
    monkeypatch.setattr(window, 'ask_password', lambda *args: PASSWORD)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args, **kwargs: (str(tmp_path / 'sauvegarde'), ''))
    window.backup_data()
    assert process_until(lambda: not window.busy and target.exists())
    assert old.setting('last_backup')
    window.reader.shutdown()
    window.close()
    # Nouveau PC : Smail vierge, restauration depuis le fichier.
    new = Database(tmp_path / 'nouveau-pc.db', Vault())
    fresh = MainWindow(new, new.secrets, TLSPolicy(new), auto_load=False)
    asked = []
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args, **kwargs: (str(target), ''))
    monkeypatch.setattr(fresh, 'ask_password', lambda *args: PASSWORD)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: asked.append(args[2]) or QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: asked.append(args[2]))
    monkeypatch.setattr(fresh, 'preferences', lambda page='Général': asked.append(page))
    fresh.restore_data()
    assert process_until(lambda: not fresh.busy and 'Comptes' in asked)
    assert [a.email for a in fresh.accounts] == ['camille@example.com']
    assert 'camille@example.com' in asked[0] and 'mots de passe' in asked[1]  # Mot de passe à ressaisir.
    from shiboken6 import delete
    for item in (window, fresh):
        item.reader.shutdown()
        item.close()
        delete(item)
    APP.processEvents()
