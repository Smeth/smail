"""Lancement autonome : python mockups/run_mockup.py --variante 2 --theme sombre."""
import argparse
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

def main():
    parser = argparse.ArgumentParser(description='Maquettes Smail — aucune connexion aux comptes réels')
    parser.add_argument('--variante',type=int,choices=(1,2,3),default=1)
    parser.add_argument('--theme',choices=('clair','sombre'),default='clair')
    parser.add_argument('--densite',choices=('compacte','normale','aeree'),default='normale')
    parser.add_argument('--ecran',default='principale')
    parser.add_argument('--captures',action='store_true',help='Générer les PNG des trois variantes dans les deux thèmes')
    parser.add_argument('--smoke-test',action='store_true')
    args = parser.parse_args()
    if args.captures or args.smoke_test:
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont
    from PySide6.QtCore import QTimer
    from mockups.theme import Theme
    from mockups.window import MockupWindow, SCENES
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    from mockups.fonts import configure_fonts
    configure_fonts(app)
    app.setApplicationName('Smail · Maquettes')
    if args.captures:
        from mockups.capture import export_all
        export_all(app)
        return 0
    if args.ecran not in dict(SCENES):
        parser.error('Écran inconnu. Choix : '+', '.join(dict(SCENES)))
    theme = Theme(args.variante,args.theme == 'sombre')
    theme.density = {'compacte':'Compacte','normale':'Normale','aeree':'Aérée'}[args.densite]
    theme.apply()
    window = MockupWindow(theme)
    window.show()
    if args.ecran != 'principale':
        QTimer.singleShot(0,lambda:window.show_scene(args.ecran))
    if args.smoke_test:
        QTimer.singleShot(300,app.quit)
    return app.exec()

if __name__ == '__main__':
    raise SystemExit(main())
