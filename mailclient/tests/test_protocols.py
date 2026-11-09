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
        return 'OK', [(b'1 (UID 70 FLAGS () BODYSTRUCTURE ("APPLICATION" "PDF" ("NAME" "a.pdf"))', b'From: a@example.com\r\nSubject: Hello\r\n\r\n'), b')']
    client.uid.side_effect = uid
    monkeypatch.setattr(IMAPClient, 'open', lambda self: client)
    rows, total = IMAPClient(account(), 'secret', None).messages('INBOX', 1)
    assert total == 120 and len(rows) == 50
    assert fetched[0][0] == b'70' and fetched[-1][0] == b'21'
    assert all('BODY.PEEK[HEADER.FIELDS' in args[1] for args in fetched)
    client.select.assert_called_once_with('"INBOX"', readonly=True)
    assert rows[0]['unread'] and rows[0]['attachment']

def test_folder_special_use_and_spaces(monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.list.return_value = ('OK', [b'(\\HasNoChildren) "/" "INBOX"', b'(\\Sent) "/" "Sent Items"', b'(\\Noselect) "/" "Hidden"'])
    monkeypatch.setattr(IMAPClient, 'open', lambda self: client)
    assert IMAPClient(account(), 'secret', None).folders() == [('INBOX', 'Boîte de réception'), ('Sent Items', 'Envoyés')]
