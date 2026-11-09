"""Tokens et état d'apparence centralisés ; rien n'est sauvegardé sur disque."""
from pathlib import Path
from string import Template
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

VARIANTS = {1: ('Classique productif', 'Tout à portée de main'),
            2: ('Épurée', 'De l’espace pour l’essentiel'),
            3: ('Rapide au clavier', 'Moins de gestes, plus de rythme')}
ACCENTS = {'Bleu': ('#275BCC', '#9EB8FF'), 'Prune': ('#7545B0', '#C8ADFA'), 'Sarcelle': ('#007568', '#81D9CB')}
LIGHT = dict(bg='#F3F5F8', surface='#FFFFFF', panel='#F8FAFC', text='#172238', muted='#56657A',
             border='#D7DEE8', hover='#EAF0F7', warning_bg='#FFF5DF', warning='#805100',
             danger_bg='#FFF0F0', danger='#AE252F', skeleton='#DFE5ED')
DARK = dict(bg='#12161E', surface='#1B212D', panel='#171D27', text='#EFF3FA', muted='#B0BDD0',
            border='#3B475B', hover='#293447', warning_bg='#382C15', warning='#FFD88F',
            danger_bg='#3D222C', danger='#FFB0B8', skeleton='#344056')

def luminance(hex_color):
    color = QColor(hex_color)
    rgb = [color.redF(), color.greenF(), color.blueF()]
    values = [v/12.92 if v <= 0.04045 else ((v+0.055)/1.055)**2.4 for v in rgb]
    return sum(a*b for a,b in zip(values, (0.2126,0.7152,0.0722)))

def contrast(a, b):
    values = sorted((luminance(a), luminance(b)))
    return (values[1]+0.05)/(values[0]+0.05)

def blend(a, b, proportion):
    a, b = QColor(a), QColor(b)
    return QColor(*(round(x*proportion+y*(1-proportion)) for x,y in zip(a.getRgb()[:3], b.getRgb()[:3]))).name()

class Theme(QObject):
    changed = Signal()

    def __init__(self, variant=1, dark=False):
        super().__init__()
        self.variant, self.dark = variant, dark
        self.density = 'Normale'
        self.accent_name = 'Bleu'
        self.custom_accent = None
        self.reduced_motion = False
        self.capture_mode = False

    @property
    def colors(self):
        colors = dict(DARK if self.dark else LIGHT)
        accent = self.custom_accent or ACCENTS[self.accent_name][self.dark]
        color = QColor(accent)
        for _ in range(80):
            if contrast(color.name(), colors['surface']) >= 4.5:
                break
            color = QColor(blend('#FFFFFF' if self.dark else '#000000', color.name(), .10))
        colors['accent'] = color.name()
        colors['on_accent'] = '#FFFFFF' if contrast('#FFFFFF', colors['accent']) >= 4.5 else '#111827'
        colors['soft'] = blend(colors['accent'], colors['surface'], .15 if self.dark else .09)
        return colors

    @property
    def row_height(self):
        base = {1: 76, 2: 102, 3: 66}[self.variant]
        return base + {'Compacte': -12, 'Normale': 0, 'Aérée': 16}[self.density]

    def update(self, **values):
        for key, value in values.items():
            setattr(self, key, value)
        self.apply()

    def apply(self):
        app = QApplication.instance()
        colors = self.colors
        values = dict(colors, pad={'Compacte': 6, 'Normale': 9, 'Aérée': 12}[self.density],
                      radius=10 if self.variant != 3 else 6,
                      heading_size={1:24,2:26,3:21}[self.variant],message_size={1:23,2:25,3:22}[self.variant])
        assets = Path(__file__).parent / 'assets' / 'style-icons'
        mode = 'sombre' if self.dark else 'clair'
        values.update(down_arrow=(assets / f'down-{mode}.svg').as_posix(),up_arrow=(assets / f'up-{mode}.svg').as_posix())
        qss = Template((Path(__file__).parent / 'styles' / 'theme.qss').read_text(encoding='utf-8')).substitute(values)
        palette = QPalette()
        for role, token in [(QPalette.Window,'bg'), (QPalette.WindowText,'text'), (QPalette.Base,'surface'),
                            (QPalette.Text,'text'), (QPalette.Button,'surface'), (QPalette.ButtonText,'text'),
                            (QPalette.Highlight,'accent'), (QPalette.HighlightedText,'on_accent')]:
            palette.setColor(role, QColor(colors[token]))
        app.setPalette(palette)
        app.setStyleSheet(qss)
        self.changed.emit()
