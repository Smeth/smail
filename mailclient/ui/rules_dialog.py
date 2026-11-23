"""Règles de tri, expéditeurs bloqués ou approuvés : éditeur de règle et page des préférences."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout, QWidget)
from mailclient.core import filters
from mailclient.ui.components import Button, label
from mailclient.ui.presentation import install_theme


class RuleDialog(QDialog):
    """Une condition, une action ; « Tous les comptes » ou un compte précis."""
    def __init__(self, database, accounts, rule=None, parent=None):
        super().__init__(parent)
        self.database, self.accounts = database, list(accounts)
        self.rule = None
        self.setWindowTitle('Règle de tri')
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.addWidget(label('Règle appliquée aux nouveaux messages de la réception', 'Bold', True))
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText('Facultatif : un nom est proposé automatiquement')
        self.account = QComboBox()
        self.account.addItem('Tous les comptes', '')
        for account in self.accounts:
            self.account.addItem(f'{account.name} — {account.email}', account.id)
        self.field, self.op, self.action = QComboBox(), QComboBox(), QComboBox()
        for box, choices in ((self.field, filters.FIELDS), (self.op, filters.OPERATORS), (self.action, filters.ACTIONS)):
            for key, text in choices.items():
                box.addItem(text, key)
        self.value = QLineEdit()
        self.value.setPlaceholderText('Ex. : newsletter@exemple.fr, @exemple.fr, Facture…')
        self.target = QComboBox()
        self.target.setEditable(False)
        self.enabled = QCheckBox('Règle active')
        self.enabled.setChecked(True)
        condition = QHBoxLayout()
        condition.addWidget(self.field)
        condition.addWidget(self.op)
        form.addRow('Nom', self.name)
        form.addRow('Compte', self.account)
        form.addRow('Si', condition)
        form.addRow('Texte', self.value)
        form.addRow('Alors', self.action)
        form.addRow('Dossier', self.target)
        layout.addLayout(form)
        layout.addWidget(self.enabled)
        self.error = QLabel()
        self.error.setObjectName('Small')
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Enregistrer')
        buttons.button(QDialogButtonBox.Cancel).setText('Annuler')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.account.currentIndexChanged.connect(self.fill_targets)
        self.action.currentIndexChanged.connect(self.update_target)
        rule = rule or {}
        self.original = rule
        self.name.setText(rule.get('name', '') if rule.get('id') else '')
        self.account.setCurrentIndex(max(0, self.account.findData(rule.get('account', ''))))
        for box, key in ((self.field, 'field'), (self.op, 'op'), (self.action, 'action')):
            box.setCurrentIndex(max(0, box.findData(rule.get(key, box.itemData(0)))))
        self.value.setText(rule.get('value', ''))
        self.enabled.setChecked(rule.get('enabled', True))
        self.fill_targets()
        if rule.get('target'):
            index = self.target.findData(rule['target'])
            if index < 0:
                self.target.addItem(rule['target'], rule['target'])
                index = self.target.count() - 1
            self.target.setCurrentIndex(index)
        self.update_target()

    def fill_targets(self, *_):
        account_id = self.account.currentData()
        self.target.clear()
        seen = set()
        for account in self.accounts:
            if account_id and account.id != account_id:
                continue
            for name, folder_label in self.database.cache_get('folders', account.id, []) or []:
                if name.upper() != 'INBOX' and name not in seen:
                    seen.add(name)
                    self.target.addItem(folder_label if folder_label == name else f'{folder_label} — {name}', name)

    def update_target(self, *_):
        self.target.setEnabled(self.action.currentData() == 'move')

    def save(self):
        try:
            values = dict(name=self.name.text(), account=self.account.currentData(), field=self.field.currentData(),
                          op=self.op.currentData(), value=self.value.text(), action=self.action.currentData(),
                          target=self.target.currentData() if self.action.currentData() == 'move' else '',
                          enabled=self.enabled.isChecked())
            if self.original.get('id'):
                self.rule = filters.validate_rule(dict(self.original, **values))
            else:
                self.rule = filters.new_rule(**values)
        except ValueError as error:
            self.error.setText(str(error))
            return
        self.accept()


class FiltersPage(QWidget):
    """Page des préférences ; chaque modification est enregistrée immédiatement."""
    def __init__(self, database, accounts, apply_now=None, parent=None):
        super().__init__(parent)
        self.database, self.accounts, self.apply_now = database, list(accounts), apply_now
        self.theme = install_theme(database)
        self.data = filters.load(database)
        box = QVBoxLayout(self)
        box.addWidget(label('Règles et courrier indésirable', 'Title', True))
        box.addWidget(label('Appliqués automatiquement aux nouveaux messages de la réception, lors de la synchronisation. '
                            'Chaque modification de cette page est enregistrée immédiatement.', 'Subtitle', True))
        box.addWidget(label('Règles', 'Bold'))
        self.rules = QListWidget()
        self.rules.setAccessibleName('Règles de tri, case à cocher pour activer')
        self.rules.setFixedHeight(130)
        self.rules.setObjectName('FramedList')
        self.rules.itemChanged.connect(self.toggled)
        self.rules.itemDoubleClicked.connect(lambda item: self.edit_rule())
        box.addWidget(self.rules)
        row = QHBoxLayout()
        for text, icon_name, slot in (('Ajouter…', 'plus', self.add_rule), ('Modifier…', 'file-pen-line', self.edit_rule),
                                      ('Supprimer', 'trash-2', self.delete_rule), ('Appliquer maintenant', 'filter', self.run_now)):
            button = Button(text, self.theme, icon_name, 'Secondary')
            button.clicked.connect(slot)
            row.addWidget(button)
            if text == 'Appliquer maintenant':
                self.apply_button = button
                button.setToolTip('Applique les règles et les blocages à toute la réception synchronisée')
                button.setEnabled(apply_now is not None)
        row.addStretch()
        box.addLayout(row)
        self.spam_headers = QCheckBox('Déplacer vers les indésirables les messages signalés comme spam par le serveur')
        self.spam_headers.setChecked(self.data.get('spam_headers', True))
        self.spam_headers.toggled.connect(self.spam_toggled)
        box.addWidget(self.spam_headers)
        lists = QHBoxLayout()
        self.blocked = self.sender_list(lists, 'Expéditeurs bloqués', 'blocked', 'Leurs messages vont directement dans les indésirables.')
        self.safe = self.sender_list(lists, 'Expéditeurs approuvés', 'safe', 'Jamais traités comme indésirables.')
        box.addLayout(lists)
        box.addStretch()
        self.refresh()

    def sender_list(self, parent_layout, title, key, hint):
        column = QVBoxLayout()
        column.addWidget(label(title, 'Bold'))
        column.addWidget(label(hint, 'Small', True))
        widget = QListWidget()
        widget.setAccessibleName(title)
        widget.setFixedHeight(110)
        widget.setObjectName('FramedList')
        column.addWidget(widget)
        entry = QLineEdit()
        entry.setPlaceholderText('nom@domaine.fr ou @domaine.fr')
        entry.setAccessibleName(f'Ajouter à {title.lower()}')
        add = Button('', self.theme, 'plus', 'Secondary', 'Ajouter (Entrée)')
        remove = Button('', self.theme, 'x', 'Secondary', 'Retirer l’adresse sélectionnée')
        add.setAccessibleName('Ajouter')
        remove.setAccessibleName('Retirer')
        controls = QHBoxLayout()
        controls.addWidget(entry, 1)
        controls.addWidget(add)
        controls.addWidget(remove)
        column.addLayout(controls)
        column.addStretch()
        add.clicked.connect(lambda: self.add_sender(key, entry))
        entry.returnPressed.connect(lambda: self.add_sender(key, entry))
        remove.clicked.connect(lambda: self.remove_sender(key, widget))
        parent_layout.addLayout(column, 1)
        return widget

    def refresh(self):
        self.rules.blockSignals(True)
        self.rules.clear()
        names = {account.id: account.name for account in self.accounts}
        for rule in self.data['rules']:
            scope = names.get(rule.get('account'), 'tous les comptes') if rule.get('account') else 'tous les comptes'
            item = QListWidgetItem(f'{rule["name"]}  ·  {scope}')
            item.setToolTip(filters.describe(rule))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if rule.get('enabled', True) else Qt.Unchecked)
            self.rules.addItem(item)
        if not self.data['rules']:
            placeholder = QListWidgetItem('Aucune règle. « Ajouter… » ou, dans un message : Message › Créer une règle.')
            placeholder.setFlags(Qt.NoItemFlags)
            self.rules.addItem(placeholder)
        self.rules.blockSignals(False)
        for widget, key in ((self.blocked, 'blocked'), (self.safe, 'safe')):
            widget.clear()
            widget.addItems(self.data[key])

    def persist(self):
        filters.save(self.database, self.data)
        self.refresh()

    def selected_rule(self):
        row = self.rules.currentRow()
        return row if 0 <= row < len(self.data['rules']) else None

    def add_rule(self):
        dialog = RuleDialog(self.database, self.accounts, parent=self)
        if dialog.exec():
            self.data['rules'].append(dialog.rule)
            self.persist()

    def edit_rule(self):
        index = self.selected_rule()
        if index is None:
            return
        dialog = RuleDialog(self.database, self.accounts, self.data['rules'][index], parent=self)
        if dialog.exec():
            self.data['rules'][index] = dialog.rule
            self.persist()

    def delete_rule(self):
        index = self.selected_rule()
        if index is None:
            return
        if QMessageBox.question(self, 'Supprimer la règle', f'Supprimer la règle « {self.data["rules"][index]["name"]} » ?',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            del self.data['rules'][index]
            self.persist()

    def toggled(self, item):
        index = self.rules.row(item)
        if 0 <= index < len(self.data['rules']):
            self.data['rules'][index]['enabled'] = item.checkState() == Qt.Checked
            filters.save(self.database, self.data)

    def spam_toggled(self, checked):
        self.data['spam_headers'] = checked
        filters.save(self.database, self.data)

    def add_sender(self, key, entry):
        try:
            value = filters.normalize_sender(entry.text())
        except ValueError as error:
            QMessageBox.warning(self, 'Adresse invalide', str(error))
            return
        other = 'safe' if key == 'blocked' else 'blocked'
        self.data[key] = sorted(set(self.data[key]) | {value})
        self.data[other] = [item for item in self.data[other] if item != value]  # Une adresse n’est jamais dans les deux listes.
        entry.clear()
        self.persist()

    def remove_sender(self, key, widget):
        item = widget.currentItem()
        if item:
            self.data[key] = [value for value in self.data[key] if value != item.text()]
            self.persist()

    def run_now(self):
        if self.apply_now and QMessageBox.question(
                self, 'Appliquer maintenant', 'Appliquer les règles et les blocages à tous les messages déjà synchronisés de la réception ?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.apply_now()
