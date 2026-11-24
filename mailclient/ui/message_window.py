"""Message ouvert dans sa propre fenêtre : même lecteur isolé, réponses renvoyées à la fenêtre principale."""
from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QVBoxLayout, QWidget
from mailclient.ui.mail_view import MailView


class MessageWindow(QWidget):
    """Lecture seule et réponses ; le rangement (archiver, supprimer…) reste dans la liste principale."""
    composeRequested = Signal(object, object, str)  # mail, compte, mode
    closed = Signal(object)

    def __init__(self, mail, account, dark=False):
        super().__init__(None)
        self.mail, self.account = mail, account
        self.setWindowTitle(mail.subject or '(Sans objet)')
        self.resize(900, 760)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        self.reader = MailView()
        self.reader.set_dark(dark)
        layout.addWidget(self.reader)
        for action in self.reader.more_menu.actions()[:4]:
            action.setVisible(False)  # Archiver, supprimer, étoiler, lu : depuis la liste uniquement.
        self.reader.replyRequested.connect(lambda: self.composeRequested.emit(self.mail, self.account, 'reply'))
        self.reader.replyAllRequested.connect(lambda: self.composeRequested.emit(self.mail, self.account, 'reply_all'))
        self.reader.forwardRequested.connect(lambda: self.composeRequested.emit(self.mail, self.account, 'forward'))
        self.reader.display(mail)
        self.reader.set_actions_enabled(True)
        QShortcut(QKeySequence('Ctrl+P'), self, activated=self.reader.print_message)
        QShortcut(QKeySequence('Escape'), self, activated=self.close)

    def closeEvent(self, event):
        self.reader.shutdown()  # La page WebEngine est détruite avant son profil.
        self.closed.emit(self)
        super().closeEvent(event)
