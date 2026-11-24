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
        # Texte réellement saisi. Quand une suggestion est survolée ou sélectionnée, Qt l’insère déjà dans le
        # champ ; repartir de ce texte ajouterait l’adresse une seconde fois (« kana…, kana…, »).
        self.typed = None
        self.produced = set()
        if parent is not None and hasattr(parent, 'textChanged'):
            parent.textChanged.connect(self.remember)

    def remember(self, text):
        if text in self.produced:
            return  # Texte inséré par la complétion elle-même.
        self.produced.clear()
        self.typed = text

    def splitPath(self, path):
        # Seule l’adresse en cours de saisie est comparée au carnet.
        return [path.split(',')[-1].strip()]

    def pathFromIndex(self, index):
        value = super().pathFromIndex(index)
        widget = self.widget()
        text = self.typed if self.typed is not None else (widget.text() if widget is not None else '')
        head = text.rsplit(',', 1)[0].strip() if ',' in text else ''
        result = (head + ', ' if head else '') + value + ', '
        self.produced.add(result)
        return result
