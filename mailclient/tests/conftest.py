"""Après chaque test : les tâches d’arrière-plan (détection de compte, réseau simulé, sauvegarde…) se terminent et
leurs résultats sont livrés AVANT la destruction des fenêtres du test suivant.

Sans cela, une tâche encore en cours peut rappeler une fenêtre déjà détruite : corruption du tas (0xc0000374),
observée de façon intermittente sous Python 3.11 en CI."""
import pytest


@pytest.fixture(autouse=True)
def finish_background_tasks():
    yield
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    QThreadPool.globalInstance().waitForDone(10_000)
    app.processEvents()  # Résultats livrés pendant que leurs destinataires existent encore.
