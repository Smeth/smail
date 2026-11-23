"""Configuration commune des tests."""
import os
import sys

_status = {}


def pytest_sessionfinish(session, exitstatus):
    _status['code'] = int(exitstatus)


def pytest_unconfigure(config):
    """Fin de session sûre pour Qt WebEngine sous Windows.

    À la sortie du processus, Windows décharge les bibliothèques ; Qt WebEngine y provoque alors une
    violation d'accès qui, sur les machines GitHub Actions, remplace le code de sortie de pytest
    (1, 127 ou 139 après « N passed »).

    pytest_unconfigure s'exécute après le résumé et l'écriture du rapport JUnit : le processus est
    terminé aussitôt avec le vrai code de pytest, sans phase de déchargement. Aucun objet Qt n'est
    manipulé ici : un nettoyage tardif des lecteurs WebEngine plantait lui-même.
    """
    if sys.platform != 'win32' or 'code' not in _status:
        return
    sys.stdout.flush()
    sys.stderr.flush()
    # Les threads WebEngine interrompus par la terminaison déclencheraient un faux rapport de plantage.
    import faulthandler
    faulthandler.disable()
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.TerminateProcess(kernel32.GetCurrentProcess(), _status['code'])
    os._exit(_status['code'])  # Uniquement si TerminateProcess était refusé.
