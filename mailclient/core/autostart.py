"""Lancement de Smail au démarrage de Windows (session de l’utilisateur, sans droits administrateur).

Smail installé : valeur « Smail » de HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run, avec --minimized
(Smail démarre réduit dans la zone de notification). Version Microsoft Store : tâche de démarrage déclarée
dans le paquet, que Windows active dans Paramètres › Applications › Démarrage. Lancé depuis les sources :
non proposé (le chemin de Python n’est pas une application)."""
import sys
from pathlib import Path

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE = 'Smail'
ARGUMENT = '--minimized'


def command(executable=None) -> str:
    return f'"{Path(executable or sys.executable)}" {ARGUMENT}'


def supported() -> bool:
    from mailclient.core.updater import installed_copy
    return installed_copy()


def _registry():
    import winreg
    return winreg


def enabled(registry=None) -> bool:
    registry = registry or _registry()
    try:
        with registry.OpenKey(registry.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = registry.QueryValueEx(key, VALUE)
    except OSError:
        return False
    return bool(value)


def set_enabled(on: bool, executable=None, registry=None) -> None:
    """Ajoute ou retire Smail des programmes lancés à l’ouverture de session."""
    registry = registry or _registry()
    with registry.CreateKey(registry.HKEY_CURRENT_USER, RUN_KEY) as key:
        if on:
            registry.SetValueEx(key, VALUE, 0, registry.REG_SZ, command(executable))
        else:
            try:
                registry.DeleteValue(key, VALUE)
            except FileNotFoundError:
                pass


def refresh(executable=None, registry=None) -> None:
    """Smail déplacé ou mis à jour : la commande enregistrée suit le chemin actuel de l’exécutable."""
    registry = registry or _registry()
    if enabled(registry):
        set_enabled(True, executable, registry)
