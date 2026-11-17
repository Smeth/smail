"""Adaptateurs de présentation ; aucun accès réseau ou au cache depuis le dessin."""
from dataclasses import dataclass
from email.utils import parseaddr, parsedate_to_datetime
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
                   row.get('preview') or (account.email if account else ''), date,
                   bool(row.get('unread')), bool(row.get('starred')), bool(row.get('attachment')),
                   account.name if account else '')

class MessageList(QListWidget):
    """Garde les points d'entrée de sélection utilisés par les handlers existants."""
    def selectRow(self, index):
        self.setCurrentRow(index)

    def setRowCount(self, count):
        if count == 0:
            self.clear()
