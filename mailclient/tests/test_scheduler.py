"""Annulation d’envoi, envoi programmé et report de messages."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
from datetime import datetime, timedelta, timezone
import pytest
from mailclient.core import scheduler
from mailclient.core.accounts import Account, Server
from mailclient.core.parser import Attachment
from mailclient.core.service import MailService
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database

ME = Account('Moi', 'moi@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))
GMAIL = Account('G', 'g@gmail.com', Server('imap.gmail.com', 993), Server('smtp.gmail.com', 465))
STATE = dict(to='a@example.com', cc='', bcc='', subject='Rapport', body='Bonjour', mail_html='', reply_id='', references='')
SERVER = 'imap.example.com:993:SSL/TLS'


class Vault:
    def get(self, key):
        return 'mot-de-passe-de-test'

    def set(self, *args):
        pass


class Client:
    def __init__(self, folders=None):
        self.calls, self.created = [], []
        self.list = folders or [('INBOX', 'Boîte de réception'), ('Sent', 'Envoyés')]
        self.found = ('41', '9')

    def folders(self):
        return list(self.list)

    def append(self, folder, raw, draft=False):
        self.calls.append(('append', folder, draft))

    def action(self, folder, uids, validity, action, target=''):
        self.calls.append(('action', folder, uids, validity, action, target))

    def manage_folder(self, operation, name, new_name=''):
        self.created.append(name)
        self.list.append(('Report&AOk-s', 'Reportés'))

    def find_by_message_id(self, folder, message_id):
        self.calls.append(('find', folder, message_id))
        return self.found


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = Database(tmp_path / 'settings.db')
    for account in (ME, GMAIL):
        db.save(account)
    client = Client()
    monkeypatch.setattr(MailService, 'client', lambda *args: client)
    sent = []
    def fake_send(account, password, tls, message, recipients):
        # La garantie anti-doublon : l’état « sending » est enregistré avant la connexion SMTP.
        sent.append(dict(to=recipients, subject=message['Subject'], states=[i['status'] for i in scheduler.outbox(db)]))
        return env.refused
    env = type('Env', (), {})()
    env.db, env.client, env.sent, env.refused = db, client, sent, {}
    env.service = MailService(db, Vault(), TLSPolicy(db))
    monkeypatch.setattr(scheduler, 'send_message', fake_send)
    return env


def future(minutes=60):
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def test_presets_are_future_and_labelled():
    from mailclient.ui.schedule_dialog import presets
    monday_morning = datetime(2026, 11, 23, 9, 0).astimezone()  # Lundi 9 h.
    labels = [text for text, _ in presets('send', monday_morning)]
    assert labels[0].startswith('Dans 1 heure') and any(text.startswith('Demain à 8 h') for text in labels)
    assert all(moment > monday_morning for _, moment in presets('snooze', monday_morning))
    late = datetime(2026, 11, 23, 22, 0).astimezone()
    assert not any(text.startswith('Ce soir') for text, _ in presets('snooze', late))  # 18 h est passé.


def test_schedule_rejects_past_and_orders_outbox(env):
    with pytest.raises(ValueError):
        scheduler.schedule(env.db, ME, STATE, [], future(-5))
    later = scheduler.schedule(env.db, ME, dict(STATE, subject='B'), [], future(120))
    sooner = scheduler.schedule(env.db, ME, dict(STATE, subject='A'), [Attachment('n.txt', 'text/plain', b'x')], future(30))
    assert [item['id'] for item in scheduler.outbox(env.db)] == [sooner['id'], later['id']]
    assert scheduler.decode_files(sooner['files'])[0].data == b'x'


def test_due_message_is_sent_once_with_copies(env):
    scheduler.schedule(env.db, ME, STATE, [], future(1))
    assert scheduler.process_outbox(env.service, [ME]) == []  # Pas encore dû.
    events = scheduler.process_outbox(env.service, [ME], future(2))
    assert events == [('sent', 'Rapport', '')]
    assert env.sent[0]['to'] == ['a@example.com'] and env.sent[0]['states'] == ['sending']
    assert scheduler.outbox(env.db) == []
    assert ('append', 'Sent', False) in env.client.calls
    assert len(env.db.cache_list('sent-copy')) == 1
    assert scheduler.process_outbox(env.service, [ME], future(3)) == [] and len(env.sent) == 1


def test_failure_and_partial_are_never_retried(env, monkeypatch):
    failing = scheduler.schedule(env.db, ME, dict(STATE, subject='Échec'), [], future(1))
    monkeypatch.setattr(scheduler, 'send_message', lambda *args: (_ for _ in ()).throw(TimeoutError()))
    events = scheduler.process_outbox(env.service, [ME], future(2))
    assert events[0][0] == 'failed' and 'Aucun renvoi automatique' in events[0][2]
    assert env.db.cache_get('outbox', failing['id'])['status'] == 'failed'
    monkeypatch.setattr(scheduler, 'send_message', lambda *args: pytest.fail('renvoi interdit'))
    assert scheduler.process_outbox(env.service, [ME], future(5)) == []
    scheduler.cancel(env.db, failing['id'])
    monkeypatch.setattr(scheduler, 'send_message', lambda *args: {'b@example.com': (550, b'non')})
    partial = scheduler.schedule(env.db, ME, dict(STATE, to='a@example.com, b@example.com'), [], future(1))
    assert scheduler.process_outbox(env.service, [ME], future(2))[0][0] == 'partial'
    assert env.db.cache_get('outbox', partial['id'])['status'] == 'partial'


def test_interrupted_send_becomes_uncertain_and_is_not_resent(env):
    item = scheduler.schedule(env.db, ME, STATE, [], future(1))
    item['status'] = 'sending'  # Smail arrêté brutalement pendant la connexion SMTP.
    env.db.cache_put('outbox', item['id'], item, ME.id)
    assert scheduler.recover(env.db) == 1
    assert env.db.cache_get('outbox', item['id'])['status'] == 'uncertain'
    assert scheduler.process_outbox(env.service, [ME], future(10)) == [] and env.sent == []


def test_gmail_keeps_its_own_sent_copy(env):
    scheduler.schedule(env.db, GMAIL, STATE, [], future(1))
    scheduler.process_outbox(env.service, [GMAIL], future(2))
    assert not any(call[0] == 'append' for call in env.client.calls)


def test_outbox_is_purged_with_account(env):
    scheduler.schedule(env.db, ME, STATE, [], future(30))
    env.db.delete_account(ME.id)
    assert scheduler.outbox(env.db) == []


def snooze_row(uid='12', mid='<m1@x>'):
    return dict(uid=uid, uidvalidity='7', folder='INBOX', account=ME.id, server=SERVER, message_id=mid, subject='À revoir')


def test_snooze_creates_folder_moves_and_returns_unread(env):
    folder = scheduler.snooze(env.service, ME, [snooze_row()], future(60))
    assert folder == 'Report&AOk-s' and env.client.created == ['Reportés']
    assert ('action', 'INBOX', '12', '7', 'move', 'Report&AOk-s') in env.client.calls
    assert scheduler.process_snoozes(env.service, [ME]) == []  # Pas encore l’heure.
    events = scheduler.process_snoozes(env.service, [ME], future(61))
    assert events == [('returned', 'À revoir', 'INBOX')]
    assert env.client.calls[-3:] == [('find', 'Report&AOk-s', '<m1@x>'), ('action', 'Report&AOk-s', '41', '9', 'unread', ''),
                                     ('action', 'Report&AOk-s', '41', '9', 'move', 'INBOX')]
    assert env.db.cache_list('snooze') == []


def test_snooze_requires_message_id_and_future(env):
    with pytest.raises(RuntimeError, match='Message-ID'):
        scheduler.snooze(env.service, ME, [snooze_row(mid='')], future(60))
    with pytest.raises(ValueError):
        scheduler.snooze(env.service, ME, [snooze_row()], future(-1))


def test_snooze_return_tolerates_missing_message_and_retries_errors(env, monkeypatch):
    env.client.list.append(('Reportés', 'Reportés'))
    scheduler.snooze(env.service, ME, [snooze_row()], future(1))
    env.client.found = ('', '9')  # Déplacé ou supprimé entre-temps.
    assert scheduler.process_snoozes(env.service, [ME], future(2)) == [] and env.db.cache_list('snooze') == []
    scheduler.snooze(env.service, ME, [snooze_row(mid='<m2@x>')], future(1))
    monkeypatch.setattr(env.client, 'find_by_message_id', lambda *args: (_ for _ in ()).throw(OSError()))
    assert scheduler.process_snoozes(env.service, [ME], future(2)) == []
    assert len(env.db.cache_list('snooze')) == 1  # Réessayé au prochain passage.


def test_imap_find_by_message_id():
    from mailclient.core.imap_client import IMAPClient
    commands = []
    class Session:
        capabilities = (b'IMAP4REV1',)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def select(self, folder, readonly=True):
            return 'OK', [b'2']
        def response(self, name):
            return name, [b'9']
        def uid(self, *args):
            commands.append(args)
            return 'OK', [b'41 42']
    client = IMAPClient(ME, 'pw', None)
    client.open = lambda: Session()
    assert client.find_by_message_id('Reportés', '<m1@x>') == ('41,42', '9')
    assert commands[-1] == ('search', None, 'HEADER', 'Message-ID', '"<m1@x>"')
    with pytest.raises(ValueError):
        client.find_by_message_id('Reportés', '<a b>" OR ALL')


def test_compose_undo_send_countdown(env, monkeypatch):
    from mailclient.tests.test_ui import process_until
    from mailclient.ui.compose_window import ComposeWindow
    env.db.set_setting('undo_send_seconds', 3)
    composer = ComposeWindow(env.service, [ME], fields=dict(to='a@example.com', subject='Délai', body='x'))
    composer.show()
    composer.send()
    assert composer.countdown and composer.send_button.text() == 'Annuler l’envoi (3 s)' and composer.send_button.isEnabled()
    assert not composer.to.isEnabled()
    composer.send()  # Annuler l’envoi.
    assert composer.countdown is None and composer.to.isEnabled() and env.sent == []
    composer.send()
    for _ in range(3):
        composer.tick_countdown()
    assert process_until(lambda: env.sent and not composer.isVisible())
    assert len(env.sent) == 1 and env.sent[0]['subject'] == 'Délai'
    # Fermer pendant le délai envoie tout de suite.
    other = ComposeWindow(env.service, [ME], fields=dict(to='a@example.com', subject='Fermé', body='x'))
    other.show()
    other.send()
    other.close()
    assert process_until(lambda: len(env.sent) == 2 and not other.isVisible())
    # Adresse invalide : refusée avant tout délai.
    bad = ComposeWindow(env.service, [ME], fields=dict(to='pas une adresse', subject='x', body='x'))
    bad.send()
    assert bad.countdown is None and 'Adresse' in bad.status.text()
    bad.saved_revision = bad.revision
    bad.close()


def test_compose_send_later_and_reopen_from_outbox(env, monkeypatch):
    from mailclient.tests.test_ui import process_until
    from mailclient.ui.compose_window import ComposeWindow
    from mailclient.ui import schedule_dialog
    from mailclient.ui.outbox_dialog import OutboxDialog
    moment = future(90)
    def fake_exec(dialog):
        dialog.moment = moment
        return True
    monkeypatch.setattr(schedule_dialog.ScheduleDialog, 'exec', fake_exec)
    composer = ComposeWindow(env.service, [ME], fields=dict(to='a@example.com', subject='Plus tard', body='Texte'))
    composer.show()
    composer.send_later()
    assert process_until(lambda: not composer.isVisible())
    [item] = scheduler.outbox(env.db)
    assert item['state']['subject'] == 'Plus tard' and scheduler.parse(item['send_at']) == moment.replace(microsecond=0)
    assert env.db.cache_get('draft', composer.id) is None and env.sent == []
    dialog = OutboxDialog(env.db, [ME])
    dialog.list.setCurrentRow(0)
    assert dialog.edit.isEnabled()
    dialog.edit_item()
    assert dialog.reopen['subject'] == 'Plus tard' and scheduler.outbox(env.db) == []
    reopened = ComposeWindow(env.service, [ME], draft=dialog.reopen)
    assert reopened.subject.text() == 'Plus tard' and reopened.state()['body'] == 'Texte'
    reopened.saved_revision = reopened.revision
    reopened.close()


def test_main_window_snooze_and_due_processing(env, monkeypatch):
    from mailclient.tests.test_ui import APP, process_until
    from mailclient.ui.main_window import MainWindow
    from mailclient.ui import schedule_dialog
    listing = [dict(uid='12', uidvalidity='7', sender='a@x.fr', subject='À revoir', date='', unread=True, starred=False,
                    attachment=False, message_id='<m1@x>')]
    env.client.messages = lambda folder, page, query='': ([dict(r) for r in listing], 1)
    env.client.message_raw = lambda folder, uid: b'From: a@x.fr\r\nSubject: A revoir\r\nMessage-ID: <m1@x>\r\n\r\nCorps'
    env.client.uidvalidity = '7'
    env.client.list.append(('Reportés', 'Reportés'))
    monkeypatch.setattr(schedule_dialog.ScheduleDialog, 'exec', lambda dialog: setattr(dialog, 'moment', future(1)) or True)
    window = MainWindow(env.db, Vault(), TLSPolicy(env.db), auto_load=False)
    window.service = env.service
    window.reload_accounts()
    window.select_account(ME.id)
    assert process_until(lambda: not window.busy and window.table.count() == 1)
    window.table.setCurrentRow(0)
    assert process_until(lambda: not window.busy and window.reader.mail is not None)
    window.snooze()
    assert process_until(lambda: not window.busy and ('action', 'INBOX', '12', '7', 'move', 'Reportés') in env.client.calls)
    assert len(env.db.cache_list('snooze')) == 1
    monkeypatch.setattr(scheduler, 'now_utc', lambda: future(5))
    window.process_due()
    assert process_until(lambda: not window.due_running and 'retour' in window.statusBar().currentMessage())
    assert env.db.cache_list('snooze') == [] and ('action', 'Reportés', '41', '9', 'move', 'INBOX') in env.client.calls
    window.reader.shutdown()
    window.close()
    from shiboken6 import delete
    delete(window)
