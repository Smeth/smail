"""Utilise Segoe UI installée sur Windows, sans copier ni redistribuer la police."""
import os
from pathlib import Path
from PySide6.QtGui import QFontDatabase, QFont

def configure_fonts(app):
    # La plateforme offscreen ne découvre pas toujours les polices Windows.
    directory = Path(os.environ.get('WINDIR','C:/Windows')) / 'Fonts'
    for filename in ('segoeui.ttf','segoeuib.ttf','seguisb.ttf','segoeuii.ttf'):
        path = directory / filename
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont('Segoe UI',10))
