"""Mises à jour automatiques : vérification en arrière-plan, téléchargement vérifié, installation à la fermeture."""
import logging
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from mailclient import __version__
from mailclient.core import updater

CHECK_DELAY = 45_000                 # Après le démarrage, pour ne pas ralentir l’ouverture.
CHECK_INTERVAL = 6 * 60 * 60_000     # Puis toutes les 6 heures (Smail reste souvent ouvert des jours).
MAX_ATTEMPTS = 2                     # Installations silencieuses tentées pour une même version.
RELEASES_PAGE = f'https://github.com/{updater.REPOSITORY}/releases/latest'


class UpdateManager(QObject):
    def __init__(self, window, database, runner, directory: Path, current=__version__):
        super().__init__(window)
        self.window, self.database, self.runner = window, database, runner
        self.directory, self.current = directory / 'updates', current
        self.ready = None          # (version, chemin) d’un installateur vérifié, installé à la fermeture.
        self.checking = False
        self.relaunch = False
        self.log = logging.getLogger('smail')
        self.timer = QTimer(self)
        self.timer.setInterval(CHECK_INTERVAL)
        self.timer.timeout.connect(lambda: self.check())
        self.forget_installed()

    def enabled(self):
        return bool(self.database.setting('auto_update', True))

    def start(self):
        if self.enabled():
            QTimer.singleShot(CHECK_DELAY, self, lambda: self.check())
            self.timer.start()

    def settings_changed(self):
        if self.enabled() and not self.timer.isActive():
            self.start()
        elif not self.enabled():
            self.timer.stop()

    def forget_installed(self):
        """Après une mise à jour réussie, l’état mémorisé de l’ancienne version est effacé."""
        pending = self.database.setting('update_pending')
        if pending and not self.is_newer(pending.get('version')):
            self.database.set_setting('update_pending', None)
            if updater.parse_version(pending['version']) == updater.parse_version(self.current):
                self.log.info('Mise à jour %s installée', self.current)

    def is_newer(self, version):
        try:
            return updater.newer(version or '', self.current)
        except updater.UpdateError:
            return False

    def attempts(self, version):
        pending = self.database.setting('update_pending') or {}
        return pending.get('attempts', 0) if pending.get('version') == version else 0

    def check(self, manual=False):
        if self.checking or self.window.quitting:
            return
        self.checking = True
        installable = updater.installed_copy()
        directory, current = self.directory, self.current
        def operation():
            update = updater.check(current)
            if update is None:
                return None, None
            return update, (updater.download(update, directory, cancelled=lambda: self.window.quitting) if installable else None)
        def done(result):
            self.checking = False
            update, path = result
            if update is None:
                if manual:
                    self.window.statusBar().showMessage(f'Smail {self.current} est à jour.')
                return
            if path is None:
                self.window.show_update_banner(f'Smail {update.version} est disponible',
                                               'Cette copie de Smail ne se met pas à jour seule (lancée depuis les sources ou un dossier copié).',
                                               'Télécharger', lambda: QDesktopServices.openUrl(QUrl(RELEASES_PAGE)))
                return
            attempts = self.attempts(update.version)
            self.database.set_setting('update_pending', dict(version=update.version, file=path.name, sha256=update.sha256,
                                                             attempts=attempts))
            if attempts >= MAX_ATTEMPTS:
                self.window.show_update_banner(f'La mise à jour vers Smail {update.version} n’a pas pu s’installer',
                                               'Installez-la manuellement depuis la page des versions.',
                                               'Ouvrir la page', lambda: QDesktopServices.openUrl(QUrl(RELEASES_PAGE)))
                return
            self.ready = (update.version, path)
            self.log.info('Mise à jour %s téléchargée et vérifiée', update.version)
            self.window.show_update_banner(f'Smail {update.version} est prêt',
                                           'La mise à jour s’installera automatiquement à la fermeture de Smail.',
                                           'Redémarrer maintenant', self.restart_now)
            if self.window.tray and self.database.setting('notifications', True):
                from PySide6.QtWidgets import QSystemTrayIcon
                self.window.tray.showMessage('Smail', f'Mise à jour {update.version} prête : elle s’installera à la fermeture.',
                                             QSystemTrayIcon.Information, 6000)
        def failed(message):
            self.checking = False
            self.log.warning('Vérification des mises à jour impossible : %s', message)
            if manual:
                self.window.statusBar().showMessage('Vérification des mises à jour impossible : ' + message)
        self.window.statusBar().showMessage('Recherche de mises à jour…') if manual else None
        self.runner.run(operation, done, failed)

    def restart_now(self):
        self.relaunch = True
        self.window.request_quit()

    def install_on_exit(self):
        """Appelé quand Smail se ferme pour de bon : lance l’installateur vérifié, s’il y en a un."""
        if not self.ready or not updater.installed_copy():
            return False
        version, path = self.ready
        try:
            pending = self.database.setting('update_pending') or {}
            if pending.get('version') != version or not path.exists() or updater.file_digest(path) != pending.get('sha256'):
                return False  # Fichier modifié depuis la vérification : on ne lance rien.
            self.database.set_setting('update_pending', dict(pending, attempts=pending.get('attempts', 0) + 1))
            updater.install(path, self.relaunch)
            self.log.info('Installation de la mise à jour %s lancée', version)
            return True
        except Exception as error:
            self.log.warning('Installation de la mise à jour impossible (%s)', type(error).__name__)
            return False
