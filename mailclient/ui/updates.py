"""Mises à jour : vérification en arrière-plan, téléchargement vérifié (après accord, ou automatique), installation
à la fermeture ou avec « Redémarrer maintenant »."""
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
# « ask » : prévenir et attendre l’accord avant de télécharger ; « auto » : télécharger seul et installer à la
# fermeture ; « off » : aucune vérification.
MODES = ('ask', 'auto', 'off')
MODE_LABELS = {'ask': 'Me demander avant de télécharger et d’installer',
               'auto': 'Automatiques : téléchargées seules, installées à la fermeture de Smail',
               'off': 'Désactivées'}


def update_mode(database) -> str:
    """Mode choisi ; l’ancien réglage « auto_update » désactivé est repris comme « off »."""
    stored = database.setting('update_mode')
    if stored in MODES:
        return stored
    return 'ask' if database.setting('auto_update', True) else 'off'


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

    def mode(self):
        return update_mode(self.database)

    def enabled(self):
        # Version du Microsoft Store : le Store installe lui-même les mises à jour.
        return self.mode() != 'off' and not updater.packaged()

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
        if self.window.quitting:
            return
        if updater.packaged():
            if manual:
                self.inform('Mises à jour', 'Cette copie de Smail vient du Microsoft Store : ses mises à jour sont '
                            'installées par le Store (Microsoft Store › Bibliothèque › Obtenir les mises à jour).')
            return
        if self.checking:
            if manual:
                self.inform('Mises à jour', 'Une recherche de mise à jour est déjà en cours. Réessayez dans un instant.')
            return
        self.checking = True
        installable = updater.installed_copy()
        fetch = installable and self.mode() == 'auto'  # Mode « me demander » : rien n’est téléchargé sans accord.
        directory, current = self.directory, self.current
        def operation():
            update = updater.check(current)
            if update is None:
                return None, None
            return update, (updater.download(update, directory, cancelled=lambda: self.window.quitting) if fetch else None)
        def done(result):
            self.checking = False
            update, path = result
            if update is None:
                if manual:
                    self.window.statusBar().showMessage(f'Smail {self.current} est à jour.')
                    self.inform('Smail est à jour', f'Vous utilisez la dernière version publiée de Smail ({self.current}).')
                return
            if not installable:
                if manual:
                    self.inform('Nouvelle version disponible',
                                f'Smail {update.version} est disponible (vous avez la version {self.current}).\n\n'
                                'Cette copie (lancée depuis les sources ou un dossier copié) ne se met pas à jour seule : '
                                'utilisez le bouton « Télécharger » du bandeau.')
                self.window.show_update_banner(f'Smail {update.version} est disponible',
                                               'Cette copie de Smail ne se met pas à jour seule (lancée depuis les sources ou un dossier copié).',
                                               'Télécharger', lambda: QDesktopServices.openUrl(QUrl(RELEASES_PAGE)))
                return
            if path is None:
                self.offer(update, manual)
                return
            self.prepared(update, path, manual)
        def failed(message):
            self.checking = False
            self.log.warning('Vérification des mises à jour impossible : %s', message)
            if manual:
                self.window.statusBar().showMessage('Vérification des mises à jour impossible : ' + message)
                self.inform('Vérification impossible', 'Smail n’a pas pu vérifier les mises à jour.\n\n' + message)
        self.window.statusBar().showMessage('Recherche de mises à jour…') if manual else None
        self.runner.run(operation, done, failed)

    @staticmethod
    def megabytes(size):
        return f'{size / 1_000_000:.0f} Mo'

    def offer(self, update, manual=False):
        """Mode « me demander » : nouvelle version signalée, téléchargée seulement après accord."""
        size = self.megabytes(update.size)
        self.window.show_update_banner(f'Smail {update.version} est disponible',
                                       f'Rien n’est téléchargé sans votre accord ({size}). Vous gardez la version {self.current} '
                                       'tant que vous ne cliquez pas.',
                                       'Télécharger et installer', lambda: self.accept(update))
        if manual:
            notes = '\n'.join(line for line in update.notes.splitlines() if line.strip())[:700]
            text = (f'Smail {update.version} est disponible (vous avez la version {self.current}).\n\n'
                    + (notes + '\n\n' if notes else '')
                    + f'Télécharger maintenant ({size}) ? L’installation se fera à la fermeture de Smail, '
                      'ou tout de suite avec « Redémarrer maintenant ».')
            if self.ask('Nouvelle version disponible', text):
                self.accept(update)

    def accept(self, update):
        """Téléchargement accepté : fichier vérifié (signature et empreinte), puis installation proposée."""
        if self.checking:
            return
        self.checking = True
        directory = self.directory
        self.window.show_update_banner(f'Téléchargement de Smail {update.version}…',
                                       'Vous pouvez continuer à travailler. Le fichier est vérifié avant toute installation.',
                                       None, None)
        def done(path):
            self.checking = False
            self.prepared(update, path, False)
        def failed(message):
            self.checking = False
            self.log.warning('Téléchargement de la mise à jour impossible : %s', message)
            self.window.show_update_banner(f'Téléchargement de Smail {update.version} impossible', message,
                                           'Réessayer', lambda: self.accept(update))
        self.runner.run(lambda: updater.download(update, directory, cancelled=lambda: self.window.quitting), done, failed)

    def prepared(self, update, path, manual):
        """Installateur téléchargé et vérifié : installé à la fermeture ou avec « Redémarrer maintenant »."""
        attempts = self.attempts(update.version)
        self.database.set_setting('update_pending', dict(version=update.version, file=path.name, sha256=update.sha256,
                                                         attempts=attempts))
        if attempts >= MAX_ATTEMPTS:
            self.window.show_update_banner(f'La mise à jour vers Smail {update.version} n’a pas pu s’installer',
                                           'Installez-la manuellement depuis la page des versions.',
                                           'Ouvrir la page', lambda: QDesktopServices.openUrl(QUrl(RELEASES_PAGE)))
            if manual:
                self.inform('Mise à jour impossible', f'Smail {update.version} n’a pas pu s’installer automatiquement. '
                            'Installez-la depuis la page des versions (bouton du bandeau).')
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
        if manual:
            self.inform('Mise à jour prête', f'Smail {update.version} est téléchargé et vérifié.\n\n'
                        'Il s’installera à la fermeture de Smail, ou tout de suite avec « Redémarrer maintenant ».')

    def inform(self, title, text):
        """Réponse visible à une vérification demandée par l’utilisateur (la barre d’état passe inaperçue)."""
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self.window, title, text)

    def ask(self, title, text):
        from PySide6.QtWidgets import QMessageBox
        return QMessageBox.question(self.window, title, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes

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
