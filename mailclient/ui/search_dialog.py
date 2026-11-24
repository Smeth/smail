"""Filtres de recherche : formulaire qui écrit les opérateurs (de:, objet:, a:pj…) à la place de l’utilisateur."""
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QCheckBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit
from mailclient.core.search_query import parse


def quoted(value: str) -> str:
    value = value.replace('"', '').strip()
    return f'"{value}"' if any(char.isspace() for char in value) else value


def build_query(words='', sender='', recipient='', subject='', attachment=False, unread=False, starred=False,
                since=None, before=None) -> str:
    """Texte de recherche équivalent aux champs remplis (dates au format AAAA-MM-JJ)."""
    parts = [words.strip()] if words.strip() else []
    for operator, value in (('de', sender), ('à', recipient), ('objet', subject)):
        if value.strip():
            parts.append(f'{operator}:{quoted(value)}')
    if attachment:
        parts.append('a:pj')
    if unread:
        parts.append('est:nonlu')
    if starred:
        parts.append('est:étoilé')
    if since:
        parts.append(f'après:{since.isoformat()}')
    if before:
        parts.append(f'avant:{before.isoformat()}')
    return ' '.join(parts)


class SearchDialog(QDialog):
    def __init__(self, current='', parent=None):
        super().__init__(parent)
        self.setWindowTitle('Filtres de recherche')
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        query = parse(current)
        self.words = QLineEdit(' '.join(query.words))
        self.sender = QLineEdit(' '.join(query.sender))
        self.recipient = QLineEdit(' '.join(query.to))
        self.subject = QLineEdit(' '.join(query.subject))
        self.words.setPlaceholderText('Mots à trouver n’importe où')
        self.sender.setPlaceholderText('Nom ou adresse')
        self.recipient.setPlaceholderText('Nom ou adresse')
        self.attachment = QCheckBox('Avec pièce jointe')
        self.unread = QCheckBox('Non lus seulement')
        self.starred = QCheckBox('Suivis (étoilés) seulement')
        self.attachment.setChecked(query.attachment)
        self.unread.setChecked(query.unread is True)
        self.starred.setChecked(bool(query.starred))
        self.since_on, self.since = QCheckBox('Après le'), QDateEdit()
        self.before_on, self.before = QCheckBox('Avant le'), QDateEdit()
        for check, edit, value in ((self.since_on, self.since, query.since), (self.before_on, self.before, query.before)):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat('dd/MM/yyyy')
            edit.setDate(QDate(value.year, value.month, value.day) if value else QDate.currentDate())
            check.setChecked(value is not None)
            edit.setEnabled(value is not None)
            check.toggled.connect(edit.setEnabled)
        form.addRow('Contient', self.words)
        form.addRow('De', self.sender)
        form.addRow('À', self.recipient)
        form.addRow('Objet', self.subject)
        for widget in (self.attachment, self.unread, self.starred):
            form.addRow('', widget)
        for check, edit in ((self.since_on, self.since), (self.before_on, self.before)):
            row = QHBoxLayout()
            row.addWidget(check)
            row.addWidget(edit, 1)
            form.addRow(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Reset | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('Rechercher')
        buttons.button(QDialogButtonBox.Reset).setText('Effacer')
        buttons.button(QDialogButtonBox.Cancel).setText('Annuler')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Reset).clicked.connect(self.clear)
        form.addRow(buttons)

    def clear(self):
        for field in (self.words, self.sender, self.recipient, self.subject):
            field.clear()
        for check in (self.attachment, self.unread, self.starred, self.since_on, self.before_on):
            check.setChecked(False)

    def query(self) -> str:
        return build_query(self.words.text(), self.sender.text(), self.recipient.text(), self.subject.text(),
                           self.attachment.isChecked(), self.unread.isChecked(), self.starred.isChecked(),
                           self.since.date().toPython() if self.since_on.isChecked() else None,
                           self.before.date().toPython() if self.before_on.isChecked() else None)
