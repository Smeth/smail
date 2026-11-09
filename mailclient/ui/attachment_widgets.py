"""Ajout local de fichiers et miniatures raster, sans ouverture ni téléchargement."""
import mimetypes
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QSize, QRect, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage, QImageReader, QPixmap, QKeySequence, QColor, QPen, QPainter
from PySide6.QtWidgets import QListWidget, QListView, QPlainTextEdit, QApplication, QStyledItemDelegate, QStyle
from mailclient.core.parser import Attachment, safe_filename
from mailclient.core.html_security import dangerous_filename

IMAGE_FILTER = 'Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tif *.tiff *.ico *.avif);;Tous les fichiers (*)'
RASTER_FORMATS = {b'png', b'jpg', b'jpeg', b'gif', b'webp', b'bmp', b'tif', b'tiff', b'ico', b'avif', b'heif'}

def local_paths(mime):
    urls = mime.urls() if mime.hasUrls() else []
    return [url.toLocalFile() for url in urls] if urls and all(url.isLocalFile() for url in urls) else []

def read_attachments(paths):
    """Une erreur sur un fichier ne fait pas perdre les autres fichiers choisis."""
    attachments, errors = [], []
    for value in paths:
        path = Path(value)
        try:
            data = path.read_bytes()
            attachments.append(Attachment(safe_filename(path.name), mimetypes.guess_type(path.name)[0] or 'application/octet-stream', data))
        except OSError:
            errors.append(path.name)
    return attachments, errors

def thumbnail(attachment, target=QSize(104,78)):
    """À exécuter dans un worker ; QPixmap reste réservé au fil graphique."""
    if dangerous_filename(attachment.name):
        return QImage(), ''
    buffer = QBuffer()
    buffer.setData(QByteArray(attachment.data))
    buffer.open(QIODevice.ReadOnly)
    reader = QImageReader(buffer)
    reader.setDecideFormatFromContent(True)
    if bytes(reader.format()).lower() not in RASTER_FORMATS:
        return QImage(), ''
    dimensions = reader.size()
    if not dimensions.isValid() or dimensions.width()*dimensions.height() > 64_000_000:
        return QImage(), 'Miniature indisponible : dimensions trop importantes. Le fichier original reste joint.'
    reader.setAutoTransform(True)
    reader.setScaledSize(dimensions.scaled(target,Qt.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        return QImage(), 'Miniature indisponible. Le fichier original reste joint.'
    image = image.scaled(target,Qt.KeepAspectRatio,Qt.SmoothTransformation)
    return image, f'{dimensions.width()} × {dimensions.height()} pixels'

def clipboard_attachment(image, name):
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    if image.isNull() or not image.save(buffer,'PNG'):
        raise RuntimeError('Impossible de joindre cette image depuis le presse-papiers.')
    return Attachment(name,'image/png',bytes(buffer.data()))

def clipboard_image(mime):
    if not mime.hasImage():
        return QImage()
    value = mime.imageData()
    if isinstance(value,QPixmap):
        return value.toImage()
    return QImage(value) if isinstance(value,QImage) else QImage()

class AttachmentDelegate(QStyledItemDelegate):
    """Cartes horizontales : aperçu centré, deux lignes toujours alignées."""
    def paint(self, painter, option, index):
        from mailclient.ui.dialog_shell import appearance
        colors = appearance().colors
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(3, 3, -3, -3)
        selected = bool(option.state & QStyle.State_Selected)
        painter.setPen(QPen(QColor(colors['accent' if selected else 'border']), 1))
        painter.setBrush(QColor(colors['soft' if selected else 'panel']))
        painter.drawRoundedRect(rect, 8, 8)
        preview = QRect(rect.left()+10, rect.top()+10, 48, 48)
        decoration = index.data(Qt.DecorationRole)
        if decoration:
            decoration.paint(painter, preview, Qt.AlignCenter)
        text_rect = QRect(preview.right()+12, rect.top()+13, rect.width()-84, 22)
        parts = (index.data(Qt.DisplayRole) or '').split('\n', 1)
        painter.setPen(QColor(colors['text']))
        font = option.font
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(parts[0], Qt.ElideMiddle, text_rect.width()))
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(colors['muted']))
        painter.drawText(text_rect.translated(0, 23), Qt.AlignLeft | Qt.AlignVCenter, parts[1] if len(parts)>1 else '')
        if option.state & QStyle.State_HasFocus:
            painter.setPen(QPen(QColor(colors['accent']), 2, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(2,2,-2,-2),6,6)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(264, 76)


class AttachmentGrid(QListWidget):
    pathsAdded = Signal(list)
    imageAdded = Signal(QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.IconMode)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(False)
        self.setItemDelegate(AttachmentDelegate(self))
        self.setGridSize(QSize(264,76))
        self.setIconSize(QSize(48,48))
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideMiddle)
        self.setSpacing(0)
        self.setFixedHeight(96)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollMode(QListView.ScrollPerPixel)
        self.setAcceptDrops(True)
        self.setDragEnabled(False)
        self.setAccessibleName('Pièces jointes avec miniatures ; glissez des fichiers ou collez une image')

    def dragEnterEvent(self, event):
        if local_paths(event.mimeData()) or event.mimeData().hasImage():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = local_paths(event.mimeData())
        if paths:
            self.pathsAdded.emit(paths)
        else:
            image = clipboard_image(event.mimeData())
            if image.isNull():
                event.ignore()
                return
            self.imageAdded.emit(image)
        event.acceptProposedAction()

    def keyPressEvent(self, event):
        mime = QApplication.clipboard().mimeData()
        if event.matches(QKeySequence.Paste) and (local_paths(mime) or mime.hasImage()):
            paths = local_paths(mime)
            if paths:
                self.pathsAdded.emit(paths)
            else:
                image = clipboard_image(mime)
                if not image.isNull():
                    self.imageAdded.emit(image)
            event.accept()
        else:
            super().keyPressEvent(event)

class ComposeEditor(QPlainTextEdit):
    pathsAdded = Signal(list)
    imageAdded = Signal(QImage)

    def canInsertFromMimeData(self, source):
        return bool(local_paths(source) or source.hasImage()) or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        paths = local_paths(source)
        if paths:
            self.pathsAdded.emit(paths)
        elif source.hasImage():
            image = clipboard_image(source)
            if not image.isNull():
                self.imageAdded.emit(image)
        else:
            super().insertFromMimeData(source)
