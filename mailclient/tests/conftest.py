"""Configuration commune des tests."""
import os
import sys

_status = {}


def pytest_sessionfinish(session, exitstatus):
    _status['code'] = int(exitstatus)


def pytest_unconfigure(config):
    """Fin de session sûre pour Qt WebEngine sous Windows.

    À la sortie du processus, Windows décharge les bibliothèques ; Qt WebEngine y provoque alors une
    violation d'accès (« Windows fatal exception: access violation »). Sur les machines GitHub
    Actions, elle remplace le code de sortie de pytest (1 ou 127 après « N passed »).

    pytest_unconfigure s'exécute après le résumé et l'écriture du rapport JUnit : on ferme les
    lecteurs encore ouverts, puis on termine le processus avec le vrai code de pytest, sans phase
    de déchargement des bibliothèques.
    """
    if sys.platform != 'win32' or 'code' not in _status:
        return
    try:
        from PySide6.QtWidgets import QApplication
        from mailclient.ui.mail_view import MailView
        app = QApplication.instance()
        if app is not None:
            for widget in app.allWidgets():
                if isinstance(widget, MailView):
                    widget.shutdown()
            app.processEvents()
    except Exception:
        pass  # Nettoyage au mieux : le code de sortie reste celui de pytest.
    sys.stdout.flush()
    sys.stderr.flush()
    # Les threads WebEngine interrompus par la terminaison déclencheraient un faux rapport de plantage.
    import faulthandler
    faulthandler.disable()
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.TerminateProcess(kernel32.GetCurrentProcess(), _status['code'])
    os._exit(_status['code'])  # Uniquement si TerminateProcess était refusé.
