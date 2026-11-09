"""Exécution des opérations réseau hors du fil graphique."""
import imaplib
import smtplib
import socket
import logging
from PySide6.QtCore import QObject, QRunnable, Signal, QThreadPool, QThread
import threading
from mailclient.core.tls_policy import CertificateAlert

def friendly_error(error: Exception) -> str:
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return 'Tous les destinataires ont été refusés par le serveur SMTP.'
    if isinstance(error, smtplib.SMTPDataError):
        return 'Le serveur SMTP a refusé le message. Vérifiez sa taille et la politique d’envoi.'
    if isinstance(error, smtplib.SMTPSenderRefused):
        return 'Le serveur SMTP a refusé l’adresse expéditrice.'
    if isinstance(error, smtplib.SMTPNotSupportedError):
        return 'Le serveur ne propose pas le mécanisme d’authentification nécessaire.'
    if isinstance(error, (imaplib.IMAP4.error, smtplib.SMTPAuthenticationError)):
        return 'Le serveur a refusé la demande. Vérifiez les identifiants, le mot de passe d’application et les autorisations IMAP/SMTP.'
    if isinstance(error, (TimeoutError, socket.timeout)):
        return 'Délai de connexion dépassé.'
    if isinstance(error, OSError):
        return 'Serveur injoignable ou connexion interrompue. Vérifiez le réseau et les paramètres.'
    if isinstance(error, (RuntimeError, ValueError)):
        return str(error)
    return 'L’opération a échoué. Vérifiez les paramètres et réessayez.'

class Signals(QObject):
    done = Signal(object)
    error = Signal(object)

class Task(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = Signals()

    def run(self):
        try:
            result = self.function()
        except Exception as error:
            logging.getLogger('smail').warning('Échec tâche (%s)', type(error).__name__)
            self.signals.error.emit(error)
        else:
            self.signals.done.emit(result)

class Runner(QObject):
    def __init__(self, parent, tls):
        super().__init__(parent)
        self.tls = tls
        self.tasks = set()

    def run(self, function, done, failed):
        task = Task(function)
        self.tasks.add(task)
        def success(result):
            self.tasks.discard(task)
            done(result)
        def failure(error):
            self.tasks.discard(task)
            if isinstance(error, CertificateAlert):
                from mailclient.ui.cert_dialog import CertificateDialog
                dialog = CertificateDialog(error, self.parent())
                if dialog.exec():
                    self.tls.approve(error, dialog.remember.isChecked())
                    self.run(function, done, failed)
                    return
                failed('Connexion annulée : certificat non approuvé.')
            else:
                failed(friendly_error(error))
        task.signals.done.connect(success)
        task.signals.error.connect(failure)
        QThreadPool.globalInstance().start(task)

class SyncThread(QThread):
    updated = Signal(str, int)
    problem = Signal(object)

    def __init__(self, service, accounts, limit, parent=None):
        super().__init__(parent)
        self.service, self.accounts, self.limit = service, list(accounts), limit
        self.cancelled = threading.Event()

    def stop(self):
        self.cancelled.set()

    def run(self):
        for account in self.accounts:
            if self.cancelled.is_set():
                break
            try:
                count = self.service.sync_account(account, self.cancelled, self.limit)
                self.updated.emit(account.id, count)
            except Exception as error:
                self.problem.emit(error)

class IdleThread(QThread):
    changed = Signal()
    problem = Signal(object)

    def __init__(self, service, account, parent=None):
        super().__init__(parent)
        self.service, self.account = service, account
        self.cancelled = threading.Event()

    def stop(self):
        self.cancelled.set()

    def run(self):
        delay = 2
        while not self.cancelled.is_set():
            try:
                supported, changed = self.service.client(self.account).idle_wait(self.cancelled)
                if not supported:
                    return  # La synchronisation périodique reste active.
                if changed and not self.cancelled.is_set():
                    self.changed.emit()
                delay = 2
                self.cancelled.wait(1)
            except CertificateAlert as error:
                self.problem.emit(error)
                return  # Une décision explicite est nécessaire avant toute reconnexion.
            except Exception:
                self.cancelled.wait(delay)
                delay = min(delay * 2, 60)
