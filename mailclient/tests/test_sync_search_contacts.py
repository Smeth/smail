"""Synchronisation incrémentale, index de recherche hors ligne et carnet d’adresses."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
import base64
import sqlite3
import threading
from mailclient.core.accounts import Account, Server
from mailclient.core.imap_client import IMAPClient
from mailclient.core.service import MailService, cache_key
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database

ACCOUNT = Account('Moi', 'moi@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))


class Vault:
    def __init__(self):
        self.values = {}

    def get(self, key):
        if key not in self.values:
            raise RuntimeError('absent')
        return self.values[key]

    def set(self, key, value):
        self.values[key] = value


def raw_mail(uid, sender='Alice <alice@example.com>', body='Bonjour'):
    return f'From: {sender}\r\nSubject: Sujet {uid}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body} {uid}\r\n'.encode()


class FakeServer:
    """Client IMAP simulé au niveau du service : compte les captures de dossiers."""
    def __init__(self, condstore=True):
        self.condstore = condstore
        self.mail = {'INBOX': {'1': raw_mail('1'), '2': raw_mail('2', 'Bob <bob@example.com>', 'Facture été')},
                     'Spam': {'5': raw_mail('5', 'Pub <pub@spam.example>')}}
        self.modseq = {'INBOX': 10, 'Spam': 3}
        self.snapshots = []

    def folders(self):
        return [('INBOX', 'Boîte de réception'), ('Spam', 'Spam')]

    def folder_status(self, folders):
        result = {}
        for folder in folders:
            values = dict(MESSAGES=len(self.mail[folder]), UIDNEXT=10, UIDVALIDITY=7)
            if self.condstore:
                values['HIGHESTMODSEQ'] = self.modseq[folder]
            result[folder] = values
        return result

    def snapshot(self, folder, limit, cancelled, known=None):
        self.snapshots.append(folder)
        rows, bodies = [], {}
        for uid, raw in sorted(self.mail[folder].items(), key=lambda item: -int(item[0])):
            cached = known(uid, '7') if known else None
            from mailclient.core.parser import metadata
            rows.append(dict(metadata(raw), uid=uid, uidvalidity='7', unread=True, starred=False))
            bodies[uid] = cached or raw
        return rows, len(rows), bodies, '7'


def service_with(tmp_path, server, monkeypatch, vault=None):
    db = Database(tmp_path / 'settings.db', vault)
    db.save(ACCOUNT)
    monkeypatch.setattr(MailService, 'client', lambda *args: server)
    return MailService(db, vault, TLSPolicy(db)), db


def test_unchanged_folders_are_skipped_with_condstore(tmp_path, monkeypatch):
    server = FakeServer()
    service, db = service_with(tmp_path, server, monkeypatch)
    writes = []
    original = db.cache_put
    monkeypatch.setattr(db, 'cache_put', lambda kind, *args, **kw: (writes.append(kind), original(kind, *args, **kw)))
    service.sync_account(ACCOUNT, threading.Event())
    assert server.snapshots == ['INBOX', 'Spam'] and writes.count('body') == 3
    server.snapshots.clear()
    writes.clear()
    service.sync_account(ACCOUNT, threading.Event())
    assert server.snapshots == []  # Rien n’a changé : aucun SELECT ni FETCH.
    server.modseq['INBOX'] = 11  # Un drapeau a changé dans la réception.
    service.sync_account(ACCOUNT, threading.Event())
    assert server.snapshots == ['INBOX']
    assert writes.count('body') == 0  # Contenus déjà en cache : jamais réécrits.
    server.snapshots.clear()
    service.sync_account(ACCOUNT, threading.Event(), limit=200)
    assert server.snapshots == ['INBOX', 'Spam']  # Une nouvelle limite impose une capture complète.
    # Cache d’une version antérieure, sans identifiants de conversation : recapturé une seule fois.
    state = service.state(ACCOUNT, 'Spam')
    state.pop('threaded')
    db.cache_put('mailbox', cache_key(ACCOUNT.id, 'Spam'), state)
    server.snapshots.clear()
    service.sync_account(ACCOUNT, threading.Event(), limit=200)
    service.sync_account(ACCOUNT, threading.Event(), limit=200)
    assert server.snapshots == ['Spam']


def test_without_condstore_every_folder_is_captured(tmp_path, monkeypatch):
    server = FakeServer(condstore=False)
    service, _ = service_with(tmp_path, server, monkeypatch)
    service.sync_account(ACCOUNT, threading.Event())
    server.snapshots.clear()
    service.sync_account(ACCOUNT, threading.Event())
    assert server.snapshots == ['INBOX', 'Spam']


def test_folder_status_parses_response_on_fresh_session():
    class Session:
        capabilities = (b'IMAP4REV1', b'CONDSTORE')
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def status(self, folder, items):
            assert 'HIGHESTMODSEQ' in items
            if folder == '"Bad"':
                return 'NO', [b'refus']
            return 'OK', [folder.encode() + b' (MESSAGES 4 UIDNEXT 12 UIDVALIDITY 7 HIGHESTMODSEQ 99)']
    client = IMAPClient(ACCOUNT, 'pw', None)
    client.open = lambda: Session()
    assert client.folder_status(['INBOX', 'Bad']) == {'INBOX': dict(MESSAGES=4, UIDNEXT=12, UIDVALIDITY=7, HIGHESTMODSEQ=99)}


def test_offline_search_uses_index_and_heals_missing_entries(tmp_path, monkeypatch):
    server = FakeServer()
    service, db = service_with(tmp_path, server, monkeypatch)
    service.sync_account(ACCOUNT, threading.Event())
    assert db.index_enabled() and len(db.index_keys()) == 3
    rows = service._known_rows(service.state(ACCOUNT, 'INBOX'))
    assert [row['uid'] for row in service._search(rows, 'FACTURE ÉTÉ')] == ['2']
    assert [row['uid'] for row in service._search(rows, 'bob')] == ['2']  # Expéditeur, hors index.
    # Une entrée retirée de l’index est retrouvée par balayage puis réindexée.
    with sqlite3.connect(db.path) as raw:
        raw.execute('DELETE FROM search_index')
    assert [row['uid'] for row in service._search(rows, 'facture')] == ['2']
    assert len(db.index_keys()) == 2  # Les deux messages balayés sont réindexés.
    # Requête courte : balayage (le tokenizer trigram exige trois caractères).
    assert [row['uid'] for row in service._search(rows, 'é 2')] == ['2']
    assert [row['uid'] for row in service._search(rows, 'zz')] == []
    assert [row['uid'] for row in service._search(rows, 'r 1')] == ['1']


def test_index_follows_body_deletion_and_account_deletion(tmp_path, monkeypatch):
    server = FakeServer()
    service, db = service_with(tmp_path, server, monkeypatch)
    service.sync_account(ACCOUNT, threading.Event())
    row = service._known_rows(service.state(ACCOUNT, 'INBOX'))[0]
    db.cache_delete('body', service.body_key(row))
    assert len(db.index_keys()) == 2
    db.delete_account(ACCOUNT.id)
    assert db.index_keys() == set()


def test_encryption_drops_plaintext_index(tmp_path, monkeypatch):
    server = FakeServer()
    service, db = service_with(tmp_path, server, monkeypatch, Vault())
    service.sync_account(ACCOUNT, threading.Event())
    assert db.index_keys()
    db.encrypt_cache(True)
    with sqlite3.connect(db.path) as raw:
        assert raw.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'search_index%'").fetchone()[0] == 0
    assert not db.index_enabled()
    rows = service._known_rows(service.state(ACCOUNT, 'INBOX'))
    assert [row['uid'] for row in service._search(rows, 'facture')] == ['2']  # Balayage du cache chiffré.
    with sqlite3.connect(db.path) as raw:
        assert raw.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='search_index'").fetchone()[0] == 0
    assert b'Facture' not in open(db.path, 'rb').read()


def test_contacts_from_sync_and_sent_messages(tmp_path, monkeypatch):
    server = FakeServer()
    service, db = service_with(tmp_path, server, monkeypatch)
    service.sync_account(ACCOUNT, threading.Event())
    assert service.contacts([ACCOUNT]) == ['Alice <alice@example.com>', 'Bob <bob@example.com>']  # Pas le spam.
    service.remember_contacts(ACCOUNT, [('Robert B.', 'BOB@example.com'), ('', 'moi@example.com'), ('Dupont, Jean', 'jd@example.com')], sent=True)
    service.remember_contacts(ACCOUNT, [('', 'jd@example.com')], sent=True)
    assert service.contacts([ACCOUNT]) == ['"Dupont Jean" <jd@example.com>'.replace('Dupont Jean', 'Dupont, Jean'),
                                           'Robert B. <bob@example.com>', 'Alice <alice@example.com>']
    from mailclient.core.smtp_client import addresses
    assert addresses(', '.join(service.contacts([ACCOUNT])) + ', ')[0] == ('Dupont, Jean', 'jd@example.com')
    db.delete_account(ACCOUNT.id)
    assert service.contacts([ACCOUNT]) == []


def test_address_completer_completes_last_segment():
    from PySide6.QtWidgets import QApplication, QLineEdit
    from mailclient.ui.address_completer import AddressCompleter
    QApplication.instance() or QApplication([])
    field = QLineEdit()
    completer = AddressCompleter(['Alice <alice@example.com>', 'Bob <bob@example.com>'], field)
    field.setCompleter(completer)
    field.setText('alice@example.com, bo')
    assert completer.splitPath(field.text()) == ['bo']
    completer.setCompletionPrefix('bo')
    assert completer.completionModel().index(0, 0).data() == 'Bob <bob@example.com>'
    source = lambda: completer.completionModel().mapToSource(completer.currentIndex())  # Qt fournit l’index du modèle source.
    completer.setCurrentRow(0)
    assert completer.pathFromIndex(source()) == 'alice@example.com, Bob <bob@example.com>, '
    field.setText('ali')
    completer.setCompletionPrefix('ali')
    completer.setCurrentRow(0)
    assert completer.pathFromIndex(source()) == 'Alice <alice@example.com>, '
