"""Notifications flottantes et annulation d’un déplacement de messages."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from mailclient.core.service import MailService
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database
from mailclient.tests.test_scheduler import ME, Vault


class Client:
    def __init__(self, found):
        self.found, self.calls = found, []

    def find_by_message_id(self, folder, message_id):
        self.calls.append(('find', folder, message_id))
        return self.found.get(message_id, ''), '9'

    def action(self, folder, uids, validity, action, target=''):
        self.calls.append(('action', folder, uids, validity, action, target))


def test_restore_finds_messages_by_message_id_and_moves_them_back(tmp_path, monkeypatch):
    db = Database(tmp_path / 'settings.db')
    client = Client({'<a@x>': '41', '<b@x>': '42', '<c@x>': '43'})
    monkeypatch.setattr(MailService, 'client', lambda *args: client)
    service = MailService(db, Vault(), TLSPolicy(db))
    rows = [dict(folder='INBOX', uid='1', message_id='<a@x>'), dict(folder='INBOX', uid='2', message_id='<b@x>'),
            dict(folder='Projets', uid='7', message_id='<c@x>'), dict(folder='INBOX', uid='3', message_id='')]
    assert service.restore(ME, rows, 'Trash') == 3  # Le message sans Message-ID ne peut pas être retrouvé.
    moves = [call for call in client.calls if call[0] == 'action']
    assert moves == [('action', 'Trash', '41,42', '9', 'move', 'INBOX'), ('action', 'Trash', '43', '9', 'move', 'Projets')]


@pytest.fixture
def window(tmp_path):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from mailclient.ui.main_window import MainWindow
    db = Database(tmp_path / 'settings.db')
    win = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    win.resize(1200, 800)
    yield win
    win.reader.shutdown()
    win.close()
    from shiboken6 import delete
    delete(win)


def test_toast_shows_action_and_runs_it_once(window):
    clicked = []
    window.notify('3 messages déplacés dans « Corbeille ».', 'Annuler', lambda: clicked.append(1))
    toast = window.toast
    assert not toast.isHidden() and toast.text.text() == '3 messages déplacés dans « Corbeille ».'
    assert toast.action.text() == 'Annuler' and not toast.action.isHidden()
    assert window.statusBar().currentMessage() == ''  # Pas de doublon dans la barre d’état.
    assert toast.y() + toast.height() <= toast.host.height()  # Dans la fenêtre, en bas.
    toast.action.click()
    toast.action.click()
    assert clicked == [1] and toast.isHidden()
    window.notify('Connexion impossible.', kind='error')
    assert toast.property('kind') == 'error' and toast.action.isHidden()


def test_undo_move_restores_and_reports(window, monkeypatch):
    from mailclient.tests.test_ui import process_until
    calls = []
    monkeypatch.setattr(window.service, 'restore', lambda account, group, target: (calls.append((group, target)), len(group))[1])
    monkeypatch.setattr(window, 'load_messages', lambda *args: None)
    moves = [(ME, [dict(uid='1'), dict(uid='2')], 'Trash')]
    window.undo_move(moves)
    assert process_until(lambda: not window.busy)
    assert calls == [([dict(uid='1'), dict(uid='2')], 'Trash')]
    assert window.toast.text.text() == 'Déplacement annulé : messages remis à leur place.'
    monkeypatch.setattr(window.service, 'restore', lambda account, group, target: 1)
    window.undo_move(moves)
    assert process_until(lambda: not window.busy)
    assert window.toast.text.text().startswith('Déplacement annulé pour 1 message sur 2')
