"""Régressions de l'import et des miniatures, sans accès réseau."""
import base64
from PySide6.QtCore import QMimeData, Qt, QUrl, QPointF
from PySide6.QtGui import QImage, QDropEvent
from mailclient.ui.attachment_widgets import clipboard_attachment, read_attachments, thumbnail
from mailclient.core.parser import Attachment
from mailclient.tests.test_ui import APP, process_until


def image_file():
    image = QImage(320, 180, QImage.Format_RGB32)
    image.fill(Qt.red)
    return image, clipboard_attachment(image, 'photo.png')


def test_import_keeps_originals_and_reports_unreadable_file(tmp_path):
    _, original = image_file()
    path = tmp_path / 'photo.png'
    path.write_bytes(original.data)
    files, errors = read_attachments([path, tmp_path / 'absent.jpg'])
    assert files[0].data == original.data
    assert files[0].content_type == 'image/png'
    assert errors == ['absent.jpg']
    preview, description = thumbnail(files[0])
    assert not preview.isNull()
    assert preview.width() <= 104 and preview.height() <= 78
    assert '320' in description
    assert thumbnail(Attachment('image.exe', 'image/png', original.data))[0].isNull()
    assert thumbnail(Attachment('corrompu.jpg', 'image/jpeg', b'invalide'))[0].isNull()


def test_compose_import_paste_restore_and_original_mime(tmp_path, monkeypatch):
    from mailclient.core.accounts import Account, Server
    from mailclient.core.service import MailService
    from mailclient.core.tls_policy import TLSPolicy
    from mailclient.storage.database import Database
    from mailclient.tests.test_complete import Vault
    from mailclient.ui.compose_window import ComposeWindow, QFileDialog
    db = Database(tmp_path / 'settings.db')
    service = MailService(db, Vault(), TLSPolicy(db))
    account = Account('Test', 'a@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))
    image, original = image_file()
    path = tmp_path / original.name
    path.write_bytes(original.data)
    composer = ComposeWindow(service, [account])
    monkeypatch.setattr(QFileDialog, 'getOpenFileNames', lambda *args: ([str(path)], ''))
    composer.choose_files(images_only=True)
    assert process_until(lambda: not composer.busy and composer.attachments.item(0).data(Qt.UserRole))
    assert composer.files[0].data == original.data
    composer._adding_files = True
    composer.set_busy(False)  # Une sauvegarde terminée ne doit pas interrompre un import.
    assert composer.busy and not composer.send_button.isEnabled()
    composer._adding_files = False
    composer.set_busy(False)
    mime = QMimeData()
    mime.setImageData(image)
    composer.body.insertFromMimeData(mime)
    assert process_until(lambda: len(composer.files) == 2 and not composer.busy and composer.attachments.item(1).data(Qt.UserRole))
    assert composer.files[1].name == 'image-collee-1.png'
    text = QMimeData()
    text.setText('Bonjour')
    composer.body.insertFromMimeData(text)
    assert 'Bonjour' in composer.body.toPlainText()
    composer.to.setText('b@example.com')
    message, _ = composer.message(composer.state(), composer.files)
    assert next(message.iter_attachments()).get_payload(decode=True) == original.data
    composer.save_draft()
    assert process_until(lambda: not composer.saving)
    draft = db.cache_get('draft', composer.id)
    assert base64.b64decode(draft['attachments'][0]['data']) == original.data
    composer.close()
    reopened = ComposeWindow(service, [account], draft=draft)
    assert process_until(lambda: reopened.attachments.item(0).data(Qt.UserRole))
    reopened.attachments.setCurrentRow(0)
    reopened.remove_attachment()
    assert len(reopened.files) == 1
    assert process_until(lambda: not reopened.runner.tasks)
    reopened.close()
    assert process_until(lambda: not reopened.saving)


def test_editor_file_drop_mime_is_attachment():
    from mailclient.ui.attachment_widgets import ComposeEditor
    editor = ComposeEditor()
    received = []
    editor.pathsAdded.connect(received.append)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile('C:/images/photo.jpg')])
    assert editor.canInsertFromMimeData(mime)
    editor.insertFromMimeData(mime)
    assert received == [['C:/images/photo.jpg']]
    assert editor.toPlainText() == ''


def test_grid_accepts_image_file_drop():
    from mailclient.ui.attachment_widgets import AttachmentGrid
    grid = AttachmentGrid()
    received = []
    grid.pathsAdded.connect(received.append)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile('C:/images/photo.jpg')])
    event = QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    grid.dropEvent(event)
    assert event.isAccepted()
    assert received == [['C:/images/photo.jpg']]
