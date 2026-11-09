from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QLineEdit, QListWidget, QListWidgetItem
from mailclient.ui.components import label, Card, Button, later
from mailclient.ui.theme import VARIANTS

class Dialog(QDialog):
    def __init__(self, theme, title, subtitle, parent=None, size=(800,700)):
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle(title + ' · Maquette Smail')
        self.resize(*size)
        self.setMinimumSize(min(size[0],660), min(size[1],480))
        self.outer = QVBoxLayout(self)
        margin = {1:20, 2:28, 3:18}[theme.variant]
        self.outer.setContentsMargins(margin,margin,margin,margin)
        self.eyebrow = label('', 'Eyebrow')
        self.outer.addWidget(self.eyebrow)
        self.outer.addWidget(label(title, 'DialogTitle'))
        self.outer.addWidget(label(subtitle, 'Subtitle', True))
        self.content = Card(margin=20 if theme.variant != 2 else 28)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.content)
        self.outer.addWidget(scroll, 1)
        self.theme.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.eyebrow.setText(f'SMAIL  /  0{self.theme.variant} · {VARIANTS[self.theme.variant][0].upper()}')

    def footer(self, primary='Enregistrer', callback=None, cancel='Annuler'):
        row = QHBoxLayout()
        row.addWidget(label('Données fictives · aucune opération réelle', 'Small'))
        row.addStretch()
        back = Button(cancel, self.theme, role='Secondary')
        self.cancel_button = back
        back.clicked.connect(self.reject)
        back.setDefault(True)
        row.addWidget(back)
        self.primary = Button(primary, self.theme, role='Primary')
        self.primary.setAutoDefault(False)
        self.primary.clicked.connect(callback or self.accept)
        row.addWidget(self.primary)
        self.outer.addLayout(row)
        return self.primary

class CommandPalette(Dialog):
    def __init__(self, theme, commands, parent=None):
        super().__init__(theme, 'Que souhaitez-vous faire ?', 'Tapez une action, puis Entrée. Les flèches parcourent les résultats.', parent, (760,610))
        self.commands = commands
        self.search = QLineEdit()
        self.search.setObjectName('CommandInput')
        self.search.setPlaceholderText('Rechercher une commande…')
        self.search.setAccessibleName('Rechercher une commande')
        self.content.box.addWidget(self.search)
        self.list = QListWidget()
        self.list.setObjectName('Commands')
        self.list.setAccessibleName('Commandes disponibles')
        self.content.box.addWidget(self.list,1)
        self.content.box.addWidget(label('↑ ↓  choisir       Entrée  exécuter       Échap  fermer', 'Small'))
        self.search.textChanged.connect(self.filter)
        self.search.returnPressed.connect(self.execute)
        self.list.itemActivated.connect(lambda item: self.execute())
        self.search.installEventFilter(self)
        self.filter('')
        later(self,0,self.search.setFocus)

    def filter(self, text):
        self.list.clear()
        for name,shortcut,callback in self.commands:
            if text.casefold() in name.casefold():
                item = QListWidgetItem(f'{name}    {shortcut}')
                item.setData(Qt.UserRole,callback)
                self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def execute(self):
        item = self.list.currentItem()
        if item:
            callback = item.data(Qt.UserRole)
            self.accept()
            callback()

    def eventFilter(self, obj, event):
        if obj == self.search and event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Up,Qt.Key_Down):
            delta = 1 if event.key() == Qt.Key_Down else -1
            self.list.setCurrentRow(max(0,min(self.list.count()-1,self.list.currentRow()+delta)))
            return True
        return super().eventFilter(obj,event)
