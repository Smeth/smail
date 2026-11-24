"""Recherche avancée : syntaxe, traduction IMAP, filtrage du cache et recherche dans tous les dossiers."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
import base64
from datetime import date
import pytest
from mailclient.core.accounts import Account, Server
from mailclient.core.imap_client import IMAPClient
from mailclient.core.search_query import imap_commands, matches, parse
from mailclient.core.service import MailService, cache_key
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database

ME = Account('Moi', 'moi@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))


def test_parse_operators_in_french_and_english():
    q = parse('de:léa from:paul à:chef to:"Équipe projet" objet:"compte rendu" a:pj est:nonlu est:étoilé '
              'après:2026-11-01 before:15/12/2026 budget "mot exact" inconnu:valeur')
    assert q.sender == ['léa', 'paul'] and q.to == ['chef', 'Équipe projet'] and q.subject == ['compte rendu']
    assert q.attachment and q.unread is True and q.starred
    assert q.since == date(2026, 11, 1) and q.before == date(2026, 12, 15)
    assert q.words == ['budget', 'mot exact', 'inconnu:valeur']
    assert parse('a:pj').attachment and parse('a:paul').to == ['paul']  # « a: » = « à: » sans accent.
    assert parse('est:lu').unread is False and parse('après:demain').words == ['après:demain']
    assert parse('   ').empty and not parse('x').empty


def test_imap_commands_quote_ascii_and_isolate_literals():
    commands = imap_commands(parse('de:léa objet:a"b\\c est:nonlu avant:2026-01-05 café thé'))
    first, *literals = commands
    assert first == (['UNDELETED', 'UNSEEN', 'BEFORE', '05-Jan-2026', 'SUBJECT', '"a\\"b\\\\c"'], None)  # Guillemet et \ échappés.
    assert literals == [(['TEXT'], 'café'.encode()), (['TEXT'], 'thé'.encode()), (['FROM'], 'léa'.encode())]
    assert imap_commands(parse('')) == [(['UNDELETED'], None)]


def row(**values):
    base = dict(uid='1', uidvalidity='7', account=ME.id, folder='INBOX', sender='Léa <lea@example.com>', recipients='moi@example.com',
                subject='Budget 2027', date='Mon, 23 Nov 2026 10:00:00 +0100', unread=True, starred=False, attachment=False)
    base.update(values)
    return base


@pytest.mark.parametrize('text,expected', [
    ('de:léa', True), ('de:paul', False), ('objet:budget', True), ('à:moi', True), ('à:chef', False),
    ('est:nonlu', True), ('est:lu', False), ('est:étoilé', False), ('a:pj', False),
    ('après:2026-11-23', True), ('après:2026-11-24', False), ('avant:2026-11-23', False), ('avant:2026-11-24', True),
    ('budget', True), ('contrat', False), ('LÉA budget', True)])
def test_offline_matching(text, expected):
    assert matches(parse(text), row()) is expected


def test_offline_words_use_message_content():
    q = parse('contrat signé')
    assert matches(q, row(), content=lambda: 'Le contrat est signé.')
    assert not matches(q, row(), content=lambda: 'Le contrat attend.')
    assert not matches(q, row(), content=lambda: None)  # Contenu absent du cache : en-têtes seulement.


class SearchSession:
    capabilities = (b'IMAP4REV1',)

    def __init__(self, results, structures=None):
        self.results, self.structures, self.calls, self.literal = results, structures or {}, [], None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def select(self, folder, readonly=True):
        return 'OK', [b'9']

    def response(self, name):
        return name, [b'7']

    def uid(self, command, *args):
        self.calls.append((command, args, self.literal))
        if command == 'search':
            key = 'literal' if self.literal else 'base'
            self.literal = None
            return 'OK', [self.results[key]]
        uids = args[0].split(',')
        if 'BODYSTRUCTURE' in args[1] and 'HEADER' not in args[1]:
            return 'OK', [f'{n} (UID {uid} BODYSTRUCTURE {self.structures.get(uid, "TEXT")})'.encode() for n, uid in enumerate(uids, 1)]
        response = []
        for n, uid in enumerate(uids, 1):
            response += [(f'{n} (UID {uid} FLAGS () BODYSTRUCTURE ("TEXT")'.encode(), f'Subject: {uid}\r\n\r\n'.encode()), b')']
        return 'OK', response


def test_imap_search_intersects_and_filters_attachments():
    session = SearchSession({'base': b'3 5 8 9', 'literal': b'5 8 12'}, {'8': '("APPLICATION" "PDF" ("NAME" "f.pdf"))'})
    client = IMAPClient(ME, 'pw', None)
    client.open = lambda: session
    rows, total = client.messages('INBOX', 0, 'café a:pj')
    assert total == 1 and [r['uid'] for r in rows] == ['8']
    searches = [call for call in session.calls if call[0] == 'search']
    assert searches[0][1] == (None, 'UNDELETED') and searches[1][1] == ('CHARSET', 'UTF-8', 'TEXT') and searches[1][2] == 'café'.encode()
    empty = SearchSession({'base': b'', 'literal': b'5'})
    client.open = lambda: empty
    assert client.messages('INBOX', 0, 'café') == ([], 0)
    assert len([c for c in empty.calls if c[0] == 'search']) == 1  # Aucun résultat : pas de commande suivante.


@pytest.fixture
def service(tmp_path, monkeypatch):
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    service = MailService(db, None, TLSPolicy(db))
    folders = [['INBOX', 'Boîte de réception'], ['Archives', 'Archives']]
    db.cache_put('folders', ME.id, folders, ME.id)
    cached = {'INBOX': [row(uid='3', subject='Budget', date='Tue, 24 Nov 2026 09:00:00 +0100'),
                        row(uid='2', subject='Divers', sender='Paul <paul@example.com>')],
              'Archives': [row(uid='9', folder='Archives', subject='Ancien budget', date='Mon, 02 Nov 2026 09:00:00 +0100', unread=False)]}
    for folder, rows in cached.items():
        db.cache_put('mailbox', cache_key(ME.id, folder), dict(account=ME.id, folder=folder, pages={'0': rows}, total=len(rows), uidvalidity='7'))
    db.cache_put('body', service.body_key(cached['INBOX'][1]), base64.b64encode(b'Subject: Divers\r\n\r\nLe budget est en annexe').decode(), ME.id)
    return service


def test_service_offline_structured_search(service):
    rows = service._known_rows(service.state(ME, 'INBOX'))
    assert [r['uid'] for r in service._search(rows, 'budget')] == ['3', '2']  # Objet, puis contenu en cache.
    assert [r['uid'] for r in service._search(rows, 'budget de:paul')] == ['2']
    assert [r['uid'] for r in service._search(rows, 'objet:budget après:2026-11-24')] == ['3']
    assert service._search(rows, 'a:pj') == []


def test_search_all_folders_offline_and_online(service, monkeypatch):
    result = service.search_all(ME, 'budget', cache_only=True)
    assert [(r['folder'], r['uid']) for r in result['rows']] == [('INBOX', '3'), ('INBOX', '2'), ('Archives', '9')]
    assert result['offline'] and not result['truncated']
    class Client:
        def folders(self):
            return [('INBOX', 'Boîte de réception'), ('Archives', 'Archives')]
        def messages(self, folder, page, query=''):
            uids = {'INBOX': ['30'], 'Archives': ['91', '90']}[folder]
            return [dict(uid=uid, uidvalidity='7', sender='x', subject='s', date=f'Mon, {int(uid) % 28 + 1:02d} Nov 2026 10:00:00 +0100',
                         unread=False, starred=False, attachment=False) for uid in uids], len(uids)
    monkeypatch.setattr(MailService, 'client', lambda *args: Client())
    online = service.search_all(ME, 'budget', limit=2)
    assert [(r['folder'], r['uid']) for r in online['rows']] == [('Archives', '91'), ('Archives', '90')]
    assert online['truncated'] and not online['offline'] and online['rows'][0]['server'] == 'imap.example.com:993:SSL/TLS'


def test_main_window_all_folders_scope(tmp_path, monkeypatch, service):
    from mailclient.tests.test_ui import process_until
    from mailclient.ui.main_window import MainWindow
    window = MainWindow(service.db, None, TLSPolicy(service.db), auto_load=False)
    window.offline.setChecked(True)
    window.reload_accounts()
    window.select_account(ME.id)
    assert process_until(lambda: not window.busy and window.table.count() > 0)
    window.result_scope.setCurrentIndex(1)
    window.search.setText('budget')
    window.new_search()
    assert process_until(lambda: not window.busy and window.table.count() == 3)
    previews = [window.table.item(i).data(256).preview for i in range(3)]
    assert previews[2].startswith('[Archives]') and 'tous les dossiers' in window.page_label.text()
    window.reader.shutdown()
    window.close()
    from shiboken6 import delete
    delete(window)
