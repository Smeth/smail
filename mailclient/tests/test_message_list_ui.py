"""Liste des messages : groupes de dates et actions au survol."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from datetime import datetime, timedelta
from email.utils import format_datetime
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
