"""Aperçu des pièces jointes, sans ouvrir de programme externe ni écrire de fichier.

Images et PDF sont affichés ; les textes (y compris HTML, XML, calendrier) sont montrés en source
brute, jamais interprétés. Les fichiers potentiellement dangereux ne sont jamais prévisualisés.
"""
from pathlib import PurePosixPath
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QScrollArea, QVBoxLayout
from mailclient.core.html_security import dangerous_filename
from mailclient.ui.components import Button, label
from mailclient.ui.dialog_shell import appearance

TEXT_EXTENSIONS = {'.txt', '.csv', '.tsv', '.json', '.xml', '.md', '.log', '.ics', '.vcf', '.html', '.htm', '.eml', '.ini', '.yaml', '.yml'}
TEXT_LIMIT = 2_000_000
IMAGE_TYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/bmp'}


def preview_kind(attachment) -> str | None:
    """'image', 'pdf', 'text' ou None (aperçu impossible ou refusé)."""
    name, content_type = attachment.name.lower(), (attachment.content_type or '').lower()
    if dangerous_filename(attachment.name) or not attachment.data:
        return None
    suffix = PurePosixPath(name).suffix
    if content_type in IMAGE_TYPES or suffix in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}:
        return 'image' if not QImage.fromData(attachment.data).isNull() else None
    if content_type == 'application/pdf' or suffix == '.pdf':
        return 'pdf' if attachment.data[:5] == b'%PDF-' else None
    if content_type.startswith('text/') or content_type in {'application/json', 'application/xml', 'message/rfc822'} or suffix in TEXT_EXTENSIONS:
        return 'text'
    return None


def decode_text(data: bytes) -> str:
    data = data[:TEXT_LIMIT]
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='replace')


class AttachmentPreview(QDialog):
    """Fenêtre d’aperçu ; « Enregistrer… » délègue à l’enregistrement existant (avec ses alertes)."""
    def __init__(self, attachment, save=None, parent=None):
        super().__init__(parent)
        self.attachment, self.kind = attachment, preview_kind(attachment)
        theme = appearance()
        self.setWindowTitle(f'Aperçu — {attachment.name}')
        self.resize(900, 700)
        layout = QVBoxLayout(self)
        layout.addWidget(label(attachment.name, 'Bold', True))
        layout.addWidget(label(f'{attachment.content_type or "type inconnu"} · {len(attachment.data) / 1024:.0f} Ko · '
                               'aperçu dans Smail, sans ouvrir d’autre programme', 'Small', True))
        self.view = self.build_view()
        layout.addWidget(self.view, 1)
        row = QHBoxLayout()
        row.addStretch()
        if save:
            button = Button('Enregistrer…', theme, 'download', 'Secondary')
            button.clicked.connect(save)
            row.addWidget(button)
        close = Button('Fermer', theme, role='Primary')
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)

    def build_view(self):
        if self.kind == 'image':
            image = QLabel()
            image.setAlignment(Qt.AlignCenter)
            pixmap = QPixmap.fromImage(QImage.fromData(self.attachment.data))
            if pixmap.width() > 1600 or pixmap.height() > 1600:
                pixmap = pixmap.scaled(1600, 1600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            image.setPixmap(pixmap)
            area = QScrollArea()
            area.setWidget(image)
            area.setWidgetResizable(True)
            return area
        if self.kind == 'pdf':
            from PySide6.QtPdf import QPdfDocument
            from PySide6.QtPdfWidgets import QPdfView
            self.pdf_data = QByteArray(self.attachment.data)  # Référence durable : le tampon ne copie pas les octets.
            self.buffer = QBuffer(self)
            self.buffer.setData(self.pdf_data)
            self.buffer.open(QIODevice.ReadOnly)
            self.document = QPdfDocument(self)
            self.document.load(self.buffer)
            view = QPdfView(self)
            view.setDocument(self.document)
            view.setPageMode(QPdfView.PageMode.MultiPage)
            view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            return view
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        content = decode_text(self.attachment.data) if self.kind == 'text' else 'Aperçu indisponible pour ce type de fichier.'
        if self.kind == 'text' and len(self.attachment.data) > TEXT_LIMIT:
            content += '\n\n[Aperçu limité aux 2 premiers Mo.]'
        text.setPlainText(content)
        return text
