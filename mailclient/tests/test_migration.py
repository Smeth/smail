"""Régressions de migration visuelle sur modèles et services contrôlés."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS','--disable-gpu')
import sys
import time
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from shiboken6 import delete
from mailclient.storage.database import Database
from mailclient.core.tls_policy import TLSPolicy
from mailclient.core.accounts import Account, Server
from mailclient.core.service import MailService
from mailclient.ui.main_window import MainWindow
from mailclient.ui.settings_dialog import SettingsDialog
from mailclient.ui.account_dialog import AccountDialog
from mailclient.ui.compose_window import ComposeWindow
from mailclient.ui.cert_dialog import CertificateDialog
from mailclient.core.tls_policy import CertificateAlert

class Vault:
    def get(self,key):
        return 'test-only'
    def set(self,*args):
        pass

def wait_for(predicate):
    deadline = time.monotonic()+5
    app = QApplication.instance()
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert predicate()

@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    database = Database(tmp_path/'presentation.db')
    window = MainWindow(database,Vault(),TLSPolicy(database),auto_load=False)
    window.show()
    app.processEvents()
    yield window
    for dialog in window.findChildren(ComposeWindow):
        dialog.saved_revision = dialog.revision
        dialog.debounce.stop()
        dialog.periodic.stop()
    window.close()
    delete(window)
    app.processEvents()

def test_style_switch_persists_without_changing_models(window):
    original = window.rows
    for variant in (1,2,3):
        window.style_box.setCurrentIndex(variant-1)
        assert window.appearance.variant == variant
        assert window.database.setting('ui_style',1) == variant
        assert window.rows is original
        assert all(key.isEnabled() for key in window.quick_keys)  # J, K, E, S dans tous les styles.
    window.toggle_theme()
    assert window.database.setting('theme') == 1
    window.density_box.setCurrentText('Aérée')
    assert window.database.setting('ui_density') == 'Aérée'

def test_settings_preview_cancel_restores_without_persisting(window):
    previous = window.appearance.variant
    dialog = SettingsDialog(window.database,window)
    dialog.style_combo.setCurrentIndex(2)
    dialog.theme.setCurrentIndex(1)
    assert window.appearance.variant == 3 and window.appearance.dark
    dialog.reject()
    assert window.appearance.variant == previous and not window.appearance.dark
    assert window.database.setting('ui_style') is None
    delete(dialog)

def test_real_dialogs_all_styles_and_themes_no_mockup_imports(window):
    account = Account('Travail','a@example.com',Server('imap.example.com',993),Server('smtp.example.com',465))
    for variant in (1,2,3):
        window.style_box.setCurrentIndex(variant-1)
        for dark in (False,True):
            window.database.set_setting('theme',int(dark))
            window.apply_theme()
            composer = ComposeWindow(window.service,[account],parent=window)
            composer.debounce.stop()
            composer.periodic.stop()
            composer.saved_revision = composer.revision
            dialogs = [composer,AccountDialog(window.database,window.secrets,window.runner.tls,window),
                CertificateDialog(CertificateAlert('a','imap:host','ab'*32,'issuer','dates','reason'),window),
                SettingsDialog(window.database,window)]
            for dialog in dialogs:
                dialog.show()
                QApplication.processEvents()
                assert dialog.isVisible()
                dialog.close()
                delete(dialog)
    assert not any(name == 'mockups' or name.startswith('mockups.') for name in sys.modules)

def test_unified_duplicate_uid_selection_uses_account_identity(window,monkeypatch):
    first = Account('Premier','a@example.com',Server('imap.example.com',993),Server('smtp.example.com',465))
    second = Account('Deuxième','b@example.com',first.imap,first.smtp)
    window.database.save(first)
    window.database.save(second)
    window.accounts = [first,second]
    window.account_box.blockSignals(True)
    window.account_box.addItem('Réception unifiée','unified')
    window.account_box.blockSignals(False)
    window.folder_data = [('INBOX','Réception unifiée')]
    window.folders.blockSignals(True)
    window.folders.addItem('Réception unifiée')
    window.folders.setCurrentRow(0)
    window.folders.blockSignals(False)
    rows = [dict(account=account.id,folder='INBOX',uid='12',uidvalidity='7',sender='test@example.com',
                 subject=account.name,date='',unread=True,attachment=False) for account in (first,second)]
    monkeypatch.setattr(window.service,'unified',lambda *args:dict(rows=rows,total=2,offline=True))
    from mailclient.core.parser import Mail
    monkeypatch.setattr(window.service,'message',lambda account,row,offline:Mail('test@example.com',account.email,row['subject'],'',text='Contenu réel contrôlé'))
    calls = []
    monkeypatch.setattr(window.service,'action',lambda account,rows,*args:calls.extend((account.id,row['uid']) for row in rows))
    window.load_messages()
    wait_for(lambda:not window.busy and window.table.count() == 2)
    window.table.selectRow(1)
    wait_for(lambda:not window.busy and window.reader.mail is not None)
    assert window.selected_row()['account'] == second.id
    window.reader.action_buttons[2].click()  # Étoile, via la même commande que le menu.
    wait_for(lambda:not window.busy and bool(calls))
    assert calls == [(second.id,'12')]

def test_delete_in_search_does_not_trigger_message_action(window,monkeypatch):
    calls = []
    monkeypatch.setattr(window,'mutate',lambda *args:calls.append(args))
    window.search.setText('abc')
    window.search.setFocus()
    QTest.keyClick(window.search,Qt.Key_Delete)
    assert not calls
    window.open_palette()
    labels = [window.palette_dialog.list.item(i).text() for i in range(window.palette_dialog.list.count())]
    assert not any('Supprimer' in value for value in labels)
    window.palette_dialog.close()
