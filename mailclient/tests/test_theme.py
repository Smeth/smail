"""Ressources visuelles et branchement, sans compte réel ni capture d'écran."""
import os
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from mailclient.storage.database import Database
from mailclient.ui.presentation import install_theme
from mailclient.ui.icons import icon
from mailclient.ui.theme import contrast


def test_resources_are_copied_from_approved_mockups():
    root = Path(__file__).resolve().parents[2]
    source, target = root / 'mockups', root / 'mailclient' / 'ui'
    # La QSS de production évolue avec les corrections UI demandées après migration.
    for name in ('theme.py', 'icons.py', 'fonts.py'):
        assert (source / name).read_bytes() == (target / name).read_bytes()
    for resource in (source / 'assets').rglob('*'):
        if resource.is_file():
            relative = resource.relative_to(source)
            assert resource.read_bytes() == (target / relative).read_bytes()


def test_default_style_and_three_themes_use_existing_settings(tmp_path):
    app = QApplication.instance() or QApplication([])
    database = Database(tmp_path / 'presentation.db')
    appearance = install_theme(database)
    assert appearance.variant == 1 and not appearance.dark
    for variant in (1, 2, 3):
        database.set_setting('ui_style', variant)
        for dark in (False, True):
            database.set_setting('theme', int(dark))
            appearance = install_theme(database)
            assert appearance.variant == variant
            assert appearance.dark == dark
            assert app.styleSheet()
            assert contrast(appearance.colors['text'], appearance.colors['surface']) >= 4.5
            assert not icon('mail', appearance.colors['accent']).isNull()
    assert database.accounts() == []


def test_invalid_visual_preferences_fall_back_without_writing(tmp_path):
    app = QApplication.instance() or QApplication([])
    database = Database(tmp_path / 'presentation.db')
    database.set_setting('ui_style', 99)
    database.set_setting('ui_density', 'inconnue')
    database.set_setting('ui_accent', 'inconnu')
    appearance = install_theme(database)
    assert (appearance.variant, appearance.density, appearance.accent_name) == (1, 'Normale', 'Bleu')
    assert database.setting('ui_style') == 99
