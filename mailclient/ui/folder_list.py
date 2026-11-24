"""Colonne des dossiers : icône par dossier spécial, dossiers système en tête, nombre de messages non lus."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem

COUNT_ROLE = Qt.UserRole + 1
# (ordre d’affichage, icône, mots reconnus dans le nom ou le libellé)
KINDS = (
    (1, 'file-pen-line', ('brouillon', 'draft')),
    (2, 'send', ('envoy', 'sent')),
    (3, 'archive', ('archive', 'all mail', 'tous les messages')),
    (4, 'shield-alert', ('spam', 'junk', 'indésirable')),
    (5, 'trash-2', ('corbeille', 'trash', 'deleted', 'supprimé')),
    (6, 'clock', ('reporté', 'snooze')),
)


def kind(name: str, label: str) -> tuple:
    """(rang, icône) du dossier : réception d’abord, puis brouillons, envoyés… et enfin vos dossiers."""
    if name.upper() == 'INBOX' or label in ('Boîte de réception', 'Réception unifiée'):
        return 0, 'inbox'
    text = (name + ' ' + label).casefold()
    for rank, icon_name, words in KINDS:
        if any(word in text for word in words):
            return rank, icon_name
    return 10, 'folder'


def ordered(folders: list) -> list:
    """Dossiers système en tête (ordre fixe), puis les autres dans l’ordre du serveur."""
    return sorted(folders, key=lambda folder: kind(*folder)[0])  # Tri stable.


class FolderDelegate(QStyledItemDelegate):
    """Dessine le nombre de non-lus à droite de chaque dossier, dans une pastille."""
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme

    def paint(self, painter, option, index):
        count = index.data(COUNT_ROLE) or 0
        if count <= 0:
            super().paint(painter, option, index)
            return
        text = '999+' if count > 999 else str(count)
        font = QFont(option.font)
        font.setBold(True)
        metrics = QFontMetrics(font)
        width, height = metrics.horizontalAdvance(text) + 14, metrics.height() + 4
        # Nom du dossier raccourci (« … ») pour laisser la place à la pastille, au lieu d’être recouvert.
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        available = option.rect.width() - styled.decorationSize.width() - width - 52
        styled.text = QFontMetrics(styled.font).elidedText(styled.text, Qt.ElideRight, max(24, available))
        style = styled.widget.style() if styled.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, styled, painter, styled.widget)
        rect = QRectF(option.rect.right() - width - 10, option.rect.center().y() - height / 2, width, height)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self.theme.colors['accent']))
        painter.drawRoundedRect(rect, height / 2, height / 2)
        painter.setFont(font)
        painter.setPen(QColor(self.theme.colors['on_accent']))
        painter.drawText(rect, Qt.AlignCenter, text)
        painter.restore()
