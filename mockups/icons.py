"""Rendu local des SVG Lucide, recolorés avec les tokens d'apparence."""
from pathlib import Path
from functools import lru_cache
from PySide6.QtCore import QByteArray, QRectF, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

DIRECTORY = Path(__file__).parent / 'assets' / 'icons'

@lru_cache(maxsize=512)
def icon(name: str, color: str, size=20) -> QIcon:
    source = (DIRECTORY / f'{name}.svg').read_text(encoding='utf-8').replace('currentColor', color)
    renderer = QSvgRenderer(QByteArray(source.encode('utf-8')))
    pixmap = QPixmap(size*2, size*2)
    pixmap.fill('transparent')
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size*2, size*2))
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
