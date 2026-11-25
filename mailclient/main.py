"""Point d'entrée : python -m mailclient.main."""
import sys
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox
from mailclient import __version__
from mailclient.utils.config import data_directory
from mailclient.utils.logger import configure
from mailclient.storage.database import Database
from mailclient.storage.secrets import Secrets
from mailclient.core.tls_policy import TLSPolicy
from mailclient.ui.main_window import MainWindow
from mailclient.ui.presentation import install_theme

def install_excepthook(logger):
    """Journalise les erreurs inattendues sans leur message (qui peut contenir des données de mail) et prévient une fois."""
    import traceback
    state = {'shown': False}
    def hook(kind, error, trace):
        frames = ' < '.join(f'{Path(frame.filename).name}:{frame.lineno}' for frame in reversed(traceback.extract_tb(trace)))
        logger.error('Erreur inattendue (%s) %s', kind.__name__, frames)
        if not state['shown'] and QApplication.instance() is not None:
            state['shown'] = True
            QMessageBox.critical(None, 'Erreur inattendue',
                                 'Une erreur inattendue s’est produite. Smail continue de fonctionner, mais il est conseillé de le redémarrer.\n\n'
                                 'Le type d’erreur a été noté dans smail.log, sans contenu de message.')
    sys.excepthook = hook

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Smail')
    app.setOrganizationName('SmailDesktop')
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(Path(__file__).parent / 'ui' / 'assets' / 'smail.ico')))
    directory = data_directory()
    from mailclient.core.mailto import is_mailto
    arguments = sys.argv[1:]
    mailto = next((value for value in arguments if is_mailto(value)), None)  # « Smail.exe --mailto mailto:… » ou « mailto:… ».
    instance = None
    if '--smoke-test' not in arguments:
        from mailclient.ui.single_instance import SingleInstance
        instance = SingleInstance(str(directory))
        if instance.forward({'mailto': mailto} if mailto else {'show': True}):
            return 0  # Smail est déjà ouvert : la demande lui est transmise.
        instance.listen()
    logger = configure(directory)
    install_excepthook(logger)
    try:
        database = Database(directory / 'settings.db', Secrets())
        install_theme(database)
        window = MainWindow(database, Secrets(), TLSPolicy(database), auto_load='--smoke-test' not in sys.argv)
    except Exception:
        QMessageBox.critical(None, 'Démarrage impossible', 'Impossible de charger la configuration locale. Vérifiez les droits d’accès au dossier Smail dans AppData.')
        return 1
    logger.info('Démarrage de l’application %s', __version__)
    if '--minimized' in arguments and not mailto:
        # Lancement à l’ouverture de session : Smail démarre discrètement (zone de notification si possible).
        if window.tray is None:
            window.showMinimized()
    else:
        window.show()
    try:
        from mailclient.core import autostart
        if autostart.supported():
            autostart.refresh()  # Après une mise à jour ou un déplacement : chemin de Smail à jour.
    except OSError:
        pass
    if instance is not None:
        instance.received.connect(window.external_request)
    if mailto:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: window.open_mailto(mailto))
    if '--smoke-test' in sys.argv:
        from PySide6.QtCore import QTimer
        # Vérifie aussi les imports dynamiques du coffre dans le build gelé.
        try:
            Secrets()._backend()
        except Exception:
            window.close()
            return 2
        from mailclient.ui.spelling import Speller
        if not Speller().available:  # Dictionnaire du correcteur absent du build.
            window.close()
            return 3
        from mailclient.core.parser import Mail
        window.reader.display(Mail('', '', 'Diagnostic', '', text='Test de lecture', html='<p>Test de lecture</p>'))
        QTimer.singleShot(500, app.quit)
    result = app.exec()
    window.reader.shutdown()
    logger.info('Arrêt de l’application')
    return result

if __name__ == '__main__':
    raise SystemExit(main())
