"""Coque de dialogue reprise des maquettes, raccordée à l'apparence réelle."""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QScrollArea, QApplication
from mailclient.ui.components import label, Card

def appearance():
    app = QApplication.instance()
    theme = getattr(app, 'smail_theme', None)
    if theme is None:
        from mailclient.ui.theme import Theme
        from mailclient.ui.fonts import configure_fonts
        configure_fonts(app)
        theme = Theme()
        theme.setParent(app)
        app.smail_theme = theme
        theme.apply()
    return theme

def dialog_layout(dialog: QDialog, title: str, subtitle: str, size=(900,760)):
    """Structure visuelle du Dialog de mockups/dialogs.py, sans données fictives."""
    theme = appearance()
    dialog.resize(*size)
    dialog.setMinimumSize(620,480)
    outer = QVBoxLayout(dialog)
    margin = {1:20,2:28,3:18}[theme.variant]
    outer.setContentsMargins(margin,margin,margin,margin)
    outer.addWidget(label('SMAIL', 'Eyebrow'))
    outer.addWidget(label(title,'DialogTitle'))
    outer.addWidget(label(subtitle,'Subtitle',True))
    content = Card(margin=20 if theme.variant != 2 else 28)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(content)
    outer.addWidget(scroll,1)
    return theme, outer, content.box
