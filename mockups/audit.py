"""Contrôle en lecture seule des fichiers hors mockups/ ; état conservé ici."""
from pathlib import Path
import hashlib
import json
import os
import sys

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = Path(__file__).with_name('.outside-baseline.json')

def inventory():
    result = {}
    for directory, folders, files in os.walk(ROOT):
        folders[:] = [name for name in folders if name != 'mockups']
        for filename in files:
            path = Path(directory) / filename
            try:
                result[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
            except PermissionError:
                result[str(path.relative_to(ROOT))] = 'INACCESSIBLE'
    return result

if __name__ == '__main__':
    current = inventory()
    if '--record' in sys.argv:
        if MANIFEST.exists():
            raise SystemExit('Un état initial existe déjà ; il ne sera pas écrasé.')
        MANIFEST.write_text(json.dumps(current, indent=2), encoding='utf-8')
        print(f'État initial : {len(current)} fichiers hors mockups/.')
    else:
        before = json.loads(MANIFEST.read_text(encoding='utf-8'))
        changes = [name for name in set(before) | set(current) if before.get(name) != current.get(name)]
        print('Aucun fichier hors mockups/ modifié.' if not changes else json.dumps(changes, indent=2))
        raise SystemExit(bool(changes))
