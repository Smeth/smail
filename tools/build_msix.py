"""Construit le paquet MSIX de Smail pour le Microsoft Store, à partir du dossier produit par PyInstaller.

  python tools/build_msix.py                 dist/Smail -> dist/msix/Smail-X.Y.Z.msix
  python tools/build_msix.py --layout-only   prépare seulement dist/msix/layout (test local avec le mode développeur :
                                             Add-AppxPackage -Register dist\\msix\\layout\\AppxManifest.xml)

Le paquet n’est pas signé : le Store le signe lui-même lors de la publication (aucun certificat à acheter).
L’identité (nom, éditeur) vient de packaging/msix/identity.json, à remplir avec les valeurs de Partner Center.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / 'packaging' / 'msix'
# Logos exigés par le manifeste : nom -> (largeur, hauteur).
LOGOS = {'StoreLogo.png': (50, 50), 'Square44x44Logo.png': (44, 44), 'Square150x150Logo.png': (150, 150),
         'Wide310x150Logo.png': (310, 150)}


def version() -> str:
    text = (ROOT / 'mailclient' / '__init__.py').read_text(encoding='utf-8')
    return re.search(r"__version__ = '(\d+\.\d+\.\d+)'", text)[1]


def manifest(identity: dict, number: str) -> str:
    """Manifeste rempli ; le Store exige une version à quatre nombres dont le dernier vaut 0."""
    values = {key: escape(str(identity[key]), {'"': '&quot;'})
              for key in ('name', 'publisher', 'publisher_display_name', 'display_name')}
    template = (PACKAGING / 'AppxManifest.xml').read_text(encoding='utf-8')
    return template.format(version=f'{number}.0', **values)


def logos(target: Path) -> None:
    sys.path.insert(0, str(ROOT / 'tools'))
    from make_icon import render
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841  (rendu Qt)
    target.mkdir(parents=True, exist_ok=True)
    for name, (width, height) in LOGOS.items():
        side = min(width, height)
        icon = QImage.fromData(render(side * 4)).scaled(side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.drawImage((width - side) // 2, (height - side) // 2, icon)
        painter.end()
        if not image.save(str(target / name), 'PNG'):
            raise SystemExit(f'Impossible d’écrire {name}.')


def makeappx() -> Path:
    """makeappx.exe du Windows SDK (installé sur les machines GitHub Actions windows-latest)."""
    found = sorted(Path(r'C:\Program Files (x86)\Windows Kits\10\bin').glob(r'10.*\x64\makeappx.exe'))
    if not found:
        raise SystemExit('makeappx.exe introuvable : installez le Windows SDK.')
    return found[-1]


def main(arguments):
    dist = ROOT / 'dist' / 'Smail'
    if not (dist / 'Smail.exe').exists():
        raise SystemExit('dist/Smail/Smail.exe absent : lancez d’abord PyInstaller (python -m PyInstaller Smail.spec).')
    identity = json.loads((PACKAGING / 'identity.json').read_text(encoding='utf-8'))
    number = version()
    output = ROOT / 'dist' / 'msix'
    layout = output / 'layout'
    shutil.rmtree(layout, ignore_errors=True)
    shutil.copytree(dist, layout)
    (layout / 'AppxManifest.xml').write_text(manifest(identity, number), encoding='utf-8')
    logos(layout / 'Assets')
    if '--layout-only' in arguments:
        print('Dossier du paquet prêt :', layout)
        return
    package = output / f'Smail-{number}.msix'
    package.unlink(missing_ok=True)
    subprocess.run([str(makeappx()), 'pack', '/d', str(layout), '/p', str(package), '/o'], check=True,
                   stdout=subprocess.DEVNULL)
    print(f'Paquet MSIX : {package} ({package.stat().st_size / 1_000_000:.1f} Mo)')
    if identity['name'].endswith('Provisoire'):
        print('Attention : identité provisoire. Remplissez packaging/msix/identity.json avant de soumettre au Store.')


if __name__ == '__main__':
    main(sys.argv[1:])
