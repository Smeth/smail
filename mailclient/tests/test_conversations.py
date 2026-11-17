"""Vue par conversation : regroupement, reconstitution depuis les autres dossiers et interface."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
from mailclient.core.accounts import Account, Server
from mailclient.core.parser import metadata
from mailclient.core.service import MailService, cache_key
from mailclient.core.threads import group_threads, normalize_subject, chronological
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database

ME = Account('Moi', 'moi@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))


def row(uid, subject='Projet', mid='', refs='', reply='', sender='Alice <alice@example.com>', account='a', folder='INBOX',
        date='', unread=False):
    return dict(uid=uid, subject=subject, message_id=mid, references=refs, in_reply_to=reply, sender=sender,
                account=account, folder=folder, uidvalidity='7', date=date, unread=unread, starred=False, attachment=False)


def uids(groups):
    return [[r['uid'] for r in group] for group in groups]


def test_metadata_extracts_thread_headers():
    raw = (b'From: a@example.com\r\nSubject: Re: X\r\nMessage-ID: <ID-3@Example.com>\r\n'
           b'In-Reply-To: <id-2@example.com>\r\nReferences: <id-1@example.com>\r\n <id-2@example.com>\r\n\r\nCorps')
    data = metadata(raw)
    assert data['message_id'] == '<id-3@example.com>'
    assert data['in_reply_to'] == '<id-2@example.com>'
    assert data['references'] == '<id-1@example.com> <id-2@example.com>'
    assert metadata(b'Subject: x\r\nReferences: n\'importe quoi\r\n\r\n')['references'] == ''


def test_references_group_messages_even_without_root():
    rows = [row('9', 'Re: Projet', '<c>', '<a> <b>'), row('8', 'Autre', '<z>'),
            row('7', 'Re: Projet', '<b>', '<a>'), row('5', 'Lancement', '<y>')]
    # La racine <a> n’est pas dans la page : ses deux réponses restent réunies.
    assert uids(group_threads(rows)) == [['9', '7'], ['8'], ['5']]


def test_accounts_are_never_mixed():
    rows = [row('2', mid='<b>', refs='<a>', account='a'), row('1', mid='<c>', refs='<a>', account='b')]
    assert uids(group_threads(rows)) == [['2'], ['1']]


def test_subject_fallback_only_for_replies_without_references():
    rows = [row('4', 'RE: Réunion budget'), row('3', 'Réunion budget', '<r>'),
            row('2', 'Réunion budget', '<s>'), row('1', 'Re: ok'), row('0', 'ok')]
    groups = uids(group_threads(rows))
    assert groups[0] == ['4', '3']  # Réponse sans référence rattachée au premier message du même sujet.
    assert ['2'] in groups  # Deux messages originaux au même sujet ne sont pas fusionnés.
    assert ['1'] in groups and ['0'] in groups  # Sujet trop court : pas de rapprochement.
    assert normalize_subject('Re: TR:  Fwd: Réunion') == 'réunion'


def test_chronological_order():
    rows = [row('3', date='Tue, 03 Mar 2026 10:00:00 +0100'), row('1', date='Sun, 01 Mar 2026 10:00:00 +0100'),
            row('2', date='Mon, 02 Mar 2026 10:00:00 +0100')]
    assert [r['uid'] for r in chronological(rows)] == ['1', '2', '3']


def test_service_conversation_adds_sent_replies_without_duplicates(tmp_path):
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    db.cache_put('folders', ME.id, [['INBOX', 'Boîte de réception'], ['Sent', 'Envoyés'], ['All', 'Tous les messages']], ME.id)
    inbox = [row('10', 'Projet', '<a>', account=ME.id, date='Sun, 01 Mar 2026 10:00:00 +0100'),
             row('12', 'Re: Projet', '<c>', '<a> <b>', account=ME.id, date='Tue, 03 Mar 2026 10:00:00 +0100')]
    sent = [row('3', 'Re: Projet', '<b>', '<a>', sender='Moi <moi@example.com>', account=ME.id, folder='Sent',
                date='Mon, 02 Mar 2026 10:00:00 +0100'),
            row('4', 'Sans rapport', '<q>', account=ME.id, folder='Sent')]
    copies = [dict(r, folder='All', uid=str(100 + i)) for i, r in enumerate(inbox + sent[:1])]  # Copies Gmail.
    for folder, rows in (('INBOX', inbox), ('Sent', sent), ('All', copies)):
        db.cache_put('mailbox', cache_key(ME.id, folder), dict(account=ME.id, folder=folder, pages={'0': rows}))
    service = MailService(db, None, TLSPolicy(db))
    messages = service.conversation(ME, [inbox[1]])
    assert [(r['folder'], r['uid']) for r in messages] == [('INBOX', '10'), ('Sent', '3'), ('INBOX', '12')]


def test_main_window_conversation_flow(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import APP, process_until
    from mailclient.ui.main_window import MainWindow
    from mailclient.core.parser import Mail
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    listing = [row('12', 'Re: Projet', '<c>', '<a>', sender='Bob <bob@example.com>', date='Tue, 03 Mar 2026 10:00:00 +0100', unread=True),
               row('11', 'Facture', '<f>', date='Mon, 02 Mar 2026 09:00:00 +0100'),
               row('10', 'Projet', '<a>', date='Sun, 01 Mar 2026 10:00:00 +0100')]
    for item in listing:
        item.pop('account')
    calls, loaded = [], []
    class Client:
        uidvalidity = '7'
        def folders(self):
            return [('INBOX', 'Boîte de réception'), ('Archive', 'Archives')]
        def messages(self, folder, page, query=''):
            return [dict(r) for r in listing], len(listing)
        def message_raw(self, folder, uid):
            loaded.append(uid)
            return f'From: x@example.com\r\nSubject: Message {uid}\r\n\r\nCorps {uid}'.encode()
        def action(self, folder, uids, validity, action, target=''):
            calls.append((uids, action, target))
    monkeypatch.setattr(MailService, 'client', lambda *args: Client())
    window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    window.reload_accounts()
    assert process_until(lambda: not window.busy and window.table.count() == 2)
    view = window.table.item(0).data(256)
    assert view.count == 2 and view.unread and view.sender == 'Alice, Bob'
    window.table.setCurrentRow(0)
    assert process_until(lambda: not window.busy and window.reader.mail is not None)
    assert loaded[-1] == '12'  # Premier message non lu de la conversation.
    assert window.reader.thread_card.isVisibleTo(window.reader) and window.reader.thread_list.count() == 2
    assert window.reader.thread_list.currentRow() == 1
    window.reader.thread_list.itemClicked.emit(window.reader.thread_list.item(0))
    assert process_until(lambda: not window.busy and loaded[-1] == '10')
    assert window.reader.mail.subject == 'Message 10' and window.reader.thread_card.isVisibleTo(window.reader)
    # Archiver agit sur toute la conversation, en une commande.
    window.move('archive')
    assert process_until(lambda: not window.busy and calls)
    assert calls[-1] == ('12,10', 'move', 'Archive')
    # Sans regroupement : une ligne par message, pas de bandeau.
    window.conversation_action.setChecked(False)
    assert window.table.count() == 3 and not db.setting('conversation_view')
    window.table.setCurrentRow(2)
    assert process_until(lambda: not window.busy and loaded[-1] == '10')
    assert not window.reader.thread_card.isVisibleTo(window.reader)
    window.reader.shutdown()
    window.close()
    from shiboken6 import delete
    delete(window)
