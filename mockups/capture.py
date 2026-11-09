"""Export déterministe des vrais widgets Qt en PNG ; écrit seulement sous mockups/."""
from pathlib import Path
import hashlib
import html
import json
from PySide6.QtCore import Qt, QRectF, QCoreApplication, QEvent
from PySide6.QtGui import QImage, QPainter, QColor, QFont
from shiboken6 import delete
from .theme import Theme, VARIANTS
from .window import MockupWindow, SCENES
from .data import messages

DIRECTORY = Path(__file__).parent / 'screenshots'

def export_all(app):
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    manifest = []
    for variant in (1,2,3):
        for dark in (False,True):
            theme = Theme(variant,dark)
            theme.capture_mode = True
            theme.apply()
            window = MockupWindow(theme)
            window.show()
            app.processEvents()
            destination = DIRECTORY / f'variante-{variant}' / ('sombre' if dark else 'clair')
            destination.mkdir(parents=True,exist_ok=True)
            for index,(scene,title) in enumerate(SCENES,1):
                for dialog in window.dialogs:
                    dialog.close()
                window.mails = messages()
                target = window.show_scene(scene)
                app.processEvents()
                QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
                if target.layout():
                    target.layout().activate()
                target.repaint()
                app.processEvents()
                filename = destination / f'{index:02d}-{scene}.png'
                pixmap = target.grab()
                if not pixmap.save(str(filename),'PNG'):
                    raise RuntimeError('Impossible d’écrire '+str(filename))
                manifest.append(dict(variant=variant,theme='sombre' if dark else 'clair',scene=scene,title=title,
                                     file=str(filename.relative_to(DIRECTORY)).replace('\\','/'),
                                     width=pixmap.width(),height=pixmap.height(),
                                     sha256=hashlib.sha256(filename.read_bytes()).hexdigest()))
            window.close()
            delete(window)
            app.processEvents()
            print(f'Variante {variant} · {"sombre" if dark else "clair"} : {len(SCENES)} captures.',flush=True)
    (DIRECTORY / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    contact_sheet()
    gallery(manifest)
    print(f'{len(manifest)} captures + COMPARAISON.png. Galerie : mockups/screenshots/index.html',flush=True)

def contact_sheet():
    image = QImage(1784,1110,QImage.Format_RGB32)
    image.fill(QColor('#101722'))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setPen(QColor('#ECF2FC'))
    painter.setFont(QFont('Segoe UI',26,QFont.DemiBold))
    painter.drawText(32,58,'Trois façons de faire place au courrier.')
    painter.setPen(QColor('#B0BDD0'))
    painter.setFont(QFont('Segoe UI',12))
    painter.drawText(34,92,'Smail / Maquettes PySide6 · mêmes données, trois rythmes · clair et sombre')
    for variant in (1,2,3):
        x = 32+(variant-1)*584
        painter.setPen(QColor('#ECF2FC'))
        painter.setFont(QFont('Segoe UI',15,QFont.DemiBold))
        painter.drawText(x,141,f'0{variant}  {VARIANTS[variant][0]}')
        painter.setFont(QFont('Segoe UI',10))
        painter.setPen(QColor('#B0BDD0'))
        painter.drawText(x,167,VARIANTS[variant][1])
        for row,theme in enumerate(('clair','sombre')):
            source = QImage(str(DIRECTORY / f'variante-{variant}' / theme / '01-principale.png'))
            y = 190+row*422
            painter.drawImage(QRectF(x,y,552,360),source)
            painter.setPen(QColor('#B0BDD0'))
            painter.setFont(QFont('Segoe UI',10))
            painter.drawText(x,y+383,'THÈME '+theme.upper())
    painter.setPen(QColor('#B0BDD0'))
    painter.drawText(34,1060,'19 écrans par variante et par thème · 30 messages fictifs · aucune connexion réseau · intégration non appliquée')
    painter.end()
    image.save(str(DIRECTORY / 'COMPARAISON.png'))

def gallery(manifest):
    sections = []
    for variant in (1,2,3):
        for theme in ('clair','sombre'):
            cards = []
            for item in manifest:
                if item['variant'] == variant and item['theme'] == theme:
                    file,title = html.escape(item['file'],quote=True),html.escape(item['title'])
                    cards.append(f'<a href="{file}"><img loading="lazy" src="{file}" alt="{title}"><span>{title}</span></a>')
            sections.append(f'<section id="v{variant}-{theme}"><h2>0{variant} · {VARIANTS[variant][0]} / {theme}</h2><div class="grid">'+''.join(cards)+'</div></section>')
    source = '''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Smail — Galerie des maquettes</title><style>body{font:15px 'Segoe UI',sans-serif;background:#101722;color:#eef3fc;margin:32px;line-height:1.5}a{color:inherit;text-decoration:none}header{max-width:1100px}h1{font-size:36px;letter-spacing:-1px;margin-bottom:8px}p{color:#b0bdd0}nav{display:flex;gap:12px;flex-wrap:wrap;position:sticky;top:0;background:#101722;padding:16px 0;z-index:2}nav a{padding:9px 16px;border:1px solid #536074;border-radius:7px}section{scroll-margin-top:85px;margin-top:45px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px}div.grid>a{border:1px solid #3b475b;border-radius:9px;overflow:hidden;background:#1b212d}img{display:block;width:100%;aspect-ratio:1.5;object-fit:contain;background:#171d27}span{display:block;padding:12px}a:focus-visible{outline:3px solid #9eb8ff;outline-offset:4px}.hero{width:100%;aspect-ratio:auto;max-width:1500px}</style><header><p>LABORATOIRE D’INTERFACE / SMAIL</p><h1>Trois rythmes. Les mêmes possibilités.</h1><p>Captures réelles des widgets PySide6. Cliquez pour afficher chaque PNG à sa taille native. Tout est local, sans service extérieur.</p></header><nav>'''
    source += ''.join(f'<a href="#v{v}-{t}">0{v} · {t}</a>' for v in (1,2,3) for t in ('clair','sombre'))
    source += '</nav><a href="COMPARAISON.png"><img class="hero" src="COMPARAISON.png" alt="Comparaison des trois variantes en clair et sombre"></a>'+''.join(sections)+'</html>'
    (DIRECTORY / 'index.html').write_text(source,encoding='utf-8')
