"""Outils de la publication (workflow release.yml).

  python .github/release.py check-tag v1.2.0        le tag correspond à mailclient/__init__.py
  python .github/release.py notes 1.2.0 notes.md     section du CHANGELOG de cette version
  python .github/release.py manifest INSTALLATEUR 1.2.0 DOSSIER
        écrit smail-update.json et sa signature Ed25519 (clé PEM dans la variable UPDATE_SIGNING_KEY)
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def version():
    text = (ROOT / 'mailclient' / '__init__.py').read_text(encoding='utf-8')
    return re.search(r"__version__ = '([^']+)'", text)[1]


def check_tag(tag):
    if tag != 'v' + version():
        raise SystemExit(f'Le tag {tag} ne correspond pas à __version__ = {version()} : '
                         'mettez à jour mailclient/__init__.py (ou utilisez tools/release.py).')


def notes(number, output):
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    match = re.search(rf'^## {re.escape(number)}\b.*?$\n(.*?)(?=^## |\Z)', text, re.S | re.M)
    if not match or not match[1].strip():
        raise SystemExit(f'Section « ## {number} » absente ou vide dans CHANGELOG.md.')
    Path(output).write_text(match[1].strip() + '\n', encoding='utf-8')


def manifest(installer, number, folder):
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    key_text = os.environ.get('UPDATE_SIGNING_KEY', '').strip()
    if not key_text:
        raise SystemExit('Secret UPDATE_SIGNING_KEY absent : la publication ne peut pas être signée.')
    key = load_pem_private_key(key_text.encode(), password=None)
    installer = Path(installer)
    data = installer.read_bytes()
    content = json.dumps(dict(version=number, file=installer.name, sha256=hashlib.sha256(data).hexdigest(),
                              size=len(data)), indent=2).encode('utf-8')
    folder = Path(folder)
    (folder / 'smail-update.json').write_bytes(content)
    (folder / 'smail-update.json.sig').write_bytes(key.sign(content))
    # Contrôle immédiat avec la clé publique embarquée dans Smail.
    sys.path.insert(0, str(ROOT))
    from mailclient.core.updater import verify_manifest
    verify_manifest(content, key.sign(content))
    print(content.decode())


if __name__ == '__main__':
    command, *arguments = sys.argv[1:]
    {'check-tag': check_tag, 'notes': notes, 'manifest': manifest}[command](*arguments)
