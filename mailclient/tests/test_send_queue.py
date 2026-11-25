"""Envoi en arrière-plan : la rédaction se ferme, la progression s’affiche dans la fenêtre principale."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
import smtplib
import threading
from unittest.mock import MagicMock
import pytest
from mailclient.core import scheduler, smtp_client
from mailclient.core.oauth import OAuth
from mailclient.core.service import MailService
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database
from mailclient.tests.test_scheduler import ME, Client


def test_upload_is_reported_in_chunks_then_server_check():
    events, written = [], []
    client = MagicMock()
    client.sock.sendall.side_effect = written.append
    original = client.send
    smtp_client.report_upload(client, lambda *event: events.append(event))
    client.send(b'MAIL FROM:<a@b.fr>\r\n')  # Commande : inchangée.
    original.assert_called_once_with(b'MAIL FROM:<a@b.fr>\r\n')
    payload = b'x' * (smtp_client.UPLOAD_CHUNK * 2 + 10) + b'\r\n.\r\n'
    client.send(payload)
    assert b''.join(written) == payload and len(written) == 3
    uploads = [event for event in events if event[0] == 'upload']
    assert [done for _, done, _ in uploads] == [smtp_client.UPLOAD_CHUNK, smtp_client.UPLOAD_CHUNK * 2, len(payload)]
    assert events[-1] == ('verify', len(payload), len(payload))
    client.sock.sendall.side_effect = ConnectionResetError()
    with pytest.raises(smtplib.SMTPServerDisconnected):
        client.send(payload)
    client.close.assert_called_once()


@pytest.fixture
def window(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import APP  # noqa: F401  (QApplication, même si ce fichier est lancé seul)
    from mailclient.ui.main_window import MainWindow
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    db.set_setting('conversation_view', False)
    imap = Client()
    monkeypatch.setattr(MailService, 'client', lambda *args: imap)
    monkeypatch.setattr(OAuth, 'credential', lambda self, account, protocol='imap': 'pw')
    state = type('State', (), {})()
    state.sent, state.release, state.error = [], threading.Event(), None
    state.release.set()
    def fake_send(account, password, tls, message, recipients, progress=None):
        progress('connect', 0, 0)
        progress('upload', 6_100_000, 13_400_000)
        state.release.wait(5)  # Le test inspecte l’affichage pendant l’envoi.
        progress('verify', 13_400_000, 13_400_000)
        if state.error:
            raise state.error
        state.sent.append(message['Subject'])
        return {}
    monkeypatch.setattr(scheduler, 'send_message', fake_send)
    win = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    win.reload_accounts()
    win.state, win.imap = state, imap
    yield win
    state.release.set()
    win.reader.shutdown()
    win.close()
    from shiboken6 import delete
    delete(win)


def compose(window, subject):
    from mailclient.ui.compose_window import ComposeWindow
    composer = ComposeWindow(window.service, [ME], ME, dict(to='a@example.com', subject=subject, body='Bonjour'), parent=window)
    window.composers.add(composer)
    composer.show()
    return composer


def test_send_closes_composer_and_shows_progress(window):
    from mailclient.tests.test_ui import process_until
    window.database.set_setting('undo_send_seconds', 0)
    window.state.release.clear()
    composer = compose(window, 'Rapport')
    composer.send()
    assert not composer.isVisible()  # Aucune attente devant la rédaction.
    queue = window.send_queue
    assert process_until(lambda: 'Mo' in queue.text.text())
    assert queue.text.text() == 'Envoi de « Rapport » — 6,1 / 13,4 Mo' and not queue.widget.isHidden()
    assert queue.bar.value() == 455 and queue.bar.maximum() == 1000
    assert [item['status'] for item in scheduler.outbox(window.database)] == ['sending']  # Avant SMTP.
    window.state.release.set()
    assert process_until(lambda: not queue.busy())
    assert window.state.sent == ['Rapport'] and scheduler.outbox(window.database) == []
    assert window.toast.text.text() == 'Message « Rapport » envoyé.' and not window.toast.isHidden()
    assert queue.widget.isHidden() and ('append', 'Sent', False) in window.imap.calls  # Copie dans Envoyés.
    assert window.database.cache_get('draft', composer.id) is None


def test_undo_delay_then_cancel_reopens_draft(window):
    from mailclient.tests.test_ui import process_until
    window.database.set_setting('undo_send_seconds', 30)
    composer = compose(window, 'Annulable')
    composer.send()
    assert not composer.isVisible()
    queue = window.send_queue
    assert queue.text.text().startswith('Envoi de « Annulable » dans') and not queue.cancel_button.isHidden()
    queue.cancel()
    assert scheduler.outbox(window.database) == [] and window.state.sent == []
    reopened = [c for c in window.composers if c.isVisible()]
    assert len(reopened) == 1 and reopened[0].subject.text() == 'Annulable' and reopened[0].id == composer.id
    assert window.database.cache_get('draft', composer.id)['subject'] == 'Annulable'
    assert queue.widget.isHidden()
    reopened[0].saved_revision = reopened[0].revision
    reopened[0].close()


def test_quitting_during_undo_delay_sends_first(window):
    from mailclient.tests.test_ui import process_until
    window.database.set_setting('undo_send_seconds', 30)
    compose(window, 'Avant fermeture').send()
    assert window.send_queue.flush_for_quit()  # Il faut attendre la fin de l’envoi.
    assert process_until(lambda: not window.send_queue.busy())
    assert window.state.sent == ['Avant fermeture'] and not window.send_queue.flush_for_quit()


@pytest.mark.parametrize('error, status, title', [
    (TimeoutError(), 'failed', 'Échec de l’envoi de « Rapport »'),
    (smtp_client.DeliveryUncertain('Le serveur d’envoi n’a pas confirmé'), 'uncertain', 'Envoi incertain de « Rapport »'),
], ids=['echec', 'incertain'])
def test_failure_is_kept_and_shown(window, error, status, title):
    from mailclient.tests.test_ui import process_until
    window.database.set_setting('undo_send_seconds', 0)
    window.state.error = error
    compose(window, 'Rapport').send()
    queue = window.send_queue
    assert process_until(lambda: not queue.busy() and queue.alert)
    assert [item['status'] for item in scheduler.outbox(window.database)] == [status]
    assert queue.text.text() == title and not queue.show_button.isHidden() and queue.bar.isHidden()
    queue.dismiss()
    assert queue.widget.isHidden()
    queue.tick()
    assert window.state.sent == []  # Jamais renvoyé automatiquement.


def test_offline_messages_wait_for_reconnection(window):
    from mailclient.tests.test_ui import process_until
    window.database.set_setting('undo_send_seconds', 0)
    window.offline.blockSignals(True)
    window.offline.setChecked(True)
    window.offline.blockSignals(False)
    queue = window.send_queue
    queue.enqueue(ME, dict(to='a@example.com', cc='', bcc='', subject='Plus tard', body='x', mail_html='',
                           reply_id='', references=''), [], 0, 'attente')
    assert queue.text.text() == '« Plus tard » partira à la reconnexion' and not queue.busy()
    assert not queue.flush_for_quit()  # Hors ligne : rien ne bloque la fermeture, l’envoi attend le prochain démarrage.
    window.offline.blockSignals(True)
    window.offline.setChecked(False)
    window.offline.blockSignals(False)
    queue.tick()
    assert process_until(lambda: window.state.sent == ['Plus tard'])
