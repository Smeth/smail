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
