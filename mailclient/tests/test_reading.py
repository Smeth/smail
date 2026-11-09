from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from mailclient.core.parser import parse_message, safe_filename, Mail, Attachment
from mailclient.core.html_security import safe_document, dangerous_filename
from mailclient.core.imap_client import IMAPClient

@pytest.mark.parametrize('charset,encoding', [('utf-8', 'base64'), ('iso-8859-1', 'quoted-printable')])
def test_body_encodings(charset, encoding):
    message = EmailMessage()
    message['Subject'] = 'Réunion'
    message.set_content('Bonjour André, café !', charset=charset, cte=encoding)
    result = parse_message(message.as_bytes())
    assert result.subject == 'Réunion'
    assert 'André, café' in result.text

def test_multipart_attachment_and_cid():
    message = EmailMessage()
    message.set_content('Texte du message')
    message.add_alternative('<p>Version HTML<img src="cid:photo"></p>', subtype='html')
    message.get_payload()[1].add_related(b'fake-png', maintype='image', subtype='png', cid='<photo>')
    message.add_attachment(b'Contenu joint', maintype='text', subtype='plain', filename='notes.txt')
    result = parse_message(message.as_bytes())
    assert 'Texte du message' in result.text
    assert 'Contenu joint' not in result.text
    assert len(result.attachments) == 2
    document = safe_document(result)
    assert 'src="data:image/png;base64,' in document
    assert 'cid:photo' not in document

@pytest.mark.parametrize('name', ['../../CON.exe', 'C:\\secret\\..\\evil.exe', 'a\u202etxt.exe', 'NUL.txt'])
def test_safe_attachment_names(name):
    result = safe_filename(name)
    assert '/' not in result and '\\' not in result and '\u202e' not in result
    assert result.split('.')[0].upper() not in {'CON', 'NUL'}

def test_sanitizer_and_remote_images():
    mail = Mail('a', 'b', 's', 'd', html='''<script>alert(1)</script><iframe src="https://bad"></iframe>
    <form action="https://bad"><input></form><img src="https://tracker/pixel" onerror="bad()">
    <img src="file:///C:/secret"><img src="data:image/svg+xml,bad"><a href="javascript:bad()">Lien</a>
    <div style="background:url(https://tracker/css)">Texte</div><svg onload="bad()"></svg>''')
    document = safe_document(mail)
    for forbidden in ('<script', '<iframe', '<form', '<input', 'onerror=', 'onload=', 'href=', 'file:///', 'image/svg', 'tracker/css', 'tracker/pixel'):
        assert forbidden not in document
    assert 'src="https://tracker/pixel"' in safe_document(mail, True)
    assert 'src="https://tracker/pixel"' not in safe_document(mail)

def test_plain_text_escaped_and_dangerous_suffixes():
    assert '&lt;script&gt;' in safe_document(Mail('', '', '', '', text='<script>'))
    assert dangerous_filename('Facture.PDF.EXE')
    assert dangerous_filename('test.js')
    assert not dangerous_filename('rapport.pdf')

def test_content_id_on_html_body_is_not_an_attachment():
    raw = b'Content-Type: text/html; charset=utf-8\r\nContent-ID: <root>\r\n\r\n<p>Bonjour</p>'
    message = parse_message(raw)
    assert message.html == '<p>Bonjour</p>'
    assert not message.attachments

def test_read_uses_peek_and_readonly(monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.select.return_value = ('OK', [])
    client.uid.return_value = ('OK', [(b'1 BODY[]', b'Subject: Test\r\n\r\nBonjour')])
    monkeypatch.setattr(IMAPClient, 'open', lambda self: client)
    result = IMAPClient(None, '', None).message('INBOX', '12')
    assert result.text == 'Bonjour'
    client.select.assert_called_once_with('"INBOX"', readonly=True)
    client.uid.assert_called_once_with('fetch', '12', '(BODY.PEEK[])')
    with pytest.raises(ValueError):
        IMAPClient(None, '', None).message('INBOX', '12\r\nLOGOUT')
