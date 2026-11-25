"""Préférences rangées par thème et page « Comptes » (liste, ajout, suppression)."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database
from mailclient.tests.test_scheduler import ME


def labels_in(widget):
    from PySide6.QtWidgets import QLabel
    return [child.text() for child in widget.findChildren(QLabel)]


def test_pages_by_theme_and_direct_opening(tmp_path):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from mailclient.ui.settings_dialog import SettingsDialog
    db = Database(tmp_path / 'settings.db')
    dialog = SettingsDialog(db, None, 'Comptes')
    assert [dialog.nav.item(i).text() for i in range(dialog.nav.count())] == list(SettingsDialog.PAGES)
    assert dialog.pages.currentIndex() == SettingsDialog.PAGES.index('Comptes')
    general, reception, security = (dialog.pages.widget(SettingsDialog.PAGES.index(name)) for name in ('Général', 'Réception', 'Sécurité'))
    assert dialog.notifications.parent() is general and dialog.update_mode.parent() is general
    assert dialog.update_mode.currentData() == 'ask'  # Par défaut : rien n’est téléchargé sans accord.
    assert dialog.minutes.parent() is reception and dialog.conversations.parent() is reception
    assert dialog.encrypt.parent() is security
    assert 'Aucun compte configuré : cliquez sur « Ajouter un compte ».' in labels_in(dialog)
    dialog.reject()


def test_accounts_page_lists_and_removes_accounts(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import APP, process_until  # noqa: F401
    from mailclient.ui.main_window import MainWindow
    from mailclient.ui.settings_dialog import SettingsDialog
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    try:
        dialog = SettingsDialog(db, window, 'Comptes')
        texts = labels_in(dialog.pages.currentWidget())
        assert 'moi@example.com · Mot de passe' in texts
        assert any(text.startswith('Réception imap.example.com:993') for text in texts)
        deleted = []
        def delete_account(account):
            deleted.append(account.id)
            db.delete_account(account.id)
            return True
        monkeypatch.setattr(window, 'delete_account', delete_account)
        dialog.delete_account(ME, dialog.accounts_list.itemAt(0).widget())
        assert process_until(lambda: 'Aucun compte configuré : cliquez sur « Ajouter un compte ».' in labels_in(dialog.pages.currentWidget()))
        assert deleted == [ME.id]
        added = []
        monkeypatch.setattr(window, 'add_account', lambda: (added.append(1), db.save(ME)))
        dialog.add_account()
        assert added and process_until(lambda: 'moi@example.com · Mot de passe' in labels_in(dialog.pages.currentWidget()))
        dialog.reject()
    finally:
        window.reader.shutdown()
        window.close()
        from shiboken6 import delete
        delete(window)
