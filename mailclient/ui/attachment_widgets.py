"""Ajout local de fichiers et miniatures raster, sans ouverture ni téléchargement."""
from mailclient.i18n import tr, N_
import mimetypes
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QSize, QRect, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage, QImageReader, QPixmap, QKeySequence, QColor, QPen, QPainter
from PySide6.QtWidgets import QListWidget, QListView, QPlainTextEdit, QApplication, QStyledItemDelegate, QStyle
from mailclient.core.parser import Attachment, safe_filename
from mailclient.core.html_security import dangerous_filename

IMAGE_FILTER = N_('Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tif *.tiff *.ico *.avif);;Tous les fichiers (*)')  # Traduit à l’affichage : tr(IMAGE_FILTER).
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
        return QImage(), tr('Miniature indisponible : dimensions trop importantes. Le fichier original reste joint.')
    reader.setAutoTransform(True)
    reader.setScaledSize(dimensions.scaled(target,Qt.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        return QImage(), tr('Miniature indisponible. Le fichier original reste joint.')
    image = image.scaled(target,Qt.KeepAspectRatio,Qt.SmoothTransformation)
    return image, f'{dimensions.width()} × {dimensions.height()} pixels'

def clipboard_attachment(image, name):
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    if image.isNull() or not image.save(buffer,'PNG'):
        raise RuntimeError(tr('Impossible de joindre cette image depuis le presse-papiers.'))
    return Attachment(name,'image/png',bytes(buffer.data()))

def clipboard_image(mime):
    if not mime.hasImage():
        return QImage()
    value = mime.imageData()
    if isinstance(value,QPixmap):
        return value.toImage()
    return QImage(value) if isinstance(value,QImage) else QImage()

CHIP = QSize(236, 46)  # Étiquette de pièce jointe : miniature, nom, taille et bouton ×.


def remove_area(rect):
    """Zone du bouton × d’une étiquette (coordonnées de la vue)."""
    return QRect(rect.right() - 30, rect.center().y() - 11, 22, 22)


class AttachmentDelegate(QStyledItemDelegate):
    """Étiquettes compactes : miniature, nom, taille et × pour retirer la pièce jointe."""
    def paint(self, painter, option, index):
        from mailclient.ui.dialog_shell import appearance
        from mailclient.ui.icons import icon
        colors = appearance().colors
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(2, 2, -2, -2)
        selected = bool(option.state & QStyle.State_Selected)
        painter.setPen(QPen(QColor(colors['accent' if selected else 'border']), 1))
        painter.setBrush(QColor(colors['soft' if selected else 'panel']))
        painter.drawRoundedRect(rect, 8, 8)
        preview = QRect(rect.left()+7, rect.center().y()-15, 30, 30)
        decoration = index.data(Qt.DecorationRole)
        if decoration:
            decoration.paint(painter, preview, Qt.AlignCenter)
        text_rect = QRect(preview.right()+9, rect.top()+4, rect.width()-82, 19)
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
        painter.drawText(text_rect.translated(0, 18), Qt.AlignLeft | Qt.AlignVCenter, parts[1] if len(parts)>1 else '')
        if getattr(self.parent(), 'removable', True):  # Rédaction seulement : pas de × dans un message reçu.
            close = remove_area(option.rect)
            icon('x', colors['muted'], 14).paint(painter, close.adjusted(4, 4, -4, -4), Qt.AlignCenter)
        if option.state & QStyle.State_HasFocus:
            painter.setPen(QPen(QColor(colors['accent']), 2, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(2,2,-2,-2),6,6)
        painter.restore()

    def sizeHint(self, option, index):
        return CHIP


class AttachmentGrid(QListWidget):
    pathsAdded = Signal(list)
    imageAdded = Signal(QImage)
    removeRequested = Signal(int)  # × d’une étiquette, ou touche Suppr.

    def __init__(self, parent=None, removable=True):
        super().__init__(parent)
        self.removable = removable
        self.setViewMode(QListView.IconMode)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)  # Les étiquettes passent à la ligne : tout est visible sans défilement latéral.
        self.setItemDelegate(AttachmentDelegate(self))
        self.setGridSize(QSize(CHIP.width()+4, CHIP.height()+4))
        self.setIconSize(QSize(30,30))
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideMiddle)
        self.setSpacing(0)
        self.setMaximumHeight(2 * (CHIP.height()+4) + 6)  # Deux rangées visibles, puis défilement vertical.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.setAcceptDrops(True)
        self.setDragEnabled(False)
        self.setMouseTracking(True)
        self.setAccessibleName(tr('Pièces jointes : × ou Suppr pour retirer ; glissez des fichiers ou collez une image'))

    def fit(self):
        """Hauteur ajustée au nombre de rangées (au plus deux)."""
        per_row = max(1, self.viewport().width() // self.gridSize().width())
        rows = min(2, max(1, -(-self.count() // per_row)))
        self.setFixedHeight(rows * self.gridSize().height() + 6)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def mouseReleaseEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if self.removable and index.isValid() and remove_area(self.visualRect(index)).contains(event.position().toPoint()):
            self.removeRequested.emit(index.row())
            event.accept()
            return
        super().mouseReleaseEvent(event)

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
        elif self.removable and event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.currentRow() >= 0:
            self.removeRequested.emit(self.currentRow())
            event.accept()
        else:
            super().keyPressEvent(event)

def __getattr__(name):
    # Éditeur de rédaction : désormais en texte enrichi (import différé, rich_text dépend de ce module).
    if name == 'ComposeEditor':
        from mailclient.ui.rich_text import RichTextEdit
        return RichTextEdit
    raise AttributeError(name)
