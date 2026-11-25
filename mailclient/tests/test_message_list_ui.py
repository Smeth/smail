"""Liste des messages : groupes de dates et actions au survol."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from datetime import datetime, timedelta
from email.utils import format_datetime
from PySide6.QtCore import Qt
from mailclient.ui.view_models import date_group

NOW = datetime(2026, 11, 24, 15, 0)


def stamp(**delta):
    return (NOW - timedelta(**delta)).timestamp()


def test_date_groups():
    assert date_group(stamp(hours=2), NOW) == 'Aujourd’hui'
    assert date_group(stamp(days=-1), NOW) == 'Aujourd’hui'  # Date future (horloge de l’expéditeur).
    assert date_group(stamp(days=1), NOW) == 'Hier'
    assert date_group(stamp(days=4), NOW) == 'Cette semaine'
    assert date_group(stamp(days=10), NOW) == 'Plus tôt ce mois-ci'
    assert date_group(stamp(days=40), NOW) == 'Octobre 2026'
    assert date_group(datetime(2025, 2, 3).timestamp(), NOW) == 'Février 2025'
    assert date_group(0, NOW) == 'Date inconnue'


def test_headers_follow_filters_and_hover_actions_act_on_the_row(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import APP, process_until  # noqa: F401
    from mailclient.core.service import MailService
    from mailclient.core.tls_policy import TLSPolicy
    from mailclient.storage.database import Database
    from mailclient.tests.test_scheduler import ME, Client
    from mailclient.ui.components import HEADER_ROLE, HEADER_HEIGHT
    from mailclient.ui.main_window import MainWindow
    now = datetime.now().astimezone()
    def row(uid, days, unread=False):
        return dict(uid=uid, subject=f'Sujet {uid}', sender='Alice <alice@example.com>', folder='INBOX', uidvalidity='7',
                    date=format_datetime(now - timedelta(days=days)), unread=unread, starred=False, attachment=False,
                    message_id=f'<{uid}@x>', references='', in_reply_to='')
    listing = [row('9', 0, unread=True), row('8', 0), row('7', 1, unread=True), row('6', 40)]
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    db.set_setting('conversation_view', False)
    client = Client()
    client.uidvalidity = '7'
    client.messages = lambda folder, page, query='': ([dict(r) for r in listing], len(listing))
    monkeypatch.setattr(MailService, 'client', lambda *args: client)
    window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    try:
        window.reload_accounts()
        window.select_account(ME.id)
        process_until(lambda: not window.busy and window.table.count() == 4)
        assert window.table.count() == 4, (window.table.count(), window.statusBar().currentMessage(), window.toast.text.text())
        headers = [window.table.item(i).data(HEADER_ROLE) for i in range(4)]
        assert headers[:3] == ['Aujourd’hui', None, 'Hier'] and headers[3] and headers[3] not in ('Hier', 'Aujourd’hui')
        delegate = window.table.itemDelegate()
        index = window.table.model().index(0, 0)
        assert delegate.sizeHint(None, index).height() == window.appearance.row_height + HEADER_HEIGHT
        window.filter_page('Non lus')  # Le titre « Aujourd’hui » reste sur le premier message visible.
        assert [window.table.item(i).data(HEADER_ROLE) for i in (0, 2)] == ['Aujourd’hui', 'Hier']
        window.filter_page('Tous')
        moved = []
        monkeypatch.setattr(window, 'move', lambda kind: moved.append((kind, [r['uid'] for r in window.selected_rows()])))
        window.table.item(1).setSelected(True)
        window.row_action(window.table.model().index(2, 0), 'archive')
        assert moved == [('archive', ['7'])]  # Seule la ligne survolée, même si une autre était sélectionnée.
        window.table.grab()  # Dessin des titres et des lignes sans erreur.
    finally:
        window.reader.shutdown()
        window.close()
        from shiboken6 import delete
        delete(window)


def test_changing_folder_resets_filter_and_hides_unread_in_sent(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import APP, process_until  # noqa: F401
    from mailclient.core.service import MailService
    from mailclient.core.tls_policy import TLSPolicy
    from mailclient.storage.database import Database
    from mailclient.tests.test_scheduler import ME, Client
    from mailclient.ui.main_window import MainWindow
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    client = Client()  # Dossiers : Boîte de réception et Envoyés.
    client.uidvalidity = '7'
    client.messages = lambda folder, page, query='': ([], 0)
    monkeypatch.setattr(MailService, 'client', lambda *args: client)
    window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    try:
        window.reload_accounts()
        window.select_account(ME.id)
        assert process_until(lambda: not window.busy and window.folders.count() == 2)
        window.filter_buttons['Non lus'].click()
        assert window.page_filter == 'Non lus'
        window.folders.setCurrentRow(1)  # Envoyés.
        assert process_until(lambda: not window.busy)
        assert window.page_filter == 'Tous' and window.filter_buttons['Tous'].isChecked()
        assert window.filter_buttons['Non lus'].isHidden() and not window.filter_buttons['Pièces jointes'].isHidden()
        window.folders.setCurrentRow(0)  # Retour à la réception : « Non lus » revient.
        assert process_until(lambda: not window.busy)
        assert not window.filter_buttons['Non lus'].isHidden()
    finally:
        window.reader.shutdown()
        window.close()
        from shiboken6 import delete
        delete(window)


def test_opening_marks_as_read_in_smail_and_on_the_server(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import APP, process_until  # noqa: F401
    from mailclient.core.service import MailService
    from mailclient.core.tls_policy import TLSPolicy
    from mailclient.storage.database import Database
    from mailclient.tests.test_scheduler import ME, Client
    from mailclient.ui.folder_list import COUNT_ROLE
    from mailclient.ui.main_window import MainWindow
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    db.set_setting('conversation_view', False)
    db.cache_put('unread', ME.id, {'INBOX': 2}, ME.id)
    client = Client()
    client.uidvalidity = '7'
    now = datetime.now().astimezone()
    listing = [dict(uid=uid, subject=f'Sujet {uid}', sender='Alice <alice@example.com>', folder='INBOX', uidvalidity='7',
                    date=format_datetime(now), unread=True, starred=False, attachment=False, message_id=f'<{uid}@x>',
                    references='', in_reply_to='') for uid in ('9', '8')]
    client.messages = lambda folder, page, query='': ([dict(r) for r in listing], 2)
    client.message_raw = lambda folder, uid: f'From: a@x.fr\r\nSubject: Sujet {uid}\r\n\r\nCorps'.encode()
    actions = []
    client.action = lambda folder, uids, validity, action, target='': actions.append((folder, uids, action))
    monkeypatch.setattr(MailService, 'client', lambda *args: client)
    window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    try:
        window.reload_accounts()
        window.select_account(ME.id)
        assert process_until(lambda: not window.busy and window.table.count() == 2)
        window.table.setCurrentRow(0)
        assert process_until(lambda: actions and not window.busy)
        assert actions == [('INBOX', '9', 'read')]  # Sur le serveur : plus « non lu » dans le webmail ni le téléphone.
        assert not window.table.item(0).data(Qt.UserRole).unread  # Dans Smail : plus en gras.
        assert window.folders.item(0).data(COUNT_ROLE) == 1  # Compteur du dossier ajusté.
        db.set_setting('mark_read_on_open', False)  # Réglage désactivé : ouverture sans marquage.
        window.table.setCurrentRow(1)
        assert process_until(lambda: window.reader.mail is not None and not window.busy and window.reader.mail.subject == 'Sujet 8')
        process_until(lambda: False, 0.3)
        assert actions == [('INBOX', '9', 'read')] and window.table.item(1).data(Qt.UserRole).unread
        db.set_setting('mark_read_on_open', True)
        def refuse(*args, **kwargs):
            raise RuntimeError('refusé')
        client.action = refuse  # Le serveur refuse : l’état « non lu » revient.
        window.table.setCurrentRow(0)
        assert process_until(lambda: not window.busy and window.reader.mail.subject == 'Sujet 9')
        window.table.setCurrentRow(1)
        assert process_until(lambda: not window.busy and window.toast.property('kind') == 'error')
        assert window.table.item(1).data(Qt.UserRole).unread
    finally:
        window.reader.shutdown()
        window.close()
        from shiboken6 import delete
        delete(window)
