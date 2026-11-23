"""Règles, expéditeurs bloqués ou approuvés, spam signalé par le serveur et désabonnement."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
import pytest
from mailclient.core import filters, unsubscribe
from mailclient.core.accounts import Account, Server
from mailclient.core.parser import metadata, parse_message
from mailclient.core.service import MailService, cache_key
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database

ME = Account('Moi', 'moi@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))
SERVER = 'imap.example.com:993:SSL/TLS'
FOLDERS = [('INBOX', 'Boîte de réception'), ('Junk', 'Spam'), ('Trash', 'Corbeille'), ('Factures', 'Factures')]


def row(uid, sender='Alice <alice@example.com>', subject='Bonjour', recipients='moi@example.com', spam=False, folder='INBOX'):
    return dict(uid=str(uid), uidvalidity='7', sender=sender, subject=subject, recipients=recipients, spam=spam,
                account=ME.id, folder=folder, server=SERVER, unread=True, starred=False, date='')


def data(**values):
    return {**filters.DEFAULTS, **values}


def test_decision_order_safe_blocked_spam_then_rules():
    rule = filters.new_rule(field='subject', op='contains', value='facture', action='move', target='Factures')
    settings = data(rules=[rule], blocked=['@pub.example'], safe=['ami@pub.example'])
    assert filters.decide(row(1, 'Promo <offres@pub.example>'), settings, ME.id)[:2] == ('junk', '')
    assert filters.decide(row(2, 'Ami <ami@pub.example>', 'Votre facture'), settings, ME.id)[:2] == ('move', 'Factures')
    assert filters.decide(row(3, spam=True), settings, ME.id)[0] == 'junk'
    assert filters.decide(row(4, 'Ami <ami@pub.example>', spam=True), settings, ME.id) is None  # Approuvé : pas de spam.
    assert filters.decide(row(5, subject='FACTURE n°12'), settings, ME.id)[:2] == ('move', 'Factures')
    assert filters.decide(row(6), data(rules=[rule], spam_headers=False), ME.id) is None
    assert filters.decide(row(7, spam=True), data(spam_headers=False), ME.id) is None


def test_rule_fields_operators_scope_and_enabled():
    to_rule = filters.new_rule(field='to', op='is', value='liste@example.com', action='read')
    ends = filters.new_rule(field='from', op='ends', value='@banque.fr', action='star', account='autre-compte')
    disabled = filters.new_rule(field='any', op='contains', value='bonjour', action='trash', enabled=False)
    settings = data(rules=[disabled, ends, to_rule])
    assert filters.decide(row(1, recipients='Liste <liste@example.com>, moi@example.com'), settings, ME.id)[0] == 'read'
    assert filters.decide(row(2, 'Banque <alerte@banque.fr>'), settings, ME.id) is None  # Autre compte.
    assert filters.decide(row(3, 'Banque <alerte@banque.fr>'), settings, 'autre-compte')[0] == 'star'
    assert filters.decide(row(4), settings, ME.id) is None  # Règle désactivée.
    assert 'Si Objet contient « x » : déplacer vers « Factures »' == filters.describe(
        dict(field='subject', op='contains', value='x', action='move', target='Factures'))


@pytest.mark.parametrize('value,expected', [('Alice <ALICE@example.com>', 'alice@example.com'), ('@exemple.fr', '@exemple.fr'),
                                            ('exemple.fr', '@exemple.fr'), (' a@b.fr ', 'a@b.fr')])
def test_normalize_sender(value, expected):
    assert filters.normalize_sender(value) == expected


@pytest.mark.parametrize('value', ['', 'pas une adresse', 'a@b', '<script>', 'a@b.fr, c@d.fr'])
def test_normalize_sender_rejects(value):
    with pytest.raises(ValueError):
        filters.normalize_sender(value)


@pytest.mark.parametrize('rule', [dict(value=''), dict(value='x', action='move', target=''), dict(value='x', field='body')])
def test_invalid_rules(rule):
    with pytest.raises(ValueError):
        filters.new_rule(**rule)


def test_metadata_recipients_and_server_spam_flags():
    base = b'From: a@x.fr\r\nTo: Moi <moi@example.com>\r\nCc: b@x.fr\r\nSubject: s\r\n'
    assert metadata(base + b'\r\nx')['recipients'] == 'Moi <moi@example.com>, b@x.fr'
    assert not metadata(base + b'\r\nx')['spam']
    for header in (b'X-Spam-Flag: YES', b'X-Spam-Status: Yes, score=9.1', b'X-Spam: yes', b'X-Spam-Level: ********'):
        assert metadata(base + header + b'\r\n\r\nx')['spam'], header
    assert not metadata(base + b'X-Spam-Status: No, score=0.1\r\nX-Spam-Level: **\r\n\r\nx')['spam']


class FakeClient:
    def __init__(self):
        self.calls = []

    def action(self, folder, uids, validity, action, target=''):
        self.calls.append((folder, uids, action, target))

    def folders(self):
        return FOLDERS


def service_with(tmp_path, monkeypatch):
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    client = FakeClient()
    monkeypatch.setattr(MailService, 'client', lambda *args: client)
    return MailService(db, None, TLSPolicy(db)), db, client


def test_filters_only_touch_new_messages(tmp_path, monkeypatch):
    service, db, client = service_with(tmp_path, monkeypatch)
    rule = filters.new_rule(field='subject', op='contains', value='facture', action='move', target='Factures')
    filters.save(db, data(rules=[rule], blocked=['spam@pub.example']))
    existing = [row(10, subject='Facture ancienne'), row(9, 'X <spam@pub.example>')]
    assert service.apply_filters(ME, FOLDERS, existing, '7') == existing  # Premier passage : repère seulement.
    assert client.calls == []
    incoming = [row(13, subject='Facture 13'), row(12, 'X <spam@pub.example>'), row(11, subject='Mot'), *existing]
    kept = service.apply_filters(ME, FOLDERS, incoming, '7')
    assert sorted(client.calls) == [('INBOX', '12', 'move', 'Junk'), ('INBOX', '13', 'move', 'Factures')]
    assert [r['uid'] for r in kept] == ['11', '10', '9']
    client.calls.clear()
    service.apply_filters(ME, FOLDERS, kept, '7')
    assert client.calls == []  # Déjà traités.
    # Recréation du dossier (UIDVALIDITY) : nouveau repère, aucun traitement rétroactif.
    assert service.apply_filters(ME, FOLDERS, [dict(r, uidvalidity='8') for r in incoming], '8') and client.calls == []


def test_flag_actions_and_missing_folder(tmp_path, monkeypatch):
    service, db, client = service_with(tmp_path, monkeypatch)
    filters.save(db, data(rules=[filters.new_rule(field='from', op='contains', value='alice', action='read'),
                                 filters.new_rule(field='from', op='contains', value='bob', action='move', target='Disparu')]))
    service.apply_filters(ME, FOLDERS, [row(1)], '7')
    kept = service.apply_filters(ME, FOLDERS, [row(3, 'Bob <bob@x.fr>'), row(2), row(1)], '7')
    assert client.calls == [('INBOX', '2', 'read', '')]  # Dossier absent : règle ignorée sans erreur.
    assert [(r['uid'], r['unread']) for r in kept] == [('3', True), ('2', False), ('1', True)]


def test_apply_now_processes_synced_inbox(tmp_path, monkeypatch):
    service, db, client = service_with(tmp_path, monkeypatch)
    inbox = [row(5, 'X <spam@pub.example>'), row(4)]
    db.cache_put('mailbox', cache_key(ME.id, 'INBOX'), dict(account=ME.id, folder='INBOX', pages={'0': inbox}, total=2, uidvalidity='7',
                                                            status={'HIGHESTMODSEQ': 3}))
    filters.save(db, data(blocked=['@pub.example']))
    assert service.apply_filters_now(ME) == 1
    assert client.calls == [('INBOX', '5', 'move', 'Junk')]
    state = service.state(ME, 'INBOX')
    assert [r['uid'] for r in state['pages']['0']] == ['4'] and 'status' not in state


def test_report_block_and_not_spam(tmp_path, monkeypatch):
    service, db, client = service_with(tmp_path, monkeypatch)
    target = service.junk(ME, [row(5, 'Promo <promo@pub.example>')], FOLDERS, block=True)
    assert target == 'Junk' and client.calls[-1] == ('INBOX', '5', 'move', 'Junk')
    assert filters.load(db)['blocked'] == ['promo@pub.example']
    service.junk(ME, [row(6, 'Promo <promo@pub.example>', folder='Junk')], FOLDERS, trust=True)
    assert client.calls[-1] == ('Junk', '6', 'move', 'INBOX')
    assert filters.load(db)['blocked'] == [] and filters.load(db)['safe'] == ['promo@pub.example']
    with pytest.raises(RuntimeError, match='indésirables'):
        service.junk(ME, [row(7)], [('INBOX', 'Boîte de réception')])


def test_filters_are_stored_in_encrypted_cache(tmp_path):
    from mailclient.tests.test_sync_search_contacts import Vault
    db = Database(tmp_path / 'settings.db', Vault())
    db.encrypt_cache(True)
    filters.save(db, data(blocked=['secret@exemple.fr']))
    assert b'secret@exemple.fr' not in open(db.path, 'rb').read()
    assert filters.load(db)['blocked'] == ['secret@exemple.fr']


def test_unsubscribe_options():
    both = unsubscribe.options('<mailto:sortie@liste.fr?subject=STOP%20liste>, <https://liste.fr/u/123>', 'List-Unsubscribe=One-Click')
    assert both.one_click == 'https://liste.fr/u/123' and both.mailto == ('sortie@liste.fr', 'STOP liste', '') and both.host == 'liste.fr'
    web = unsubscribe.options('<https://liste.fr/u/123>')
    assert not web.one_click and web.web == 'https://liste.fr/u/123'
    mail_only = unsubscribe.options('<mailto:sortie@liste.fr>')
    assert mail_only.mailto == ('sortie@liste.fr', 'unsubscribe', '') and mail_only.host == 'liste.fr'
    assert not unsubscribe.options('') and not unsubscribe.options('<javascript:alert(1)>, <mailto:pas-une-adresse>')
    injected = unsubscribe.options('<mailto:a@b.fr?subject=x%0D%0ABcc:%20victime@c.fr>')
    assert '\r' not in injected.mailto[1] and '\n' not in injected.mailto[1]
    assert parse_message(b'From: a@b.fr\r\nList-Unsubscribe: <https://l.fr/u>\r\nList-Unsubscribe-Post: List-Unsubscribe=One-Click\r\n\r\nx').list_unsubscribe == '<https://l.fr/u>'


@pytest.mark.parametrize('host', ['localhost', '127.0.0.1', '10.0.0.5', '192.168.1.1', '169.254.1.1', '[::1]', ''])
def test_unsubscribe_refuses_local_hosts(host):
    assert not unsubscribe.public_host(host.strip('[]'))


def test_one_click_posts_without_redirects(monkeypatch):
    sent = {}
    class Reply:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    class Opener:
        def open(self, request, timeout):
            sent.update(method=request.get_method(), data=request.data, url=request.full_url, timeout=timeout)
            return Reply()
    handlers = []
    monkeypatch.setattr(unsubscribe, 'public_host', lambda host: True)
    monkeypatch.setattr(unsubscribe.urllib.request, 'build_opener', lambda *h: (handlers.extend(h), Opener())[1])
    assert unsubscribe.one_click('https://liste.fr/u/1') == 200
    assert sent == dict(method='POST', data=b'List-Unsubscribe=One-Click', url='https://liste.fr/u/1', timeout=15)
    assert handlers == [unsubscribe._NoRedirect]
    with pytest.raises(RuntimeError):
        unsubscribe.one_click('http://liste.fr/u/1')
    monkeypatch.setattr(unsubscribe, 'public_host', lambda host: False)
    with pytest.raises(RuntimeError):
        unsubscribe.one_click('https://intranet.local/u/1')


def test_main_window_junk_rule_and_unsubscribe(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from mailclient.tests.test_ui import APP, process_until
    from mailclient.ui.main_window import MainWindow
    from mailclient.ui import rules_dialog
    import mailclient.core.smtp_client as smtp
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    listing = [dict(uid='8', uidvalidity='7', sender='Promo <promo@pub.example>', subject='Offre', date='', unread=True,
                    starred=False, attachment=False)]
    calls, sent = [], []
    class Client:
        uidvalidity = '7'
        def folders(self):
            return FOLDERS
        def messages(self, folder, page, query=''):
            return [dict(r) for r in listing], len(listing)
        def message_raw(self, folder, uid):
            return (b'From: Promo <promo@pub.example>\r\nSubject: Offre\r\nList-Unsubscribe: <mailto:stop@pub.example?subject=STOP>\r\n\r\nPromo')
        def action(self, folder, uids, validity, action, target=''):
            calls.append((folder, uids, action, target))
    monkeypatch.setattr(MailService, 'client', lambda *args: Client())
    monkeypatch.setattr(MailService, 'oauth', type('O', (), {'credential': lambda self, a: 'x'})(), raising=False)
    monkeypatch.setattr(smtp, 'send_message', lambda account, password, tls, message, recipients: sent.append((message['To'], message['Subject'], recipients)))
    window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    window.service.oauth = type('O', (), {'credential': lambda self, a: 'x'})()
    window.reload_accounts()
    assert process_until(lambda: not window.busy and window.table.count() == 1)
    window.table.setCurrentRow(0)
    assert process_until(lambda: not window.busy and window.reader.mail is not None)
    assert window.reader.unsubscribe_banner.isVisibleTo(window.reader)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    window.unsubscribe()
    assert process_until(lambda: not window.busy and sent)
    assert sent[0] == ('stop@pub.example', 'STOP', ['stop@pub.example'])
    # Règle créée à partir du message, pré-remplie avec l’expéditeur.
    captured = {}
    def fake_exec(dialog):
        captured['value'] = dialog.value.text()
        dialog.action.setCurrentIndex(dialog.action.findData('trash'))
        dialog.save()
        return True
    monkeypatch.setattr(rules_dialog.RuleDialog, 'exec', fake_exec)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.No)
    window.create_rule_from_message()
    assert captured['value'] == 'promo@pub.example'
    assert filters.load(db)['rules'][0]['action'] == 'trash'
    # Bloquer l’expéditeur : liste mise à jour et message déplacé.
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    window.table.setCurrentRow(0)
    APP.processEvents()
    window.report_junk(block=True)
    assert process_until(lambda: not window.busy and calls)
    assert calls[-1] == ('INBOX', '8', 'move', 'Junk') and filters.load(db)['blocked'] == ['promo@pub.example']
    window.reader.shutdown()
    window.close()
    from shiboken6 import delete
    delete(window)


def test_filters_page_edits_lists_and_rules(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox
    from PySide6.QtCore import Qt
    from mailclient.ui.rules_dialog import FiltersPage
    QApplication.instance() or QApplication([])
    db = Database(tmp_path / 'settings.db')
    db.save(ME)
    page = FiltersPage(db, [ME])
    entry = QLineEdit('@pub.example')
    page.add_sender('blocked', entry)
    page.add_sender('safe', QLineEdit('ami@pub.example'))
    assert filters.load(db)['blocked'] == ['@pub.example'] and filters.load(db)['safe'] == ['ami@pub.example']
    page.add_sender('safe', QLineEdit('@pub.example'))  # Passe d’une liste à l’autre, jamais les deux.
    assert filters.load(db)['blocked'] == [] and '@pub.example' in filters.load(db)['safe']
    warned = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warned.append(args[2]))
    page.add_sender('blocked', QLineEdit('pas une adresse'))
    assert warned and filters.load(db)['blocked'] == []
    page.data['rules'].append(filters.new_rule(field='subject', op='contains', value='x', action='read'))
    page.persist()
    page.rules.item(0).setCheckState(Qt.Unchecked)
    assert filters.load(db)['rules'][0]['enabled'] is False
    page.spam_headers.setChecked(False)
    assert filters.load(db)['spam_headers'] is False
