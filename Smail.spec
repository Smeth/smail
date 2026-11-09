# Exécuter depuis la racine : pyinstaller --clean Smail.spec
from pathlib import Path
root = Path(SPECPATH)
a = Analysis([str(root / 'mailclient' / 'main.py')], pathex=[str(root)],
             binaries=[], datas=[
                 (str(root / 'mailclient' / 'ui' / 'styles'), 'mailclient/ui/styles'),
                 (str(root / 'mailclient' / 'ui' / 'assets'), 'mailclient/ui/assets'),
             ], hiddenimports=['keyring.backends.Windows'],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Smail',
          debug=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Smail')
