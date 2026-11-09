"""Branchement des ressources visuelles validées sur l'application réelle."""
from PySide6.QtWidgets import QApplication
from mailclient.ui.fonts import configure_fonts
from mailclient.ui.icons import icon
from mailclient.ui.theme import Theme, VARIANTS, ACCENTS
from PySide6.QtGui import QColor


def install_theme(database) -> Theme:
    """Relit les préférences visuelles via l'API existante, sans les modifier."""
    app = QApplication.instance()
    if app is None:
        raise RuntimeError('Une application Qt doit être créée avant son thème.')
    theme = getattr(app, 'smail_theme', None)
    if theme is None:
        app.setStyle('Fusion')
        configure_fonts(app)
        theme = Theme()  # Le style 1 reste le choix initial.
        theme.setParent(app)
        app.smail_theme = theme
        theme.changed.connect(lambda: app.setWindowIcon(icon('mail', theme.colors['accent'])))

    variant = database.setting('ui_style', 1)
    density = database.setting('ui_density', 'Normale')
    accent = database.setting('ui_accent', 'Bleu')
    theme.variant = variant if variant in VARIANTS else 1
    theme.density = density if density in ('Compacte', 'Normale', 'Aérée') else 'Normale'
    theme.accent_name = accent if accent in ACCENTS else 'Bleu'
    custom = database.setting('ui_custom_accent',None)
    theme.custom_accent = custom if isinstance(custom,str) and QColor(custom).isValid() else None
    theme.dark = database.setting('theme', 0) == 1
    theme.reduced_motion = bool(database.setting('ui_reduced_motion', False))
    theme.apply()
    return theme
