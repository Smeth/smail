"""Langue de l’interface : français (langue du code) ou anglais.

Chaque texte affiché passe par tr() : le français est la clé, la traduction vient de mailclient/i18n/en.json.
Les noms internes (filtres, dossiers spéciaux, réglages) ne sont jamais traduits : seulement leur affichage.

La langue est choisie au démarrage, avant la construction de l’interface (setup) : « auto » suit la langue de
Windows (français si Windows est en français, anglais sinon) ; changer de langue s’applique au redémarrage."""
import json
import sqlite3
from pathlib import Path

LANGUAGES = {'auto': 'Automatique (langue de Windows)', 'fr': 'Français', 'en': 'English'}
CATALOGS = Path(__file__).resolve().parent
_current = 'fr'
_catalog: dict = {}


def current() -> str:
    return _current


def tr(text: str) -> str:
    """Texte traduit dans la langue de l’interface (le texte français s’il n’a pas de traduction)."""
    if _current == 'fr' or not text:
        return text
    return _catalog.get(text) or text


def N_(text: str) -> str:
    """Marque un texte à traduire à l’affichage sans le changer ici : noms de dossiers, groupes de dates, couleurs…
    restent des valeurs internes en français (enregistrées, comparées) ; tr() s’applique au moment d’afficher."""
    return text


MONTH_YEAR = None  # Voir display_group().


def display_group(key: str) -> str:
    """Titre affiché d’un groupe de dates : « Octobre 2026 » -> « October 2026 », « Hier » -> « Yesterday »."""
    month, _, year = key.rpartition(' ')
    if month and year.isdigit():
        return f'{tr(month)} {year}'
    return tr(key)


def system_language() -> str:
    from PySide6.QtCore import QLocale
    return 'fr' if QLocale.system().language() == QLocale.French else 'en'


def resolve(choice: str | None) -> str:
    return choice if choice in ('fr', 'en') else system_language()


def stored_choice(database_path: Path) -> str:
    """Réglage « language » lu directement (avant toute importation de l’interface)."""
    try:
        with sqlite3.connect(f'file:{database_path}?mode=ro', uri=True) as db:
            row = db.execute("SELECT value FROM settings WHERE key='language'").fetchone()
        return json.loads(row[0]) if row else 'auto'
    except (sqlite3.Error, ValueError, TypeError):
        return 'auto'


def set_language(language: str) -> str:
    """Active une langue (« fr », « en » ou « auto ») ; renvoie la langue effective."""
    global _current, _catalog
    language = resolve(language)
    _catalog = {}
    if language != 'fr':
        try:
            _catalog = json.loads((CATALOGS / f'{language}.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            language = 'fr'  # Catalogue absent ou abîmé : l’interface reste en français.
    _current = language
    return language


def install_qt_translations(app) -> None:
    """Boutons et fenêtres standard de Qt (Oui / Non, Annuler, choix de fichier) dans la langue de Smail."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    translator = QTranslator(app)
    if translator.load(QLocale(_current), 'qtbase', '_', QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)
        app.smail_qt_translator = translator  # Gardé en vie avec l’application.
    QLocale.setDefault(QLocale(QLocale.French if _current == 'fr' else QLocale.English))
