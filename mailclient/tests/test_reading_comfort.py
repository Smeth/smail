"""Confort de lecture : aperçu des pièces jointes, impression, fenêtre séparée et glisser-déposer."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
import json
import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QPointF, Qt, QMimeData
from PySide6.QtGui import QDropEvent, QImage, QPainter, QPdfWriter
from mailclient.tests.test_ui import APP, process_until
from mailclient.core.accounts import Account, Server
from mailclient.core.parser import Attachment, Mail
from mailclient.core.service import MailService
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database
from mailclient.ui.attachment_preview import AttachmentPreview, preview_kind, decode_text

ME = Account('Moi', 'moi@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))


def png_bytes():
    image = QImage(40, 20, QImage.Format_RGB32)
    image.fill(Qt.red)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, 'PNG')
    return bytes(data)


def pdf_bytes():
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    writer = QPdfWriter(buffer)
    painter = QPainter(writer)
    painter.drawText(100, 100, 'Facture 2026')
    painter.end()
    return bytes(data)


@pytest.mark.parametrize('name,content_type,data,expected', [
    ('photo.png', 'image/png', None, 'image'), ('scan.pdf', 'application/pdf', 'pdf', 'pdf'),
    ('faux.pdf', 'application/pdf', b'MZ\x90 pas un pdf', None), ('notes.txt', 'text/plain', b'Bonjour', 'text'),
    ('page.html', 'text/html', b'<script>alert(1)</script>', 'text'), ('invitation.ics', 'application/octet-stream', b'BEGIN:VCALENDAR', 'text'),
    ('outil.exe', 'application/octet-stream', b'MZ', None), ('logo.svg', 'image/svg+xml', b'<svg/>', None),
    ('archive.zip', 'application/zip', b'PK\x03\x04', None), ('vide.txt', 'text/plain', b'', None)])
def test_preview_kind(name, content_type, data, expected):
    data = {None: png_bytes(), 'pdf': pdf_bytes()}.get(data, data)
    assert preview_kind(Attachment(name, content_type, data)) == expected


def test_text_preview_decodes_and_never_renders_html():
    assert decode_text('Café'.encode('cp1252')) == 'Café'
    assert decode_text('﻿Été'.encode('utf-8')) == 'Été'
    dialog = AttachmentPreview(Attachment('page.html', 'text/html', b'<b>gras</b><script>x</script>'))
    assert dialog.view.toPlainText() == '<b>gras</b><script>x</script>'  # Source brute, rien d’interprété.
    dialog.close()


def test_image_and_pdf_previews_build():
    image = AttachmentPreview(Attachment('photo.png', 'image/png', png_bytes()))
    assert not image.view.widget().pixmap().isNull()
    image.close()
    pdf = AttachmentPreview(Attachment('scan.pdf', 'application/pdf', pdf_bytes()))
    assert process_until(lambda: pdf.document.pageCount() == 1)
    pdf.close()


def test_print_document_has_header_body_and_no_remote_image(tmp_path):
    from PySide6.QtPrintSupport import QPrinter
    from mailclient.ui.mail_view import print_document
    mail = Mail('Léa <lea@example.com>', 'moi@example.com', 'Compte rendu', 'Mon, 23 Nov 2026 10:00:00 +0100',
                html='<p>Bonjour <b>tous</b></p><img src="https://pistage.example/p.png"><script>x()</script>',
                attachments=[Attachment('cr.pdf', 'application/pdf', b'%PDF-')], cc='chef@example.com')
    document = print_document(mail)
    text, html = document.toPlainText(), document.toHtml()
    for expected in ('Compte rendu', 'Léa <lea@example.com>', 'chef@example.com', 'Bonjour tous', 'Pièces jointes : cr.pdf'):
        assert expected in text
    assert 'pistage.example' not in html and 'script' not in html.lower().replace('description', '')
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(tmp_path / 'message.pdf'))
    document.print_(printer)
    assert (tmp_path / 'message.pdf').read_bytes()[:5] == b'%PDF-'


def test_message_list_drag_carries_only_identifiers():
    from PySide6.QtWidgets import QListWidgetItem
    from mailclient.ui.view_models import MessageList, MessageRow, DRAG_MIME
    rows = [dict(account='a', folder='INBOX', uidvalidity='7', uid=uid, sender='x', subject='Secret', date='') for uid in ('3', '2')]
    listing = MessageList()
    item = QListWidgetItem('conversation')
    item.setData(Qt.UserRole, MessageRow.from_thread(rows))
    listing.addItem(item)
    data = listing.mimeData([item])
    assert json.loads(bytes(data.data(DRAG_MIME))) == [['a', 'INBOX', '7', '3'], ['a', 'INBOX', '7', '2']]
    assert b'Secret' not in bytes(data.data(DRAG_MIME))


class Client:
    uidvalidity = '7'

    def __init__(self):
        self.calls = []

    def folders(self):
        return [('INBOX', 'Boîte de réception'), ('Projets', 'Projets'), ('Trash', 'Corbeille')]

    def messages(self, folder, page, query=''):
        return [dict(uid=uid, uidvalidity='7', sender='Léa <lea@example.com>', subject=f'Sujet {uid}', date='', unread=False,
                     starred=False, attachment=False) for uid in ('5', '4')], 2

    def message_raw(self, folder, uid):
        return f'From: Léa <lea@example.com>\r\nTo: moi@example.com\r\nSubject: Sujet {uid}\r\nMessage-ID: <{uid}@x>\r\n\r\nCorps {uid}'.encode()

    def action(self, folder, uids, validity, action, target=''):
        self.calls.append((folder, uids, action, target))


@pytest.fixture
def window(tmp_path, monkeypatch):
    from mailclient.ui.main_window import MainWindow
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    client = Client()
    monkeypatch.setattr(MailService, 'client', lambda *args: client)
    db.set_setting('conversation_view', False)
    window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    window.client = client
    window.reload_accounts()
    window.select_account(ME.id)
    assert process_until(lambda: not window.busy and window.table.count() == 2)
    yield window
    for other in list(window.message_windows):
        other.close()
    window.reader.shutdown()
    window.close()
    from shiboken6 import delete
    delete(window)


def drop_event(window, row, keys):
    from mailclient.ui.view_models import DRAG_MIME
    data = QMimeData()
    data.setData(DRAG_MIME, json.dumps(keys).encode())
    rect = window.folders.visualItemRect(window.folders.item(row))
    return QDropEvent(QPointF(rect.center()), Qt.MoveAction, data, Qt.LeftButton, Qt.NoModifier), data


def test_drop_messages_on_folder_moves_them(window):
    window.table.selectAll()
    keys = json.loads(bytes(window.table.mimeData(window.table.selectedItems()).data('application/x-smail-messages')))
    projets = next(index for index, (name, _) in enumerate(window.folder_data) if name == 'Projets')
    event, _ = drop_event(window, projets, keys)
    assert window.eventFilter(window.folders.viewport(), event) and event.isAccepted()
    assert process_until(lambda: not window.busy and window.client.calls)
    assert window.client.calls[-1] == ('INBOX', '5,4', 'move', 'Projets')
    # Dépôt sur le dossier courant, ou hors ligne : refusé.
    same, _ = drop_event(window, 0, keys)
    window.eventFilter(window.folders.viewport(), same)
    assert not same.isAccepted()
    window.offline.setChecked(True)
    assert process_until(lambda: not window.busy)
    offline, _ = drop_event(window, 1, keys)
    window.eventFilter(window.folders.viewport(), offline)
    assert not offline.isAccepted()


def test_open_in_window_and_reply_from_it(window):
    from mailclient.ui.compose_window import ComposeWindow
    window.table.setCurrentRow(0)
    window.open_in_window()  # Double-clic pendant le chargement : ouverture à la fin.
    assert window.pending_window
    assert process_until(lambda: not window.busy and window.message_windows)
    [opened] = window.message_windows
    assert opened.reader.mail.subject == 'Sujet 5' and opened.windowTitle() == 'Sujet 5'
    assert not any(action.isVisible() for action in opened.reader.more_menu.actions()[:4])
    opened.reader.replyRequested.emit()
    composer = next(widget for widget in window.composers if isinstance(widget, ComposeWindow))
    assert composer.to.text() == 'Léa <lea@example.com>' and composer.subject.text() == 'Re: Sujet 5'
    composer.saved_revision = composer.revision
    composer.close()
    opened.close()
    assert opened.reader.disposed and not window.message_windows
