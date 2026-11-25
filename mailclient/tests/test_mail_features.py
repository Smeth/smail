"""Répondu / transféré, réponses mises en forme, transfert en pièce jointe, thème et accessibilité de Windows,
brouillons du serveur."""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from email import message_from_bytes, policy  # noqa: E402

from mailclient.core.accounts import Account, Server  # noqa: E402
from mailclient.core.parser import Attachment, Mail  # noqa: E402
from mailclient.tests.test_bulk_and_folders import FakeIMAP, client_with  # noqa: E402

ME = Account('Moi', 'moi@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465), signature='Camille')
ORIGIN = dict(account=ME.id, folder='INBOX', uid='42', uidvalidity='7', server='imap.example.com:993:SSL/TLS')


def compose_service(tmp_path):
    from mailclient.tests.test_rich_compose import make_service
    service, db = make_service(tmp_path)
    db.save(ME)
    return service


class FakeService:
    def __init__(self):
        self.calls = []
        self.db = type('DB', (), {'accounts': staticmethod(lambda: [ME])})()

    def action(self, account, rows, action, target=''):
        self.calls.append((account.id, rows[0]['uid'], action))


# 1. Répondu / transféré ------------------------------------------------------------------------------------------

def test_answered_and_forwarded_flags_are_stored_on_the_server():
    fake = FakeIMAP()
    client_with(fake).action('INBOX', '42', '7', 'answered')
    client_with(fake).action('INBOX', '42', '7', 'forwarded')
    assert ('STORE', '42', '+FLAGS.SILENT', '(\\Answered)') in fake.commands
    assert ('STORE', '42', '+FLAGS.SILENT', '($Forwarded)') in fake.commands


def test_origin_is_marked_after_sending_and_never_blocks_it():
    from mailclient.core import scheduler
    service = FakeService()
    scheduler.mark_origin(service, dict(ORIGIN, flag='answered'))
    assert service.calls == [(ME.id, '42', 'answered')]
    service.action = lambda *args: (_ for _ in ()).throw(RuntimeError('NO'))  # Serveur sans mots-clés.
    scheduler.mark_origin(service, dict(ORIGIN, flag='forwarded'))  # Aucune exception : l’envoi a déjà réussi.
    scheduler.mark_origin(service, None)


def test_reply_records_its_origin_in_the_draft_state(tmp_path):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from mailclient.ui.compose_window import ComposeWindow, reply_fields
    mail = Mail('Léa <lea@x.fr>', 'moi@example.com', 'Devis', 'date', text='Bonjour')
    fields = reply_fields(mail, ME, 'reply')
    fields['origin'] = dict(ORIGIN, flag='answered')
    window = ComposeWindow(compose_service(tmp_path), [ME], ME, fields)
    assert window.state()['origin']['flag'] == 'answered' and window.windowTitle()
    window.saved_revision = window.revision
    from shiboken6 import delete
    delete(window)


# 2. Réponse qui garde la mise en forme -----------------------------------------------------------------------------

HTML_MAIL = Mail('Léa <lea@x.fr>', 'moi@example.com', 'Rapport', 'mardi',
                 text='Bonjour\nVoici le tableau.',
                 html='<p>Bonjour <b>Camille</b></p><table><tr><td>Total</td><td>42</td></tr></table>'
                      '<img src="https://tracker.example/pixel.gif"><img src="cid:logo"><a href="javascript:alert(1)">x</a>'
                      '<a href="https://example.com/doc">doc</a><script>alert(1)</script>',
                 attachments=[Attachment('logo.png', 'image/png', b'\x89PNG', 'logo')])


def test_html_reply_quotes_the_formatted_original_without_remote_content():
    from mailclient.core.quote import merged
    from mailclient.ui.compose_window import reply_fields
    fields = reply_fields(HTML_MAIL, ME, 'reply')
    assert fields['body'] == '\n\nCamille'  # L’éditeur reçoit la signature ; l’original part en citation.
    quote = fields['quote_html']
    assert '<b>Camille</b>' in quote and '<table>' in quote and '<blockquote' in quote
    assert 'tracker.example' not in quote and 'javascript:' not in quote and '<script' not in quote
    assert 'src="data:image/png;base64,' in quote and 'href="https://example.com/doc"' in quote
    state = dict(body='Merci !\n\nCamille', mail_html='', mail_fragment='<div>Merci !</div>',
                 quote_html=quote, quote_text=fields['quote_text'], quote_included=True)
    text, document = merged(state)
    assert text.startswith('Merci !') and '> Bonjour' in text and 'a écrit :' in text
    assert document.startswith('<!DOCTYPE html>') and '<div>Merci !</div>' in document and '<table>' in document
    assert merged(dict(state, quote_included=False)) == ('Merci !\n\nCamille', '')  # Citation décochée.


def test_plain_text_original_is_still_quoted_inline():
    from mailclient.ui.compose_window import reply_fields
    fields = reply_fields(Mail('Léa <lea@x.fr>', 'moi@example.com', 'Devis', 'mardi', text='Bonjour'), ME, 'reply')
    assert '> Bonjour' in fields['body'] and not fields.get('quote_html')


def test_compose_sends_the_quote_and_keeps_it_in_drafts(tmp_path):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from mailclient.ui.compose_window import ComposeWindow, reply_fields
    window = ComposeWindow(compose_service(tmp_path), [ME], ME, reply_fields(HTML_MAIL, ME, 'forward'))
    assert window.quote_box.isVisibleTo(window) and window.windowTitle()
    state = window.state()
    assert state['quote_html'] and state['quote_included'] and 'Message transféré' in state['quote_text']
    message, _ = window.message(dict(state, to='paul@example.com'), [], True)
    html = message.get_body(('html',)).get_content()
    assert '<table>' in html and 'Message transféré' in html and 'tracker.example' not in html
    window.saved_revision = window.revision
    from shiboken6 import delete
    delete(window)


# 3. Transférer en pièce jointe -------------------------------------------------------------------------------------

def test_forward_as_attachment_is_a_proper_message_part():
    from mailclient.core.smtp_client import build_message
    raw = b'From: Lea <lea@x.fr>\r\nSubject: Devis\r\nMessage-ID: <1@x.fr>\r\n\r\nBonjour\r\n'
    message, _ = build_message(ME, 'paul@example.com', '', '', 'Tr: Devis', 'Voir ci-joint',
                               [Attachment('Devis.eml', 'message/rfc822', raw)])
    parsed = message_from_bytes(message.as_bytes(), policy=policy.default)
    part = next(part for part in parsed.iter_attachments())
    assert part.get_content_type() == 'message/rfc822' and part.get_filename() == 'Devis.eml'
    assert part.get('Content-Transfer-Encoding', '7bit').lower() != 'base64'  # Interdit par la RFC 2046.
    assert part.get_content()['Message-ID'] == '<1@x.fr>'


# 4. Thème comme Windows, contraste élevé, taille du texte ------------------------------------------------------------

def test_theme_follows_windows_and_its_accessibility_settings(tmp_path, monkeypatch):
    from PySide6.QtGui import QColor, QPalette
    from mailclient.tests.test_ui import APP
    from mailclient.storage.database import Database
    from mailclient.ui import presentation
    db = Database(tmp_path / 'settings.db')
    monkeypatch.setattr(presentation, 'system_dark', lambda: True)
    assert presentation.install_theme(db).dark  # Par défaut : comme Windows.
    db.set_setting('theme', 0)
    assert not presentation.install_theme(db).dark  # Choix explicite : clair.
    theme = APP.smail_theme
    palette = QPalette()
    for role, color in ((QPalette.Window, '#000000'), (QPalette.WindowText, '#FFFFFF'), (QPalette.Base, '#000000'),
                        (QPalette.Highlight, '#1AEBFF'), (QPalette.HighlightedText, '#000000')):
        palette.setColor(role, QColor(color))
    monkeypatch.setattr(presentation, 'high_contrast', lambda: True)
    previous = theme.system_palette, theme.text_scale
    theme.system_palette = palette
    try:
        presentation.install_theme(db)
        colors = theme.colors
        assert (colors['bg'], colors['text'], colors['accent']) == ('#000000', '#ffffff', '#1aebff')
        theme.text_scale = 1.5
        theme.apply()
        assert 'font-size: 24px' in APP.styleSheet() or 'font-size: 27px' in APP.styleSheet()  # 16 px ou 18 px × 1,5.
    finally:
        monkeypatch.setattr(presentation, 'high_contrast', lambda: False)
        theme.system_palette, theme.text_scale = previous
        presentation.install_theme(db)


# 5. Brouillons du serveur -------------------------------------------------------------------------------------------

def test_append_reports_where_the_draft_was_stored():
    class Appending(FakeIMAP):
        sock = None

        def append(self, folder, flags, date, raw):
            self.commands.append(('APPEND', folder, flags))
            return 'OK', [b'[APPENDUID 38505 3955] APPEND completed']
    fake = Appending()
    assert client_with(fake).append('Drafts', b'Subject: x\r\n\r\ny', draft=True) == dict(uidvalidity='38505', uid='3955')
    assert ('APPEND', '"Drafts"', '(\\Draft)') in fake.commands or ('APPEND', 'Drafts', '(\\Draft)') in fake.commands


def test_sent_or_replaced_server_draft_is_removed():
    from mailclient.core import scheduler
    service = FakeService()
    assert scheduler.remove_server_draft(service, ORIGIN) and service.calls == [(ME.id, '42', 'delete')]
    assert not scheduler.remove_server_draft(service, None)
    assert not scheduler.remove_server_draft(service, dict(ORIGIN, uid=None))


def test_server_draft_opens_with_its_formatting_and_location(tmp_path):
    from mailclient.tests.test_ui import APP  # noqa: F401
    from mailclient.ui.compose_window import ComposeWindow
    fields = dict(to='paul@example.com', subject='Brouillon du téléphone', body='Bonjour Paul',
                  qt_html='<div>Bonjour <b>Paul</b></div>', server_draft=dict(ORIGIN, folder='Drafts'))
    window = ComposeWindow(compose_service(tmp_path), [ME], ME, fields)
    assert window.body.toPlainText().startswith('Bonjour Paul') and window.state()['server_draft']['folder'] == 'Drafts'
    assert '<b>Paul</b>' in window.state()['mail_html'] or 'font-weight' in window.body.toHtml()
    window.saved_revision = window.revision
    from shiboken6 import delete
    delete(window)
