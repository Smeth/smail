"""Captures d’écran pour la fiche du Microsoft Store (1920 × 1080), avec des données d’exemple uniquement.

  python tools/store_screenshots.py            -> dist/store/*.png

Aucun compte réel, aucun réseau : serveur simulé, adresses fictives (example.com)."""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mailclient.tests.test_ui import APP, process_until  # noqa: E402
from mailclient.core.accounts import Account, Server  # noqa: E402
from mailclient.core.parser import Mail  # noqa: E402
from mailclient.core.service import MailService  # noqa: E402
from mailclient.core.tls_policy import TLSPolicy  # noqa: E402
from mailclient.storage.database import Database  # noqa: E402

NOW = datetime.now().astimezone()
ME = Account('Camille Martin', 'camille@example.com', Server('mail.example.com', 993), Server('mail.example.com', 465))
MESSAGES = [
    ('9', 0, 'Léa Bernard <lea@example.com>', 'Réunion de lancement jeudi', 'Bonjour Camille, je te propose jeudi 10 h pour le lancement…', True, True),
    ('8', 0, 'Équipe Projet <projet@example.com>', 'Compte rendu du comité', 'Voici le compte rendu et les prochaines étapes.', True, False),
    ('7', 1, 'Thomas Petit <thomas@example.com>', 'Re: Devis cuisine', 'Merci pour le devis, c’est validé de notre côté.', False, True),
    ('6', 2, 'Banque Exemple <info@example.com>', 'Votre relevé de novembre', 'Votre relevé mensuel est disponible.', False, False),
    ('5', 4, 'Sophie Laurent <sophie@example.com>', 'Photos du week-end', 'Les photos sont en pièces jointes !', False, True),
    ('4', 12, 'Association Les Amis <contact@example.com>', 'Lettre d’information', 'Le programme des sorties de décembre.', False, False),
    ('3', 35, 'Marc Dubois <marc@example.com>', 'Facture octobre', 'Veuillez trouver la facture ci-jointe.', False, True),
]


class Client:
    uidvalidity = '7'

    def folders(self):
        return [('INBOX', 'Boîte de réception'), ('Drafts', 'Brouillons'), ('Sent', 'Envoyés'), ('Archive', 'Archives'),
                ('Junk', 'Spam'), ('Trash', 'Corbeille'), ('Projets', 'Projets'), ('Famille', 'Famille')]

    def messages(self, folder, page, query=''):
        rows = [dict(uid=uid, subject=subject, sender=sender, folder='INBOX', uidvalidity='7',
                     date=format_datetime(NOW - timedelta(days=days, hours=2)), unread=unread, starred=uid == '7',
                     attachment=attachment, message_id=f'<{uid}@example.com>', references='', in_reply_to='', preview=preview)
                for uid, days, sender, subject, preview, unread, attachment in MESSAGES]
        return rows, len(rows)

    def message_raw(self, folder, uid):
        return ('From: Léa Bernard <lea@example.com>\r\nTo: camille@example.com\r\nSubject: Réunion de lancement jeudi\r\n'
                'Content-Type: text/plain; charset=utf-8\r\n\r\nBonjour Camille,\r\n\r\nJe te propose jeudi à 10 h pour '
                'la réunion de lancement du projet.\r\nL’ordre du jour est en pièce jointe.\r\n\r\nBonne journée,\r\nLéa\r\n').encode()


def main():
    out = ROOT / 'dist' / 'store'
    out.mkdir(parents=True, exist_ok=True)
    MailService.client = lambda *args: Client()
    db = Database(Path(tempfile.mkdtemp()) / 'settings.db')
    db.save(ME)
    db.cache_put('unread', ME.id, {'INBOX': 2, 'Projets': 1}, ME.id)
    from mailclient.ui.main_window import MainWindow
    from mailclient.ui.compose_window import ComposeWindow
    from mailclient.ui.settings_dialog import SettingsDialog
    window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    window.resize(1920, 1080)
    window.show()
    window.reload_accounts()
    window.select_account(ME.id)
    process_until(lambda: not window.busy and window.table.count() == len(MESSAGES), 10)
    window.last_sync = datetime.now()
    window.update_connection()
    window.table.setCurrentRow(0)
    process_until(lambda: window.reader.mail is not None and not window.busy, 10)
    process_until(lambda: False, 1.5)
    window.grab().save(str(out / '1-boite-de-reception.png'))
    window.toggle_theme()
    process_until(lambda: False, 1.5)
    window.grab().save(str(out / '2-theme-sombre.png'))
    window.toggle_theme()
    composer = ComposeWindow(window.service, [ME], ME, dict(to='Léa Bernard <lea@example.com>', subject='Re: Réunion de lancement jeudi',
                             body='Bonjour Léa,\n\nJeudi 10 h me convient parfaitement. Je préparre la présentation.\n\nÀ jeudi,\nCamille'),
                             parent=window)
    composer.resize(1366, 900)
    composer.show()
    process_until(lambda: False, 1.5)
    composer.grab().save(str(out / '3-redaction.png'))
    composer.saved_revision = composer.revision
    composer.close()
    dialog = SettingsDialog(db, window, 'Général')
    dialog.resize(1366, 860)
    dialog.show()
    process_until(lambda: False, 1)
    dialog.grab().save(str(out / '4-preferences.png'))
    dialog.reject()
    window.reader.shutdown()
    print('Captures :', out)


if __name__ == '__main__':
    main()
