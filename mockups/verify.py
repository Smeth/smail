"""Vérifications de la maquette uniquement, sans pytest ni import métier.

Exécuter : python -B mockups/verify.py
"""
import ast
import os
from pathlib import Path
import socket
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QPushButton, QLineEdit
from PySide6.QtTest import QTest
from mockups.fonts import configure_fonts
from mockups.theme import Theme, ACCENTS, contrast
from mockups.data import messages, ACCOUNTS
from mockups.window import MockupWindow, SCENES
from mockups.dialogs import AccountDialog, CertificateDialog, CommandPalette, SettingsDialog

APP = QApplication.instance() or QApplication([])
APP.setStyle('Fusion')
configure_fonts(APP)

class MockupTests(unittest.TestCase):
    def setUp(self):
        self.theme = Theme()
        self.theme.capture_mode = True
        self.theme.apply()
        self.window = MockupWindow(self.theme)
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        from shiboken6 import delete
        self.window.close()
        delete(self.window)
        APP.processEvents()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_all_screens_in_all_variants_and_themes(self):
        for variant in (1,2,3):
            for dark in (False,True):
                self.theme.update(variant=variant,dark=dark)
                for scene,_ in SCENES:
                    target = self.window.show_scene(scene)
                    APP.processEvents()
                    self.assertFalse(target.grab().isNull(),(variant,dark,scene))
                    if target != self.window:
                        target.close()

    def test_data_and_keyboard_navigation(self):
        self.assertEqual(len(messages()),30)
        self.assertEqual(len(ACCOUNTS),3)
        self.assertTrue(any(not a.secure for a in ACCOUNTS))
        self.assertTrue(any(m.remote_images for m in messages()))
        self.assertTrue(any(m.html for m in messages()))
        self.assertTrue(any(a.suspect for m in messages() for a in m.attachments))
        self.theme.update(variant=3)
        self.window.mail_list.setFocus()
        APP.processEvents()
        first = self.window.mail_list.currentRow()
        QTest.keyClick(self.window.mail_list,Qt.Key_J)
        self.assertEqual(self.window.mail_list.currentRow(),first+1)
        QTest.keyClick(self.window.mail_list,Qt.Key_K)
        self.assertEqual(self.window.mail_list.currentRow(),first)

    def test_account_warning_confirmation_and_ports(self):
        dialog = AccountDialog(self.theme,self.window)
        self.window.open_dialog(dialog)
        dialog.servers['IMAP'][1].setCurrentIndex(2)
        self.assertEqual(dialog.servers['IMAP'][2].value(),143)
        self.assertFalse(dialog.primary.isEnabled())
        dialog.confirm.setChecked(True)
        self.assertTrue(dialog.primary.isEnabled())
        dialog.servers['SMTP'][1].setCurrentIndex(1)
        self.assertEqual(dialog.servers['SMTP'][2].value(),587)
        self.assertFalse(dialog.primary.isEnabled())
        dialog.servers['IMAP'][2].setValue(1143)
        self.assertEqual(dialog.servers['IMAP'][2].value(),1143)
        dialog.confirm.setChecked(True)
        dialog.auth.setCurrentIndex(1)
        self.assertFalse(dialog.primary.isEnabled())
        self.assertIn('OAuth2 exige',dialog.status.text())

    def test_certificate_cancel_by_default(self):
        dialog = CertificateDialog(self.theme,self.window)
        self.window.open_dialog(dialog)
        defaults = [button.text() for button in dialog.findChildren(QPushButton) if button.isDefault()]
        self.assertEqual(defaults,['Annuler'])
        self.assertFalse(dialog.remember.isChecked())

    def test_command_palette_search_executes_locally(self):
        called = []
        dialog = CommandPalette(self.theme,[('Action fictive','',lambda:called.append(True))],self.window)
        self.window.open_dialog(dialog)
        dialog.search.setText('fictive')
        self.assertEqual(dialog.list.count(),1)
        dialog.search.setText('introuvable')
        self.assertEqual(dialog.list.count(),0)
        dialog.search.setText('Action')
        dialog.execute()
        self.assertEqual(called,[True])

    def test_search_filters_and_selection(self):
        self.window.show_scene('recherche')
        self.assertEqual(self.window.mail_list.count(),2)
        self.window.set_filter('Pièces jointes')
        self.assertEqual(self.window.mail_list.count(),1)
        self.window.search.setText('un-terme-totalement-inexistant')
        self.assertEqual(self.window.mail_list.count(),0)
        self.assertEqual(self.window.empty_list.heading.text(),'Aucun résultat')

    def test_theme_density_and_custom_accent_contrast(self):
        for dark in (False,True):
            for accent in ACCENTS:
                self.theme.update(dark=dark,accent_name=accent)
                colors = self.theme.colors
                self.assertGreaterEqual(contrast(colors['text'],colors['surface']),4.5)
                self.assertGreaterEqual(contrast(colors['muted'],colors['surface']),4.5)
                self.assertGreaterEqual(contrast(colors['accent'],colors['surface']),4.5)
                self.assertGreaterEqual(contrast(colors['on_accent'],colors['accent']),4.5)
            for color in ('#000000','#FFFFFF','#FEFEEE','#00FF00'):
                self.theme.update(custom_accent=color)
                colors = self.theme.colors
                self.assertGreaterEqual(contrast(colors['accent'],colors['surface']),4.5)
            self.theme.update(custom_accent=None)
        self.theme.update(density='Compacte')
        compact = self.theme.row_height
        self.theme.update(density='Aérée')
        self.assertGreater(self.theme.row_height,compact)

    def test_no_business_imports_or_runtime_network(self):
        root = Path(__file__).parent
        for path in root.glob('*.py'):
            if path.name in {'audit.py','verify.py'}:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node,ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node,ast.ImportFrom):
                    imports = [node.module or '']
                else:
                    continue
                self.assertFalse(any(name.startswith(('mailclient','socket','urllib','requests','http','imaplib','smtplib','keyring','sqlite3')) for name in imports),path.name)
        self.assertIsNone(self.window.browser.loadResource(2,None))

if __name__ == '__main__':
    # Le code Qt de la maquette n’utilise aucun composant réseau. Ce garde-fou
    # rejette aussi tout appel socket Python introduit par erreur dans un futur changement.
    socket.create_connection = lambda *a,**k: (_ for _ in ()).throw(AssertionError('Accès réseau interdit'))
    unittest.main(verbosity=2)
