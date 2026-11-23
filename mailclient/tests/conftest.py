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
    process = kernel32.GetCurrentProcess()
    if kernel32.TerminateProcess(process, _status['code']):
        # TerminateProcess rend la main avant la fin effective : attendre plutôt que d'enchaîner sur
        # os._exit, dont la phase de déchargement des bibliothèques provoque justement le plantage.
        kernel32.WaitForSingleObject(process, 30_000)
    os._exit(_status['code'])  # Secours uniquement : terminaison refusée ou anormalement lente.
