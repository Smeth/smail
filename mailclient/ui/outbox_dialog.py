"""Envois programmés : consulter, modifier (retour en brouillon) ou supprimer."""
from mailclient.i18n import tr
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout
from mailclient.core import scheduler
from mailclient.ui.components import Button, label
from mailclient.ui.presentation import install_theme

STATUS = {'scheduled': tr('Programmé'), 'sending': tr('Envoi en cours'), 'failed': tr('Échec — non renvoyé'),
          'partial': tr('Envoi partiel'), 'uncertain': tr('État incertain — vérifiez vos Envoyés')}


class OutboxDialog(QDialog):
    def __init__(self, database, accounts, parent=None):
        super().__init__(parent)
        self.database = database
        self.accounts = {account.id: account for account in accounts}
        self.reopen = None  # Brouillon à rouvrir dans une fenêtre de rédaction.
        theme = install_theme(database)
        self.setWindowTitle(tr('Envois programmés'))
        self.setMinimumSize(620, 380)
        layout = QVBoxLayout(self)
        layout.addWidget(label(tr('Envois programmés'), 'Title'))
        layout.addWidget(label(tr('Envoyés par Smail à l’heure prévue s’il est ouvert (sinon au prochain démarrage). On y retrouve aussi '
                               'les envois en échec ou incertains. Un échec n’est jamais renvoyé automatiquement : « Modifier… » '
                               'rouvre le message pour le corriger et le renvoyer.'), 'Subtitle', True))
        self.list = QListWidget()
        self.list.setObjectName('FramedList')
        self.list.setAccessibleName(tr('Envois programmés'))
        layout.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.edit = Button(tr('Modifier…'), theme, 'file-pen-line', 'Secondary', tr('Annule la programmation et rouvre le message en brouillon'))
        self.remove = Button(tr('Supprimer'), theme, 'trash-2', 'QuietDanger')
        close = Button(tr('Fermer'), theme, role='Secondary')
        self.edit.clicked.connect(self.edit_item)
        self.remove.clicked.connect(self.remove_item)
        close.clicked.connect(self.accept)
        for widget in (self.edit, self.remove):
            row.addWidget(widget)
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)
        self.list.currentRowChanged.connect(self.update_buttons)
        self.refresh()

    def refresh(self):
        self.items = scheduler.outbox(self.database)
        self.list.clear()
        for item in self.items:
            state = item['state']
            moment = scheduler.parse(item['send_at']).astimezone()
            account = self.accounts.get(item['account'])
            entry = QListWidgetItem(f'{moment:%d/%m %H:%M} · {STATUS.get(item["status"], item["status"])} · '
                                    f'{state.get("subject") or "(Sans objet)"} → {state.get("to", "")}')
            entry.setToolTip((account.email if account else tr('Compte supprimé')) + ('\n' + item['error'] if item.get('error') else ''))
            self.list.addItem(entry)
        if not self.items:
            empty = QListWidgetItem(tr('Aucun envoi programmé. Dans une rédaction, utilisez le bouton horloge « Envoyer plus tard ».'))
            empty.setFlags(Qt.NoItemFlags)
            self.list.addItem(empty)
        self.update_buttons()

    def current(self):
        row = self.list.currentRow()
        return self.items[row] if 0 <= row < len(self.items) else None

    def update_buttons(self, *_):
        item = self.current()
        self.edit.setEnabled(bool(item) and item['status'] != 'sending' and item['account'] in self.accounts)
        self.remove.setEnabled(bool(item) and item['status'] != 'sending')

    def edit_item(self):
        item = self.current()
        if not item:
            return
        if item['status'] in {'partial', 'uncertain'} and QMessageBox.question(
                self, tr('Modifier'), tr('Ce message a peut-être déjà été reçu par certains destinataires. Le rouvrir quand même en brouillon ?'),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        scheduler.cancel(self.database, item['id'])
        draft = dict(item['state'], id=item['id'], account=item['account'], attachments=item['files'])
        self.database.cache_put('draft', item['id'], draft, item['account'])
        self.reopen = draft
        self.accept()

    def remove_item(self):
        item = self.current()
        if item and QMessageBox.question(self, tr('Supprimer'), tr('Supprimer définitivement cet envoi programmé ?'),
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            scheduler.cancel(self.database, item['id'])
            self.refresh()
