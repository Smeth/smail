"""Disposition réelle, menus et états vides ; aucun rendu de capture ni réseau."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu
from mailclient.tests.test_ui import APP, process_until
from mailclient.tests.test_complete import Vault
from mailclient.core.accounts import Account, Server
from mailclient.core.service import MailService
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database
from mailclient.ui.compose_window import ComposeWindow
from mailclient.ui.main_window import MainWindow
from mailclient.ui.attachment_widgets import clipboard_attachment
from PySide6.QtGui import QImage


@pytest.mark.parametrize('variant', [1,2,3])
@pytest.mark.parametrize('dark', [False,True])
@pytest.mark.parametrize('density', ['Compacte','Normale','Aérée'])
def test_compose_fits_screen_and_keeps_footer_visible(tmp_path,variant,dark,density):
    db = Database(tmp_path/'layout.db')
    service = MailService(db,Vault(),TLSPolicy(db))
    account = Account('a@example.com','a@example.com',Server('imap.example.com',993),Server('smtp.example.com',465))
    composer = ComposeWindow(service,[account])
    composer.appearance.update(variant=variant,dark=dark,density=density)
    composer.debounce.stop()
    composer.periodic.stop()
    composer.show()
    APP.processEvents()
    assert composer.height() <= composer.screen().availableGeometry().height()-32
    assert composer.width() <= 780
    assert composer.cc.isHidden() and composer.bcc.isHidden()
    assert not composer.attachment_panel.isVisible()
    assert composer.account_box.currentText() == account.email
    image = QImage(320,120,QImage.Format_RGB32)
    image.fill(Qt.red)
    composer.files = [clipboard_attachment(image,'une-image-avec-un-nom-vraiment-long.png'),
                      clipboard_attachment(image,'seconde.png')]
    composer.show_files()
    assert process_until(lambda: not composer.runner.tasks)
    APP.processEvents()
    # Le rendu du delegate est déclenché par l'affichage, pas par une capture.
    composer.attachments.viewport().repaint()
    first = composer.attachments.visualItemRect(composer.attachments.item(0))
    second = composer.attachments.visualItemRect(composer.attachments.item(1))
    assert first.top() == second.top() and first.right() < second.left()
    for widget in (composer.body,composer.attachment_panel,composer.send_button,composer.status):
        bounds = widget.rect().translated(widget.mapTo(composer,widget.rect().topLeft()))
        assert composer.rect().contains(bounds)
    assert composer.body.height() >= 100
    assert isinstance(composer.more_button.menu(),QMenu)
    composer.recipient_toggles[0].click()
    composer.recipient_toggles[1].click()
    APP.processEvents()
    assert not composer.cc.isHidden()
    assert composer.height() <= composer.screen().availableGeometry().height()-32
    composer.saved_revision = composer.revision
    composer.close()


def test_reader_has_one_empty_prompt_and_menus_are_connected(tmp_path):
    db = Database(tmp_path/'menus.db')
    window = MainWindow(db,Vault(),TLSPolicy(db),auto_load=False)
    window.show()
    APP.processEvents()
    reader = window.reader
    assert reader.headers.text() == '' and reader.headers.isHidden()
    assert reader.empty_message.isVisible()
    assert [action.text() for action in window.menuBar().actions()] == ['Fichier','Message','Affichage','Comptes','Outils']
    assert window.table.contextMenuPolicy() == Qt.CustomContextMenu
    assert all(not action.isEnabled() for action in window.message_actions)
    window.set_busy(True)
    assert not window.offline_action.isEnabled()
    window.offline_action.trigger()
    assert not window.offline.isChecked()
    window.set_busy(False)
    window.style_actions[3].trigger()
    assert window.appearance.variant == 3
    window.toggle_theme()
    # Le menu annonce l’action (vers l’autre thème), comme le bouton de l’en-tête.
    expected = 'Passer au thème clair' if window.appearance.dark else 'Passer au thème sombre'
    assert window.dark_action.text() == expected and window.theme_button.toolTip().startswith(expected)
    window.density_actions['Compacte'].trigger()
    assert window.density_box.currentText() == 'Compacte'
    window.close()


def test_compact_attachments_with_total_and_remove_buttons(tmp_path):
    from PySide6.QtCore import QPoint, QPointF, QEvent
    from PySide6.QtGui import QMouseEvent
    from mailclient.core.parser import Attachment
    from mailclient.ui.attachment_widgets import remove_area
    db = Database(tmp_path/'compact.db')
    service = MailService(db,Vault(),TLSPolicy(db))
    account = Account('a@example.com','a@example.com',Server('imap.example.com',993),Server('smtp.example.com',465))
    composer = ComposeWindow(service,[account],fields=dict(subject='Rapport annuel'))
    composer.debounce.stop()
    composer.periodic.stop()
    composer.resize(760, 700)
    composer.show()
    assert composer.windowTitle() == 'Rapport annuel — Smail'
    composer.subject.setText('')
    assert composer.windowTitle() == 'Nouveau message — Smail'
    composer.files = [Attachment('a.pdf','application/pdf',b'x'*2_400_000), Attachment('b.txt','text/plain',b'y'*3000)]
    composer.show_files()
    assert composer.attachment_label.text() == 'Pièces jointes · 2 · 2,4 Mo' and composer.attachment_label.styleSheet() == ''
    assert composer.remove_file.isHidden()
    rect = composer.attachments.visualItemRect(composer.attachments.item(0))
    point = QPointF(remove_area(rect).center())
    release = QMouseEvent(QEvent.MouseButtonRelease, point, composer.attachments.viewport().mapToGlobal(point.toPoint()),
                          Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    composer.attachments.mouseReleaseEvent(release)  # Clic sur le × de la première étiquette.
    assert [a.name for a in composer.files] == ['b.txt']
    composer.files.append(Attachment('video.mp4','video/mp4',b'z'*20_000_000))
    composer.show_files()
    assert 'risque de refus' in composer.attachment_label.text() and 'color' in composer.attachment_label.styleSheet()
    composer.attachments.setCurrentRow(1)
    composer.attachments.setFocus()
    from PySide6.QtTest import QTest
    QTest.keyClick(composer.attachments, Qt.Key_Delete)
    assert [a.name for a in composer.files] == ['b.txt']
    assert composer.more_button.text() == 'Enregistrer' and composer.add_file.text() == 'Joindre'
    composer.saved_revision = composer.revision
    composer.close()
