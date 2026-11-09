"""Point d'entrée : python -m mailclient.main."""
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from mailclient.utils.config import data_directory
from mailclient.utils.logger import configure
from mailclient.storage.database import Database
from mailclient.storage.secrets import Secrets
from mailclient.core.tls_policy import TLSPolicy
from mailclient.ui.main_window import MainWindow
from mailclient.ui.presentation import install_theme

def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Smail')
    app.setOrganizationName('SmailDesktop')
    directory = data_directory()
    logger = configure(directory)
    try:
        database = Database(directory / 'settings.db', Secrets())
        install_theme(database)
        window = MainWindow(database, Secrets(), TLSPolicy(database), auto_load='--smoke-test' not in sys.argv)
    except Exception:
        QMessageBox.critical(None, 'Démarrage impossible', 'Impossible de charger la configuration locale. Vérifiez les droits d’accès au dossier Smail dans AppData.')
        return 1
    logger.info('Démarrage de l’application')
    window.show()
    if '--smoke-test' in sys.argv:
        from PySide6.QtCore import QTimer
        # Vérifie aussi les imports dynamiques du coffre dans le build gelé.
        try:
            Secrets()._backend()
        except Exception:
            window.close()
            return 2
        from mailclient.core.parser import Mail
        window.reader.display(Mail('', '', 'Diagnostic', '', text='Test de lecture', html='<p>Test de lecture</p>'))
        QTimer.singleShot(500, app.quit)
    result = app.exec()
    window.reader.shutdown()
    logger.info('Arrêt de l’application')
    return result

if __name__ == '__main__':
    raise SystemExit(main())
