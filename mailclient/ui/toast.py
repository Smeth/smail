"""Notification flottante en bas de la fenêtre : « Message envoyé », « 3 messages déplacés — Annuler »…

Plus visible que la barre d’état, elle disparaît seule après quelques secondes (plus longtemps si elle propose
une action) ; une nouvelle notification remplace la précédente. Le texte reste aussi dans la barre d’état."""
from mailclient.i18n import tr
from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton


class Toast(QFrame):
    def __init__(self, host, colors=None):
        super().__init__(host)
        self.host = host
        self.colors = colors or (lambda: {'bg': '#FFFFFF'})  # Couleurs du thème courant (icône de fermeture).
        self.setObjectName('Toast')
        self.setAccessibleName(tr('Notification'))
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 8, 8, 8)
        row.setSpacing(6)
        self.text = QLabel()
        self.text.setTextFormat(Qt.PlainText)
        self.text.setWordWrap(True)
        self.action = QPushButton()
        self.action.setCursor(Qt.PointingHandCursor)
        self.close_button = QPushButton()  # Icône « x » de l’application : le caractère ✕ manque dans certaines polices.
        self.close_button.setFixedWidth(32)
        self.close_button.setAccessibleName(tr('Fermer la notification'))
        self.close_button.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.text, 1)
        row.addWidget(self.action)
        row.addWidget(self.close_button)
        self.callback = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self.action.clicked.connect(self.run_action)
        self.close_button.clicked.connect(self.hide)
        self.watcher = _ResizeWatcher(self)
        host.installEventFilter(self.watcher)
        self.hide()

    def show_message(self, text, action=None, callback=None, kind='info', seconds=None):
        self.text.setText(text)
        self.callback = callback if action else None
        self.action.setText(action or '')
        self.action.setVisible(bool(action))
        self.setProperty('kind', kind)
        from mailclient.ui.icons import icon
        self.close_button.setIcon(icon('x', '#FFFFFF' if kind == 'error' else self.colors()['bg'], 16))
        self.style().unpolish(self)
        self.style().polish(self)
        self.timer.start(int((seconds or (10 if action else 5)) * 1000))
        self.show()
        self.place()
        self.raise_()

    def run_action(self):
        callback, self.callback = self.callback, None
        self.hide()
        if callback:
            callback()

    def place(self):
        width = min(560, max(280, self.host.width() - 40))
        self.setFixedWidth(width)
        self.adjustSize()
        self.move((self.host.width() - width) // 2, self.host.height() - self.height() - 24)


class _ResizeWatcher(QObject):
    def __init__(self, toast):
        super().__init__(toast)
        self.toast = toast

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize and self.toast.isVisible():
            self.toast.place()
        return False
