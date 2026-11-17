"""Génère mailclient/ui/assets/smail.ico (16 à 256 px) depuis le pictogramme Lucide « mail ».

Usage depuis la racine : python tools/make_icon.py
"""
import struct
import sys
from pathlib import Path
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'mailclient' / 'ui' / 'assets'
SIZES = (16, 24, 32, 48, 64, 128, 256)
BACKGROUND = '#275BCC'  # Accent « Bleu » par défaut du thème clair.


def render(size: int) -> bytes:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(BACKGROUND))
    radius = size * 0.22
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    svg = (ASSETS / 'icons' / 'mail.svg').read_text(encoding='utf-8').replace('currentColor', '#FFFFFF')
    if size <= 24:
        svg = svg.replace('stroke-width="2"', 'stroke-width="2.6"')  # Trait lisible en petite taille.
    margin = size * 0.17
    QSvgRenderer(QByteArray(svg.encode('utf-8'))).render(painter, QRectF(margin, margin, size - 2 * margin, size - 2 * margin))
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, 'PNG')
    return bytes(data)


def build_ico(images: list[tuple[int, bytes]]) -> bytes:
    """ICO à entrées PNG (pris en charge depuis Windows Vista)."""
    header = struct.pack('<HHH', 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, payload = b'', b''
    for size, png in images:
        dimension = 0 if size >= 256 else size
        entries += struct.pack('<BBBBHHII', dimension, dimension, 0, 0, 1, 32, len(png), offset + len(payload))
        payload += png
    return header + entries + payload


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    images = [(size, render(size)) for size in SIZES]
    (ASSETS / 'smail.ico').write_bytes(build_ico(images))
    (ASSETS / 'smail.png').write_bytes(images[-1][1])
    del app
    print('Icône écrite dans', ASSETS)


if __name__ == '__main__':
    main()
