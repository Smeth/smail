"""Adaptateurs de présentation ; aucun accès réseau ou au cache depuis le dessin."""
from dataclasses import dataclass
from mailclient.i18n import N_
from email.utils import parseaddr, parsedate_to_datetime
from PySide6.QtCore import QMimeData, Qt
from PySide6.QtWidgets import QListWidget

@dataclass(frozen=True)
class MessageRow:
    raw: dict
    sender: str
    subject: str
    preview: str
    time: str
    unread: bool
    starred: bool
    attachments: bool
    account_name: str
    thread: tuple = ()  # Messages de la conversation présents dans la liste, du plus récent au plus ancien.

    @property
    def count(self) -> int:
        return max(1, len(self.thread))

    @property
    def rows(self) -> tuple:
        return self.thread or (self.raw,)

    @classmethod
    def from_thread(cls, rows, account=None):
        """Conversation : le message le plus récent la représente ; les indicateurs agrègent tous les messages."""
        if len(rows) == 1:
            return cls.from_row(rows[0], account)
        base = cls.from_row(rows[0], account)
        names = []
        for row in reversed(rows):  # Ordre d’arrivée dans la conversation.
            name, address = parseaddr(row.get('sender', ''))
            name = name.split()[0].strip('",') if name.strip() else (address.split('@')[0] or '?')
            if account and address.casefold() == account.email.casefold():
                name = 'moi'
            if name not in names:
                names.append(name)
        sender = ', '.join(names[:3]) + ('…' if len(names) > 3 else '')
        return cls(rows[0], sender, base.subject, base.preview, base.time,
                   any(row.get('unread') for row in rows), any(row.get('starred') for row in rows),
                   any(row.get('attachment') for row in rows), base.account_name, tuple(rows))

    @classmethod
    def from_row(cls, row, account=None):
        sender, address = parseaddr(row.get('sender', ''))
        date = row.get('date', '')
        try:
            date = parsedate_to_datetime(date).astimezone().strftime('%d/%m %H:%M')
        except (ValueError, TypeError, OverflowError):
            pass
        return cls(row, sender or address or row.get('sender', ''), row.get('subject', ''),
                   row.get('preview') or '', date,
                   bool(row.get('unread')), bool(row.get('starred')), bool(row.get('attachment')),
                   account.name if account else '')

DRAG_MIME = 'application/x-smail-messages'


class MessageList(QListWidget):
    """Garde les points d'entrée de sélection utilisés par les handlers existants.

    Les messages sélectionnés se glissent sur un dossier ; le glisser ne transporte que leurs
    identifiants (compte, dossier, UIDVALIDITY, UID), jamais leur contenu."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragOnly)
        self.setDefaultDropAction(Qt.MoveAction)
        self.header_clicked = None  # Rappel (groupe) : clic sur un titre de groupe de dates.
        self.checking = False  # Clic en cours sur une case à cocher (le relâchement ne doit rien sélectionner).

    def mousePressEvent(self, event):
        """Clic sur le titre d’un groupe (« HIER », « OCTOBRE 2026 »…) : repli ou dépli, sans sélectionner."""
        from mailclient.ui.components import ALWAYS_OPEN, COLLAPSED_ROLE, GROUP_ROLE, HEADER_HEIGHT, HEADER_ROLE
        index = self.indexAt(event.position().toPoint())
        if self.header_clicked and index.isValid() and index.data(HEADER_ROLE) and index.data(HEADER_ROLE) != ALWAYS_OPEN:
            on_title = event.position().y() < self.visualRect(index).top() + HEADER_HEIGHT
            if index.data(COLLAPSED_ROLE) or on_title:
                self.header_clicked(index.data(GROUP_ROLE))
                event.accept()
                return
        if event.button() == Qt.LeftButton and self.on_check_box(index, event.position()):
            from PySide6.QtCore import QItemSelectionModel
            self.checking = True
            self.selectionModel().setCurrentIndex(index, QItemSelectionModel.NoUpdate)
            self.selectionModel().select(index, QItemSelectionModel.Toggle)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.checking:
            self.checking = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if self.checking:  # Pas de glisser-déposer depuis une case à cocher.
            event.accept()
            return
        super().mouseMoveEvent(event)

    def on_check_box(self, index, position) -> bool:
        """Le clic tombe-t-il sur les initiales (case à cocher) d’un message ?"""
        from mailclient.ui.components import MailDelegate
        if not index.isValid() or not isinstance(index.data(Qt.UserRole), MessageRow) or index.data(__import__('mailclient.ui.components', fromlist=['COLLAPSED_ROLE']).COLLAPSED_ROLE):
            return False
        option_rect = self.visualRect(index)
        from PySide6.QtWidgets import QStyleOptionViewItem
        option = QStyleOptionViewItem()
        option.rect = option_rect
        delegate = self.itemDelegate()
        if isinstance(delegate, MailDelegate):
            option, position = delegate.virtual(option, position)  # Taille du texte de Windows.
        area = MailDelegate.check_rect(MailDelegate.message_rect(option, index))
        return area.adjusted(-6, -6, 6, 6).contains(position)

    def mimeTypes(self):
        return [DRAG_MIME]

    def mimeData(self, items):
        import json
        keys = [[row.get('account'), row.get('folder'), row.get('uidvalidity', ''), row.get('uid')]
                for item in items if isinstance(item.data(Qt.UserRole), MessageRow) for row in item.data(Qt.UserRole).rows]
        data = QMimeData()
        data.setData(DRAG_MIME, json.dumps(keys).encode('utf-8'))
        data.setText(count(len(keys), 'message'))
        return data
    def selectRow(self, index):
        self.setCurrentRow(index)

    def setRowCount(self, count):
        if count == 0:
            self.clear()


def human_size(size: int) -> str:
    """Taille lisible dans la langue de l’interface : « 1,4 Mo » / « 1.4 MB »."""
    from mailclient.i18n import current, tr
    text = tr('{valeur:.1f} Mo').format(valeur=size / 1048576) if size >= 1048576 else \
        tr('{valeur:.1f} Ko').format(valeur=max(size, 1) / 1024)
    return text.replace('.', ',') if current() == 'fr' else text


MONTHS = (N_('Janvier'), N_('Février'), N_('Mars'), N_('Avril'), N_('Mai'), N_('Juin'), N_('Juillet'), N_('Août'),
          N_('Septembre'), N_('Octobre'), N_('Novembre'), N_('Décembre'))  # Clés des groupes ; traduites à l’affichage.


def date_group(stamp: float, now=None) -> str:
    """Groupe de dates d’un message pour la liste : « Aujourd’hui », « Hier », « Cette semaine »…"""
    from datetime import datetime, timedelta
    if not stamp:
        return N_('Date inconnue')
    now = now or datetime.now()
    day, today = datetime.fromtimestamp(stamp).date(), now.date()
    if day >= today:
        return N_('Aujourd’hui')
    if day == today - timedelta(days=1):
        return N_('Hier')
    if day > today - timedelta(days=7):
        return N_('Cette semaine')
    if (day.year, day.month) == (today.year, today.month):
        return N_('Plus tôt ce mois-ci')
    return f'{MONTHS[day.month - 1]} {day.year}'


def count(number: int, singular: str, plural: str | None = None) -> str:
    """« 1 message », « 5 messages » : accord en nombre au lieu de « message(s) »."""
    from mailclient.i18n import tr
    return f'{number} {tr(singular) if abs(number) < 2 else tr(plural or singular + "s")}'  # Mots traduits.
