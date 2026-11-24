"""Copie dans Envoyés des gros messages, nouvel essai sans doublon, alerte de taille, autocomplétion sans doublon."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
import base64
from unittest.mock import MagicMock
from mailclient.core import scheduler
from mailclient.core.imap_client import IMAPClient
from mailclient.tests.test_scheduler import ME, GMAIL, env  # noqa: F401  (fixture)


def test_append_allows_a_long_upload_then_restores_the_timeout(monkeypatch):
    imap = MagicMock()
    imap.sock.gettimeout.return_value = 20
    imap.append.return_value = ('OK', [b''])
    client = IMAPClient(ME, 'pw', None)
    client.open = lambda: imap
    imap.__enter__.return_value = imap
    client.append('Sent', b'x' * 10, False)
    assert [call.args[0] for call in imap.sock.settimeout.call_args_list] == [IMAPClient.APPEND_TIMEOUT, 20]


def sent_copy(env, local_id, account=ME, message_id='<m1@example.com>'):
    raw = f'Message-ID: {message_id}\r\nSubject: Gros\r\n\r\nCorps'.encode()
    env.db.cache_put('sent-copy', local_id, dict(id=local_id, account=account.id, raw=base64.b64encode(raw).decode(),
                                                 server_saved=False))
    return raw


def test_missing_sent_copies_are_retried_without_duplicates(env):
    sent_copy(env, 'deja')                                    # Le serveur l’avait enregistrée sans le confirmer.
    sent_copy(env, 'absente', message_id='<m2@example.com>')
    sent_copy(env, 'gmail', account=GMAIL)                    # Gmail garde lui-même ses envoyés.
    found = {'<m1@example.com>': ('41', '9'), '<m2@example.com>': ('', '9')}
    env.client.find_by_message_id = lambda folder, mid: (env.client.calls.append(('find', folder, mid)), found[mid])[1]
    assert scheduler.retry_sent_copies(env.service, [ME, GMAIL]) == 3
    assert [call for call in env.client.calls if call[0] == 'append'] == [('append', 'Sent', False)]  # Seule la copie absente.
    assert all(env.db.cache_get('sent-copy', key)['server_saved'] for key in ('deja', 'absente', 'gmail'))
    assert scheduler.retry_sent_copies(env.service, [ME, GMAIL]) == 0  # Plus rien à faire.


def test_sent_copy_retries_stop_after_a_few_failures(env):
    sent_copy(env, 'echec')
    def broken(folder, mid):
        raise OSError('coupure')
    env.client.find_by_message_id = broken
    for _ in range(scheduler.COPY_ATTEMPTS + 2):
        assert scheduler.retry_sent_copies(env.service, [ME]) == 0
    copy = env.db.cache_get('sent-copy', 'echec')
    assert copy['attempts'] == scheduler.COPY_ATTEMPTS and not copy['server_saved']


def test_large_message_asks_before_sending(env, monkeypatch):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from PySide6.QtWidgets import QMessageBox
    from mailclient.ui import compose_window
    from mailclient.ui.compose_window import ComposeWindow
    asked = []
    monkeypatch.setattr(compose_window, 'SIZE_WARNING', 100)
    monkeypatch.setattr(QMessageBox, 'warning', lambda parent, title, text, *rest: (asked.append(title), QMessageBox.No)[1])
    env.db.set_setting('undo_send_seconds', 0)
    composer = ComposeWindow(env.service, [ME], ME, dict(to='a@example.com', subject='Lourd', body='x' * 500))
    composer.send()
    assert asked == ['Message volumineux'] and env.sent == [] and not composer.busy  # Rien n’est parti.
    composer.saved_revision = composer.revision
    composer.close()


def test_choosing_a_suggestion_inserts_the_address_once():
    from mailclient.tests.test_ui import APP  # noqa: F401
    from PySide6.QtWidgets import QLineEdit
    from mailclient.ui.address_completer import AddressCompleter
    field = QLineEdit()
    completer = AddressCompleter(['kana smeth <kanasmeth@gmail.com>'], field)
    field.setCompleter(completer)
    field.setText('ka')  # Saisie de l’utilisateur.
    completer.setCompletionPrefix('ka')
    completer.setCurrentRow(0)
    index = completer.completionModel().mapToSource(completer.currentIndex())
    field.setText(completer.pathFromIndex(index))  # Qt insère d’abord la suggestion survolée…
    assert completer.pathFromIndex(index) == 'kana smeth <kanasmeth@gmail.com>, '  # … puis la valide : une seule fois.
    field.setText('alice@example.com, ka')
    completer.setCurrentRow(0)
    assert completer.pathFromIndex(index) == 'alice@example.com, kana smeth <kanasmeth@gmail.com>, '
