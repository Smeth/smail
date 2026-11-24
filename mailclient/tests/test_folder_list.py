"""Colonne des dossiers : ordre, icônes et non-lus."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from mailclient.ui.folder_list import COUNT_ROLE, kind, ordered


def test_system_folders_first_with_icons():
    folders = [('INBOX.Projets', 'Projets'), ('INBOX.Trash', 'Corbeille'), ('INBOX', 'Boîte de réception'),
               ('INBOX.Sent', 'Envoyés'), ('INBOX.spam', 'Spam'), ('INBOX.Archive', 'Archives'),
               ('INBOX.Drafts', 'Brouillons'), ('Clients', 'Clients'), ('Report&AOk-s', 'Reportés')]
    assert [label for _, label in ordered(folders)] == [
        'Boîte de réception', 'Brouillons', 'Envoyés', 'Archives', 'Spam', 'Corbeille', 'Reportés', 'Projets', 'Clients']
    assert [kind(*folder)[1] for folder in ordered(folders)][:7] == [
        'inbox', 'file-pen-line', 'send', 'archive', 'shield-alert', 'trash-2', 'clock']
    assert kind('Factures', 'Factures') == (10, 'folder')


def test_status_reads_unseen():
    from unittest.mock import MagicMock
    from mailclient.core.imap_client import IMAPClient
    from mailclient.tests.test_scheduler import ME
    imap = MagicMock()
    imap.__enter__.return_value = imap
    imap.capabilities = (b'CONDSTORE',)
    imap.status.return_value = ('OK', [b'"INBOX" (MESSAGES 12 UIDNEXT 40 UIDVALIDITY 7 UNSEEN 3 HIGHESTMODSEQ 99)'])
    client = IMAPClient(ME, 'pw', None)
    client.open = lambda: imap
    assert client.folder_status(['INBOX'])['INBOX']['UNSEEN'] == 3
    assert 'UNSEEN' in imap.status.call_args.args[1]


def test_window_shows_unread_counts(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import APP, process_until  # noqa: F401
    from mailclient.core.service import MailService
    from mailclient.core.tls_policy import TLSPolicy
    from mailclient.storage.database import Database
    from mailclient.tests.test_scheduler import ME, Client
    from mailclient.ui.main_window import MainWindow
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    client = Client([('Projets', 'Projets'), ('INBOX', 'Boîte de réception'), ('Sent', 'Envoyés')])
    client.messages = lambda folder, page, query='': ([], 0)
    monkeypatch.setattr(MailService, 'client', lambda *args: client)
    db.cache_put('unread', ME.id, {'INBOX': 4, 'Projets': 0}, ME.id)
    window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    try:
        window.reload_accounts()
        window.select_account(ME.id)
        assert process_until(lambda: not window.busy and window.folders.count() == 3)
        assert [window.folders.item(i).text() for i in range(3)] == ['Boîte de réception', 'Envoyés', 'Projets']
        assert window.folders.item(0).data(COUNT_ROLE) == 4 and window.folders.item(2).data(COUNT_ROLE) == 0
        assert not window.folders.item(0).icon().isNull()
        db.cache_put('unread', ME.id, {'INBOX': 1}, ME.id)  # Nouvelle synchronisation.
        window.update_folder_counts()
        assert window.folders.item(0).data(COUNT_ROLE) == 1
        window.folders.grab()  # Dessin de la pastille sans erreur.
    finally:
        window.reader.shutdown()
        window.close()
        from shiboken6 import delete
        delete(window)
