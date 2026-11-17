"""Actions groupées, suppression définitive, tout marquer comme lu et gestion des dossiers."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
import pytest
from mailclient.core.accounts import Account, Server
from mailclient.core.imap_client import IMAPClient, encode_folder, uid_set
from mailclient.core.parser import decode_folder
from mailclient.core.service import MailService, cache_key
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database


class FakeIMAP:
    """Enregistre les commandes ; répond comme un serveur conforme."""
    def __init__(self, capabilities=(b'IMAP4REV1', b'UIDPLUS', b'MOVE'), uids=b'3 4 9', unseen=b'4 9'):
        self.capabilities, self.commands = capabilities, []
        self.uids, self.unseen = uids, unseen

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def select(self, folder, readonly=True):
        self.commands.append(('select', folder, readonly))
        return 'OK', [b'3']

    def response(self, name):
        return name, [b'7']

    def uid(self, command, *args):
        self.commands.append((command.upper(),) + args)
        if command.upper() == 'SEARCH':
            return 'OK', [self.unseen if 'UNSEEN' in args else self.uids]
        return 'OK', [None]

    def expunge(self):
        self.commands.append(('EXPUNGE-GLOBAL',))
        return 'OK', [None]

    def create(self, name):
        self.commands.append(('create', name))
        return 'OK', [None]

    def rename(self, old, new):
        self.commands.append(('rename', old, new))
        return 'OK', [None]

    def delete(self, name):
        self.commands.append(('delete', name))
        return 'OK', [None]


def client_with(fake):
    account = Account('T', 't@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))
    client = IMAPClient(account, 'pw', None)
    client.open = lambda: fake
    return client


@pytest.mark.parametrize('name', ['Factures', 'Éléments envoyés', 'A & B', 'Projets/2026 été', '日本語'])
def test_folder_name_utf7_roundtrip(name):
    encoded = encode_folder(name)
    assert encoded.isascii()
    assert decode_folder(encoded) == name
    assert encode_folder('Éléments envoyés') == '&AMk-l&AOk-ments envoy&AOk-s'


def test_uid_set_validation():
    assert uid_set(['3', '4']) == '3,4'
    assert uid_set('12') == '12'
    for bad in (['0'], ['1 2'], ['1:*'], [], ['3', 'x']):
        with pytest.raises(ValueError):
            uid_set(bad)


def test_bulk_store_is_one_command():
    fake = FakeIMAP()
    client_with(fake).action('INBOX', ['3', '4', '9'], '7', 'read')
    assert ('STORE', '3,4,9', '+FLAGS.SILENT', '(\\Seen)') in fake.commands


def test_permanent_delete_uses_uid_expunge_only():
    fake = FakeIMAP()
    client_with(fake).action('Trash', '4,9', '7', 'delete')
    assert ('STORE', '4,9', '+FLAGS.SILENT', '(\\Deleted)') in fake.commands
    assert ('EXPUNGE', '4,9') in fake.commands
    assert ('EXPUNGE-GLOBAL',) not in fake.commands


def test_permanent_delete_without_uidplus_never_purges_globally():
    fake = FakeIMAP(capabilities=(b'IMAP4REV1',))
    client_with(fake).action('Trash', '4', '7', 'delete')
    assert ('STORE', '4', '+FLAGS.SILENT', '(\\Deleted)') in fake.commands
    assert not any(command[0].startswith('EXPUNGE') for command in fake.commands)


def test_empty_folder_and_mark_all_read():
    fake = FakeIMAP(capabilities=(b'IMAP4REV1',))
    client = client_with(fake)
    assert client.empty_folder('Trash') == 3
    assert ('STORE', '3,4,9', '+FLAGS.SILENT', '(\\Deleted)') in fake.commands
    assert ('EXPUNGE-GLOBAL',) in fake.commands  # Tout le dossier est vidé : purge globale acceptable.
    assert client.mark_all_read('INBOX') == 2
    assert ('STORE', '4,9', '+FLAGS.SILENT', '(\\Seen)') in fake.commands
    assert ('select', '"INBOX"', False) in fake.commands


def test_mark_all_read_on_empty_folder():
    fake = FakeIMAP(unseen=b'')
    assert client_with(fake).mark_all_read('INBOX') == 0
    assert not any(command[0] == 'STORE' for command in fake.commands)


def test_manage_folder_encodes_names():
    fake = FakeIMAP()
    client = client_with(fake)
    client.manage_folder('create', ' Été ')
    client.manage_folder('rename', '&AMk-t&AOk-', 'Hiver')
    client.manage_folder('delete', 'Hiver')
    assert fake.commands == [('create', '"&AMk-t&AOk-"'), ('rename', '"&AMk-t&AOk-"', '"Hiver"'), ('delete', '"Hiver"')]
    for bad in ('', 'a*b', 'x%', 'a\r\nb'):
        with pytest.raises(ValueError):
            client.manage_folder('create', bad)


def test_service_groups_by_folder_and_updates_cache(tmp_path, monkeypatch):
    db = Database(tmp_path / 'settings.db')
    account = Account('T', 't@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))
    db.save(account)
    server = 'imap.example.com:993:SSL/TLS'
    rows = [dict(account=account.id, folder=folder, uid=uid, uidvalidity='7', server=server, unread=True, starred=False)
            for folder, uid in (('INBOX', '3'), ('INBOX', '4'), ('Work', '5'))]
    db.cache_put('mailbox', cache_key(account.id, 'INBOX'), dict(account=account.id, pages={'0': [dict(r) for r in rows[:2]]}, total=2))
    calls = []
    class Client:
        def action(self, folder, uids, validity, action, target=''):
            calls.append((folder, uids, action))
        def mark_all_read(self, folder):
            return 2
    monkeypatch.setattr(MailService, 'client', lambda *args: Client())
    service = MailService(db, None, TLSPolicy(db))
    service.action(account, rows, 'read')
    assert sorted(calls) == [('INBOX', '3,4', 'read'), ('Work', '5', 'read')]
    assert not any(row['unread'] for row in service.state(account, 'INBOX')['pages']['0'])
    service.action(account, rows[:1], 'delete')
    state = service.state(account, 'INBOX')
    assert [row['uid'] for row in state['pages']['0']] == ['4'] and state['total'] == 1
    with pytest.raises(RuntimeError):
        service.action(account, [dict(rows[0], server='other:993:SSL/TLS')], 'read')


def test_main_window_multi_selection(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from mailclient.tests.test_ui import APP, process_until
    from mailclient.ui.main_window import MainWindow
    db = Database(tmp_path / 'settings.db')
    account = Account('T', 't@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))
    db.save(account)
    db.cache_put('folders', account.id, [['INBOX', 'Boîte de réception'], ['Trash', 'Corbeille']], account.id)
    server = 'imap.example.com:993:SSL/TLS'
    listing = {folder: [dict(uid=uid, uidvalidity='7', sender='x@example.com', subject=f'Sujet {uid}', date='', unread=True,
                             starred=False, attachment=False) for uid in ('3', '4', '9')] for folder in ('INBOX', 'Trash')}
    calls = []
    class Client:
        uidvalidity = '7'
        def folders(self):
            return [('INBOX', 'Boîte de réception'), ('Trash', 'Corbeille')]
        def messages(self, folder, page, query=''):
            return [dict(row) for row in listing[folder]], len(listing[folder])
        def action(self, folder, uids, validity, action, target=''):
            calls.append((folder, uids, action, target))
    monkeypatch.setattr(MailService, 'client', lambda *args: Client())
    window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    window.reload_accounts()
    assert process_until(lambda: not window.busy and window.table.count() == 3)
    window.table.selectAll()
    APP.processEvents()
    assert len(window.selected_rows()) == 3 and window.selected_row() is None
    assert not window.single_actions[0].isEnabled()  # Répondre exige un seul message.
    assert next(a for a in window.message_actions if a.text() == 'Étoiler').isEnabled()
    window.toggle_star()
    assert process_until(lambda: not window.busy and calls)
    assert calls[-1] == ('INBOX', '3,4,9', 'star', '')
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    window.table.selectAll()
    APP.processEvents()
    window.move('trash')
    assert process_until(lambda: not window.busy and len(calls) == 2)
    assert calls[-1] == ('INBOX', '3,4,9', 'move', 'Trash')
    # Dans la corbeille, Supprimer devient une suppression définitive confirmée.
    window.folders.setCurrentRow(1)
    assert process_until(lambda: not window.busy and window.table.count() == 3)
    assert window.folder_actions['empty'].isEnabled() and not window.folder_actions['rename'].isEnabled()
    window.table.item(0).setSelected(True)
    window.table.item(1).setSelected(True)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: QMessageBox.Cancel)
    window.move('trash')
    assert len(calls) == 2
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: QMessageBox.Yes)
    window.move('trash')
    assert process_until(lambda: not window.busy and len(calls) == 3)
    assert calls[-1] == ('Trash', '3,4', 'delete', '')
    window.reader.shutdown()
    window.close()
    from shiboken6 import delete
    delete(window)
