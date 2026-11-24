from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from mailclient.core.accounts import Account, Server
from mailclient.core.imap_client import IMAPClient
from mailclient.core.smtp_client import test_connection as smtp_test

def account(mode='STARTTLS'):
    return Account('Test', 'a@example.com', Server('imap.example.com', 143, mode), Server('smtp.example.com', 587, mode))

@pytest.mark.parametrize('protocol', ['imap', 'smtp'])
def test_no_credentials_sent_when_starttls_missing(monkeypatch, protocol):
    client = MagicMock()
    client.capabilities = (b'IMAP4rev1',)
    client.has_extn.return_value = False
    tls = SimpleNamespace(connect=lambda account, endpoint, factory: factory(None))
    if protocol == 'imap':
        monkeypatch.setattr('imaplib.IMAP4', lambda *a, **k: client)
        operation = lambda: IMAPClient(account(), 'secret', tls).open()
    else:
        monkeypatch.setattr('smtplib.SMTP', lambda *a, **k: client)
        operation = lambda: smtp_test(account(), 'secret', tls)
    with pytest.raises(RuntimeError, match='STARTTLS'):
        operation()
    client.login.assert_not_called()

def test_pagination_is_readonly_and_does_not_download_bodies(monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.select.return_value = ('OK', [b'120'])
    fetched = []
    def uid(command, *args):
        if command == 'search':
            return 'OK', [b' '.join(str(i).encode() for i in range(1, 121))]
        fetched.append(args)
        response = []
        for n, value in enumerate(args[0].split(','), 1):
            # FLAGS placé après le littéral sur un message sur deux, comme certains serveurs.
            before, after = (b'FLAGS () ', b'') if n % 2 else (b'', b' FLAGS (\\Seen)')
            response += [(b'%d (UID %s %sBODYSTRUCTURE ("APPLICATION" "PDF" ("NAME" "a.pdf"))' % (n, value.encode(), before),
                          b'From: a@example.com\r\nSubject: Hello ' + value.encode() + b'\r\n\r\n'), after + b')']
        response.append(b'5 (FLAGS (\\Seen))')  # Notification non sollicitée sans UID : ignorée.
        return 'OK', response
    client.uid.side_effect = uid
    monkeypatch.setattr(IMAPClient, 'open', lambda self: client)
    rows, total = IMAPClient(account(), 'secret', None).messages('INBOX', 1)
    assert total == 120 and len(rows) == 50
    assert len(fetched) == 1  # Une seule commande pour toute la page.
    assert fetched[0][0] == ','.join(str(i) for i in range(70, 20, -1))
    assert 'BODY.PEEK[HEADER.FIELDS' in fetched[0][1] and 'BODY.PEEK[]' not in fetched[0][1]
    client.select.assert_called_once_with('"INBOX"', readonly=True)
    assert [row['uid'] for row in rows] == [str(i) for i in range(70, 20, -1)]
    assert rows[0]['subject'] == 'Hello 70' and rows[0]['unread'] and rows[0]['attachment']
    assert not rows[1]['unread']

def test_folder_special_use_and_spaces(monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.list.return_value = ('OK', [b'(\\HasNoChildren) "/" "INBOX"', b'(\\Sent) "/" "Sent Items"', b'(\\Noselect) "/" "Hidden"'])
    monkeypatch.setattr(IMAPClient, 'open', lambda self: client)
    assert IMAPClient(account(), 'secret', None).folders() == [('INBOX', 'Boîte de réception'), ('Sent Items', 'Envoyés')]


def test_send_waits_for_slow_server_and_reports_uncertain_delivery(monkeypatch):
    """Analyse antivirus après DATA : réponse lente acceptée ; coupure signalée comme envoi incertain."""
    import smtplib
    from email.message import EmailMessage
    from mailclient.core import smtp_client
    client = MagicMock()
    monkeypatch.setattr(smtp_client, 'open_connection', lambda *args: client)
    client.send_message.return_value = {}
    assert smtp_client.send_message(account(), 'pw', None, EmailMessage(), ['a@example.com']) == {}
    client.sock.settimeout.assert_called_once_with(smtp_client.SEND_TIMEOUT)
    assert smtp_client.SEND_TIMEOUT >= 300
    client.send_message.side_effect = smtplib.SMTPServerDisconnected('Connection unexpectedly closed: timed out')
    with pytest.raises(smtp_client.DeliveryUncertain, match='peut-être été envoyé'):
        smtp_client.send_message(account(), 'pw', None, EmailMessage(), ['a@example.com'])
    assert client.close.call_count == 2
