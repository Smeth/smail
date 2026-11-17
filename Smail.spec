# Exécuter depuis la racine : pyinstaller --clean Smail.spec
import re
from pathlib import Path
from PyInstaller.utils.win32.versioninfo import (VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable,
                                                 StringStruct, VarFileInfo, VarStruct)
root = Path(SPECPATH)
# Version unique : mailclient/__init__.py.
version = re.search(r"__version__ = '([^']+)'", (root / 'mailclient' / '__init__.py').read_text(encoding='utf-8'))[1]
numbers = tuple(int(part) for part in (version.split('.') + ['0'] * 4)[:4])
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
    kids=[StringFileInfo([StringTable('040C04B0', [
              StringStruct('CompanyName', 'Smail'),
              StringStruct('FileDescription', 'Smail — client mail'),
              StringStruct('FileVersion', version),
              StringStruct('InternalName', 'Smail'),
              StringStruct('OriginalFilename', 'Smail.exe'),
              StringStruct('ProductName', 'Smail'),
              StringStruct('ProductVersion', version)])]),
          VarFileInfo([VarStruct('Translation', [0x040C, 1200])])])
a = Analysis([str(root / 'mailclient' / 'main.py')], pathex=[str(root)],
             binaries=[], datas=[
                 (str(root / 'mailclient' / 'ui' / 'styles'), 'mailclient/ui/styles'),
                 (str(root / 'mailclient' / 'ui' / 'assets'), 'mailclient/ui/assets'),
             ], hiddenimports=['keyring.backends.Windows'],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Smail',
          debug=False, strip=False, upx=False, console=False,
          icon=str(root / 'mailclient' / 'ui' / 'assets' / 'smail.ico'), version=version_info)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Smail')
