import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
import time
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread
from mailclient.storage.database import Database
from mailclient.core.tls_policy import TLSPolicy
from mailclient.core.sync import Runner
from mailclient.ui.account_dialog import AccountDialog
from mailclient.ui.main_window import MainWindow

APP = QApplication.instance() or QApplication([])

@pytest.fixture(autouse=True)
def close_webengine_readers():
    yield
    from mailclient.ui.mail_view import MailView
    for widget in APP.allWidgets():
        if isinstance(widget, MailView):
            widget.shutdown()
    APP.processEvents()

class FakeSecrets:
    def set(self, *args):
        pass

def test_ui_cleartext_confirmation_and_ports(tmp_path):
    db = Database(tmp_path / 'settings.db')
    dialog = AccountDialog(db, FakeSecrets(), TLSPolicy(db))
    dialog.name.setText('Compte')
    dialog.address.setText('a@gmail.com')
    dialog.password.setText('test-secret')
    dialog.preset()
    assert dialog.servers['smtp'][2].value() == 587
    assert dialog.servers['imap'][2].value() == 993
    dialog.servers['imap'][1].setCurrentIndex(2)
    assert dialog.servers['imap'][2].value() == 143
    import pytest
    with pytest.raises(ValueError, match='confirmer'):
        dialog.values()
    dialog.confirm.setChecked(True)
    assert dialog.values()[0].imap.mode == 'Aucun'
    dialog.servers['imap'][2].setValue(1143)
    assert dialog.values()[0].imap.port == 1143
    window = MainWindow(db, FakeSecrets(), TLSPolicy(db))
    window.show()
    APP.processEvents()
    assert window.isVisible()
    window.close()

def test_network_task_runs_off_main_and_callback_on_main(tmp_path):
    db = Database(tmp_path / 'settings.db')
    window = MainWindow(db, FakeSecrets(), TLSPolicy(db))
    runner = Runner(window, TLSPolicy(db))
    results = []
    runner.run(lambda: QThread.currentThread() == APP.thread(),
               lambda result: results.append((result, QThread.currentThread() == APP.thread())),
               lambda error: results.append(error))
    deadline = time.monotonic() + 5
    while not results and time.monotonic() < deadline:
        APP.processEvents()
        time.sleep(0.01)
    assert results == [(False, True)]

def test_certificate_dialog_defaults_to_cancel():
    from mailclient.core.tls_policy import CertificateAlert
    from mailclient.ui.cert_dialog import CertificateDialog
    from PySide6.QtWidgets import QDialogButtonBox
    dialog = CertificateDialog(CertificateAlert('account', 'imap:host', 'ab' * 32,
                                               'CN=Test', 'dates', 'auto-signé'))
    buttons = dialog.findChild(QDialogButtonBox).buttons()
    assert next(button for button in buttons if button.isDefault()).text() == 'Annuler'
    assert not dialog.remember.isChecked()

def test_reader_blocks_remote_images_until_explicit_click():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from mailclient.ui.mail_view import MailView
    from mailclient.core.parser import Mail
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.end_headers()
            import base64
            self.wfile.write(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='))
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    reader = MailView()
    reader.show()
    def process_until(predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            APP.processEvents()
            time.sleep(0.01)
        return predicate()
    try:
        loaded = []
        reader.web.loadFinished.connect(lambda ok: loaded.append(ok))
        root = f'http://127.0.0.1:{server.server_port}'
        reader.display(Mail('a', 'b', 'c', 'd', html=f'<img src="{root}/pixel"><script>fetch("{root}/script")</script>'))
        assert process_until(lambda: bool(loaded))
        assert not requests
        assert not reader.web.settings().testAttribute(QWebEngineSettings.JavascriptEnabled)
        reader.show_images()
        assert process_until(lambda: '/pixel' in requests)
        assert '/script' not in requests
        loaded.clear()
        reader.display(Mail('a', 'b', 'next', 'd', html=f'<img src="{root}/blocked">'))
        assert process_until(lambda: bool(loaded))
        assert not reader.interceptor.remote
        assert '/blocked' not in requests
    finally:
        reader.web.stop()
        reader.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

def test_save_attachment_and_executable_warning(tmp_path, monkeypatch):
    from mailclient.ui.mail_view import MailView
    from mailclient.core.parser import Mail, Attachment
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    destination = tmp_path / 'test.exe'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(destination), ''))
    reader = MailView()
    reader.display(Mail('', '', '', '', attachments=[Attachment('test.exe', 'application/octet-stream', b'payload')]))
    reader.attachments.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: QMessageBox.Cancel)
    reader.save_attachment()
    assert not destination.exists()
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: QMessageBox.Save)
    reader.save_attachment()
    assert destination.read_bytes() == b'payload'
    reader.close()

