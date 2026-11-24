"""Prépare une nouvelle version de Smail.

  python tools/release.py 1.1.0           numéro de version, CHANGELOG daté, commit et tag v1.1.0
  python tools/release.py 1.1.0 --push    … puis envoi sur GitHub : la publication démarre

Le tag poussé déclenche .github/workflows/release.yml : tests, construction, signature du manifeste,
publication. Les Smail installés installent ensuite la nouvelle version à leur fermeture.
"""
import datetime
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / 'mailclient' / '__init__.py'
CHANGELOG = ROOT / 'CHANGELOG.md'


def git(*arguments, capture=False):
    result = subprocess.run(['git', *arguments], cwd=ROOT, check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else None


def main(arguments):
    if not arguments or not re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,4}', arguments[0]):
        raise SystemExit(__doc__)
    number, push = arguments[0], '--push' in arguments
    current = re.search(r"__version__ = '([^']+)'", INIT.read_text(encoding='utf-8'))[1]
    as_tuple = lambda text: tuple(int(part) for part in text.split('.'))
    if as_tuple(number) <= as_tuple(current):
        raise SystemExit(f'La version {number} doit être supérieure à la version actuelle {current}.')
    if git('status', '--porcelain', capture=True):
        raise SystemExit('Des modifications ne sont pas enregistrées : faites un commit avant de publier.')
    if git('tag', '--list', f'v{number}', capture=True):
        raise SystemExit(f'Le tag v{number} existe déjà.')
    text = CHANGELOG.read_text(encoding='utf-8')
    section = re.search(r'^## Non publié\s*$\n(.*?)(?=^## |\Z)', text, re.S | re.M)
    if not section or not section[1].strip():
        raise SystemExit('La section « ## Non publié » du CHANGELOG est vide : décrivez les changements de cette version.')
    today = datetime.date.today().isoformat()
    text = text[:section.start()] + f'## Non publié\n\n## {number} — {today}\n' + text[section.start() + len('## Non publié'):]
    CHANGELOG.write_bytes(text.encode('utf-8'))
    INIT.write_bytes(INIT.read_bytes().replace(f"__version__ = '{current}'".encode(), f"__version__ = '{number}'".encode()))
    git('add', str(INIT), str(CHANGELOG))
    git('commit', '-m', f'Version {number}')
    git('tag', '-a', f'v{number}', '-m', f'Smail {number}')
    branch = git('rev-parse', '--abbrev-ref', 'HEAD', capture=True)
    if push:
        git('push', 'origin', branch)
        git('push', 'origin', f'v{number}')
        print(f'Version {number} envoyée : suivez la publication dans l’onglet Actions du dépôt GitHub.')
    else:
        print(f'Version {number} prête. Pour publier :\n  git push origin {branch}\n  git push origin v{number}')


if __name__ == '__main__':
    main(sys.argv[1:])
