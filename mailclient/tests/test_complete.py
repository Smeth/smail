"""Régressions des phases 3 et 4, sans compte ni service externe."""
import base64
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen
import pytest
from mailclient.core.accounts import Account, Server
from mailclient.core.imap_client import IMAPClient
from mailclient.core.smtp_client import build_message, addresses, send_message
from mailclient.core.parser import Attachment, Mail
from mailclient.core.service import MailService, cache_key
from mailclient.core.oauth import OAuth, xoauth2
from mailclient.storage.database import Database

class Vault:
    def __init__(self):
        self.data = {}
    def get(self, key):
        if key not in self.data:
            raise RuntimeError('Secret absent')
        return self.data[key]
    def set(self, key, value):
        self.data[key] = value

@pytest.fixture
def account():
    return Account('André', 'a@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))

def test_bcc_only_in_envelope_and_attachment_encoding(account):
    message, recipients = build_message(account, 'Béa <b@example.com>', 'c@example.com', 'secret@example.com',
                                         'Réunion', 'Café !', [Attachment('fichier.bin', 'application/octet-stream', b'\x00\xff')])
    raw = message.as_bytes()
    assert recipients == ['b@example.com', 'c@example.com', 'secret@example.com']
    assert b'Bcc:' not in raw and b'secret@example.com' not in raw
    assert message.get_body(preferencelist=('plain',)).get_content().strip() == 'Café !'
    assert next(message.iter_attachments()).get_payload(decode=True) == b'\x00\xff'

@pytest.mark.parametrize('value', ['a@example.com\r\nBcc: bad@example.com', 'bad', 'a@example.com\x00', 'x@y.com\t'])
def test_recipient_injection_rejected(value):
    with pytest.raises(ValueError):
        addresses(value)

def test_subject_injection_rejected(account):
    with pytest.raises(ValueError):
        build_message(account, 'a@example.com', '', '', 'Hi\nBcc: x@y.com', 'body')

def test_no_smtp_retry_after_uncertain_delivery(account, monkeypatch):
    from mailclient.core.smtp_client import DeliveryUncertain
    client = MagicMock()
    client.send_message.side_effect = ConnectionResetError()
    monkeypatch.setattr('mailclient.core.smtp_client.open_connection', lambda *args: client)
    message, recipients = build_message(account, 'b@example.com', '', '', 'Test', 'Bonjour')
    with pytest.raises(DeliveryUncertain):
        send_message(account, 'secret', None, message, recipients)
    assert client.send_message.call_count == 1
    client.close.assert_called_once()

@pytest.mark.parametrize('capabilities,expected', [((b'MOVE',), ['MOVE']), ((b'UIDPLUS',), ['COPY', 'STORE', 'EXPUNGE']), ((), ['COPY', 'STORE'])])
def test_move_never_expunge_other_messages(account, monkeypatch, capabilities, expected):
    client = MagicMock()
    client.__enter__.return_value = client
    client.select.return_value = ('OK', [b'2'])
    client.response.return_value = ('UIDVALIDITY', [b'7'])
    client.capabilities = capabilities
    client.uid.return_value = ('OK', [])
    monkeypatch.setattr(IMAPClient, 'open', lambda self: client)
    IMAPClient(account, '', None).action('INBOX', '12', '7', 'move', 'Trash')
    assert [call.args[0] for call in client.uid.call_args_list] == expected
    client.expunge.assert_not_called()

def test_uidvalidity_change_prevents_modification(account, monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.select.return_value = ('OK', [b'2'])
    client.response.return_value = ('UIDVALIDITY', [b'new'])
    monkeypatch.setattr(IMAPClient, 'open', lambda self: client)
    with pytest.raises(RuntimeError, match='recréé'):
        IMAPClient(account, '', None).action('INBOX', '12', 'old', 'read')
    client.uid.assert_not_called()

def test_cache_encryption_migration_and_missing_key(tmp_path):
    vault = Vault()
    path = tmp_path / 'settings.db'
    db = Database(path, vault)
    secret_content = 'CONFIDENTIEL_927651'
    db.cache_put('draft', 'draft1', dict(body=secret_content))
    assert secret_content.encode() in path.read_bytes()
    db.encrypt_cache(True)
    assert secret_content.encode() not in path.read_bytes()
    reopened = Database(path, vault)
    assert reopened.cache_get('draft', 'draft1')['body'] == secret_content
    reopened.encrypt_cache(False)
    assert reopened.cache_get('draft', 'draft1')['body'] == secret_content
    reopened.encrypt_cache(True)
    vault.data.clear()
    with pytest.raises(RuntimeError, match='Clé'):
        Database(path, vault).cache_get('draft', 'draft1')

def test_offline_folders_messages_body_and_search(account, tmp_path, monkeypatch):
    vault = Vault()
    db = Database(tmp_path / 'settings.db', vault)
    service = MailService(db, vault, None)
    client = SimpleNamespace(uidvalidity='7', folders=lambda: [('INBOX', 'Réception')],
        messages=lambda *args: ([dict(uid='12', uidvalidity='7', sender='a@example.com', subject='Bonjour', date='', unread=True, attachment=False)], 1),
        message_raw=lambda *args: b'Subject: Bonjour\r\n\r\nContenu confidentiel')
    monkeypatch.setattr(service, 'client', lambda account: client)
    assert not service.folders(account)[1]
    row = service.messages(account, 'INBOX')['rows'][0]
    assert service.message(account, row).text == 'Contenu confidentiel'
    monkeypatch.setattr(service, 'client', lambda account: (_ for _ in ()).throw(OSError()))
    assert service.folders(account)[1]
    assert service.messages(account, 'INBOX')['offline']
    assert service.messages(account, 'INBOX', query='confidentiel')['total'] == 1
    assert service.message(account, row, True).subject == 'Bonjour'
    with pytest.raises(RuntimeError, match='pas encore'):
        service.message(account, dict(row, uidvalidity='8'), True)

def test_unified_routes_accounts_and_sorts_dates(tmp_path, account):
    other = Account('Autre', 'other@example.com', account.imap, account.smtp)
    db = Database(tmp_path / 'settings.db')
    service = MailService(db, Vault(), None)
    for acc,date in [(account, 'Mon, 01 Jan 2024 10:00:00 +0000'), (other, 'Tue, 02 Jan 2024 10:00:00 +0000')]:
        row = dict(account=acc.id, folder='INBOX', uid='1', uidvalidity='7', subject='Test', sender='test@example.com', date=date)
        db.cache_put('mailbox', cache_key(acc.id, 'INBOX'), dict(pages={'0': [row]}))
    rows = service.unified([account, other])['rows']
    assert [row['account'] for row in rows] == [other.id, account.id]

def test_oauth_pkce_state_and_loopback(account, monkeypatch):
    account.auth_method, account.oauth_client_id = 'google', 'test-client'
    vault = Vault()
    oauth = OAuth(vault)
    authorization = {}
    requests = []
    browser_thread = None
    def browser(url):
        nonlocal browser_thread
        query = parse_qs(urlparse(url).query)
        authorization.update(query)
        def callback():
            from urllib.error import HTTPError
            redirect = query['redirect_uri'][0]
            try:
                urlopen(redirect + '?state=wrong&code=attack', timeout=3)
            except HTTPError as error:
                assert error.code == 400
            with urlopen(redirect + '?state=' + query['state'][0] + '&code=valid', timeout=3) as response:
                assert response.status == 200
        browser_thread = threading.Thread(target=callback)
        browser_thread.start()
        return True
    def exchange(acc, values):
        import hashlib
        challenge = base64.urlsafe_b64encode(hashlib.sha256(values['code_verifier'].encode()).digest()).rstrip(b'=').decode()
        assert challenge == authorization['code_challenge'][0]
        assert values['code'] == 'valid'
        assert values['redirect_uri'].startswith('http://127.0.0.1:')
        requests.append(values)
        return dict(access_token='token', refresh_token='refresh', expires_at=time.time()+3600,
                    client_id=account.oauth_client_id, provider='google', email=account.email)
    monkeypatch.setattr('mailclient.core.oauth.webbrowser.open', browser)
    monkeypatch.setattr(oauth, '_request', exchange)
    oauth.authorize(account)
    browser_thread.join(timeout=3)
    assert len(requests) == 1
    assert oauth.credential(account) == 'token'
    assert oauth.is_authorized(account)

def test_oauth_refresh_uses_vault(account, monkeypatch):
    account.auth_method, account.oauth_client_id = 'microsoft', 'client'
    vault = Vault()
    vault.set(account.id + ':oauth', json.dumps(dict(access_token='old', refresh_token='refresh', expires_at=0,
              client_id='client', provider='microsoft', email=account.email)))
    oauth = OAuth(vault)
    def exchange(acc, values):
        assert values == dict(grant_type='refresh_token', refresh_token='refresh')
        return dict(access_token='new', expires_at=time.time()+3600)
    monkeypatch.setattr(oauth, '_request', exchange)
    assert oauth.credential(account) == 'new'
    assert json.loads(vault.get(account.id + ':oauth'))['refresh_token'] == 'refresh'
    assert xoauth2(account.email, 'new').endswith(b'\x01\x01')
    with pytest.raises(ValueError):
        xoauth2(account.email, 'bad\x01token')

def test_windows_long_tokens_are_split_inside_vault(monkeypatch):
    from mailclient.storage.secrets import Secrets
    values = {}
    def store(service, key, value):
        assert len(value.encode('utf-16-le')) <= 2560
        values[key] = value
    backend = SimpleNamespace(get_password=lambda service,key: values.get(key), set_password=store,
                              delete_password=lambda service,key: values.pop(key))
    vault = Secrets()
    monkeypatch.setattr(vault, '_backend', lambda: backend)
    token = 'x' * 9000
    vault.set('oauth', token)
    assert vault.get('oauth') == token
    vault.set('oauth', 'new')
    assert vault.get('oauth') == 'new'
    assert list(values) == ['oauth']

def test_real_smtp_session_keeps_bcc_private(account):
    import socketserver
    capture = dict(recipients=[], data=b'')
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b'220 localhost test\r\n')
            while True:
                line = self.rfile.readline()
                if not line:
                    return
                command = line.upper()
                if command.startswith(b'EHLO'):
                    self.wfile.write(b'250-localhost\r\n250-AUTH PLAIN\r\n250 SIZE 999999\r\n')
                elif command.startswith(b'AUTH'):
                    self.wfile.write(b'235 Authenticated\r\n')
                elif command.startswith(b'RCPT'):
                    capture['recipients'].append(line)
                    self.wfile.write(b'250 OK\r\n')
                elif command.startswith(b'DATA'):
                    self.wfile.write(b'354 Start data\r\n')
                    data = []
                    while True:
                        item = self.rfile.readline()
                        if item == b'.\r\n' or not item:
                            break
                        data.append(item)
                    capture['data'] = b''.join(data)
                    self.wfile.write(b'250 Accepted\r\n')
                else:
                    self.wfile.write(b'250 OK\r\n')
    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True
    with Server(('127.0.0.1', 0), Handler) as server:
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
        thread.start()
        try:
            account.smtp = type(account.smtp)('127.0.0.1', server.server_address[1], 'Aucun')
            message, recipients = build_message(account, 'b@example.com', '', 'secret@example.com', 'Test', 'Bonjour')
            assert send_message(account, 'fake-test-password', None, message, recipients) == {}
            assert any(b'secret@example.com' in line for line in capture['recipients'])
            assert b'secret@example.com' not in capture['data']
            assert b'Bonjour' in capture['data']
        finally:
            server.shutdown()
            thread.join(timeout=2)

def test_idle_reads_coalesced_events_and_sends_done(account, monkeypatch):
    import socket
    left, right = socket.socketpair()
    commands = []
    class Client:
        capabilities = (b'IDLE',)
        sock = left
        file = left.makefile('rb')
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.file.close()
            self.sock.close()
        def select(self, *args, **kwargs):
            return 'OK', [b'1']
        def response(self, *args):
            return 'UIDVALIDITY', [b'7']
        def send(self, data):
            self.sock.sendall(data)
        def readline(self):
            return self.file.readline()
    def server():
        with right, right.makefile('rb') as stream:
            commands.append(stream.readline())
            right.sendall(b'+ idling\r\n* 1 EXISTS\r\n* 2 EXISTS\r\n')
            commands.append(stream.readline())
            right.sendall(b'SMAILIDLE OK completed\r\n')
    thread = threading.Thread(target=server)
    thread.start()
    monkeypatch.setattr(IMAPClient, 'open', lambda self: Client())
    assert IMAPClient(account, '', None).idle_wait(threading.Event(), seconds=2) == (True, True)
    thread.join(timeout=3)
    assert commands == [b'SMAILIDLE IDLE\r\n', b'DONE\r\n']

def test_search_is_utf8_literal_not_command_interpolation(account, monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.select.return_value = ('OK', [b'0'])
    client.response.return_value = ('UIDVALIDITY', [b'7'])
    client.uid.return_value = ('OK', [b''])
    monkeypatch.setattr(IMAPClient, 'open', lambda self: client)
    # Texte ASCII : chaîne IMAP entre guillemets, échappée ; tentative d’injection neutralisée.
    assert IMAPClient(account, '', None).messages('INBOX', 0, 'x" OR ALL "y') == ([], 0)
    client.uid.assert_called_once_with('search', None, 'UNDELETED', 'TEXT', '"x\\""', 'TEXT', '"OR"', 'TEXT', '"ALL"', 'TEXT', '"\\"y"')
    # Texte accentué : littéral UTF-8, jamais interpolé dans la commande ; résultats croisés.
    client.uid.reset_mock()
    client.uid.return_value = ('OK', [b'5'])
    IMAPClient(account, '', None).messages('INBOX', 0, 'café test')
    searches = [call.args for call in client.uid.call_args_list if call.args[0] == 'search']
    assert searches == [('search', None, 'UNDELETED', 'TEXT', '"test"'), ('search', 'CHARSET', 'UTF-8', 'TEXT')]
    assert client.literal == 'café'.encode('utf-8')

def test_sync_only_notifies_new_uids_after_first_sync(account, tmp_path, monkeypatch):
    db = Database(tmp_path / 'settings.db')
    service = MailService(db, Vault(), None)
    ids = ['1']
    def snapshot(folder, limit, cancelled, known=None):
        rows = [dict(uid=uid, uidvalidity='7', sender='a@example.com', subject='Bonjour', date='', unread=True, attachment=False) for uid in reversed(ids)]
        bodies = {uid: b'Subject: Bonjour\r\n\r\nTexte' for uid in ids}
        return rows, len(ids), bodies, '7'
    client = SimpleNamespace(folders=lambda: [('INBOX', 'Réception')], snapshot=snapshot)
    monkeypatch.setattr(service, 'client', lambda account: client)
    assert service.sync_account(account, threading.Event()) == 0
    ids.append('2')
    assert service.sync_account(account, threading.Event()) == 1
    assert service.sync_account(account, threading.Event()) == 0