def process_until(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        APP.processEvents()
        time.sleep(0.01)
    return predicate()

def test_draft_autosave_and_reopen(tmp_path):
    from mailclient.ui.compose_window import ComposeWindow
    from mailclient.core.service import MailService
    from mailclient.core.accounts import Account, Server
    from mailclient.tests.test_complete import Vault
    db = Database(tmp_path / 'settings.db')
    service = MailService(db, Vault(), TLSPolicy(db))
    account = Account('Test', 'a@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))
    composer = ComposeWindow(service, [account])
    composer.show()
    composer.to.setText('b@example.com')
    composer.subject.setText('Brouillon hors ligne')
    composer.body.setPlainText('Contenu sauvegardé')
    composer.save_draft()
    assert process_until(lambda: not composer.saving)
    draft = db.cache_get('draft', composer.id)
    assert draft['body'] == 'Contenu sauvegardé'
    composer.close()
    reopened = ComposeWindow(service, [account], draft=draft)
    assert reopened.to.text() == 'b@example.com'
    assert reopened.subject.text() == 'Brouillon hors ligne'
    reopened.close()
    assert process_until(lambda: not reopened.saving)

def test_reply_all_excludes_self_and_keeps_threads():
    from mailclient.ui.compose_window import reply_fields
    from mailclient.core.parser import Mail
    from mailclient.core.accounts import Account, Server
    account = Account('Test', 'me@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465), signature='Signature')
    mail = Mail('sender@example.com', 'me@example.com, friend@example.com', 'Sujet', 'date', text='Texte',
                cc='friend@example.com, other@example.com', reply_to='reply@example.com', message_id='<id@example.com>')
    fields = reply_fields(mail, account, 'reply_all')
    assert fields['to'] == 'reply@example.com'
    assert 'me@example.com' not in fields['cc']
    assert fields['cc'].count('friend@example.com') == 1
    assert fields['reply_id'] == '<id@example.com>'
    assert 'Signature' in fields['body'] and '> Texte' in fields['body']

def test_sent_copy_certificate_retry_never_resends_smtp(tmp_path, monkeypatch):
    from mailclient.ui.compose_window import ComposeWindow
    from mailclient.core.service import MailService
    from mailclient.core.accounts import Account, Server
    from mailclient.core.tls_policy import CertificateAlert
    from mailclient.tests.test_complete import Vault
    from PySide6.QtWidgets import QDialog
    db = Database(tmp_path / 'settings.db')
    account = Account('Test', 'a@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))
    vault = Vault()
    vault.set(account.id, 'fake-test-password')
    service = MailService(db, vault, TLSPolicy(db))
    sent, appended = [], []
    monkeypatch.setattr('mailclient.ui.compose_window.send_message', lambda *args: sent.append(args) or {})
    monkeypatch.setattr(service, 'folders', lambda *args: ([('Sent', 'Envoyés')], False))
    class Client:
        def append(self, *args):
            appended.append(args)
            if len(appended) == 1:
                raise CertificateAlert(account.id, 'imap:host', 'ab'*32, 'issuer', 'dates', 'raison')
    monkeypatch.setattr(service, 'client', lambda *args: Client())
    monkeypatch.setattr('mailclient.ui.cert_dialog.CertificateDialog.exec', lambda self: QDialog.Accepted)
    composer = ComposeWindow(service, [account], fields=dict(to='b@example.com', subject='Test', body='Bonjour'))
    composer.show()
    composer.send()
    assert process_until(lambda: composer.delivered and not composer.isVisible())
    assert len(sent) == 1 and len(appended) == 2
    assert db.cache_get('draft', composer.id) is None

def test_large_html_is_served_in_memory():
    from mailclient.ui.mail_view import MailView
    from mailclient.core.parser import Mail
    reader = MailView()
    reader.show()
    reader.display(Mail('', '', '', '', html='<p>' + 'é'*360000 + 'FIN-DU-MESSAGE</p>'))
    assert reader.web.url().scheme() in {'', 'smail'}
    result = []
    reader.web.loadFinished.connect(lambda ok: reader.web.page().toPlainText(lambda value: result.append(value)) if ok else None)
    assert process_until(lambda: any('FIN-DU-MESSAGE' in value for value in result))
    reader.close()

def test_partial_send_preserves_only_rejected_recipients(tmp_path, monkeypatch):
    from mailclient.ui.compose_window import ComposeWindow
    from mailclient.core.service import MailService
    from mailclient.core.accounts import Account, Server
    from mailclient.tests.test_complete import Vault
    from types import SimpleNamespace
    db = Database(tmp_path / 'settings.db')
    vault = Vault()
    account = Account('Test', 'a@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))
    vault.set(account.id, 'fake-test-password')
    service = MailService(db, vault, TLSPolicy(db))
    monkeypatch.setattr('mailclient.ui.compose_window.send_message', lambda *args: {'refused@example.com': (550, b'refused')})
    monkeypatch.setattr(service, 'folders', lambda *args: ([('Sent', 'Envoyés')], False))
    monkeypatch.setattr(service, 'client', lambda *args: SimpleNamespace(append=lambda *args: None))
    composer = ComposeWindow(service, [account], fields=dict(to='accepted@example.com, refused@example.com', subject='Test', body='Bonjour'))
    composer.show()
    composer.send()
    assert process_until(lambda: not composer.busy and not composer.saving and db.cache_get('draft', composer.id) is not None)
    assert composer.to.text() == 'refused@example.com'
    assert db.cache_get('draft', composer.id)['to'] == 'refused@example.com'
    assert not composer.delivered
    composer.close()

def test_offline_composer_does_not_contact_smtp(tmp_path, monkeypatch):
    from mailclient.ui.compose_window import ComposeWindow
    from mailclient.core.service import MailService
    from mailclient.core.accounts import Account, Server
    from mailclient.tests.test_complete import Vault
    db = Database(tmp_path / 'settings.db')
    account = Account('Test', 'a@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))
    service = MailService(db, Vault(), TLSPolicy(db))
    called = []
    monkeypatch.setattr('mailclient.ui.compose_window.send_message', lambda *args: called.append(args))
    composer = ComposeWindow(service, [account], fields=dict(to='b@example.com', subject='Test'), offline=lambda: True)
    composer.send()
    assert not called and 'hors ligne' in composer.status.text().lower()
    composer.close()
    assert process_until(lambda: not composer.saving)

def test_theme_switch_restores_light_palette(tmp_path):
    from PySide6.QtGui import QPalette
    db = Database(tmp_path / 'settings.db')
    window = MainWindow(db, FakeSecrets(), TLSPolicy(db), auto_load=False)
    db.set_setting('theme', 1)
    window.apply_theme()
    assert APP.palette().color(QPalette.Base).lightness() < 100
    assert window.reader.dark
    db.set_setting('theme', 0)
    window.apply_theme()
    assert APP.palette().color(QPalette.Base).lightness() > 100
    assert not window.reader.dark
    window.close()

def test_main_window_load_read_star_move_and_offline(tmp_path, monkeypatch):
    from mailclient.core.service import MailService
    from mailclient.core.accounts import Account, Server
    from mailclient.tests.test_complete import Vault
    from PySide6.QtWidgets import QMessageBox
    db = Database(tmp_path / 'settings.db')
    account = Account('Test', 'a@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))
    db.save(account)
    rows = [dict(uid='12', uidvalidity='7', sender='b@example.com', subject='Message réel simulé', date='', unread=True, starred=False, attachment=False)]
    called = []
    class Client:
        uidvalidity = '7'
        def folders(self):
            return [('INBOX', 'Réception'), ('Trash', 'Corbeille')]
        def messages(self, folder, page, query=''):
            return list(rows), len(rows)
        def message_raw(self, folder, uid):
            return b'Subject: Lecture\r\n\r\nCorps du message'
        def action(self, folder, uid, expected, action, target):
            called.append((folder, uid, expected, action, target))
            if action == 'star':
                rows[0]['starred'] = True
            elif action == 'move':
                rows.clear()
    monkeypatch.setattr(MailService, 'client', lambda *args: Client())
    window = MainWindow(db, Vault(), TLSPolicy(db), auto_load=False)
    window.reload_accounts()
    assert process_until(lambda: not window.busy and len(window.rows) == 1)
    window.table.selectRow(0)
    assert process_until(lambda: not window.busy and window.reader.mail is not None)
    assert window.reader.mail.text == 'Corps du message'
    window.toggle_star()
    assert process_until(lambda: not window.busy and window.rows[0]['starred'])
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    window.table.selectRow(0)
    assert process_until(lambda: not window.busy)
    window.move('trash')
    assert process_until(lambda: not window.busy and not window.rows)
    assert called[-1] == ('INBOX', '12', '7', 'move', 'Trash')
    window.offline.setChecked(True)
    assert process_until(lambda: not window.busy)
    assert window.offline.isChecked()
    window.close()
