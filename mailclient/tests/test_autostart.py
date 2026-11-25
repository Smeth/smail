"""Lancement de Smail au démarrage de Windows (registre de l’utilisateur simulé)."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from mailclient.core import autostart


class Registry:
    """Clé « Run » simulée : aucune modification du vrai registre pendant les tests."""
    HKEY_CURRENT_USER, REG_SZ = 'HKCU', 1

    def __init__(self):
        self.values = {}

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def OpenKey(self, root, path):
        return self.Key()

    CreateKey = OpenKey

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[name] = value

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


def test_enable_disable_and_follow_the_executable():
    registry = Registry()
    assert not autostart.enabled(registry)
    autostart.set_enabled(True, r'C:\Users\x\AppData\Local\Programs\Smail\Smail.exe', registry)
    assert registry.values['Smail'] == r'"C:\Users\x\AppData\Local\Programs\Smail\Smail.exe" --minimized'
    assert autostart.enabled(registry)
    autostart.refresh(r'D:\Smail\Smail.exe', registry)  # Smail déplacé : la commande suit.
    assert registry.values['Smail'] == r'"D:\Smail\Smail.exe" --minimized'
    autostart.set_enabled(False, registry=registry)
    autostart.set_enabled(False, registry=registry)  # Déjà retiré : sans erreur.
    assert not autostart.enabled(registry)
    autostart.refresh(r'D:\Smail\Smail.exe', registry)  # Désactivé : refresh ne le réactive pas.
    assert 'Smail' not in registry.values


def test_only_installed_copies_offer_it(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from mailclient.core import updater
    from mailclient.storage.database import Database
    from mailclient.ui.settings_dialog import SettingsDialog
    db = Database(tmp_path / 'settings.db')
    dialog = SettingsDialog(db)
    assert not dialog.autostart.isEnabled()  # Lancé depuis les sources.
    dialog.reject()
    registry = Registry()
    monkeypatch.setattr(updater, 'installed_copy', lambda: True)
    monkeypatch.setattr(autostart, '_registry', lambda: registry)
    registry.values['Smail'] = '"C:\\Smail.exe" --minimized'
    dialog = SettingsDialog(db)
    assert dialog.autostart.isEnabled() and dialog.autostart.isChecked()
    dialog.reject()
