"""Autocomplétion des destinataires : complète l’adresse en cours après la dernière virgule."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCompleter


class AddressCompleter(QCompleter):
    def __init__(self, entries, parent=None):
        super().__init__(list(entries), parent)
        self.setCaseSensitivity(Qt.CaseInsensitive)
        self.setFilterMode(Qt.MatchContains)
        self.setCompletionMode(QCompleter.PopupCompletion)
        self.setMaxVisibleItems(8)

    def splitPath(self, path):
        # Seule l’adresse en cours de saisie est comparée au carnet.
        return [path.split(',')[-1].strip()]

    def pathFromIndex(self, index):
        value = super().pathFromIndex(index)
        widget = self.widget()
        text = widget.text() if widget is not None else ''
        head = text.rsplit(',', 1)[0].strip() if ',' in text else ''
        return (head + ', ' if head else '') + value + ', '
