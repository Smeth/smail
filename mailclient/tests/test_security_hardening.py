"""Correctifs de l’audit de sécurité : HTML dans les infobulles et boîtes de message, marque Internet, canal local."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

HOSTILE = "Bob <img src='file://203.0.113.9/partage/x.png'>"


def test_untrusted_text_is_never_rich_text():
    from PySide6.QtGui import QTextDocument
    from mailclient.ui.components import safe_rich
    shown = safe_rich(HOSTILE + '\nObjet <b>gras</b>')
    assert shown.startswith('<qt>') and '<img' not in shown and '<b>' not in shown
    document = QTextDocument()
    document.setHtml(shown)
    assert document.toPlainText() == HOSTILE + '\nObjet <b>gras</b>'


def test_message_list_tooltip_escapes_the_sender(tmp_path, monkeypatch):
    from mailclient.tests.test_ui import APP, process_until  # noqa: F401
    from mailclient.core.accounts import Account, Server
    from mailclient.core.service import MailService
    from mailclient.core.tls_policy import TLSPolicy
    from mailclient.storage.database import Database
    from mailclient.ui.main_window import MainWindow
    db = Database(tmp_path / 'settings.db')
    account = Account('T', 't@example.com', Server('imap.example.com', 993), Server('smtp.example.com', 465))
    db.save(account)
    db.cache_put('folders', account.id, [['INBOX', 'Boîte de réception']], account.id)

    class Client:
        uidvalidity = '7'

        def folders(self):
            return [('INBOX', "Boîte <img src='file://203.0.113.9/d'>")]

        def messages(self, folder, page, query=''):
            return [dict(uid='1', uidvalidity='7', sender=HOSTILE, subject='<img src=x>', date='', unread=True,
                         starred=False, attachment=False)], 1
    monkeypatch.setattr(MailService, 'client', lambda *args: Client())
    window = MainWindow(db, None, TLSPolicy(db), auto_load=False)
    window.reload_accounts()
    assert process_until(lambda: not window.busy and window.table.count() == 1)
    for tip in (window.table.item(0).toolTip(), *(window.folders.item(i).toolTip() for i in range(window.folders.count()))):
        assert tip.startswith('<qt>') and '<img' not in tip
    from mailclient.core.parser import Mail
    window.reader.display(Mail(HOSTILE, '<img src=x>', '<img src=y>', '<img src=z>', text='corps'))
    for widget in (window.reader.subject, window.reader.sender_name, window.reader.recipient_summary, window.reader.date_label):
        assert widget.toolTip().startswith('<qt>') and '<img' not in widget.toolTip()
    window.reader.shutdown()
    window.close()
    from shiboken6 import delete
    delete(window)
    APP.processEvents()


@pytest.mark.skipif(os.name != 'nt', reason='Flux NTFS propres à Windows')
def test_saved_attachments_carry_the_mark_of_the_web(tmp_path):
    from mailclient.core.html_security import mark_from_internet
    target = tmp_path / 'facture.docx'
    target.write_bytes(b'PK')
    mark_from_internet(target)
    with open(f'{target}:Zone.Identifier', encoding='ascii') as stream:
        assert 'ZoneId=3' in stream.read()


@pytest.mark.parametrize('name', ['photo.iso', 'notes.one', 'macro.xll', 'ancien.doc', 'disque.vhdx', 'appli.appinstaller',
                                  'raccourci.settingcontent-ms', 'FACTURE.PDF.EXE ', 'compte.xlam'])
def test_dangerous_attachment_types(name):
    from mailclient.core.html_security import dangerous_filename
    assert dangerous_filename(name)


def test_single_instance_name_depends_on_a_private_secret(tmp_path):
    from mailclient.ui.single_instance import SingleInstance, instance_secret
    first = SingleInstance(str(tmp_path)).name
    secret = (tmp_path / 'instance.id').read_text(encoding='ascii')
    assert len(secret) == 32 and instance_secret(str(tmp_path)) == secret
    assert SingleInstance(str(tmp_path)).name == first  # Stable pour cet utilisateur…
    (tmp_path / 'instance.id').write_text('0' * 32, encoding='ascii')
    assert SingleInstance(str(tmp_path)).name != first  # … imprévisible sans le secret.
