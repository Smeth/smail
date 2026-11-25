"""Coque de dialogue reprise des maquettes, raccordée à l'apparence réelle."""
from mailclient.i18n import tr
from PySide6.QtWidgets import QDialog, QVBoxLayout, QScrollArea, QApplication
from mailclient.ui.components import label, Card

def appearance():
    app = QApplication.instance()
    theme = getattr(app, 'smail_theme', None)
    if theme is None:
        from PySide6.QtGui import QPalette
        from mailclient.ui.presentation import SystemTheme, text_scale
        from mailclient.ui.fonts import configure_fonts
        configure_fonts(app)
        theme = SystemTheme()  # Mêmes réglages d’accessibilité que la fenêtre principale.
        theme.system_palette = QPalette(app.palette())
        theme.text_scale = text_scale()
        theme.setParent(app)
        app.smail_theme = theme
        theme.apply()
    return theme

def dialog_layout(dialog: QDialog, title: str, subtitle: str, size=(900,760)):
    """Structure visuelle du Dialog de mockups/dialogs.py, sans données fictives."""
    theme = appearance()
    dialog.setMinimumSize(620,480)
    parent = dialog.parentWidget()
    # Jamais dialog.screen() avant l’affichage : la fenêtre native serait créée trop tôt (plantage de Qt).
    screen = parent.screen() if parent is not None and parent.isVisible() else QApplication.primaryScreen()
    if screen is not None:  # Jamais plus grand que l’écran (portables 1366 × 768 notamment).
        area = screen.availableGeometry()
        size = (min(size[0], int(area.width() * .9)), min(size[1], int(area.height() * .85)))
    dialog.resize(max(size[0], 620), max(size[1], 480))
    outer = QVBoxLayout(dialog)
    margin = {1:20,2:28,3:18}[theme.variant]
    outer.setContentsMargins(margin,margin,margin,margin)
    outer.addWidget(label(tr('SMAIL'), 'Eyebrow'))
    outer.addWidget(label(title,'DialogTitle'))
    outer.addWidget(label(subtitle,'Subtitle',True))
    content = Card(margin=20 if theme.variant != 2 else 28)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(content)
    outer.addWidget(scroll,1)
    return theme, outer, content.box
