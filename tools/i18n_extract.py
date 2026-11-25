"""Textes à traduire de Smail : tout ce qui passe par tr() ou N_(), plus quelques valeurs affichées traduites.

    python tools/i18n_extract.py            # liste les textes sans traduction anglaise
    python tools/i18n_extract.py --update   # les ajoute à mailclient/i18n/en.json (valeur vide, à traduire)
                                            # et retire les traductions devenues inutiles

Le français est la clé : modifier un texte dans le code crée une nouvelle clé à traduire. Le test
test_i18n vérifie qu’il ne reste aucune clé sans traduction.
"""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'mailclient'
CATALOG = PACKAGE / 'i18n' / 'en.json'


def literal(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def from_code() -> set:
    texts = set()
    for path in sorted(PACKAGE.rglob('*.py')):
        if 'tests' in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'page':
                texts.update(literal(arg) for arg in node.args[:2] if literal(arg))  # Titre et sous-titre traduits par page().
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.args):
                continue
            name = node.func.id
            if name in ('tr', 'N_') and literal(node.args[0]):
                texts.add(literal(node.args[0]))
            elif name == 'count' and len(node.args) >= 2 and literal(node.args[1]):
                singular = literal(node.args[1])  # count(n, 'message', 'messages') traduit ses mots.
                plural = literal(node.args[2]) if len(node.args) > 2 else None
                texts.update({singular, plural or singular + 's'})
    return texts


def from_values() -> set:
    """Valeurs internes affichées avec tr() mais définies hors des marques (theme.py reste identique aux maquettes)."""
    sys.path.insert(0, str(ROOT))
    from mailclient.ui.theme import ACCENTS, VARIANTS
    from mailclient.core.accounts import MODES
    from mailclient.i18n import LANGUAGES
    texts = {text for pair in VARIANTS.values() for text in pair} | set(ACCENTS)
    texts |= {'Compacte', 'Normale', 'Aérée'} | {mode for mode in MODES if mode == 'Aucun'}
    texts.add(LANGUAGES['auto'])
    return texts


def texts() -> set:
    return {text for text in from_code() | from_values() if text and any(ch.isalpha() for ch in text)}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Console Windows.
    wanted = texts()
    catalog = json.loads(CATALOG.read_text(encoding='utf-8')) if CATALOG.exists() else {}
    missing = sorted(text for text in wanted if not catalog.get(text))
    unused = sorted(set(catalog) - wanted)
    if '--update' in sys.argv:
        merged = {text: catalog.get(text, '') for text in sorted(wanted)}
        CATALOG.write_text(json.dumps(merged, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'{len(merged)} textes ; {len(missing)} à traduire ; {len(unused)} retirés.')
    else:
        for text in missing:
            print(repr(text))
        print(f'{len(missing)} sans traduction, {len(unused)} inutilisés, {len(wanted)} au total.')


if __name__ == '__main__':
    main()
