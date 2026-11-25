"""Version anglaise : catalogue complet et cohérent, choix de la langue, interface réellement traduite."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from mailclient import i18n

ROOT = Path(__file__).resolve().parents[2]
CATALOG = json.loads((ROOT / 'mailclient' / 'i18n' / 'en.json').read_text(encoding='utf-8'))
PLACEHOLDER = re.compile(r'\{(\w*)[^{}]*\}')  # Nom seulement : le format d’une date peut changer (%m/%d).


@pytest.fixture
def english():
    i18n.set_language('en')
    yield
    i18n.set_language('fr')


def test_every_displayed_text_has_an_english_translation():
    sys.path.insert(0, str(ROOT / 'tools'))
    from i18n_extract import texts
    missing = sorted(text for text in texts() if not CATALOG.get(text))
    assert not missing, f'{len(missing)} textes sans traduction (python tools/i18n_extract.py --update) : {missing[:10]}'


def test_translations_keep_their_placeholders_and_shape():
    for french, english in CATALOG.items():
        # L’anglais peut se passer d’une variable (accord du pluriel français), jamais en inventer une.
        assert set(PLACEHOLDER.findall(english)) <= set(PLACEHOLDER.findall(french)), french
        assert set(PLACEHOLDER.findall(french)) - set(PLACEHOLDER.findall(english)) <= {'valeur', 'valeur2'}, french  # Accords du français.
        from datetime import datetime
        values = {name: datetime(2026, 11, 25, 8, 30) if '%' in spec else 1.5
                  for name, spec in re.findall(r'\{(\w+)([^{}]*)\}', french + english)}
        assert english.format(**values) and french.format(**values), french  # Aucune accolade cassée.
        if not french.startswith((' ?', ' :', ' !')):  # Espace française avant la ponctuation : supprimée en anglais.
            assert french.startswith((' ', '\n')) == english.startswith((' ', '\n')), french
        assert french.endswith(('…',)) <= english.endswith(('…',)), french


def test_uncertain_send_is_still_recognised_in_english():
    """compose_window reconnaît un envoi non confirmé par le début du message : il doit être le même traduit."""
    prefix = 'Le serveur d’envoi n’a pas confirmé'
    sentences = [key for key in CATALOG if key.startswith(prefix) and key != prefix]
    assert sentences and prefix in CATALOG
    assert all(CATALOG[key].startswith(CATALOG[prefix]) for key in sentences)


def test_french_is_the_default_and_english_translates(english):
    assert i18n.current() == 'en'
    assert i18n.tr('Boîte de réception') == 'Inbox' and i18n.tr('Texte inconnu') == 'Texte inconnu'
    assert i18n.display_group('Octobre 2026') == 'October 2026' and i18n.display_group('Hier') == 'Yesterday'
    from mailclient.ui.view_models import count
    assert count(1, 'message') == '1 message' and count(3, 'message déplacé', 'messages déplacés') == '3 messages moved'
    i18n.set_language('fr')
    assert i18n.tr('Boîte de réception') == 'Boîte de réception' and count(2, 'message') == '2 messages'


def test_language_choice_is_read_before_the_interface(tmp_path, monkeypatch):
    from mailclient.storage.database import Database
    path = tmp_path / 'settings.db'
    assert i18n.stored_choice(path) == 'auto'  # Premier lancement : pas encore de base.
    Database(path).set_setting('language', 'en')
    assert i18n.stored_choice(path) == 'en'
    monkeypatch.setattr(i18n, 'system_language', lambda: 'en')
    assert i18n.resolve('auto') == 'en' and i18n.resolve('fr') == 'fr'
    monkeypatch.setattr(i18n, 'CATALOGS', tmp_path)  # Catalogue absent : l’interface reste en français.
    assert i18n.set_language('en') == 'fr' and i18n.tr('Boîte de réception') == 'Boîte de réception'


def test_language_setting_in_preferences(tmp_path):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from mailclient.storage.database import Database
    from mailclient.ui.settings_dialog import SettingsDialog
    db = Database(tmp_path / 'settings.db')
    db.set_setting('language', 'en')
    dialog = SettingsDialog(db)
    assert [dialog.language.itemData(i) for i in range(dialog.language.count())] == ['auto', 'fr', 'en']
    assert dialog.language.currentData() == 'en' and dialog.language.itemText(2) == 'English'
    from shiboken6 import delete
    delete(dialog)


ENGLISH_WINDOW = r'''
import json, sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
app = QApplication([])
from mailclient import i18n
assert i18n.set_language('en') == 'en'
from mailclient.storage.database import Database
from mailclient.core.tls_policy import TLSPolicy
from mailclient.ui.main_window import MainWindow
from mailclient.ui.settings_dialog import SettingsDialog
from mailclient.tests.test_scheduler import ME
db = Database(Path(sys.argv[1]) / 'settings.db')
db.save(ME)
window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
dialog = SettingsDialog(db, window)
from mailclient.ui.compose_window import ComposeWindow
from PySide6.QtWidgets import QLabel, QAbstractButton
composer = ComposeWindow(window.service, [ME], ME, parent=window)
compose = [w.text() for w in composer.findChildren(QLabel) + composer.findChildren(QAbstractButton) if w.text()]
print(json.dumps(dict(
    compose=compose,
    reader=[a.text() for a in window.reader.more_menu.actions()],
    menus=[a.text() for a in window.menuBar().actions()],
    filters=[b.text() for b in window.filter_buttons.values()],
    pages=[dialog.nav.item(i).text() for i in range(dialog.nav.count())],
    title=window.windowTitle())))
'''


def test_the_interface_is_in_english(tmp_path):
    """Langue choisie au démarrage : menus, filtres et préférences en anglais (processus séparé, comme au lancement)."""
    result = subprocess.run([sys.executable, '-c', ENGLISH_WINDOW, str(tmp_path)], cwd=ROOT, capture_output=True,
                            text=True, encoding='utf-8', timeout=120,
                            env=dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM='offscreen'))
    assert result.returncode == 0, result.stderr[-2000:]
    shown = json.loads(result.stdout.strip().splitlines()[-1])
    english = set(CATALOG.values())
    for text in shown['menus'] + shown['filters'] + shown['pages']:
        assert text.replace('&', '') in english or not any(ch in text for ch in 'éèàùçÉ'), text
    assert shown['filters'] == ['All', 'Unread', 'Attachments']
    assert shown['pages'][0] == 'General' and 'Accounts' in shown['pages']
    # Libellés venant de listes (« Objet », « Cci ») : longtemps oubliés par la conversion.
    assert {'Subject', 'Bcc', 'Send'} <= set(shown['compose']) and not {'Objet', 'Cci', 'Envoyer'} & set(shown['compose'])
    assert 'Archive' in shown['reader'] and 'Archiver' not in shown['reader']
