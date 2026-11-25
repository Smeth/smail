"""Branchement des ressources visuelles validées sur l'application réelle."""
from mailclient.i18n import tr
from PySide6.QtWidgets import QApplication
from mailclient.ui.fonts import configure_fonts
from mailclient.ui.icons import icon
from mailclient.ui.theme import Theme, VARIANTS, ACCENTS
from PySide6.QtGui import QColor, QGuiApplication, QPalette
import re

THEMES = ('light', 'dark', 'system')  # Réglage « theme » : 0 clair, 1 sombre, 2 comme Windows (par défaut).


def system_dark() -> bool:
    """Windows en mode sombre (Paramètres › Personnalisation › Couleurs)."""
    from PySide6.QtCore import Qt
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt antérieur à 6.5.
        return False


def high_contrast() -> bool:
    """Contraste élevé de Windows (Accessibilité › Thèmes de contraste) activé."""
    import os
    if os.name != 'nt':
        return False
    import ctypes
    from ctypes import wintypes

    class HIGHCONTRAST(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.UINT), ('dwFlags', wintypes.DWORD), ('lpszDefaultScheme', wintypes.LPWSTR)]
    value = HIGHCONTRAST(ctypes.sizeof(HIGHCONTRAST), 0, None)
    try:
        if ctypes.windll.user32.SystemParametersInfoW(0x0042, ctypes.sizeof(value), ctypes.byref(value), 0):
            return bool(value.dwFlags & 0x1)  # HCF_HIGHCONTRASTON
    except (AttributeError, OSError):
        pass
    return False


def text_scale() -> float:
    """Taille du texte de Windows (Accessibilité › Taille du texte), de 1,0 à 2,25."""
    import os
    if os.name != 'nt':
        return 1.0
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Accessibility') as key:
            value = int(winreg.QueryValueEx(key, 'TextScaleFactor')[0])
    except (OSError, ValueError, TypeError):
        return 1.0
    return min(2.25, max(1.0, value / 100))


class SystemTheme(Theme):
    """Thème validé, complété par les réglages d’accessibilité de Windows : couleurs du contraste élevé et taille
    du texte. theme.py reste identique à la maquette : seuls les couleurs et la taille des polices sont adaptées."""
    high_contrast = False
    system_palette = None
    text_scale = 1.0

    @property
    def colors(self):
        if not self.high_contrast or self.system_palette is None:
            return Theme.colors.fget(self)
        role = lambda name: self.system_palette.color(name).name()
        text, window, base = role(QPalette.WindowText), role(QPalette.Window), role(QPalette.Base)
        highlight, highlighted = role(QPalette.Highlight), role(QPalette.HighlightedText)
        return dict(bg=window, surface=base, panel=window, text=text, muted=text, border=text, hover=window,
                    warning_bg=base, warning=text, danger_bg=base, danger=text, skeleton=text,
                    accent=highlight, on_accent=highlighted, soft=window)

    def apply(self):
        super().apply()
        if abs(self.text_scale - 1) > .01:
            app = QApplication.instance()
            app.setStyleSheet(re.sub(r'font-size:\s*(\d+(?:\.\d+)?)px',
                                     lambda size: f'font-size: {round(float(size[1]) * self.text_scale)}px', app.styleSheet()))


def follow_windows(app, database) -> None:
    """Thème « Comme Windows » : suit le passage de Windows en mode clair ou sombre, sans redémarrer."""
    app.smail_theme_database = database
    if getattr(app, 'smail_follows_windows', False):
        return
    app.smail_follows_windows = True
    def changed(*_):
        db = getattr(app, 'smail_theme_database', None)
        if db is not None and db.setting('theme', 2) == 2:
            install_theme(db)
    try:
        QGuiApplication.styleHints().colorSchemeChanged.connect(changed)
    except AttributeError:
        pass


def install_theme(database) -> Theme:
    """Relit les préférences visuelles via l'API existante, sans les modifier."""
    app = QApplication.instance()
    if app is None:
        raise RuntimeError(tr('Une application Qt doit être créée avant son thème.'))
    theme = getattr(app, 'smail_theme', None)
    if theme is None:
        system_palette = QPalette(app.palette())  # Couleurs de Windows (contraste élevé), avant les nôtres.
        app.setStyle('Fusion')
        configure_fonts(app)
        theme = SystemTheme()  # Le style 1 reste le choix initial.
        theme.system_palette = system_palette
        theme.text_scale = text_scale()
        if abs(theme.text_scale - 1) > .01:
            font = app.font()
            font.setPointSizeF(font.pointSizeF() * theme.text_scale)
            app.setFont(font)
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
    choice = database.setting('theme', 2)
    theme.dark = choice == 1 or (choice not in (0, 1) and system_dark())
    theme.high_contrast = high_contrast()
    follow_windows(app, database)
    theme.reduced_motion = bool(database.setting('ui_reduced_motion', False))
    theme.apply()
    return theme
