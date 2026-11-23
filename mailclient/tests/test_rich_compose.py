"""Rédaction HTML : conversion, MIME, brouillons et signature mise en forme."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
from email import message_from_bytes, policy
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QTextCursor
from mailclient.tests.test_ui import APP, process_until
from mailclient.core.accounts import Account, Server
from mailclient.core.service import MailService
from mailclient.core.smtp_client import build_message
from mailclient.core.tls_policy import TLSPolicy
from mailclient.storage.database import Database
from mailclient.ui.rich_text import RichTextEdit, render, has_formatting, clean_qt_html


def account(**values):
    return Account('Moi', 'moi@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465), **values)


def editor_with(html):
    editor = RichTextEdit()
    editor.setHtml(html)
    return editor


def test_render_keeps_safe_subset_and_plain_equivalent():
    editor = editor_with('<p>Bonjour <b>Léa</b> &amp; <i>Tom</i> <u>souligné</u> <a href="https://exemple.fr">le site</a>'
                         ' <a href="javascript:alert(1)">piège</a> &lt;script&gt;</p><ul><li>un</li><li>deux</li></ul>'
                         '<ol><li>premier</li></ol>')
    fragment, text = render(editor.document())
    assert '<b>Léa</b>' in fragment and '<i>Tom</i>' in fragment and '<u>souligné</u>' in fragment
    assert '<a href="https://exemple.fr">le site</a>' in fragment
    assert 'javascript' not in fragment and 'piège' in fragment  # Lien dangereux réduit à son texte.
    assert '&lt;script&gt;' in fragment and '<script' not in fragment
    assert '<ul' in fragment and '<li>deux</li>' in fragment and '<ol' in fragment
    assert text.splitlines() == ['Bonjour Léa & Tom souligné le site (https://exemple.fr) piège <script>', '• un', '• deux', '1. premier']
    assert has_formatting(editor.document())
    assert not has_formatting(editor_with('<p>Texte simple</p>').document())


def test_pasted_html_is_reduced_to_email_subset():
    cleaned = clean_qt_html('<div style="color:red" onclick="x()"><img src="https://pistage.example/p.png">'
                            'Texte <script>alert(1)</script><strong>fort</strong> <span style="font-size:40px">grand</span></div>')
    assert cleaned == '<div>Texte <b>fort</b> grand</div>'
    editor = RichTextEdit()
    mime = QMimeData()
    mime.setHtml('<p>Collé <em>ici</em> <img src="https://pistage.example/p.png"></p>')
    editor.insertFromMimeData(mime)
    fragment, _ = render(editor.document())
    assert '<i>ici</i>' in fragment and 'img' not in fragment and 'pistage' not in editor.toHtml()


def test_signature_editor_refuses_attachments():
    editor = RichTextEdit(attachments=False)
    mime = QMimeData()
    from PySide6.QtCore import QUrl
    mime.setUrls([QUrl.fromLocalFile('C:/x/photo.jpg')])
    assert not editor.canInsertFromMimeData(mime)


def test_html_message_is_multipart_alternative_with_attachments_and_hidden_bcc():
    from mailclient.core.parser import Attachment
    html = '<!DOCTYPE html><html><body><div><b>Bonjour</b></div></body></html>'
    message, recipients = build_message(account(), 'a@example.com', '', 'secret@example.com', 'Sujet', 'Bonjour',
                                        [Attachment('note.txt', 'text/plain', b'x')], html=html)
    parsed = message_from_bytes(message.as_bytes(), policy=policy.default)
    assert parsed.get_content_type() == 'multipart/mixed'
    alternative = next(part for part in parsed.walk() if part.get_content_type() == 'multipart/alternative')
    assert [p.get_content_type() for p in alternative.iter_parts()] == ['text/plain', 'text/html']
    assert '<b>Bonjour</b>' in parsed.get_body(('html',)).get_content()
    assert parsed.get_body(('plain',)).get_content().strip() == 'Bonjour'
    assert 'secret@example.com' not in message.as_string() and 'secret@example.com' in recipients
    plain, _ = build_message(account(), 'a@example.com', '', '', 'Sujet', 'Texte')
    assert plain.get_content_type() == 'text/plain'


def make_service(tmp_path):
    from mailclient.tests.test_complete import Vault
    db = Database(tmp_path / 'settings.db')
    return MailService(db, Vault(), TLSPolicy(db)), db


def test_compose_formats_sends_html_and_restores_draft(tmp_path):
    from mailclient.ui.compose_window import ComposeWindow
    service, db = make_service(tmp_path)
    me = account()
    composer = ComposeWindow(service, [me])
    composer.show()
    composer.to.setText('a@example.com')
    composer.body.setPlainText('Important')
    cursor = composer.body.textCursor()
    cursor.select(QTextCursor.Document)
    composer.body.setTextCursor(cursor)
    composer.format_bar.apply('bold')
    assert composer.format_bar.buttons['bold'].isChecked()
    state = composer.state()
    assert '<b>Important</b>' in state['mail_html'] and state['body'] == 'Important'
    message, _ = composer.message(state, [])
    assert message.get_content_type() == 'multipart/alternative'
    composer.save_draft()
    assert process_until(lambda: not composer.saving)
    draft = db.cache_get('draft', composer.id)
    composer.close()
    reopened = ComposeWindow(service, [me], draft=draft)
    assert '<b>Important</b>' in reopened.state()['mail_html']
    reopened.close()
    assert process_until(lambda: not reopened.saving)
    # Sans mise en forme : message texte simple, comme avant.
    plain = ComposeWindow(service, [me])
    plain.body.setPlainText('Simple')
    assert plain.state()['mail_html'] == '' and plain.message(dict(plain.state(), to='a@example.com'), [])[0].get_content_type() == 'text/plain'
    plain.close()
    assert process_until(lambda: not plain.saving)


def test_formatted_signature_in_new_message_and_reply(tmp_path):
    from mailclient.ui.compose_window import ComposeWindow, reply_fields
    from mailclient.core.parser import Mail
    service, db = make_service(tmp_path)
    me = account(signature='Claire Martin\nDirectrice')
    db.save(me)
    signature = editor_with('<p><b>Claire Martin</b><br>Directrice · <a href="https://exemple.fr">exemple.fr</a></p>')
    service.set_signature(me, signature.toHtml())
    composer = ComposeWindow(service, [me])
    fragment = composer.state()['mail_html']
    assert '<b>Claire Martin</b>' in fragment and 'href="https://exemple.fr"' in fragment
    assert composer.body.textCursor().position() == 0  # On écrit au-dessus de la signature.
    composer.close()
    assert process_until(lambda: not composer.saving)
    mail = Mail('Léa <lea@example.com>', 'moi@example.com', 'Projet', 'date', text='Question ?', message_id='<q@x>')
    reply = ComposeWindow(service, [me], me, reply_fields(mail, me, 'reply'))
    text = reply.state()['body']
    assert text.index('Claire Martin') < text.index('a écrit') < text.index('> Question ?')
    assert '<b>Claire Martin</b>' in reply.state()['mail_html']
    reply.close()
    assert process_until(lambda: not reply.saving)
    # Sans signature mise en forme : comportement texte inchangé.
    service.set_signature(me)
    simple = ComposeWindow(service, [me])
    assert simple.body.toPlainText() == '\n\nClaire Martin\nDirectrice' and simple.state()['mail_html'] == ''
    simple.close()
    assert process_until(lambda: not simple.saving)


def test_account_dialog_saves_formatted_signature(tmp_path, monkeypatch):
    from mailclient.ui.account_dialog import AccountDialog
    from mailclient.tests.test_ui import FakeSecrets
    db = Database(tmp_path / 'settings.db')
    me = account()
    db.save(me)
    dialog = AccountDialog(db, FakeSecrets(), TLSPolicy(db), account=me)
    dialog.password.setText('secret-de-test')
    dialog.signature.setHtml('<p><b>Claire</b> — <i>Smail</i></p>')
    dialog.save()
    assert db.accounts()[0].signature == 'Claire — Smail'
    stored = editor_with(db.cache_get('signature', me.id)['qt_html'])
    assert '<b>Claire</b>' in render(stored.document())[0]
    reopened = AccountDialog(db, FakeSecrets(), TLSPolicy(db), account=db.accounts()[0])
    assert has_formatting(reopened.signature.document())
    reopened.signature.setPlainText('Texte seul')
    reopened.password.setText('secret-de-test')
    reopened.save()
    assert db.cache_get('signature', me.id) is None and db.accounts()[0].signature == 'Texte seul'
    db.delete_account(me.id)


def test_account_config_from_newer_version_is_tolerated():
    data = account().to_dict()
    data['champ_futur'] = 'valeur'
    assert Account.from_dict(data).email == 'moi@example.com'
