"""Liste des messages sans pagination : les messages plus anciens se chargent au défilement."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
from mailclient.core.accounts import Account, Server
from mailclient.core.service import MailService
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database

ME = Account('Moi', 'moi@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))


def listing(count):
    return [dict(uid=str(1000 - i), subject=f'Message {i}', sender='Alice <alice@example.com>', folder='INBOX',
                 uidvalidity='7', date='Mon, 02 Mar 2026 10:00:00 +0100', unread=False, starred=False,
                 attachment=False, message_id=f'<m{i}@example.com>', references='', in_reply_to='')
            for i in range(count)]


def test_older_messages_load_when_scrolling_to_the_bottom(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import process_until
    from mailclient.ui.main_window import MainWindow
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    db.set_setting('conversation_view', False)
    mailbox, requested = listing(130), []
    class Client:
        uidvalidity = '7'
        def folders(self):
            return [('INBOX', 'Boîte de réception')]
        def messages(self, folder, page, query=''):
            requested.append(page)
            # Un message arrivé après la première page décale la suite d’un cran : pas de doublon.
            shift = 1 if page else 0
            rows = mailbox[page * 50 - shift:(page + 1) * 50 - shift]
            return [dict(r) for r in rows], len(mailbox)
        def message_raw(self, folder, uid):
            return f'From: a@example.com\r\nSubject: Ouvert {uid}\r\n\r\nCorps'.encode()
    monkeypatch.setattr(MailService, 'client', lambda *args: Client())
    window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    try:
        assert not hasattr(window, 'next') and not hasattr(window, 'previous')  # Plus de barre de pages.
        window.resize(1200, 700)
        window.show()
        window.reload_accounts()
        assert process_until(lambda: not window.busy and window.table.count() == 50)
        process_until(lambda: False, 0.2)
        assert requested == [0]  # La première page remplit la liste : rien d’autre n’est chargé.
        assert '50 sur 130' in window.page_label.text()
        window.table.setCurrentRow(2)
        assert process_until(lambda: not window.busy and window.reader.mail is not None)
        opened = window.reader.mail.subject
        bar = window.table.verticalScrollBar()
        assert bar.maximum() > 0
        bar.setValue(bar.maximum())
        assert process_until(lambda: len(window.rows) == 99 and not window.loading_more)
        assert len({r['uid'] for r in window.rows}) == 99
        assert window.table.currentRow() == 2 and window.table.item(2).isSelected()  # Sélection conservée.
        assert window.reader.mail.subject == opened  # Le message lu reste affiché.
        assert '99 sur 130' in window.page_label.text()
        bar.setValue(bar.maximum())
        assert process_until(lambda: len(window.rows) == 130 and not window.loading_more)
        assert window.page_label.text() == '130 messages'
        bar.setValue(bar.maximum())
        process_until(lambda: False, 0.2)
        assert requested == [0, 1, 2]  # Tout est chargé : plus aucune requête.
        # Après une action, la liste est rechargée à la même profondeur.
        window.load_messages()
        assert process_until(lambda: not window.busy and len(window.rows) == 130)
        assert requested[3:] == [0, 1, 2]
    finally:
        window.reader.shutdown()
        window.close()
        from shiboken6 import delete
        delete(window)


def test_short_list_fills_itself_without_scrolling(tmp_path, monkeypatch):
    """Filtre « Non lus » ou grande fenêtre : la liste se complète seule, dans une limite raisonnable."""
    from mailclient.tests.test_ui import process_until
    from mailclient.ui.main_window import MainWindow
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    db.set_setting('conversation_view', False)
    mailbox, requested = listing(1000), []
    class Client:
        uidvalidity = '7'
        def folders(self):
            return [('INBOX', 'Boîte de réception')]
        def messages(self, folder, page, query=''):
            requested.append(page)
            return [dict(r) for r in mailbox[page * 50:(page + 1) * 50]], len(mailbox)
    monkeypatch.setattr(MailService, 'client', lambda *args: Client())
    window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    try:
        window.resize(1200, 700)
        window.show()
        window.reload_accounts()
        assert process_until(lambda: not window.busy and requested)
        window.user_filter('Non lus')  # Aucun message non lu : la liste visible reste vide.
        process_until(lambda: False, 1)
        assert requested == [0, 1, 2, 3, 4]  # Quatre pages automatiques au plus, puis on attend l’utilisateur.
    finally:
        window.reader.shutdown()
        window.close()
        from shiboken6 import delete
        delete(window)
